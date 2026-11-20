"""Tính số liệu Dashboard từ 3 bảng, theo đúng schema backend và đề bài (mục 2 file thiết kế). HÀM THUẦN, không gọi AWS.

Lưu ý: frontend hiện tự tính các số này từ 3 API (frontend/js/dashboard.js). File này là bản tham chiếu để
  (1) đối chiếu số liệu với giao diện, (2) dùng cho báo cáo offline (report_inventory.py),
  (3) Backend có thể gọi nếu sau này làm API GET /dashboard.

Định nghĩa (khớp frontend/js/dashboard.js):
  - Sắp hết  : quantity < minThreshold  (so sánh NHỎ HƠN; gồm cả hết hàng)
  - Hết hàng : quantity == 0
  - Giá trị kho = Σ quantity × price
  - "Hôm nay" và "7 ngày qua" tính theo ngày UTC của timestamp
"""
from datetime import datetime, timedelta, timezone


def _n(v):
    return int(v) if v is not None and v == int(v) else (float(v) if v is not None else 0)


def _day(ts):
    return str(ts)[:10]


def _bucket(items, in_cat="IN"):
    return {
        "importCount": sum(1 for t in items if t["type"] == "IN"),
        "exportCount": sum(1 for t in items if t["type"] == "OUT"),
        "importQuantity": sum(_n(t["amount"]) for t in items if t["type"] == "IN"),
        "exportQuantity": sum(_n(t["amount"]) for t in items if t["type"] == "OUT"),
    }


def compute_dashboard(products, suppliers, transactions, now=None, days=7, low_limit=10, recent=5):
    now = now or datetime.now(timezone.utc)
    today = now.strftime("%Y-%m-%d")

    low = [p for p in products if _n(p.get("quantity")) < _n(p.get("minThreshold"))]
    low.sort(key=lambda p: (_n(p["quantity"]) / _n(p["minThreshold"]) if _n(p["minThreshold"]) else 0, p["productId"]))

    cats = {}
    for p in products:
        c = cats.setdefault(p.get("category") or "Khác", {"category": p.get("category") or "Khác",
                                                            "productCount": 0, "quantity": 0, "stockValue": 0})
        c["productCount"] += 1
        c["quantity"] += _n(p.get("quantity"))
        c["stockValue"] += _n(p.get("quantity")) * _n(p.get("price"))

    keys = [(now - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(days - 1, -1, -1)]
    by_day = []
    for k in keys:
        b = _bucket([t for t in transactions if _day(t["timestamp"]) == k])
        by_day.append({"date": k, "in": b["importQuantity"], "out": b["exportQuantity"],
                       "importCount": b["importCount"], "exportCount": b["exportCount"]})

    latest = sorted(transactions, key=lambda t: t["gsi1sk"] if "gsi1sk" in t else t["timestamp"], reverse=True)[:recent]
    return {
        "totalProducts": len(products),
        "totalSuppliers": len(suppliers),
        "totalStockQuantity": sum(_n(p.get("quantity")) for p in products),
        "totalStockValue": sum(_n(p.get("quantity")) * _n(p.get("price")) for p in products),
        "lowStockCount": len(low),
        "outOfStockCount": sum(1 for p in products if _n(p.get("quantity")) == 0),
        "lowStockItems": [{"productId": p["productId"], "name": p["name"], "category": p.get("category"),
                           "quantity": _n(p["quantity"]), "minThreshold": _n(p["minThreshold"])} for p in low[:low_limit]],
        "today": {"date": today, **_bucket([t for t in transactions if _day(t["timestamp"]) == today])},
        "last7Days": by_day,
        "byCategory": sorted(cats.values(), key=lambda c: -c["stockValue"]),
        "recentTransactions": [{k: t.get(k) for k in ("transactionId", "timestamp", "type", "productId", "productName",
                                                       "amount", "performedBy")} for t in latest],
    }
