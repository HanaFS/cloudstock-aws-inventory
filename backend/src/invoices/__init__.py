import os
import re
import uuid
from datetime import datetime, timezone
from urllib.parse import urlsplit

import boto3
from botocore.exceptions import ClientError

from ..common.dynamodb import dynamodb
from ..common.http import ApiError, parse_body, require_any_group, success, with_error_handling

MAX_INVOICE_BYTES = 10 * 1024 * 1024
RESERVATION_TTL_SECONDS = 10 * 60
UPLOAD_URL_TTL_SECONDS = 5 * 60
DOWNLOAD_URL_TTL_SECONDS = 5 * 60
_UPLOAD_ID = re.compile(r"^[0-9a-f]{32}$")
_INVOICE_KEY = re.compile(r"^invoices/[0-9a-f]{32}\.(pdf|jpg|png|webp)$")
_FORMATS = {
    "application/pdf": {"extensions": {".pdf"}, "key_extension": ".pdf", "signature": b"%PDF-"},
    "image/jpeg": {"extensions": {".jpg", ".jpeg"}, "key_extension": ".jpg", "signature": b"\xff\xd8\xff"},
    "image/png": {"extensions": {".png"}, "key_extension": ".png", "signature": b"\x89PNG\r\n\x1a\n"},
    "image/webp": {"extensions": {".webp"}, "key_extension": ".webp", "signature": b"RIFF"},
}


def _table():
    return dynamodb.Table(os.environ["TRANSACTIONS_TABLE"])


def _now_epoch():
    return int(datetime.now(timezone.utc).timestamp())


def _subject(event):
    subject = event.get("requestContext", {}).get("authorizer", {}).get("claims", {}).get("sub")
    if not isinstance(subject, str) or not subject:
        raise ApiError(401, "UNAUTHORIZED", "A Cognito subject is required.")
    return subject


def _s3_client():
    endpoint = os.environ.get("S3_ENDPOINT_URL")
    local = os.environ.get("AWS_SAM_LOCAL") == "true" or bool(os.environ.get("DYNAMODB_ENDPOINT"))
    if local:
        parsed = urlsplit(endpoint or "")
        if parsed.scheme != "http" or parsed.hostname not in ("localhost", "127.0.0.1"):
            raise ApiError(503, "LOCAL_S3_NOT_CONFIGURED", "Configure an HTTP loopback S3-compatible endpoint for local invoice operations.")
    options = {"region_name": os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or "us-east-1"}
    if endpoint:
        options["endpoint_url"] = endpoint
    return boto3.client("s3", **options)


def _validate_upload(body):
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
        raise ApiError(400, "UNSUPPORTED_INVOICE_TYPE", "Use a PDF, JPEG, PNG, or WebP file with a matching extension.")
    if isinstance(size_bytes, bool) or not isinstance(size_bytes, int) or not 1 <= size_bytes <= MAX_INVOICE_BYTES:
        raise ApiError(400, "INVALID_INVOICE_SIZE", f"sizeBytes must be between 1 and {MAX_INVOICE_BYTES}.")
    return content_type, size_bytes, file_format


def _upload_id(value):
    if not isinstance(value, str) or not _UPLOAD_ID.fullmatch(value):
        raise ApiError(404, "UPLOAD_RESERVATION_NOT_FOUND", "Invoice upload reservation not found.")
    return value


def load_invoice_reservation(identifier, subject, allow_consumed_by=None):
    identifier = _upload_id(identifier)
    item = _table().get_item(Key={"transactionId": f"UPLOAD#{identifier}"}, ConsistentRead=True).get("Item")
    if not item or item.get("recordType") != "UPLOAD_RESERVATION" or item.get("reservationType") != "INVOICE":
        raise ApiError(404, "UPLOAD_RESERVATION_NOT_FOUND", "Invoice upload reservation not found.")
    if item.get("ownerSub") != subject:
        raise ApiError(403, "UPLOAD_RESERVATION_FORBIDDEN", "This invoice upload belongs to another user.")
    if item.get("state") == "CONSUMED" and allow_consumed_by and item.get("attachedTransactionId") == allow_consumed_by:
        return item
    now = _now_epoch()
    if item.get("state") != "PENDING" or not isinstance(item.get("expiresAt"), int) or item["expiresAt"] <= now:
        raise ApiError(409, "UPLOAD_RESERVATION_EXPIRED", "Invoice upload reservation is expired or already consumed.")
    if not isinstance(item.get("s3Key"), str) or not _INVOICE_KEY.fullmatch(item["s3Key"]):
        raise ApiError(409, "INVALID_INVOICE_REFERENCE", "Invoice reservation has an invalid object key.")
    if item.get("contentType") not in _FORMATS:
        raise ApiError(409, "INVALID_INVOICE_REFERENCE", "Invoice reservation has an invalid content type.")
    size_bytes = item.get("sizeBytes")
    if isinstance(size_bytes, bool) or not isinstance(size_bytes, int) or not 1 <= size_bytes <= MAX_INVOICE_BYTES:
        raise ApiError(409, "INVALID_INVOICE_REFERENCE", "Invoice reservation has an invalid size.")
    return item


def verify_invoice_object(reservation):
    s3 = _s3_client()
    bucket = os.environ["INVOICES_BUCKET"]
    key = reservation["s3Key"]
    try:
        metadata = s3.head_object(Bucket=bucket, Key=key)
    except ClientError as error:
        if error.response.get("Error", {}).get("Code") in ("404", "NoSuchKey", "NotFound"):
            raise ApiError(409, "UPLOAD_OBJECT_MISSING", "Uploaded invoice object was not found.") from error
        raise
    if metadata.get("ContentLength") != reservation["sizeBytes"]:
        raise ApiError(400, "UPLOAD_SIZE_MISMATCH", "Uploaded invoice size does not match its reservation.")
    if metadata.get("ContentType") != reservation["contentType"]:
        raise ApiError(400, "UPLOAD_TYPE_MISMATCH", "Uploaded invoice content type does not match its reservation.")
    try:
        result = s3.get_object(Bucket=bucket, Key=key, Range="bytes=0-11")
    except ClientError as error:
        if error.response.get("Error", {}).get("Code") in ("404", "NoSuchKey", "NotFound"):
            raise ApiError(409, "UPLOAD_OBJECT_MISSING", "Uploaded invoice object was not found.") from error
        raise
    body = result["Body"]
    try:
        header = body.read(12)
    finally:
        close = getattr(body, "close", None)
        if close:
            close()
    signature = _FORMATS[reservation["contentType"]]["signature"]
    if reservation["contentType"] == "image/webp":
        valid = len(header) >= 12 and header[:4] == b"RIFF" and header[8:12] == b"WEBP"
    else:
        valid = header.startswith(signature)
    if not valid:
        raise ApiError(400, "INVALID_INVOICE_CONTENT", "Uploaded bytes do not match the declared invoice type.")


def _create_upload(event):
    subject = _subject(event)
    content_type, size_bytes, file_format = _validate_upload(parse_body(event))
    now = _now_epoch()
    identifier = uuid.uuid4().hex
    key = f"invoices/{uuid.uuid4().hex}{file_format['key_extension']}"
    reservation = {
        "transactionId": f"UPLOAD#{identifier}",
        "recordType": "UPLOAD_RESERVATION",
        "reservationType": "INVOICE",
        "ownerSub": subject,
        "s3Key": key,
        "contentType": content_type,
        "sizeBytes": size_bytes,
        "expiresAt": now + RESERVATION_TTL_SECONDS,
        "state": "PENDING",
    }
    _table().put_item(Item=reservation, ConditionExpression="attribute_not_exists(transactionId)")
    upload_url = _s3_client().generate_presigned_url(
        "put_object",
        Params={
            "Bucket": os.environ["INVOICES_BUCKET"],
            "Key": key,
            "ContentType": content_type,
            "ContentLength": size_bytes,
            "IfNoneMatch": "*",
        },
        ExpiresIn=300,
        HttpMethod="PUT",
    )
    return success({
        "reservationId": identifier,
        "uploadUrl": upload_url,
        "expiresAt": reservation["expiresAt"],
        "requiredHeaders": {"Content-Type": content_type, "If-None-Match": "*"},
        "sizeBytes": size_bytes,
    }, 201)


def _invoice_reference(transaction):
    legacy = transaction.get("invoiceKey")
    canonical = transaction.get("invoiceUrl")
    if legacy not in (None, "") and canonical not in (None, "") and legacy != canonical:
        raise ApiError(409, "INVALID_INVOICE_REFERENCE", "Transaction invoice fields conflict.")
    key = legacy or canonical
    if not isinstance(key, str) or not _INVOICE_KEY.fullmatch(key):
        raise ApiError(404, "INVOICE_NOT_FOUND", "Transaction has no supported private invoice reference.")
    return key


def _get_invoice(event, transaction_id):
    transaction = _table().get_item(Key={"transactionId": transaction_id}, ConsistentRead=True).get("Item")
    if not transaction or transaction.get("recordType") == "UPLOAD_RESERVATION":
        raise ApiError(404, "TRANSACTION_NOT_FOUND", "Transaction not found.")
    key = _invoice_reference(transaction)
    reservation_id = transaction.get("invoiceReservationId")
    if reservation_id:
        reservation = _table().get_item(
            Key={"transactionId": f"UPLOAD#{_upload_id(reservation_id)}"},
            ConsistentRead=True,
        ).get("Item")
        if (
            not reservation
            or reservation.get("recordType") != "UPLOAD_RESERVATION"
            or reservation.get("reservationType") != "INVOICE"
            or reservation.get("state") != "CONSUMED"
            or reservation.get("attachedTransactionId") != transaction_id
            or reservation.get("s3Key") != key
        ):
            raise ApiError(409, "INVALID_INVOICE_REFERENCE", "Invoice reservation does not match the transaction.")
    s3 = _s3_client()
    try:
        s3.head_object(Bucket=os.environ["INVOICES_BUCKET"], Key=key)
    except ClientError as error:
        if error.response.get("Error", {}).get("Code") in ("404", "NoSuchKey", "NotFound"):
            raise ApiError(404, "INVOICE_NOT_FOUND", "Invoice object was not found.") from error
        raise
    url = s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": os.environ["INVOICES_BUCKET"], "Key": key},
        ExpiresIn=DOWNLOAD_URL_TTL_SECONDS,
        HttpMethod="GET",
    )
    return success({"transactionId": transaction_id, "downloadUrl": url, "expiresIn": DOWNLOAD_URL_TTL_SECONDS})


@with_error_handling
def handler(event, context=None):
    require_any_group(event, ["Admin", "Staff"])
    method = event.get("httpMethod")
    path_parameters = event.get("pathParameters") or {}
    if method == "POST" and (
        event.get("resource") == "/transactions/invoice-uploads"
        or event.get("path") == "/transactions/invoice-uploads"
    ):
        return _create_upload(event)
    if method == "GET" and path_parameters.get("transactionId"):
        return _get_invoice(event, path_parameters["transactionId"])
    raise ApiError(404, "ROUTE_NOT_FOUND", "Endpoint not found.")
