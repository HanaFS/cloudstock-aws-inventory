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

    low_items = [p for p in products if int(p["stockQuantity"]) <= int(p["minThreshold"])]
    low_items.sort(key=lambda p: (int(p["stockQuantity"]), p.get("name", "")))

    by_cat = defaultdict(lambda: {"productCount": 0, "stockQuantity": 0, "stockValue": 0})
    for p in products:
        c = by_cat[p.get("category") or "Khác"]
        c["productCount"] += 1
        c["stockQuantity"] += int(p["stockQuantity"])
        c["stockValue"] += p["price"] * int(p["stockQuantity"])

    today = datetime.now(VN_TZ).date()
    days = [today - timedelta(days=i) for i in range(6, -1, -1)]
    daily = {d: {"date": d.isoformat(), "import": 0, "export": 0} for d in days}
    today_import = today_export = 0
    for t in transactions:
        try:
            d = _vn_date(t["createdAt"])
        except (KeyError, ValueError):
            continue
        key = "import" if t.get("type") == "IMPORT" else "export"
        if d in daily:
            daily[d][key] += int(t["quantity"])
        if d == today:
            if key == "import":
                today_import += 1
            else:
                today_export += 1

    transactions.sort(key=lambda t: t.get("createdAt", ""), reverse=True)
    series = [daily[d] for d in days]
    return {
        "totalProducts": len(products),
        "totalSuppliers": suppliers_count,
        "totalStockValue": sum(p["price"] * int(p["stockQuantity"]) for p in products),
        "lowStockCount": len(low_items),
        "outOfStockCount": sum(1 for p in products if int(p["stockQuantity"]) <= 0),
        "todayImport": today_import,
        "todayExport": today_export,
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
    if parts != ["dashboard"]:
        raise ApiError(404, "Không tìm thấy đường dẫn")
    if method != "GET":
        raise ApiError(405, f"Không hỗ trợ {method} cho đường dẫn này")
    return build_response(200, _dashboard())


def lambda_handler(event, context):
    return run_handler(event, _route)
