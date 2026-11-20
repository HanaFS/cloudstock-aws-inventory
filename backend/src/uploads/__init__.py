import os
import uuid
from pathlib import PurePath
from urllib.parse import quote

import boto3
from boto3.dynamodb.conditions import Key

from ..common.dynamodb import dynamodb, table_name
from ..common.http import ApiError, parse_body, require_any_group, success, with_error_handling

UPLOAD_TYPES = {
    "product-image": {
        "prefix": "products/",
        "content_types": {"image/jpeg", "image/png", "image/webp"},
        "max_bytes": 5 * 1024 * 1024,
        "extensions": {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"},
    },
    "invoice": {
        "prefix": "invoices/",
        "content_types": {"application/pdf", "image/jpeg", "image/png"},
        "max_bytes": 15 * 1024 * 1024,
        "extensions": {
            "application/pdf": ".pdf",
            "image/jpeg": ".jpg",
            "image/png": ".png",
        },
    },
}


def _client():
    if os.environ.get("LOCAL_API") == "true" and not os.environ.get("S3_ENDPOINT"):
        raise ApiError(503, "LOCAL_SERVICE_UNAVAILABLE", "S3 không được cấu hình cho chế độ local.")
    options = {}
    if os.environ.get("S3_ENDPOINT"):
        options["endpoint_url"] = os.environ["S3_ENDPOINT"]
    return boto3.client("s3", **options)


def _bucket():
    bucket = os.environ.get("BUCKET_NAME")
    if not bucket:
        raise RuntimeError("BUCKET_NAME environment variable is required.")
    return bucket


def _key_for(upload_type, file_name, content_type):
    settings = UPLOAD_TYPES[upload_type]
    if not isinstance(file_name, str) or not file_name.strip() or len(file_name) > 255:
        raise ApiError(400, "INVALID_FILE_NAME", "fileName là bắt buộc và tối đa 255 ký tự.")
    extension = PurePath(file_name).suffix.lower()
    allowed_extensions = set(settings["extensions"].values())
    if content_type == "image/jpeg":
        allowed_extensions.add(".jpeg")
    if extension and extension not in allowed_extensions:
        raise ApiError(400, "INVALID_FILE_NAME", "Định dạng phần mở rộng tệp không được hỗ trợ.")
    return f"{settings['prefix']}{uuid.uuid4().hex}{settings['extensions'][content_type]}"


def _object_url(key):
    base_url = os.environ.get("PRODUCT_IMAGE_BASE_URL")
    if base_url:
        return f"{base_url.rstrip('/')}/{quote(key, safe='/')}"
    region = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
    return f"https://{_bucket()}.s3.{region}.amazonaws.com/{quote(key, safe='/')}"


@with_error_handling
def product_image_upload_url(event, context=None):
    require_any_group(event, ["Admin", "Staff"])
    if event.get("httpMethod") != "POST" or event.get("path") != "/products/upload-url":
        raise ApiError(404, "ROUTE_NOT_FOUND", "Không tìm thấy endpoint.")
    body = parse_body(event)
    content_type = body.get("contentType")
    if content_type not in UPLOAD_TYPES["product-image"]["content_types"]:
        raise ApiError(400, "INVALID_CONTENT_TYPE", "Ảnh phải là JPEG, PNG hoặc WebP.")
    key = _key_for("product-image", body.get("fileName"), content_type)
    settings = UPLOAD_TYPES["product-image"]
    response = _client().generate_presigned_post(
        Bucket=_bucket(),
        Key=key,
        Fields={"Content-Type": content_type},
        Conditions=[
            {"Content-Type": content_type},
            ["content-length-range", 1, settings["max_bytes"]],
        ],
        ExpiresIn=300,
    )
    return success({
        **response,
        "objectKey": key,
        "imageUrl": _object_url(key),
        "expiresIn": 300,
    })


@with_error_handling
def invoice_upload_url(event, context=None):
    require_any_group(event, ["Admin", "Staff"])
    if event.get("httpMethod") != "POST" or event.get("path") != "/transactions/invoice-upload-url":
        raise ApiError(404, "ROUTE_NOT_FOUND", "Không tìm thấy endpoint.")
    body = parse_body(event)
    content_type = body.get("contentType")
    if content_type not in UPLOAD_TYPES["invoice"]["content_types"]:
        raise ApiError(400, "INVALID_CONTENT_TYPE", "Chứng từ phải là PDF, JPEG hoặc PNG.")
    key = _key_for("invoice", body.get("fileName"), content_type)
    settings = UPLOAD_TYPES["invoice"]
    response = _client().generate_presigned_post(
        Bucket=_bucket(),
        Key=key,
        Fields={"Content-Type": content_type},
        Conditions=[
            {"Content-Type": content_type},
            ["content-length-range", 1, settings["max_bytes"]],
        ],
        ExpiresIn=300,
    )
    return success({
        **response,
        "objectKey": key,
        "invoiceUrl": key,
        "expiresIn": 300,
    })


@with_error_handling
def invoice_download_url(event, context=None):
    require_any_group(event, ["Admin", "Staff"])
    transaction_id = (event.get("pathParameters") or {}).get("transactionId")
    if event.get("httpMethod") != "GET" or not transaction_id:
        raise ApiError(404, "ROUTE_NOT_FOUND", "Không tìm thấy endpoint.")
    result = dynamodb.Table(table_name("TABLE_TRANSACTIONS")).query(
        KeyConditionExpression=Key("transactionId").eq(transaction_id),
        Limit=1,
        ConsistentRead=True,
    )
    items = result.get("Items", [])
    if not items:
        raise ApiError(404, "TRANSACTION_NOT_FOUND", "Không tìm thấy giao dịch.")
    key = items[0].get("invoiceUrl")
    if not isinstance(key, str) or not key.startswith("invoices/") or ".." in key.split("/"):
        raise ApiError(404, "INVOICE_NOT_FOUND", "Giao dịch không có chứng từ.")
    url = _client().generate_presigned_url(
        "get_object",
        Params={"Bucket": _bucket(), "Key": key},
        ExpiresIn=300,
    )
    return success({"url": url, "expiresIn": 300})
