import os
import re
import uuid
from datetime import datetime, timezone
from urllib.parse import urlsplit

import boto3
from boto3.dynamodb.types import TypeSerializer
from botocore.exceptions import ClientError

from ..common.dynamodb import dynamodb
from ..common.http import ApiError, parse_body, require_any_group, success, with_error_handling

MAX_IMAGE_BYTES = 5 * 1024 * 1024
RESERVATION_TTL_SECONDS = 10 * 60
UPLOAD_URL_TTL_SECONDS = 5 * 60
_RESERVATION_ID = re.compile(r"^[0-9a-f]{32}$")
_FORMATS = {
    "image/jpeg": {"extensions": {".jpg", ".jpeg"}, "key_extension": ".jpg", "signature": "jpeg"},
    "image/png": {"extensions": {".png"}, "key_extension": ".png", "signature": "png"},
    "image/webp": {"extensions": {".webp"}, "key_extension": ".webp", "signature": "webp"},
}
_serializer = TypeSerializer()


def _table(env_name):
    return dynamodb.Table(os.environ[env_name])


def _serialize(item):
    return {name: _serializer.serialize(value) for name, value in item.items()}


def _now_epoch():
    return int(datetime.now(timezone.utc).timestamp())


def _claims(event):
    return event.get("requestContext", {}).get("authorizer", {}).get("claims", {})


def _subject(event):
    subject = _claims(event).get("sub")
    if not isinstance(subject, str) or not subject:
        raise ApiError(401, "UNAUTHORIZED", "A Cognito subject is required.")
    return subject


def _local_execution():
    return os.environ.get("AWS_SAM_LOCAL") == "true" or bool(os.environ.get("DYNAMODB_ENDPOINT"))


def _s3_client():
    endpoint = os.environ.get("S3_ENDPOINT_URL")
    if _local_execution():
        if not endpoint:
            raise ApiError(503, "LOCAL_S3_NOT_CONFIGURED", "Configure a local S3-compatible endpoint to use image uploads locally.")
        parsed = urlsplit(endpoint)
        if parsed.scheme != "http" or parsed.hostname not in ("localhost", "127.0.0.1"):
            raise ApiError(503, "LOCAL_S3_NOT_CONFIGURED", "Local image uploads may use only an HTTP loopback S3 endpoint.")
    options = {"region_name": os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or "us-east-1"}
    if endpoint:
        options["endpoint_url"] = endpoint
    return boto3.client("s3", **options)


def _validate_upload_request(body):
    filename = body.get("filename")
    content_type = body.get("contentType")
    size_bytes = body.get("sizeBytes")
    if (
        not isinstance(filename, str)
        or not filename
        or len(filename) > 255
        or filename in (".", "..")
        or "/" in filename
        or "\\" in filename
        or any(ord(char) < 32 for char in filename)
    ):
        raise ApiError(400, "INVALID_FILENAME", "filename must be a simple file name.")
    file_format = _FORMATS.get(content_type) if isinstance(content_type, str) else None
    if not file_format or os.path.splitext(filename)[1].lower() not in file_format["extensions"]:
        raise ApiError(400, "UNSUPPORTED_IMAGE_TYPE", "Use a JPEG, PNG, or WebP image with a matching file extension.")
    if isinstance(size_bytes, bool) or not isinstance(size_bytes, int) or not 1 <= size_bytes <= MAX_IMAGE_BYTES:
        raise ApiError(400, "INVALID_IMAGE_SIZE", f"sizeBytes must be between 1 and {MAX_IMAGE_BYTES}.")
    return content_type, size_bytes, file_format


def _reservation_id(value):
    if not isinstance(value, str) or not _RESERVATION_ID.fullmatch(value):
        raise ApiError(404, "UPLOAD_RESERVATION_NOT_FOUND", "Image upload reservation not found.")
    return value


def _missing_s3_object(error):
    code = error.response.get("Error", {}).get("Code")
    return code in ("404", "NoSuchKey", "NotFound")


def _verify_image_object(s3, bucket, reservation):
    key = reservation["s3Key"]
    try:
        metadata = s3.head_object(Bucket=bucket, Key=key)
    except ClientError as error:
        if _missing_s3_object(error):
            raise ApiError(409, "UPLOAD_OBJECT_MISSING", "Uploaded image object was not found.") from error
        raise
    if metadata.get("ContentLength") != reservation["sizeBytes"]:
        raise ApiError(400, "UPLOAD_SIZE_MISMATCH", "Uploaded image size does not match its reservation.")
    if metadata.get("ContentType") != reservation["contentType"]:
        raise ApiError(400, "UPLOAD_TYPE_MISMATCH", "Uploaded image content type does not match its reservation.")

    # Content-Type is client supplied metadata. Check a small byte range as well
    # so a renamed non-image file cannot be attached as a product image.
    try:
        result = s3.get_object(Bucket=bucket, Key=key, Range="bytes=0-11")
    except ClientError as error:
        if _missing_s3_object(error):
            raise ApiError(409, "UPLOAD_OBJECT_MISSING", "Uploaded image object was not found.") from error
        raise
    body = result["Body"]
    try:
        header = body.read(12)
    finally:
        close = getattr(body, "close", None)
        if close:
            close()
    kind = _FORMATS[reservation["contentType"]]["signature"]
    valid = (
        header.startswith(b"\xff\xd8\xff") if kind == "jpeg" else
        header.startswith(b"\x89PNG\r\n\x1a\n") if kind == "png" else
        len(header) >= 12 and header[:4] == b"RIFF" and header[8:12] == b"WEBP"
    )
    if not valid:
        raise ApiError(400, "INVALID_IMAGE_CONTENT", "Uploaded bytes do not match the declared image type.")


def _public_image_url(key):
    base_url = os.environ.get("PRODUCT_IMAGES_PUBLIC_BASE_URL", "").rstrip("/")
    parsed = urlsplit(base_url)
    if parsed.scheme != "https" or not parsed.netloc or parsed.query or parsed.fragment:
        raise ApiError(503, "IMAGE_URL_NOT_CONFIGURED", "A public HTTPS base URL for product images is required.")
    if not key.startswith("products/"):
        raise ApiError(500, "INVALID_IMAGE_KEY", "Generated image key is outside the products prefix.")
    return f"{base_url}/{key}"


def _create_upload(event, product_id):
    subject = _subject(event)
    body = parse_body(event)
    content_type, size_bytes, file_format = _validate_upload_request(body)
    products = _table("PRODUCTS_TABLE")
    if not products.get_item(Key={"productId": product_id}).get("Item"):
        raise ApiError(404, "PRODUCT_NOT_FOUND", "Product not found.")

    now = _now_epoch()
    identifier = uuid.uuid4().hex
    key = f"products/{uuid.uuid4().hex}{file_format['key_extension']}"
    bucket = os.environ["PRODUCT_IMAGES_BUCKET"]
    reservation = {
        "transactionId": f"UPLOAD#{identifier}",
        "recordType": "UPLOAD_RESERVATION",
        "reservationType": "PRODUCT_IMAGE",
        "ownerSub": subject,
        "productId": product_id,
        "s3Key": key,
        "contentType": content_type,
        "sizeBytes": size_bytes,
        "expiresAt": now + RESERVATION_TTL_SECONDS,
        "state": "PENDING",
    }
    try:
        _table("TRANSACTIONS_TABLE").put_item(
            Item=reservation,
            ConditionExpression="attribute_not_exists(transactionId)",
        )
    except Exception as error:
        if getattr(error, "response", {}).get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            raise ApiError(409, "UPLOAD_RESERVATION_CONFLICT", "Could not reserve this image upload.") from error
        raise

    upload_url = _s3_client().generate_presigned_url(
        "put_object",
        Params={
            "Bucket": bucket,
            "Key": key,
            "ContentType": content_type,
            "ContentLength": size_bytes,
            "IfNoneMatch": "*",
        },
        ExpiresIn=UPLOAD_URL_TTL_SECONDS,
        HttpMethod="PUT",
    )
    return success({
        "reservationId": identifier,
        "uploadUrl": upload_url,
        "expiresAt": reservation["expiresAt"],
        "requiredHeaders": {"Content-Type": content_type, "If-None-Match": "*"},
        "sizeBytes": size_bytes,
    }, 201)


def _attach_upload(event, product_id, identifier):
    subject = _subject(event)
    identifier = _reservation_id(identifier)
    transactions = _table("TRANSACTIONS_TABLE")
    reservation = transactions.get_item(
        Key={"transactionId": f"UPLOAD#{identifier}"}
    ).get("Item")
    if not reservation or reservation.get("recordType") != "UPLOAD_RESERVATION" or reservation.get("reservationType") != "PRODUCT_IMAGE":
        raise ApiError(404, "UPLOAD_RESERVATION_NOT_FOUND", "Image upload reservation not found.")
    if reservation.get("ownerSub") != subject:
        raise ApiError(403, "UPLOAD_RESERVATION_FORBIDDEN", "This image upload belongs to another user.")
    if reservation.get("productId") != product_id:
        raise ApiError(409, "UPLOAD_PRODUCT_MISMATCH", "Image upload reservation belongs to another product.")
    now = _now_epoch()
    if reservation.get("state") != "PENDING" or not isinstance(reservation.get("expiresAt"), int) or reservation["expiresAt"] <= now:
        raise ApiError(409, "UPLOAD_RESERVATION_EXPIRED", "Image upload reservation is expired or already consumed.")

    bucket = os.environ["PRODUCT_IMAGES_BUCKET"]
    s3 = _s3_client()
    _verify_image_object(s3, bucket, reservation)
    image_url = _public_image_url(reservation["s3Key"])
    try:
        dynamodb.meta.client.transact_write_items(TransactItems=[
            {
                "Update": {
                    "TableName": os.environ["TRANSACTIONS_TABLE"],
                    "Key": _serialize({"transactionId": reservation["transactionId"]}),
                    "UpdateExpression": "SET #state = :consumed, #consumedAt = :now, #attachedProductId = :productId",
                    "ConditionExpression": (
                        "#state = :pending AND #ownerSub = :subject AND #productId = :productId "
                        "AND #reservationType = :reservationType AND #expiresAt > :now "
                        "AND #s3Key = :s3Key AND #contentType = :contentType AND #sizeBytes = :sizeBytes"
                    ),
                    "ExpressionAttributeNames": {
                        "#state": "state",
                        "#consumedAt": "consumedAt",
                        "#attachedProductId": "attachedProductId",
                        "#ownerSub": "ownerSub",
                        "#productId": "productId",
                        "#reservationType": "reservationType",
                        "#expiresAt": "expiresAt",
                        "#s3Key": "s3Key",
                        "#contentType": "contentType",
                        "#sizeBytes": "sizeBytes",
                    },
                    "ExpressionAttributeValues": _serialize({
                        ":consumed": "CONSUMED",
                        ":now": now,
                        ":productId": product_id,
                        ":pending": "PENDING",
                        ":subject": subject,
                        ":reservationType": "PRODUCT_IMAGE",
                        ":s3Key": reservation["s3Key"],
                        ":contentType": reservation["contentType"],
                        ":sizeBytes": reservation["sizeBytes"],
                    }),
                }
            },
            {
                "Update": {
                    "TableName": os.environ["PRODUCTS_TABLE"],
                    "Key": _serialize({"productId": product_id}),
                    "UpdateExpression": "SET #imageUrl = :imageUrl, #imageKey = :imageKey",
                    "ConditionExpression": "attribute_exists(#productId)",
                    "ExpressionAttributeNames": {
                        "#imageUrl": "imageUrl",
                        "#imageKey": "imageKey",
                        "#productId": "productId",
                    },
                    "ExpressionAttributeValues": _serialize({
                        ":imageUrl": image_url,
                        ":imageKey": reservation["s3Key"],
                    }),
                }
            },
        ])
    except ClientError as error:
        if error.response.get("Error", {}).get("Code") == "TransactionCanceledException":
            raise ApiError(409, "UPLOAD_RESERVATION_CONFLICT", "Image upload was already consumed, expired, or its product changed.") from error
        raise
    return success({"productId": product_id, "imageUrl": image_url, "imageKey": reservation["s3Key"]})


@with_error_handling
def handler(event, context=None):
    require_any_group(event, ["Admin", "Staff"])
    product_id = (event.get("pathParameters") or {}).get("productId")
    identifier = (event.get("pathParameters") or {}).get("reservationId")
    if not isinstance(product_id, str) or not product_id:
        raise ApiError(400, "INVALID_PRODUCT_ID", "productId is required.")
    if event.get("httpMethod") != "POST":
        raise ApiError(404, "ROUTE_NOT_FOUND", "Endpoint not found.")
    if identifier is None:
        return _create_upload(event, product_id)
    return _attach_upload(event, product_id, identifier)
