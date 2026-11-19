import hashlib
import json
import os
import re
from datetime import datetime, timezone

from boto3.dynamodb.types import TypeSerializer

from ..common.dynamodb import dynamodb, query_page
from ..common.http import ApiError, parse_body, require_any_group, success, with_error_handling

PRODUCT_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_serializer = TypeSerializer()


def _table(name):
    return dynamodb.Table(os.environ[name])


def _client():
    return dynamodb.meta.client


def _validate_transaction(input_data):
    if input_data.get("invoiceUrl") not in (None, ""):
        raise ApiError(400, "UPLOAD_REQUIRED", "Tải chứng từ lên S3 trước; không gửi URL hoặc Base64 trong request.")
    transaction_type = input_data.get("type")
    if transaction_type not in ("IN", "OUT"):
        raise ApiError(400, "INVALID_TYPE", "type phải là IN hoặc OUT.")
    product_id = input_data.get("productId")
    if not isinstance(product_id, str) or not PRODUCT_ID_PATTERN.fullmatch(product_id):
        raise ApiError(400, "INVALID_PRODUCT_ID", "productId không hợp lệ.")
    amount = input_data.get("amount")
    if isinstance(amount, bool) or not isinstance(amount, int) or amount <= 0:
        raise ApiError(400, "INVALID_AMOUNT", "amount phải là số nguyên dương.")
    reason = input_data.get("reason", "").strip() if isinstance(input_data.get("reason"), str) else ""
    if not reason or len(reason) > 500:
        raise ApiError(400, "INVALID_REASON", "reason là bắt buộc và tối đa 500 ký tự.")
    supplier_id = input_data.get("supplierId") or None
    if supplier_id is not None and (not isinstance(supplier_id, str) or len(supplier_id) > 64):
        raise ApiError(400, "INVALID_SUPPLIER_ID", "supplierId không hợp lệ.")
    if transaction_type == "OUT" and supplier_id:
        raise ApiError(400, "INVALID_SUPPLIER_ID", "Giao dịch OUT không nhận supplierId.")
    invoice_key = input_data.get("invoiceKey") or None
    if invoice_key is not None and (not isinstance(invoice_key, str) or len(invoice_key) > 1024):
        raise ApiError(400, "INVALID_INVOICE_KEY", "invoiceKey không hợp lệ.")
    return {
        "type": transaction_type,
        "productId": product_id,
        "amount": amount,
        "supplierId": supplier_id,
        "reason": reason,
        "invoiceKey": invoice_key,
    }


def _serialize_transaction(transaction):
    return {
        "transactionId": transaction["transactionId"],
        "timestamp": transaction["timestamp"],
        "performedBy": transaction["performedBy"],
        "type": transaction["type"],
        "productId": transaction["productId"],
        "productName": transaction["productName"],
        "amount": transaction["amount"],
        "supplierId": transaction.get("supplierId"),
        "reason": transaction["reason"],
        "invoiceKey": transaction.get("invoiceKey"),
    }


def _actor(claims):
    username = claims.get("cognito:username") or claims.get("username") or claims.get("sub")
    subject = claims.get("sub") or username
    if not isinstance(username, str) or not isinstance(subject, str):
        raise ApiError(401, "INVALID_IDENTITY", "Không đọc được danh tính từ Cognito token.")
    return username, subject


def _serialize(value):
    return {key: _serializer.serialize(item) for key, item in value.items()}


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
    return dynamodb.Table(table_name).get_item(Key=key, ConsistentRead=True).get("Item")


def _respond_existing(transaction, request_hash):
    if transaction.get("requestHash") != request_hash:
        raise ApiError(409, "IDEMPOTENCY_KEY_REUSED", "Idempotency-Key này đã được dùng cho request khác.")
    return success(_serialize_transaction(transaction))


@with_error_handling
def handler(event, context=None):
    require_any_group(event, ["Admin", "Staff"])
    transactions_table = os.environ["TRANSACTIONS_TABLE"]
    products_table = os.environ["PRODUCTS_TABLE"]
    suppliers_table = os.environ["SUPPLIERS_TABLE"]
    method = event.get("httpMethod")
    transaction_id = (event.get("pathParameters") or {}).get("transactionId")

    if method == "GET" and not transaction_id:
        page = query_page(
            _table("TRANSACTIONS_TABLE"),
            event,
            IndexName="ByTimestamp",
            KeyConditionExpression="#gsi1pk = :partition",
            ExpressionAttributeNames={"#gsi1pk": "gsi1pk"},
            ExpressionAttributeValues={":partition": "TRANSACTION"},
            ScanIndexForward=True,
        )
        return success([_serialize_transaction(item) for item in page["items"]], extra={"nextToken": page["nextToken"]} if page["nextToken"] else None)
    if method == "GET" and transaction_id:
        item = _get_item(transactions_table, {"transactionId": transaction_id})
        if not item:
            raise ApiError(404, "TRANSACTION_NOT_FOUND", "Không tìm thấy giao dịch.")
        return success(_serialize_transaction(item))
    if method == "POST" and not transaction_id:
        transaction_input = _validate_transaction(parse_body(event))
        claims = event.get("requestContext", {}).get("authorizer", {}).get("claims", {})
        username, subject = _actor(claims)
        key = _idempotency_key(event)
        request_hash = _request_hash(transaction_input)
        transaction_id = _transaction_id(subject, key)
        existing = _get_item(transactions_table, {"transactionId": transaction_id})
        if existing:
            return _respond_existing(existing, request_hash)

        product = _get_item(products_table, {"productId": transaction_input["productId"]})
        if not product:
            raise ApiError(404, "PRODUCT_NOT_FOUND", "Không tìm thấy sản phẩm.")
        quantity = product.get("quantity")
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
        transaction = {
            "transactionId": transaction_id,
            "timestamp": timestamp,
            "performedBy": username,
            **transaction_input,
            "productName": product["name"],
            "requestHash": request_hash,
            "gsi1pk": "TRANSACTION",
            "gsi1sk": f"{timestamp}#{transaction_id}",
        }
        names = {"#quantity": "quantity", "#updatedAt": "updatedAt"}
        values = {":delta": amount if transaction_input["type"] == "IN" else -amount, ":timestamp": timestamp}
        condition = "attribute_exists(productId) AND #quantity <= :maxQuantity" if transaction_input["type"] == "IN" else "attribute_exists(productId) AND #quantity >= :amount"
        if transaction_input["type"] == "IN":
            values[":maxQuantity"] = 9007199254740991 - amount
        else:
            values[":amount"] = amount
        try:
            _client().transact_write_items(
                TransactItems=[
                    {
                        "Update": {
                            "TableName": products_table,
                            "Key": _serialize({"productId": transaction_input["productId"]}),
                            "UpdateExpression": "SET #quantity = #quantity + :delta, #updatedAt = :timestamp",
                            "ConditionExpression": condition,
                            "ExpressionAttributeNames": names,
                            "ExpressionAttributeValues": _serialize(values),
                        }
                    },
                    {
                        "Put": {
                            "TableName": transactions_table,
                            "Item": _serialize(transaction),
                            "ConditionExpression": "attribute_not_exists(transactionId)",
                        }
                    },
                ]
            )
            return success(_serialize_transaction(transaction), 201)
        except Exception as error:
            error_response = getattr(error, "response", {})
            if error_response.get("Error", {}).get("Code") != "TransactionCanceledException":
                raise
            existing = _get_item(transactions_table, {"transactionId": transaction_id})
            if existing:
                return _respond_existing(existing, request_hash)
            latest = _get_item(products_table, {"productId": transaction_input["productId"]})
            if not latest:
                raise ApiError(404, "PRODUCT_NOT_FOUND", "Không tìm thấy sản phẩm.") from error
            latest_quantity = latest.get("quantity", 0)
            if transaction_input["type"] == "OUT" and latest_quantity < amount:
                raise ApiError(409, "INSUFFICIENT_STOCK", f"Không đủ tồn kho. Hiện có: {latest_quantity}, yêu cầu xuất: {amount}.") from error
            if transaction_input["type"] == "IN" and latest_quantity + amount > 9007199254740991:
                raise ApiError(409, "QUANTITY_LIMIT", "Số lượng tồn kho vượt giới hạn hỗ trợ.") from error
            raise ApiError(409, "TRANSACTION_CONFLICT", "Giao dịch bị xung đột; có thể thử lại với cùng Idempotency-Key.") from error
    raise ApiError(404, "ROUTE_NOT_FOUND", "Không tìm thấy endpoint.")
