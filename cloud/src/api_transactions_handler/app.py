"""api-transactions-handler - Module 4 & 5: Nhập/Xuất kho, lịch sử giao dịch, log CloudWatch.
Route: /transactions, /transactions/{proxy+}

  GET  /transactions                     Admin, Staff   ?type=IMPORT|EXPORT&productId=   (mới nhất lên đầu)
  GET  /transactions/{transactionId}     Admin, Staff
  POST /transactions                     Admin, Staff
       IMPORT: {type, productId, quantity, supplierId, invoiceUrl?}
       EXPORT: {type, productId, quantity, reason?}
  GET  /transactions/invoice-url?key=invoices/xxx.pdf   Admin, Staff  -> {viewUrl}
  GET  /transactions/logs?hours=24&limit=100&q=         Admin         -> [{timestamp, message, logStream, logGroup}]

Chống âm kho: cập nhật tồn kho + ghi giao dịch nằm trong MỘT transact_write_items, kèm điều kiện
"stockQuantity còn đúng giá trị vừa đọc". Nếu có người khác vừa đổi tồn kho thì đọc lại và thử lại.
"""
import time
import uuid
from datetime import datetime, timedelta, timezone

from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError
from common import *

TX_TYPES = ("IMPORT", "EXPORT")
MAX_RETRIES = 5
VIEW_URL_TTL = 300  # giây
# Client của resource đã tự chuyển kiểu Python <-> DynamoDB, nên truyền thẳng giá trị Python thường
# (KHÔNG dùng TypeSerializer ở đây, nếu không dữ liệu sẽ bị bọc kiểu 2 lần và ghi sai).
_ddb_client = dynamodb.meta.client


# --------------------------------------------------------------------- list
def _list_transactions(query):
    tx_type = query.get("type")
    product_id = query.get("productId")
    if tx_type and tx_type not in TX_TYPES:
        raise ApiError(400, "type chỉ nhận IMPORT hoặc EXPORT")

    if product_id:
        # Dùng GSI productId-createdAt-index: không phải quét cả bảng, và đã sắp xếp sẵn.
        kwargs = {"IndexName": "productId-createdAt-index",
                  "KeyConditionExpression": Key("productId").eq(product_id),
                  "ScanIndexForward": False}
        if tx_type:
            kwargs["FilterExpression"] = "#t = :t"
            kwargs["ExpressionAttributeNames"] = {"#t": "type"}
            kwargs["ExpressionAttributeValues"] = {":t": tx_type}
        items, resp = [], transactions_table.query(**kwargs)
        items.extend(resp["Items"])
        while "LastEvaluatedKey" in resp:
            resp = transactions_table.query(ExclusiveStartKey=resp["LastEvaluatedKey"], **kwargs)
            items.extend(resp["Items"])
    else:
        kwargs = {}
        if tx_type:
            kwargs = {"FilterExpression": "#t = :t", "ExpressionAttributeNames": {"#t": "type"},
                      "ExpressionAttributeValues": {":t": tx_type}}
        items = scan_all(transactions_table, **kwargs)
    items.sort(key=lambda i: i.get("createdAt", ""), reverse=True)
    return build_response(200, items)


def _get_transaction(transaction_id):
    resp = transactions_table.query(KeyConditionExpression=Key("transactionId").eq(transaction_id))
    if not resp["Items"]:
        raise ApiError(404, f"Không tìm thấy giao dịch {transaction_id}")
    return build_response(200, resp["Items"][0])


# ------------------------------------------------------------------- create
def _normalize_invoice_key(value):
    """Chấp nhận cả s3Key ('invoices/a.pdf') lẫn URL đầy đủ; luôn lưu s3Key."""
    value = clean_str(value, "invoiceUrl", required=False, max_len=1000)
    if not value:
        return None
    if value.startswith("http"):
        marker = "/invoices/"
        pos = value.find(marker)
        if pos == -1:
            raise ApiError(400, "invoiceUrl phải nằm trong thư mục invoices/")
        value = value[pos + 1:].split("?")[0]
    if not value.startswith("invoices/") or ".." in value:
        raise ApiError(400, "invoiceUrl phải bắt đầu bằng invoices/")
    return value


def _create_transaction(body, user):
    tx_type = clean_str(body.get("type"), "type")
    if tx_type not in TX_TYPES:
        raise ApiError(400, "type chỉ nhận IMPORT hoặc EXPORT")
    product_id = clean_str(body.get("productId"), "productId")
    quantity = to_int(body.get("quantity"), "quantity", minimum=1)

    supplier_id = invoice_key = reason = None
    if tx_type == "IMPORT":
        supplier_id = clean_str(body.get("supplierId"), "supplierId")
        if not suppliers_table.get_item(Key={"supplierId": supplier_id}).get("Item"):
            raise ApiError(400, f"Nhà cung cấp {supplier_id} không tồn tại")
        invoice_key = _normalize_invoice_key(body.get("invoiceUrl"))
    else:
        reason = clean_str(body.get("reason"), "reason", required=False, max_len=500) or "Xuất kho"

    for _ in range(MAX_RETRIES):
        product = products_table.get_item(Key={"productId": product_id}).get("Item")
        if not product:
            raise ApiError(404, f"Không tìm thấy sản phẩm {product_id}")
        old_stock = int(product["stockQuantity"])
        if tx_type == "EXPORT" and quantity > old_stock:
            raise ApiError(400, f"Không đủ tồn kho. Hiện có {old_stock}, yêu cầu xuất {quantity}")
        new_stock = old_stock + quantity if tx_type == "IMPORT" else old_stock - quantity
        now = get_iso_now()

        record = {
            "transactionId": f"TXN-{now[:10].replace('-', '')}-{uuid.uuid4().hex[:6].upper()}",
            "createdAt": now,
            "type": tx_type,
            "productId": product_id,
            "productName": product["name"],
            "quantity": quantity,
            "performedBy": user["email"],
            "supplierId": supplier_id,
            "invoiceUrl": invoice_key,
            "reason": reason,
        }
        try:
            _ddb_client.transact_write_items(TransactItems=[
                {"Update": {
                    "TableName": TABLE_PRODUCTS,
                    "Key": {"productId": product_id},
                    "UpdateExpression": "SET stockQuantity = :new, #s = :status, updatedAt = :now",
                    # chỉ ghi nếu tồn kho chưa bị ai đổi từ lúc đọc (new_stock đã được kiểm tra >= 0 ở trên)
                    "ConditionExpression": "stockQuantity = :old",
                    "ExpressionAttributeNames": {"#s": "status"},
                    "ExpressionAttributeValues": {
                        ":new": new_stock, ":old": old_stock,
                        ":status": "IN_STOCK" if new_stock > 0 else "OUT_OF_STOCK",
                        ":now": now},
                }},
                {"Put": {
                    "TableName": TABLE_TRANSACTIONS,
                    "Item": record,
                    "ConditionExpression": "attribute_not_exists(transactionId)",
                }},
            ])
        except ClientError as exc:
            if exc.response["Error"]["Code"] == "TransactionCanceledException":
                time.sleep(0.05)  # có người vừa đổi tồn kho -> đọc lại và thử lại
                continue
            raise
        return build_response(201, {**record, "message": "Created",
                                    "stockQuantity": new_stock,
                                    "status": "IN_STOCK" if new_stock > 0 else "OUT_OF_STOCK"})
    raise ApiError(409, "Kho đang được cập nhật bởi người khác, vui lòng thử lại")


# ---------------------------------------------------------------- invoice / logs
def _invoice_url(query):
    key = _normalize_invoice_key(query.get("key"))
    if not key:
        raise ApiError(400, "Thiếu tham số key (ví dụ ?key=invoices/xxx.pdf)")
    url = s3_client.generate_presigned_url(
        "get_object", Params={"Bucket": BUCKET_NAME, "Key": key}, ExpiresIn=VIEW_URL_TTL)
    return build_response(200, {"viewUrl": url, "s3Key": key, "expiresIn": VIEW_URL_TTL})


def _logs(query):
    hours = to_int(query.get("hours", 24), "hours", minimum=1)
    limit = min(to_int(query.get("limit", 100), "limit", minimum=1), 500)
    text = (query.get("q") or "").strip().lower()
    start_ms = int((datetime.now(timezone.utc) - timedelta(hours=min(hours, 168))).timestamp() * 1000)

    events = []
    for group in LOG_GROUP_NAMES:
        try:
            resp = logs_client.filter_log_events(logGroupName=group, startTime=start_ms, limit=limit)
        except ClientError as exc:
            logger.warning("Không đọc được log group %s: %s", group, exc)
            continue
        for e in resp.get("events", []):
            msg = e["message"].strip()
            if msg.startswith(("START RequestId", "END RequestId")):
                continue  # bỏ dòng nhiễu của Lambda
            if text and text not in msg.lower():
                continue
            events.append({
                "timestamp": datetime.fromtimestamp(e["timestamp"] / 1000, timezone.utc)
                                     .strftime("%Y-%m-%dT%H:%M:%SZ"),
                "message": msg,
                "logStream": e.get("logStreamName", ""),
                "logGroup": group,
                "_ts": e["timestamp"],
            })
    events.sort(key=lambda x: x["_ts"], reverse=True)
    for e in events:
        del e["_ts"]
    return build_response(200, events[:limit])


# ------------------------------------------------------------------- router
def _route(method, path, user, event):
    parts = path_segments(path)
    if not parts or parts[0] != "transactions":
        raise ApiError(404, "Không tìm thấy đường dẫn")
    sub = parts[1] if len(parts) > 1 else None

    if sub == "_ping":
        def check():
            transactions_table.scan(Limit=1)
            result = {"dynamodb": "ok"}
            if LOG_GROUP_NAMES:
                logs_client.filter_log_events(logGroupName=LOG_GROUP_NAMES[0], limit=1)
                result["cloudwatchLogs"] = "ok"
            return result
        return run_ping("api-transactions-handler", user, check)

    if sub == "logs":
        denied = require_role(user, "Admin")
        if denied:
            return denied
        if method != "GET":
            raise ApiError(405, f"Không hỗ trợ {method} cho đường dẫn này")
        return _logs(get_query(event))
    if sub == "invoice-url":
        if method != "GET":
            raise ApiError(405, f"Không hỗ trợ {method} cho đường dẫn này")
        return _invoice_url(get_query(event))

    if method == "GET":
        return _get_transaction(sub) if sub else _list_transactions(get_query(event))
    if method == "POST" and sub is None:
        return _create_transaction(body_or_400(event), user)
    raise ApiError(405, f"Không hỗ trợ {method} cho đường dẫn này")


def lambda_handler(event, context):
    return run_handler(event, _route)
