import hashlib
import json
import re
from datetime import datetime, timezone

from boto3.dynamodb.conditions import Key
from boto3.dynamodb.types import TypeSerializer

from ..common.dynamodb import dynamodb, query_page, table_name
from ..common.http import ApiError, parse_body, require_any_group, success, with_error_handling

PRODUCT_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_serializer = TypeSerializer()


def _table(logical_name):
    return dynamodb.Table(table_name(logical_name))


def _client():
    return dynamodb.meta.client


def _validate_transaction(input_data):
    input_data = dict(input_data)
    transaction_type = input_data.get("type")
    transaction_type = {"IN": "IMPORT", "OUT": "EXPORT"}.get(transaction_type, transaction_type)
    if transaction_type not in ("IMPORT", "EXPORT"):
        raise ApiError(400, "INVALID_TYPE", "type phải là IN hoặc OUT.")
    product_id = input_data.get("productId")
    if not isinstance(product_id, str) or not PRODUCT_ID_PATTERN.fullmatch(product_id):
        raise ApiError(400, "INVALID_PRODUCT_ID", "productId không hợp lệ.")
    amount = input_data.pop("amount", None)
    quantity = input_data.get("quantity", amount)
    if "quantity" in input_data and amount is not None and input_data["quantity"] != amount:
        raise ApiError(400, "CONFLICTING_QUANTITY", "amount và quantity phải có cùng giá trị.")
    if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity <= 0:
        raise ApiError(400, "INVALID_QUANTITY", "amount phải là số nguyên dương.")
    supplier_id = input_data.get("supplierId") or None
    if supplier_id is not None and (
        transaction_type != "IMPORT"
        or not isinstance(supplier_id, str)
        or len(supplier_id) > 64
    ):
        raise ApiError(400, "INVALID_SUPPLIER_ID", "supplierId chỉ hợp lệ cho IMPORT.")
    invoice_url = input_data.get("invoiceKey") or input_data.get("invoiceUrl") or None
    if invoice_url is not None and (
        transaction_type != "IMPORT"
        or not isinstance(invoice_url, str)
        or len(invoice_url) > 2048
        or not invoice_url.startswith("invoices/")
    ):
        raise ApiError(400, "INVALID_INVOICE_URL", "invoiceUrl phải là khóa S3 trong invoices/ và chỉ dùng cho IMPORT.")
    reason = input_data.get("reason")
    if transaction_type == "EXPORT":
        reason = reason.strip() if isinstance(reason, str) else ""
        if not reason or len(reason) > 500:
            raise ApiError(400, "INVALID_REASON", "reason là bắt buộc cho EXPORT và tối đa 500 ký tự.")
    elif reason is not None:
        reason = reason.strip() if isinstance(reason, str) else ""
        if len(reason) > 500:
            raise ApiError(400, "INVALID_REASON", "reason tối đa 500 ký tự.")
    return {
        "type": transaction_type,
        "productId": product_id,
        "quantity": quantity,
        "supplierId": supplier_id,
        "invoiceUrl": invoice_url,
        "reason": reason,
    }


def _serialize_transaction(transaction):
    result = {
        "transactionId": transaction["transactionId"],
        "timestamp": transaction["createdAt"],
        "performedBy": transaction["performedBy"],
        "type": {"IMPORT": "IN", "EXPORT": "OUT"}[transaction["type"]],
        "productId": transaction["productId"],
        "productName": transaction["productName"],
        "amount": transaction["quantity"],
    }
    if transaction["type"] == "IMPORT":
        if transaction.get("supplierId"):
            result["supplierId"] = transaction["supplierId"]
        if transaction.get("invoiceUrl"):
            result["invoiceUrl"] = transaction["invoiceUrl"]
    if transaction.get("reason"):
        result["reason"] = transaction["reason"]
    return result


def _actor(claims):
    username = claims.get("cognito:username") or claims.get("username") or claims.get("sub")
    subject = claims.get("sub") or username
    if not isinstance(username, str) or not isinstance(subject, str):
        raise ApiError(401, "INVALID_IDENTITY", "Không đọc được danh tính từ Cognito token.")
    return username, subject


def _serialize(value):
    return {key: _serializer.serialize(item) for key, item in value.items() if item is not None}


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


def _transaction_by_id(transaction_id):
    result = _table("TABLE_TRANSACTIONS").query(
        KeyConditionExpression=Key("transactionId").eq(transaction_id),
        Limit=1,
        ConsistentRead=True,
    )
    items = result.get("Items", [])
    return items[0] if items else None


def _product_by_id(product_id):
    return _table("TABLE_PRODUCTS").get_item(
        Key={"productId": product_id},
        ConsistentRead=True,
    ).get("Item")


def _respond_existing(transaction, request_hash):
    if transaction.get("requestHash") != request_hash:
        raise ApiError(409, "IDEMPOTENCY_KEY_REUSED", "Idempotency-Key này đã được dùng cho request khác.")
    return success(_serialize_transaction(transaction))


@with_error_handling
def handler(event, context=None):
    path = event.get("path", "")
    if path == "/logs":
        from ..logs import handler as logs_handler

        return logs_handler(event, context)
    if path == "/transactions/invoice-upload-url":
        from ..uploads import invoice_upload_url

        return invoice_upload_url(event, context)
    if path.endswith("/invoice-url"):
        from ..uploads import invoice_download_url

        return invoice_download_url(event, context)

    require_any_group(event, ["Admin", "Staff"])
    method = event.get("httpMethod")
    transaction_id = (event.get("pathParameters") or {}).get("transactionId")

    if method == "GET" and not transaction_id:
        page = query_page(
            _table("TABLE_TRANSACTIONS"),
            event,
            IndexName="ByCreatedAt",
            KeyConditionExpression=Key("gsi1pk").eq("TRANSACTION"),
            ScanIndexForward=True,
        )
        return success(
            [_serialize_transaction(item) for item in page["items"]],
            extra={"nextToken": page["nextToken"]} if page["nextToken"] else None,
        )
    if method == "GET" and transaction_id:
        item = _transaction_by_id(transaction_id)
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
        existing = _transaction_by_id(transaction_id)
        if existing:
            return _respond_existing(existing, request_hash)

        product = _product_by_id(transaction_input["productId"])
        if not product:
            raise ApiError(404, "PRODUCT_NOT_FOUND", "Không tìm thấy sản phẩm.")
        stock = product.get("stockQuantity")
        if isinstance(stock, bool) or not isinstance(stock, int) or stock < 0:
            raise ApiError(409, "INVALID_STOCK_STATE", "Tồn kho sản phẩm không hợp lệ.")
        quantity = transaction_input["quantity"]
        importing = transaction_input["type"] == "IMPORT"
        if not importing and stock < quantity:
            raise ApiError(409, "INSUFFICIENT_STOCK", f"Không đủ tồn kho. Hiện có: {stock}, yêu cầu xuất: {quantity}.")
        if stock + (quantity if importing else -quantity) > 9007199254740991:
            raise ApiError(409, "QUANTITY_LIMIT", "Số lượng tồn kho vượt giới hạn hỗ trợ.")
        if importing and transaction_input["supplierId"]:
            supplier = _table("TABLE_SUPPLIERS").get_item(
                Key={"supplierId": transaction_input["supplierId"]}
            ).get("Item")
            if not supplier:
                raise ApiError(400, "UNKNOWN_SUPPLIER", "Nhà cung cấp không tồn tại.")

        created_at = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        transaction = {
            "transactionId": transaction_id,
            "createdAt": created_at,
            "performedBy": username,
            **transaction_input,
            "productName": product["name"],
            "requestHash": request_hash,
            "gsi1pk": "TRANSACTION",
            "gsi1sk": f"{created_at}#{transaction_id}",
        }
        new_stock = stock + (quantity if importing else -quantity)
        names = {
            "#stock": "stockQuantity",
            "#status": "status",
            "#updatedAt": "updatedAt",
        }
        values = {
            ":delta": quantity if importing else -quantity,
            ":timestamp": created_at,
            ":status": "IN_STOCK" if new_stock > 0 else "OUT_OF_STOCK",
            ":expectedStock": stock,
        }
        condition = (
            "attribute_exists(productId) AND #stock = :expectedStock AND #stock <= :maxStock"
            if importing
            else "attribute_exists(productId) AND #stock = :expectedStock AND #stock >= :minimum"
        )
        if importing:
            values[":maxStock"] = 9007199254740991 - quantity
        else:
            values[":minimum"] = quantity
        try:
            _client().transact_write_items(
                TransactItems=[
                    {
                        "Update": {
                            "TableName": table_name("TABLE_PRODUCTS"),
                            "Key": _serialize({"productId": transaction_input["productId"]}),
                            "UpdateExpression": "SET #stock = #stock + :delta, #status = :status, #updatedAt = :timestamp",
                            "ConditionExpression": condition,
                            "ExpressionAttributeNames": names,
                            "ExpressionAttributeValues": _serialize(values),
                        }
                    },
                    {
                        "Put": {
                            "TableName": table_name("TABLE_TRANSACTIONS"),
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
            existing = _transaction_by_id(transaction_id)
            if existing:
                return _respond_existing(existing, request_hash)
            latest = _product_by_id(transaction_input["productId"])
            if not latest:
                raise ApiError(404, "PRODUCT_NOT_FOUND", "Không tìm thấy sản phẩm.") from error
            latest_stock = latest.get("stockQuantity", 0)
            if not importing and latest_stock < quantity:
                raise ApiError(409, "INSUFFICIENT_STOCK", f"Không đủ tồn kho. Hiện có: {latest_stock}, yêu cầu xuất: {quantity}.") from error
            if importing and latest_stock + quantity > 9007199254740991:
                raise ApiError(409, "QUANTITY_LIMIT", "Số lượng tồn kho vượt giới hạn hỗ trợ.") from error
            raise ApiError(409, "TRANSACTION_CONFLICT", "Giao dịch bị xung đột; có thể thử lại với cùng Idempotency-Key.") from error
    raise ApiError(404, "ROUTE_NOT_FOUND", "Không tìm thấy endpoint.")
