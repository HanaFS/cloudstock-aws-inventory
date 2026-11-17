"""api-transactions-handler - Module 4 & 5: Nhập/Xuất kho, lịch sử, log CloudWatch.
Route: /transactions, /transactions/{proxy+}

TODO (backend) theo tài liệu nhóm:
  GET  /transactions                (Admin, Staff)  ?type=&productId=  sắp xếp createdAt giảm dần
  POST /transactions                (Admin, Staff)
       IMPORT: {type, productId, quantity, supplierId, invoiceUrl}
       EXPORT: {type, productId, quantity, reason}
       Khuyến nghị: dùng dynamodb client.transact_write_items để vừa cập nhật tồn kho
       (UpdateExpression + ConditionExpression "stockQuantity >= :q" khi EXPORT) vừa ghi
       Transactions trong 1 giao dịch -> không bị âm kho khi 2 người xuất cùng lúc.
  GET  /transactions/invoice-url?key=invoices/xxx.pdf  -> {viewUrl} (presigned GET)
  GET  /transactions/logs           (Admin)  -> logs_client.filter_log_events trên LOG_GROUP_NAMES
Lưu ý: bảng Transactions có GSI "productId-createdAt-index" để query theo sản phẩm.
"""
from common import *


def lambda_handler(event, context):
    method, path = get_request_info(event)
    user = get_current_user(event)

    if path.endswith("/_ping"):
        def check():
            transactions_table.scan(Limit=1)
            result = {"dynamodb": "ok"}
            if LOG_GROUP_NAMES:
                logs_client.filter_log_events(logGroupName=LOG_GROUP_NAMES[0], limit=1)
                result["cloudwatchLogs"] = "ok"
            return result
        return run_ping("api-transactions-handler", user, check)

    return not_implemented("api-transactions-handler", method, path)
