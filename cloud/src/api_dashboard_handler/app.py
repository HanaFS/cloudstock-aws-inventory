"""api-dashboard-handler - Module 2: Thống kê tổng quan & dữ liệu vẽ biểu đồ.
Route: GET /dashboard   (Admin, Staff)

Định nghĩa các chỉ số:
  totalStockValue  = tổng (price x stockQuantity) của mọi sản phẩm
  lowStockCount    = số sản phẩm có stockQuantity <= minThreshold (gồm cả hết hàng, theo quy tắc của nhóm)
  outOfStockCount  = số sản phẩm có stockQuantity <= 0
  chartData.importTotal / exportTotal = tổng SỐ LƯỢNG nhập / xuất trong 7 ngày gần nhất
  chartData.last7Days  = [{date, import, export}] theo ngày giờ Việt Nam (UTC+7), dùng cho biểu đồ cột
  chartData.byCategory = [{category, productCount, stockQuantity, stockValue}] dùng cho biểu đồ tròn
  todayImport / todayExport = số PHIẾU nhập / xuất trong ngày hôm nay (giờ Việt Nam)
"""
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from common import *

VN_TZ = timezone(timedelta(hours=7))
RECENT_LIMIT = 10


def _vn_date(iso):
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(VN_TZ).date()


def _dashboard():
    products = scan_all(products_table)
    resp = suppliers_table.scan(Select="COUNT")
    suppliers_count = resp["Count"]
    while "LastEvaluatedKey" in resp:
        resp = suppliers_table.scan(Select="COUNT", ExclusiveStartKey=resp["LastEvaluatedKey"])
        suppliers_count += resp["Count"]
    transactions = scan_all(transactions_table)

    low_items = [p for p in products if int(p.get("stockQuantity", p.get("quantity", 0))) <= int(p.get("minThreshold", 0))]
    low_items.sort(key=lambda p: (int(p.get("stockQuantity", p.get("quantity", 0))), p.get("name", "")))

    by_cat = defaultdict(lambda: {"productCount": 0, "stockQuantity": 0, "stockValue": 0})
    for p in products:
        c = by_cat[p.get("category") or "Khác"]
        c["productCount"] += 1
        qty = int(p.get("stockQuantity", p.get("quantity", 0)))
        c["stockQuantity"] += qty
        c["stockValue"] += p.get("price", 0) * qty

    today = datetime.now(VN_TZ).date()
    days = [today - timedelta(days=i) for i in range(6, -1, -1)]
    daily = {d: {"date": d.isoformat(), "import": 0, "export": 0} for d in days}
    today_import_count = today_export_count = 0
    today_in_qty = today_out_qty = 0
    today_transactions_count = 0

    for t in transactions:
        try:
            d = _vn_date(t.get("createdAt") or t.get("timestamp"))
        except (KeyError, ValueError, TypeError):
            continue
        t_type = (t.get("type") or "").upper()
        key = "import" if t_type in ("IMPORT", "IN") else "export"
        qty = int(t.get("quantity") if "quantity" in t else t.get("amount", 0))

        if d in daily:
            daily[d][key] += qty
        if d == today:
            today_transactions_count += 1
            if key == "import":
                today_import_count += 1
                today_in_qty += qty
            else:
                today_export_count += 1
                today_out_qty += qty

    transactions.sort(key=lambda t: t.get("createdAt", "") or t.get("timestamp", ""), reverse=True)
    series = [daily[d] for d in days]
    total_quantity = sum(int(p.get("stockQuantity", p.get("quantity", 0))) for p in products)
    total_value = sum(p.get("price", 0) * int(p.get("stockQuantity", p.get("quantity", 0))) for p in products)

    return {
        # 8 trường Frontend api.js mong đợi:
        "totalProducts": len(products),
        "totalQuantity": total_quantity,
        "totalValue": total_value,
        "lowStockCount": len(low_items),
        "totalSuppliers": suppliers_count,
        "todayIn": today_in_qty,
        "todayOut": today_out_qty,
        "todayTransactions": today_transactions_count,

        # Các trường bổ sung phục vụ biểu đồ và UI:
        "totalStockValue": total_value,
        "outOfStockCount": sum(1 for p in products if int(p.get("stockQuantity", p.get("quantity", 0))) <= 0),
        "todayImport": today_import_count,
        "todayExport": today_export_count,
        "lowStockItems": low_items,
        "recentTransactions": transactions[:RECENT_LIMIT],
        "chartData": {
            "importTotal": sum(x["import"] for x in series),
            "exportTotal": sum(x["export"] for x in series),
            "last7Days": series,
            "byCategory": [{"category": k, **v} for k, v in sorted(by_cat.items())],
        },
    }


def _route(method, path, user, event):
    parts = path_segments(path)
    if parts and parts[-1] == "_ping":
        return run_ping("api-dashboard-handler", user, lambda: {
            "products": products_table.scan(Limit=1)["Count"] >= 0,
            "transactions": transactions_table.scan(Limit=1)["Count"] >= 0})
    if parts not in (["dashboard"], ["dashboard", "stats"]):
        raise ApiError(404, "Không tìm thấy đường dẫn")
    if method != "GET":
        raise ApiError(405, f"Không hỗ trợ {method} cho đường dẫn này")
    return build_response(200, _dashboard())


def lambda_handler(event, context):
    return run_handler(event, _route)
