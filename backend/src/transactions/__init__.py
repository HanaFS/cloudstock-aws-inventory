import hashlib
import json
import os
import re
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from urllib.parse import urlsplit

import boto3
from boto3.dynamodb.conditions import Key
from boto3.dynamodb.types import TypeSerializer
from botocore.exceptions import ClientError

from ..common.dynamodb import dynamodb, query_page
from ..common.http import ApiError, parse_body, require_any_group, success, with_error_handling

PRODUCT_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
INVOICE_RESERVATION_PATTERN = re.compile(r"^[0-9a-f]{32}$")
INVOICE_OBJECT_PATTERN = re.compile(r"^invoices/[A-Za-z0-9._/-]{1,900}$")
INVOICE_GENERATED_OBJECT_PATTERN = re.compile(r"^invoices/[0-9a-f]{32}\.(pdf|jpg|png|webp)$")
MAX_INVOICE_BYTES = 10 * 1024 * 1024
INVOICE_UPLOAD_TTL_SECONDS = 10 * 60
INVOICE_URL_TTL_SECONDS = 5 * 60
INVOICE_FORMATS = {
    "application/pdf": {"extensions": {".pdf"}, "key_extension": ".pdf", "signature": b"%PDF-"},
    "image/jpeg": {"extensions": {".jpg", ".jpeg"}, "key_extension": ".jpg", "signature": b"\xff\xd8\xff"},
    "image/png": {"extensions": {".png"}, "key_extension": ".png", "signature": b"\x89PNG\r\n\x1a\n"},
    "image/webp": {"extensions": {".webp"}, "key_extension": ".webp", "signature": b"RIFF"},
}
_serializer = TypeSerializer()


def _env_var(*names):
    for n in names:
        val = os.environ.get(n)
        if val:
            return val
    raise KeyError(f"Missing required environment variable, looked for: {names}")


def _transactions_table_name():
    return _env_var("TABLE_TRANSACTIONS", "TRANSACTIONS_TABLE")


def _products_table_name():
    return _env_var("TABLE_PRODUCTS", "PRODUCTS_TABLE")


def _suppliers_table_name():
    return _env_var("TABLE_SUPPLIERS", "SUPPLIERS_TABLE")


def _invoices_bucket_name():
    return _env_var("BUCKET_NAME", "INVOICES_BUCKET")


def _table(name):
    if name in ("TRANSACTIONS_TABLE", "TABLE_TRANSACTIONS"):
        return dynamodb.Table(_transactions_table_name())
    if name in ("PRODUCTS_TABLE", "TABLE_PRODUCTS"):
        return dynamodb.Table(_products_table_name())
    if name in ("SUPPLIERS_TABLE", "TABLE_SUPPLIERS"):
        return dynamodb.Table(_suppliers_table_name())
    return dynamodb.Table(_env_var(name))


def _client():
    return dynamodb.meta.client


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
    if local:
        options["aws_access_key_id"] = "local"
        options["aws_secret_access_key"] = "local"
    return boto3.client("s3", **options)


def _validate_invoice_upload(body):
    product_id = body.get("productId")
    if not isinstance(product_id, str) or not PRODUCT_ID_PATTERN.fullmatch(product_id):
        raise ApiError(400, "INVALID_PRODUCT_ID", "productId is invalid.")
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
    file_format = INVOICE_FORMATS.get(content_type) if isinstance(content_type, str) else None
    if not file_format or os.path.splitext(filename)[1].lower() not in file_format["extensions"]:
        raise ApiError(400, "UNSUPPORTED_INVOICE_TYPE", "Use a PDF, JPEG, PNG, or WebP file with a matching extension.")
    if isinstance(size_bytes, bool) or not isinstance(size_bytes, int) or not 1 <= size_bytes <= MAX_INVOICE_BYTES:
        raise ApiError(400, "INVALID_INVOICE_SIZE", f"sizeBytes must be between 1 and {MAX_INVOICE_BYTES}.")
    return product_id, content_type, size_bytes, file_format


def _invoice_reservation(identifier, subject, transaction_id, product_id, allow_consumed=False):
    if not isinstance(identifier, str) or not INVOICE_RESERVATION_PATTERN.fullmatch(identifier):
        raise ApiError(404, "UPLOAD_RESERVATION_NOT_FOUND", "Invoice upload reservation not found.")
    reservation = _get_item(
        _transactions_table_name(), {"transactionId": f"UPLOAD#{identifier}"}
    )
    if not reservation or reservation.get("recordType") != "UPLOAD_RESERVATION" or reservation.get("reservationType") != "INVOICE":
        raise ApiError(404, "UPLOAD_RESERVATION_NOT_FOUND", "Invoice upload reservation not found.")
    if reservation.get("ownerSub") != subject:
        raise ApiError(403, "UPLOAD_RESERVATION_FORBIDDEN", "This invoice upload belongs to another user.")
    if allow_consumed:
        if (
            reservation.get("state") != "CONSUMED"
            or reservation.get("attachedTransactionId") != transaction_id
            or reservation.get("productId") != product_id
        ):
            raise ApiError(409, "UPLOAD_RESERVATION_CONFLICT", "Invoice reservation is not consumed by this transaction.")
    else:
        now = int(datetime.now(timezone.utc).timestamp())
        if reservation.get("state") != "PENDING" or not isinstance(reservation.get("expiresAt"), int) or reservation["expiresAt"] <= now:
            raise ApiError(409, "UPLOAD_RESERVATION_EXPIRED", "Invoice upload reservation is expired or already consumed.")
    if not isinstance(reservation.get("s3Key"), str) or not INVOICE_GENERATED_OBJECT_PATTERN.fullmatch(reservation["s3Key"]):
        raise ApiError(409, "INVALID_INVOICE_REFERENCE", "Invoice reservation has an invalid object key.")
    if reservation.get("contentType") not in INVOICE_FORMATS:
        raise ApiError(409, "INVALID_INVOICE_REFERENCE", "Invoice reservation has an invalid content type.")
    size_bytes = reservation.get("sizeBytes")
    if isinstance(size_bytes, bool) or not isinstance(size_bytes, int) or not 1 <= size_bytes <= MAX_INVOICE_BYTES:
        raise ApiError(409, "INVALID_INVOICE_REFERENCE", "Invoice reservation has an invalid size.")
    if reservation.get("productId") != product_id:
        raise ApiError(409, "UPLOAD_PRODUCT_MISMATCH", "Invoice upload is reserved for a different product.")
    return reservation


def _verify_invoice_object(reservation):
    s3 = _s3_client()
    bucket = _invoices_bucket_name()
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
    file_format = INVOICE_FORMATS[reservation["contentType"]]
    if reservation["contentType"] == "image/webp":
        valid = len(header) >= 12 and header[:4] == b"RIFF" and header[8:12] == b"WEBP"
    else:
        valid = header.startswith(file_format["signature"])
    if not valid:
        raise ApiError(400, "INVALID_INVOICE_CONTENT", "Uploaded bytes do not match the declared invoice type.")


def _create_invoice_upload(event):
    claims = event.get("requestContext", {}).get("authorizer", {}).get("claims", {})
    _, subject = _actor(claims)
    product_id, content_type, size_bytes, file_format = _validate_invoice_upload(parse_body(event))
    identifier = uuid.uuid4().hex
    object_key = f"invoices/{uuid.uuid4().hex}{file_format['key_extension']}"
    now = int(datetime.now(timezone.utc).timestamp())
    reservation = {
        "transactionId": f"UPLOAD#{identifier}",
        "recordType": "UPLOAD_RESERVATION",
        "reservationType": "INVOICE",
        "ownerSub": subject,
        "productId": product_id,
        "s3Key": object_key,
        "contentType": content_type,
        "sizeBytes": size_bytes,
        "expiresAt": now + INVOICE_UPLOAD_TTL_SECONDS,
        "state": "PENDING",
    }
    upload_url = _s3_client().generate_presigned_url(
        "put_object",
        Params={
            "Bucket": _invoices_bucket_name(),
            "Key": object_key,
            "ContentType": content_type,
            "ContentLength": size_bytes,
            "IfNoneMatch": "*",
        },
        ExpiresIn=INVOICE_URL_TTL_SECONDS,
        HttpMethod="PUT",
    )
    _table("TRANSACTIONS_TABLE").put_item(
        Item=reservation,
        ConditionExpression="attribute_not_exists(transactionId)",
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
    object_key = legacy or canonical
    if (
        not isinstance(object_key, str)
        or not INVOICE_OBJECT_PATTERN.fullmatch(object_key)
        or any(part in ("", ".", "..") for part in object_key.split("/"))
        or "\\" in object_key
    ):
        raise ApiError(404, "INVOICE_NOT_FOUND", "Transaction has no supported private invoice reference.")
    return object_key


def _get_private_invoice(transaction_id):
    transaction = _get_item(_transactions_table_name(), {"transactionId": transaction_id})
    if not transaction or _is_upload_reservation(transaction):
        raise ApiError(404, "TRANSACTION_NOT_FOUND", "Transaction not found.")
    object_key = _invoice_reference(transaction)
    reservation_id = transaction.get("invoiceReservationId")
    if reservation_id:
        if not isinstance(reservation_id, str) or not INVOICE_RESERVATION_PATTERN.fullmatch(reservation_id):
            raise ApiError(409, "INVALID_INVOICE_REFERENCE", "Transaction invoice reservation is invalid.")
        reservation = _get_item(
            _transactions_table_name(), {"transactionId": f"UPLOAD#{reservation_id}"}
        )
        if (
            not reservation
            or reservation.get("recordType") != "UPLOAD_RESERVATION"
            or reservation.get("reservationType") != "INVOICE"
            or reservation.get("state") != "CONSUMED"
            or reservation.get("attachedTransactionId") != transaction_id
            or reservation.get("s3Key") != object_key
        ):
            raise ApiError(409, "INVALID_INVOICE_REFERENCE", "Invoice reservation does not match the transaction.")
    s3 = _s3_client()
    try:
        s3.head_object(Bucket=_invoices_bucket_name(), Key=object_key)
    except ClientError as error:
        if error.response.get("Error", {}).get("Code") in ("404", "NoSuchKey", "NotFound"):
            raise ApiError(404, "INVOICE_NOT_FOUND", "Invoice object was not found.") from error
        raise
    download_url = s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": _invoices_bucket_name(), "Key": object_key},
        ExpiresIn=INVOICE_URL_TTL_SECONDS,
        HttpMethod="GET",
    )
    return success({
        "transactionId": transaction_id,
        "downloadUrl": download_url,
        "expiresIn": INVOICE_URL_TTL_SECONDS,
    })


def _normalize_transaction_type(input_data):
    legacy_to_canonical = {"IN": "IMPORT", "OUT": "EXPORT"}
    canonical_to_legacy = {value: key for key, value in legacy_to_canonical.items()}
    request_type = input_data.get("type")
    request_canonical = input_data.get("canonicalType")

    if request_type in legacy_to_canonical:
        canonical_type = legacy_to_canonical[request_type]
        legacy_type = request_type
    elif request_type in canonical_to_legacy:
        canonical_type = request_type
        legacy_type = canonical_to_legacy[request_type]
    elif request_type is None and request_canonical in canonical_to_legacy:
        canonical_type = request_canonical
        legacy_type = canonical_to_legacy[request_canonical]
    else:
        raise ApiError(400, "INVALID_TYPE", "type must be IN/OUT or IMPORT/EXPORT.")

    if request_canonical is not None:
        if request_canonical not in canonical_to_legacy:
            raise ApiError(400, "INVALID_TYPE", "canonicalType must be IMPORT or EXPORT.")
        if request_canonical != canonical_type:
            raise ApiError(400, "FIELD_CONFLICT", "type and canonicalType conflict.")
    return legacy_type, canonical_type


def _normalize_product_quantity(product):
    """Lấy stockQuantity từ product, hỗ trợ cả field quantity và stockQuantity"""
    for field in ("stockQuantity", "quantity"):
        value = product.get(field)
        if value is None:
            continue
        if isinstance(value, Decimal):
            if value.is_finite() and value == value.to_integral_value():
                value = int(value)
            else:
                raise ApiError(409, "INVALID_STOCK_STATE", "Tồn kho sản phẩm không hợp lệ.")
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ApiError(409, "INVALID_STOCK_STATE", "Tồn kho sản phẩm không hợp lệ.")
        return value
    raise ApiError(409, "INVALID_STOCK_STATE", "Tồn kho sản phẩm không hợp lệ.")


def _is_upload_reservation(transaction):
    return transaction.get("recordType") == "UPLOAD_RESERVATION"


def _validate_transaction(input_data):
    if input_data.get("invoiceUrl") not in (None, ""):
        raise ApiError(400, "UPLOAD_REQUIRED", "Upload the invoice and send invoiceReservationId; direct URLs are not accepted.")
    legacy_invoice_key = input_data.get("invoiceKey") or None
    if legacy_invoice_key is not None and (
        not isinstance(legacy_invoice_key, str) or len(legacy_invoice_key) > 1024
    ):
        raise ApiError(400, "INVALID_INVOICE_KEY", "invoiceKey is invalid.")
    invoice_reservation_id = input_data.get("invoiceReservationId") or None
    if invoice_reservation_id is not None and (
        not isinstance(invoice_reservation_id, str)
        or not INVOICE_RESERVATION_PATTERN.fullmatch(invoice_reservation_id)
    ):
        raise ApiError(400, "INVALID_INVOICE_RESERVATION", "invoiceReservationId is invalid.")
    transaction_type, canonical_type = _normalize_transaction_type(input_data)
    if transaction_type not in ("IN", "OUT"):
        raise ApiError(400, "INVALID_TYPE", "type phải là IN hoặc OUT.")
    product_id = input_data.get("productId")
    if not isinstance(product_id, str) or not PRODUCT_ID_PATTERN.fullmatch(product_id):
        raise ApiError(400, "INVALID_PRODUCT_ID", "productId không hợp lệ.")
    amount = input_data.get("amount", input_data.get("quantity"))
    if "amount" in input_data and "quantity" in input_data and input_data["amount"] != input_data["quantity"]:
        raise ApiError(400, "FIELD_CONFLICT", "amount and quantity conflict.")
    if isinstance(amount, bool) or not isinstance(amount, int) or amount <= 0:
        raise ApiError(400, "INVALID_AMOUNT", "amount phải là số nguyên dương.")
    reason = input_data.get("reason", "").strip() if isinstance(input_data.get("reason"), str) else ""
    if transaction_type == "OUT":
        if not reason or len(reason) > 500:
            raise ApiError(400, "INVALID_REASON", "reason là bắt buộc cho xuất kho và tối đa 500 ký tự.")
    elif len(reason) > 500:
        raise ApiError(400, "INVALID_REASON", "reason tối đa 500 ký tự.")
    supplier_id = input_data.get("supplierId") or None
    if supplier_id is not None and (not isinstance(supplier_id, str) or len(supplier_id) > 64):
        raise ApiError(400, "INVALID_SUPPLIER_ID", "supplierId không hợp lệ.")
    if transaction_type == "OUT" and supplier_id:
        raise ApiError(400, "INVALID_SUPPLIER_ID", "Giao dịch OUT không nhận supplierId.")
    return {
        "type": transaction_type,
        "canonicalType": canonical_type,
        "productId": product_id,
        "amount": amount,
        "quantity": amount,
        "supplierId": supplier_id,
        "reason": reason,
        "invoiceKey": legacy_invoice_key,
        "invoiceUrl": None,
        "invoiceReservationId": invoice_reservation_id,
    }


def _serialize_transaction(transaction):
    if _is_upload_reservation(transaction):
        raise ApiError(404, "TRANSACTION_NOT_FOUND", "Transaction not found.")
    compatible = dict(transaction)
    for field in ("amount", "quantity"):
        value = compatible.get(field)
        if isinstance(value, Decimal) and value.is_finite() and value == value.to_integral_value():
            compatible[field] = int(value)
    invoice = compatible.get("invoiceKey") or compatible.get("invoiceUrl") or None
    return {
        "transactionId": compatible["transactionId"],
        "timestamp": compatible.get("timestamp", compatible.get("createdAt")),
        "createdAt": compatible.get("createdAt", compatible.get("timestamp")),
        "performedBy": compatible["performedBy"],
        "type": compatible["type"],
        "canonicalType": compatible.get("canonicalType"),
        "productId": compatible["productId"],
        "productName": compatible.get("productName"),
        "amount": compatible.get("amount", compatible.get("quantity")),
        "quantity": compatible.get("quantity", compatible.get("amount")),
        "supplierId": compatible.get("supplierId"),
        "reason": compatible.get("reason"),
        "invoiceKey": invoice,
        "invoiceUrl": invoice,
    }


def _actor(claims):
    username = claims.get("cognito:username") or claims.get("username") or claims.get("sub")
    subject = claims.get("sub") or username
    if not isinstance(username, str) or not isinstance(subject, str):
        raise ApiError(401, "INVALID_IDENTITY", "Không đọc được danh tính từ Cognito token.")
    return username, subject


def _serialize(value):
    return {
        key: _serializer.serialize(item)
        for key, item in value.items()
        if item is not None
    }


def _request_hash(transaction):
    encoded = json.dumps(transaction, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _transaction_id(subject, idempotency_key):
    encoded = json.dumps([subject, idempotency_key], separators=(",", ":"))
    return "txn-" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:32]


def _idempotency_key(event):
    headers = event.get("headers") or {}
    key = next((value for name, value in headers.items() if name.lower() == "idempotency-key"), None)
    if not isinstance(key, str) or not 1 <= len(key) <= 128:
        raise ApiError(400, "IDEMPOTENCY_KEY_REQUIRED", "Gửi Idempotency-Key dài từ 1 đến 128 ký tự.")
    return key


def _get_item(table_name, key):
    table = dynamodb.Table(table_name)
    try:
        return table.get_item(Key=key, ConsistentRead=True).get("Item")
    except ClientError as err:
        if err.response.get("Error", {}).get("Code") == "ValidationException" and "schema" in str(err).lower():
            # Khi bảng có composite primary key (ví dụ: HASH transactionId + RANGE createdAt)
            # nhưng truy vấn chỉ có HASH key, tự động chuyển sang Query với Limit=1
            key_name, key_val = next(iter(key.items()))
            try:
                res = table.query(
                    KeyConditionExpression=Key(key_name).eq(key_val),
                    Limit=1,
                    ConsistentRead=True,
                )
            except ClientError:
                res = table.query(
                    KeyConditionExpression=Key(key_name).eq(key_val),
                    Limit=1,
                )
            items = res.get("Items", [])
            return items[0] if items else None
        raise


def _respond_existing(transaction, request_hash):
    if transaction.get("requestHash") != request_hash:
        raise ApiError(409, "IDEMPOTENCY_KEY_REUSED", "Idempotency-Key này đã được dùng cho request khác.")
    return success(_serialize_transaction(transaction))


@with_error_handling
def handler(event, context=None):
    require_any_group(event, ["Admin", "Staff"])
    transactions_table = _transactions_table_name()
    products_table = _products_table_name()
    suppliers_table = _suppliers_table_name()
    method = event.get("httpMethod")
    path_transaction_id = (event.get("pathParameters") or {}).get("transactionId")
    resource = event.get("resource")
    path = event.get("path", "")

    if method == "POST" and (
        resource == "/transactions/invoice-uploads"
        or path == "/transactions/invoice-uploads"
    ):
        return _create_invoice_upload(event)
    if method == "GET" and path_transaction_id and (
        resource == "/transactions/{transactionId}/invoice"
        or path.endswith("/invoice")
    ):
        return _get_private_invoice(path_transaction_id)

    if method == "GET" and not path_transaction_id:
        try:
            page = query_page(
                _table("TRANSACTIONS_TABLE"),
                event,
                IndexName="ByCreatedAt",
                KeyConditionExpression="#gsi1pk = :partition",
                ExpressionAttributeNames={"#gsi1pk": "gsi1pk"},
                ExpressionAttributeValues={":partition": "TRANSACTION"},
                ScanIndexForward=True,
            )
        except ClientError as error:
            if error.response.get("Error", {}).get("Code") == "ValidationException":
                from ..common.dynamodb import scan_page
                page = scan_page(_table("TRANSACTIONS_TABLE"), event, ["transactionId", "createdAt"])
            else:
                raise
        transactions = [item for item in page["items"] if not _is_upload_reservation(item)]
        return success(
            [_serialize_transaction(item) for item in transactions],
            extra={"nextToken": page["nextToken"]} if page["nextToken"] else None,
        )
    if method == "GET" and path_transaction_id:
        item = _get_item(transactions_table, {"transactionId": path_transaction_id})
        if not item or _is_upload_reservation(item):
            raise ApiError(404, "TRANSACTION_NOT_FOUND", "Không tìm thấy giao dịch.")
        return success(_serialize_transaction(item))
    if method == "POST" and not path_transaction_id:
        transaction_input = _validate_transaction(parse_body(event))
        invoice_reservation_id = transaction_input.pop("invoiceReservationId")
        claims = event.get("requestContext", {}).get("authorizer", {}).get("claims", {})
        username, subject = _actor(claims)
        key = _idempotency_key(event)
        transaction_id = _transaction_id(subject, key)
        existing = _get_item(transactions_table, {"transactionId": transaction_id})
        invoice_reservation = None
        if invoice_reservation_id:
            if transaction_input["invoiceKey"] is not None:
                raise ApiError(400, "FIELD_CONFLICT", "Send invoiceReservationId instead of an invoiceKey.")
            invoice_reservation = _invoice_reservation(
                invoice_reservation_id,
                subject,
                transaction_id,
                transaction_input["productId"],
                allow_consumed=bool(existing),
            )
            if not existing:
                _verify_invoice_object(invoice_reservation)
        invoice_key = invoice_reservation["s3Key"] if invoice_reservation else transaction_input["invoiceKey"]
        if transaction_input["invoiceKey"] is not None and not invoice_reservation and not existing:
            raise ApiError(400, "UPLOAD_REQUIRED", "Upload the invoice and send invoiceReservationId; direct object keys are not accepted.")
        transaction_input["invoiceKey"] = invoice_key
        transaction_input["invoiceUrl"] = invoice_key
        request_hash = _request_hash({
            "type": transaction_input["type"],
            "productId": transaction_input["productId"],
            "amount": transaction_input["amount"],
            "supplierId": transaction_input["supplierId"],
            "reason": transaction_input["reason"],
            "invoiceKey": invoice_key,
        })
        if existing and not _is_upload_reservation(existing):
            if invoice_reservation_id and existing.get("invoiceReservationId") != invoice_reservation_id:
                raise ApiError(409, "IDEMPOTENCY_KEY_REUSED", "Idempotency-Key was used with a different invoice reservation.")
            if not invoice_reservation_id and existing.get("invoiceReservationId"):
                raise ApiError(409, "IDEMPOTENCY_KEY_REUSED", "Idempotency-Key was used with a different invoice reservation.")
            existing_invoice_key = existing.get("invoiceKey") or existing.get("invoiceUrl")
            if invoice_key != existing_invoice_key:
                raise ApiError(409, "IDEMPOTENCY_KEY_REUSED", "Idempotency-Key was used with a different invoice reference.")
            return _respond_existing(existing, request_hash)
        if existing:
            raise ApiError(409, "TRANSACTION_CONFLICT", "Transaction identifier conflicts with an upload reservation.")

        product = _get_item(products_table, {"productId": transaction_input["productId"]})
        if not product:
            raise ApiError(404, "PRODUCT_NOT_FOUND", "Không tìm thấy sản phẩm.")
        quantity = _normalize_product_quantity(product)
        if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity < 0:
            raise ApiError(409, "INVALID_STOCK_STATE", "Tồn kho sản phẩm không hợp lệ.")
        amount = transaction_input["amount"]
        if transaction_input["type"] == "OUT" and quantity < amount:
            raise ApiError(409, "INSUFFICIENT_STOCK", f"Không đủ tồn kho. Hiện có: {quantity}, yêu cầu xuất: {amount}.")
        if quantity + (amount if transaction_input["type"] == "IN" else -amount) > 9007199254740991:
            raise ApiError(409, "QUANTITY_LIMIT", "Số lượng tồn kho vượt giới hạn hỗ trợ.")
        if transaction_input["type"] == "IN" and transaction_input["supplierId"]:
            if not _get_item(suppliers_table, {"supplierId": transaction_input["supplierId"]}):
                raise ApiError(400, "UNKNOWN_SUPPLIER", "Nhà cung cấp không tồn tại.")

        timestamp = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        resulting_quantity = quantity + (amount if transaction_input["type"] == "IN" else -amount)
        transaction = {
            "transactionId": transaction_id,
            "timestamp": timestamp,
            "createdAt": timestamp,
            "performedBy": username,
            **transaction_input,
            "productName": product["name"],
            "requestHash": request_hash,
            "gsi1pk": "TRANSACTION",
            "gsi1sk": f"{timestamp}#{transaction_id}",
        }
        if invoice_reservation_id:
            transaction["invoiceReservationId"] = invoice_reservation_id
        names = {
            "#quantity": "quantity",
            "#stockQuantity": "stockQuantity",
            "#updatedAt": "updatedAt",
            "#status": "status",
        }
        values = {
            ":delta": amount if transaction_input["type"] == "IN" else -amount,
            ":timestamp": timestamp,
            ":currentQuantity": quantity,
            ":status": "IN_STOCK" if resulting_quantity > 0 else "OUT_OF_STOCK",
        }
        stock_exists = "(attribute_exists(#quantity) OR attribute_exists(#stockQuantity))"
        stock_synchronized = "(attribute_not_exists(#quantity) OR attribute_not_exists(#stockQuantity) OR #quantity = #stockQuantity)"
        stock_snapshot = "((attribute_exists(#quantity) AND #quantity = :currentQuantity) OR (attribute_not_exists(#quantity) AND #stockQuantity = :currentQuantity))"
        if transaction_input["type"] == "IN":
            condition = (
                f"attribute_exists(productId) AND {stock_exists} AND {stock_synchronized} "
                f"AND {stock_snapshot} AND "
                "(attribute_not_exists(#quantity) OR #quantity <= :maxQuantity) AND "
                "(attribute_not_exists(#stockQuantity) OR #stockQuantity <= :maxQuantity)"
            )
        else:
            condition = (
                f"attribute_exists(productId) AND {stock_exists} AND {stock_synchronized} "
                f"AND {stock_snapshot} AND "
                "(attribute_not_exists(#quantity) OR #quantity >= :amount) AND "
                "(attribute_not_exists(#stockQuantity) OR #stockQuantity >= :amount)"
            )
        update_expression = (
            "SET #quantity = if_not_exists(#quantity, :currentQuantity) + :delta, "
            "#stockQuantity = if_not_exists(#stockQuantity, :currentQuantity) + :delta, "
            "#updatedAt = :timestamp, #status = :status"
        )
        if transaction_input["type"] == "IN":
            values[":maxQuantity"] = 9007199254740991 - amount
        else:
            values[":amount"] = amount
        try:
            transact_items = [
                {
                    "Update": {
                        "TableName": products_table,
                        "Key": _serialize({"productId": transaction_input["productId"]}),
                        "UpdateExpression": update_expression,
                        "ConditionExpression": condition,
                        "ExpressionAttributeNames": names,
                        "ExpressionAttributeValues": _serialize(values),
                    }
                },
            ]
            if invoice_reservation:
                now_epoch = int(datetime.now(timezone.utc).timestamp())
                transact_items.append({
                    "Update": {
                        "TableName": transactions_table,
                        "Key": _serialize({"transactionId": invoice_reservation["transactionId"]}),
                        "UpdateExpression": "SET #state = :consumed, #consumedAt = :now, #attachedTransactionId = :transactionId",
                        "ConditionExpression": (
                            "#recordType = :recordType AND #state = :pending "
                            "AND #ownerSub = :subject AND #expiresAt > :now "
                            "AND #reservationType = :reservationType AND #s3Key = :s3Key "
                            "AND #contentType = :contentType AND #sizeBytes = :sizeBytes "
                            "AND #productId = :productId"
                        ),
                        "ExpressionAttributeNames": {
                            "#state": "state",
                            "#recordType": "recordType",
                            "#consumedAt": "consumedAt",
                            "#attachedTransactionId": "attachedTransactionId",
                            "#ownerSub": "ownerSub",
                            "#expiresAt": "expiresAt",
                            "#reservationType": "reservationType",
                            "#s3Key": "s3Key",
                            "#contentType": "contentType",
                            "#sizeBytes": "sizeBytes",
                            "#productId": "productId",
                        },
                        "ExpressionAttributeValues": _serialize({
                            ":consumed": "CONSUMED",
                            ":now": now_epoch,
                            ":transactionId": transaction_id,
                            ":pending": "PENDING",
                            ":recordType": "UPLOAD_RESERVATION",
                            ":subject": subject,
                            ":reservationType": "INVOICE",
                            ":s3Key": invoice_reservation["s3Key"],
                            ":contentType": invoice_reservation["contentType"],
                            ":sizeBytes": invoice_reservation["sizeBytes"],
                            ":productId": transaction_input["productId"],
                        }),
                    }
                })
            transact_items.append({
                "Put": {
                    "TableName": transactions_table,
                    "Item": _serialize(transaction),
                    "ConditionExpression": "attribute_not_exists(transactionId)",
                }
            })
            _client().transact_write_items(TransactItems=transact_items)
            return success(_serialize_transaction(transaction), 201)
        except Exception as error:
            error_response = getattr(error, "response", {})
            if error_response.get("Error", {}).get("Code") != "TransactionCanceledException":
                raise
            existing = _get_item(transactions_table, {"transactionId": transaction_id})
            if existing and not _is_upload_reservation(existing):
                return _respond_existing(existing, request_hash)
            latest = _get_item(products_table, {"productId": transaction_input["productId"]})
            if not latest:
                raise ApiError(404, "PRODUCT_NOT_FOUND", "Không tìm thấy sản phẩm.") from error
            latest_quantity = _normalize_product_quantity(latest)
            if transaction_input["type"] == "OUT" and latest_quantity < amount:
                raise ApiError(409, "INSUFFICIENT_STOCK", f"Không đủ tồn kho. Hiện có: {latest_quantity}, yêu cầu xuất: {amount}.") from error
            if transaction_input["type"] == "IN" and latest_quantity + amount > 9007199254740991:
                raise ApiError(409, "QUANTITY_LIMIT", "Số lượng tồn kho vượt giới hạn hỗ trợ.") from error
            raise ApiError(409, "TRANSACTION_CONFLICT", "Giao dịch bị xung đột; có thể thử lại với cùng Idempotency-Key.") from error
    raise ApiError(404, "ROUTE_NOT_FOUND", "Không tìm thấy endpoint.")