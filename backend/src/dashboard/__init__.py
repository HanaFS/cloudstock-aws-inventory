import os
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

from ..common.dynamodb import dynamodb, scan_all
from ..common.http import ApiError, require_any_group, success, with_error_handling
from ..schema_compat import CompatibilityError, normalize_product, normalize_transaction


def _integer_fields(record, fields):
    compatible = dict(record)
    for field in fields:
        value = compatible.get(field)
        if isinstance(value, Decimal) and value.is_finite() and value == value.to_integral_value():
            compatible[field] = int(value)
    return compatible


def _as_decimal(value, field, nonnegative=True):
    if isinstance(value, bool):
        raise ApiError(409, "INVALID_DASHBOARD_DATA", f"Invalid {field} in dashboard data.")
    try:
        number = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as error:
        raise ApiError(409, "INVALID_DASHBOARD_DATA", f"Invalid {field} in dashboard data.") from error
    if not number.is_finite() or (nonnegative and number < 0):
        raise ApiError(409, "INVALID_DASHBOARD_DATA", f"Invalid {field} in dashboard data.")
    return number


def _json_number(value):
    return int(value) if value == value.to_integral_value() else float(value)


def _utc_date(timestamp):
    try:
        parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except (AttributeError, TypeError, ValueError) as error:
        raise ApiError(409, "INVALID_DASHBOARD_DATA", "A transaction has an invalid timestamp.") from error
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).date()


def _dashboard_stats(today=None):
    products = scan_all(dynamodb.Table(os.environ["PRODUCTS_TABLE"]))
    transactions = scan_all(dynamodb.Table(os.environ["TRANSACTIONS_TABLE"]))
    today = today or datetime.now(timezone.utc).date()

    total_quantity = 0
    low_stock_count = 0
    out_of_stock_count = 0
    total_value = Decimal(0)
    for product in products:
        try:
            normalized = normalize_product(_integer_fields(product, ("quantity", "stockQuantity")))
        except CompatibilityError as error:
            raise ApiError(409, "INVALID_DASHBOARD_DATA", "A product has missing, invalid, or conflicting stock fields.") from error
        quantity = normalized["stockQuantity"]
        threshold = _as_decimal(product.get("minThreshold"), "minThreshold")
        price = _as_decimal(product.get("price"), "price")
        total_quantity += quantity
        low_stock_count += quantity <= threshold
        out_of_stock_count += quantity == 0
        total_value += price * quantity

    today_in = 0
    today_out = 0
    today_transactions = 0
    for transaction in transactions:
        if transaction.get("recordType") == "UPLOAD_RESERVATION":
            continue
        try:
            normalized = normalize_transaction(_integer_fields(transaction, ("amount", "quantity")))
        except CompatibilityError as error:
            raise ApiError(409, "INVALID_DASHBOARD_DATA", "A transaction has missing, invalid, or conflicting fields.") from error
        if _utc_date(normalized["createdAt"]) != today:
            continue
        today_transactions += 1
        if normalized["canonicalType"] == "IMPORT":
            today_in += normalized["quantity"]
        elif normalized["canonicalType"] == "EXPORT":
            today_out += normalized["quantity"]

    return {
        "totalProducts": len(products),
        "totalQuantity": total_quantity,
        "totalValue": _json_number(total_value),
        "lowStockCount": low_stock_count,
        "outOfStockCount": out_of_stock_count,
        "todayIn": today_in,
        "todayOut": today_out,
        "todayTransactions": today_transactions,
    }


@with_error_handling
def handler(event, context=None):
    require_any_group(event, ["Admin", "Staff"])
    route = event.get("resource") or event.get("path")
    if event.get("httpMethod") != "GET" or route not in ("/dashboard", "/dashboard/stats"):
        raise ApiError(404, "ROUTE_NOT_FOUND", "Dashboard endpoint not found.")
    return success(_dashboard_stats())
