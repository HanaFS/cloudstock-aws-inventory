from datetime import datetime, timezone

from ..common.dynamodb import dynamodb, scan_all, table_name
from ..common.http import ApiError, require_any_group, success, with_error_handling


def _table(env_name):
    return dynamodb.Table(table_name(env_name))


@with_error_handling
def handler(event, context=None):
    require_any_group(event, ["Admin", "Staff"])
    if event.get("httpMethod") != "GET" or event.get("path") not in ("/dashboard", "/dashboard/stats"):
        raise ApiError(404, "ROUTE_NOT_FOUND", "Không tìm thấy endpoint.")

    products = scan_all(_table("TABLE_PRODUCTS"))
    suppliers = scan_all(_table("TABLE_SUPPLIERS"))
    transactions = scan_all(_table("TABLE_TRANSACTIONS"))
    today = datetime.now(timezone.utc).date().isoformat()
    today_transactions = [
        transaction
        for transaction in transactions
        if isinstance(transaction.get("createdAt"), str)
        and transaction["createdAt"][:10] == today
    ]

    stats = {
        "totalProducts": len(products),
        "totalQuantity": sum(item.get("stockQuantity", 0) for item in products),
        "totalValue": sum(item.get("stockQuantity", 0) * item.get("price", 0) for item in products),
        "lowStockCount": sum(
            1
            for item in products
            if item.get("stockQuantity", 0) < item.get("minThreshold", 0)
        ),
        "totalSuppliers": len(suppliers),
        "todayIn": sum(
            item.get("quantity", 0)
            for item in today_transactions
            if item.get("type") == "IMPORT"
        ),
        "todayOut": sum(
            item.get("quantity", 0)
            for item in today_transactions
            if item.get("type") == "EXPORT"
        ),
        "todayTransactions": len(today_transactions),
    }
    return success(stats)
