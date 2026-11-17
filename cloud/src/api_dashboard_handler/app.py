"""api-dashboard-handler - Module 2: Thống kê tổng quan & dữ liệu biểu đồ.
Route: GET /dashboard

TODO (backend): trả về JSON
  { totalProducts, totalSuppliers, totalStockValue, lowStockCount, outOfStockCount,
    lowStockItems[], recentTransactions[], chartData{importTotal, exportTotal, byCategory[]} }
Gợi ý: scan 3 bảng (dữ liệu nhỏ nên scan là đủ), low stock = stockQuantity <= minThreshold.
"""
from common import *


def _count(table):
    return table.scan(Select="COUNT")["Count"]


def lambda_handler(event, context):
    method, path = get_request_info(event)
    user = get_current_user(event)

    if path.endswith("/_ping"):
        return run_ping("api-dashboard-handler", user, lambda: {
            "products": _count(products_table),
            "suppliers": _count(suppliers_table),
            "transactions": _count(transactions_table),
        })

    return not_implemented("api-dashboard-handler", method, path)
