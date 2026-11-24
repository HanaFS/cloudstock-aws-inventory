"""Sinh dữ liệu mẫu cho CloudStock theo ĐÚNG schema backend trong repo (backend/src/*, template.yaml).

Mô phỏng 60 ngày hoạt động của kho, kết thúc ở ngày --end-date (mặc định: hôm nay) để dashboard
"7 ngày qua / hôm nay" của frontend có số liệu:
  - Ngày đầu: nhập tồn đầu kỳ cho mọi sản phẩm (type IN).
  - Mỗi ngày: xuất bán ngẫu nhiên (type OUT, không bao giờ vượt tồn), sản phẩm sắp hết thì nhập bổ sung.
  - 14 ngày cuối: vài sản phẩm cạn dần để demo cảnh báo (quantity < minThreshold) và hết hàng.
Tồn kho tính từ lịch sử:  quantity = tổng IN - tổng OUT   (đối soát bằng validate_data.py)

Schema (khớp backend):
  Products     : productId, name, category, price, quantity, minThreshold, supplierId, imageKey, updatedAt
  Suppliers    : supplierId, name, phone, address
  Transactions : transactionId (txn-<32 hex>), timestamp, performedBy, type (IN|OUT), productId, productName,
                 amount, supplierId (chỉ IN), reason (bắt buộc), invoiceKey, requestHash,
                 gsi1pk ("TRANSACTION"), gsi1sk ("<timestamp>#<transactionId>")  -> cho GSI ByTimestamp

    python generate_seed.py
    python generate_seed.py --end-date 2026-11-20 --admin admin.nguyen --staff staff.tran,staff.le
"""
import hashlib
import json
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

SEED = 42
DAYS = 60
OUT_DIR = Path(__file__).resolve().parent / "seed"

SUPPLIERS = [
    ("SUP-001", "Công ty TNHH Phân Phối Công Nghệ Việt", "0901234567", "268 Lý Thường Kiệt, Quận 10, TP. Hồ Chí Minh"),
    ("SUP-002", "Công ty CP Thế Giới Số", "0909123456", "123 Nguyễn Thị Minh Khai, Quận 1, TP. Hồ Chí Minh"),
    ("SUP-003", "Công ty TNHH Linh Kiện Sài Gòn", "0283822113", "45 Nguyễn Thái Học, Quận 1, TP. Hồ Chí Minh"),
    ("SUP-004", "Công ty CP Máy Tính Miền Nam", "0938765432", "12 Trần Hưng Đạo, Thành phố Thủ Đức, TP. Hồ Chí Minh"),
    ("SUP-005", "Công ty TNHH Thiết Bị Mạng Việt Tín", "0912345098", "89 Cách Mạng Tháng Tám, Quận 3, TP. Hồ Chí Minh"),
    ("SUP-006", "Công ty TNHH Phụ Kiện Số Bình Minh", "0977654321", "34 Phan Văn Trị, Quận Bình Thạnh, TP. Hồ Chí Minh"),
]

# (tên, danh mục, đơn giá VND, ngưỡng tối thiểu, danh sách nhà cung cấp)
PRODUCTS = [
    ("Laptop Dell XPS 15 9530", "Laptop", 52900000, 3, ["SUP-002", "SUP-004"]),
    ("Laptop ASUS ZenBook 14 OLED", "Laptop", 24900000, 3, ["SUP-002", "SUP-004"]),
    ("Laptop Lenovo ThinkPad X1 Carbon Gen 11", "Laptop", 38900000, 2, ["SUP-002"]),
    ("Laptop Apple MacBook Air M2 13 inch", "Laptop", 26990000, 3, ["SUP-004"]),
    ("Laptop HP Pavilion 15", "Laptop", 15490000, 4, ["SUP-002", "SUP-004"]),
    ("Màn hình LG UltraGear 27GP850", "Màn hình", 8990000, 5, ["SUP-001", "SUP-004"]),
    ("Màn hình Dell U2723QE 27 inch 4K", "Màn hình", 13500000, 4, ["SUP-001"]),
    ("Màn hình Samsung Odyssey G5 27 inch", "Màn hình", 6490000, 5, ["SUP-001", "SUP-004"]),
    ("Màn hình ASUS ProArt PA278QV", "Màn hình", 7990000, 3, ["SUP-001"]),
    ("Bàn phím cơ không dây Keychron K8 Pro", "Phụ kiện", 2450000, 10, ["SUP-001", "SUP-006"]),
    ("Chuột Logitech MX Master 3S", "Phụ kiện", 2290000, 10, ["SUP-001", "SUP-006"]),
    ("Tai nghe Sony WH-1000XM5", "Phụ kiện", 7490000, 5, ["SUP-001"]),
    ("Webcam Logitech C920 HD Pro", "Phụ kiện", 1890000, 8, ["SUP-006"]),
    ("Chuột Razer DeathAdder V3", "Phụ kiện", 1590000, 10, ["SUP-006"]),
    ("Bàn phím Logitech MX Keys", "Phụ kiện", 2690000, 8, ["SUP-001", "SUP-006"]),
    ("Hub USB-C Anker 7 cổng", "Phụ kiện", 1190000, 12, ["SUP-006"]),
    ("SSD Samsung 990 PRO 1TB", "Linh kiện", 3290000, 15, ["SUP-003"]),
    ("RAM Kingston Fury 16GB DDR5", "Linh kiện", 1450000, 20, ["SUP-003"]),
    ("Card đồ họa GeForce RTX 4060 8GB", "Linh kiện", 8490000, 4, ["SUP-003"]),
    ("CPU Intel Core i5-13400F", "Linh kiện", 4590000, 6, ["SUP-003"]),
    ("Mainboard ASUS PRIME B760M", "Linh kiện", 3150000, 6, ["SUP-003"]),
    ("Nguồn Corsair RM750e 750W", "Linh kiện", 2790000, 6, ["SUP-003"]),
    ("Router TP-Link Archer AX55", "Thiết bị mạng", 1590000, 8, ["SUP-005"]),
    ("Switch Cisco CBS110 8 cổng", "Thiết bị mạng", 1290000, 6, ["SUP-005"]),
]

MAX_EXPORT_QTY = {"Laptop": 3, "Màn hình": 4, "Phụ kiện": 6, "Linh kiện": 8, "Thiết bị mạng": 5}
CATEGORY_WEIGHT = {"Laptop": 1.5, "Màn hình": 2, "Phụ kiện": 3, "Linh kiện": 3, "Thiết bị mạng": 1.5}
EXPORT_REASONS = ["Xuất bán khách lẻ", "Xuất bán đơn hàng đại lý", "Xuất bán đơn online",
                  "Xuất cho dự án doanh nghiệp", "Xuất bảo hành đổi mới"]
IMPORT_REASONS = ["Nhập hàng theo đơn đặt hàng", "Nhập bổ sung hàng sắp hết", "Nhập hàng từ nhà cung cấp"]
ADMIN_USER = "admin.nguyen"          # trùng username trong frontend/js/mock-data.js (Cognito username)
STAFF_USERS = ("staff.tran", "staff.le")


def _iso(dt):
    """Cùng định dạng backend ghi: UTC, mili giây, hậu tố Z."""
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"


def _txn_id(username, key):
    """Giống backend: txn- + sha256([username, idempotency-key]) rút gọn 32 ký tự."""
    return "txn-" + hashlib.sha256(json.dumps([username, key], separators=(",", ":")).encode()).hexdigest()[:32]


def _request_hash(tx):
    body = {k: tx[k] for k in ("type", "productId", "amount", "supplierId", "reason", "invoiceKey")}
    return hashlib.sha256(json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()


def build(end_date=None, admin_user=ADMIN_USER, staff_users=STAFF_USERS):
    END_DATE = end_date or datetime.now(timezone.utc).replace(tzinfo=None, hour=0, minute=0, second=0, microsecond=0)
    rng = random.Random(SEED)
    start = END_DATE - timedelta(days=DAYS - 1)

    products = []
    for i, (name, category, price, min_threshold, sups) in enumerate(PRODUCTS, start=1):
        products.append({"productId": f"PRD-{i:03d}", "name": name, "category": category, "price": price,
                         "stockQuantity": 0, "minThreshold": min_threshold,
                         "updatedAt": _iso(start), "_sups": sups})
    by_id = {p["productId"]: p for p in products}
    raw = []  # giao dịch chưa gán mã

    def add(dt, kind, p, qty, **extra):
        if kind == "IN":
            p["stockQuantity"] += qty
        else:
            p["stockQuantity"] -= qty
        raw.append({"dt": dt, "type": kind, "p": p, "qty": qty, **extra})

    def do_import(dt, p, qty, reason=None):
        add(dt, "IN", p, qty, supplierId=rng.choice(p["_sups"]),
            reason=reason or rng.choice(IMPORT_REASONS),
            performedBy=rng.choice([admin_user, admin_user, staff_users[0]]))

    def do_export(dt, p, qty, reason=None):
        add(dt, "OUT", p, qty,
            reason=reason or f"{rng.choice(EXPORT_REASONS)} #DH-{rng.randint(100, 999)}",
            performedBy=rng.choice([*staff_users, admin_user]))

    # 1. Tồn đầu kỳ
    for i, p in enumerate(products):
        qty = int(p["minThreshold"] * rng.uniform(4, 8)) + rng.randint(0, 5)
        do_import(start.replace(hour=7, minute=30 + i), p, qty, "Nhập tồn đầu kỳ")

    # 2. Chọn trước 6 sản phẩm sẽ "cạn dần" ở cuối kỳ: 2 hết hàng, 4 sắp hết (để demo cảnh báo)
    picks = rng.sample(products, 6)
    target = {p["productId"]: (0 if k < 2 else rng.randint(1, p["minThreshold"] - 1)) for k, p in enumerate(picks)}
    drain_days = 14

    # 3. Hoạt động hằng ngày
    weights = [CATEGORY_WEIGHT[p["category"]] for p in products]
    for d in range(DAYS):
        day = start + timedelta(days=d)
        draining = d >= DAYS - drain_days
        events = []
        for p in products:  # nhập bổ sung sớm trong ngày nếu sắp hết
            if draining and p["productId"] in target:
                continue  # nhóm đang cạn dần: không nhập bổ sung
            if p["stockQuantity"] <= p["minThreshold"] * 1.5 and rng.random() < 0.6:
                qty = int(p["minThreshold"] * rng.uniform(4, 7)) + rng.randint(0, 4)
                events.append((day.replace(hour=8) + timedelta(minutes=rng.randint(0, 90)), "IN", p, qty))
        n_exports = rng.randint(0, 2) if day.weekday() >= 5 else rng.randint(2, 6)
        for _ in range(n_exports):
            p = rng.choices(products, weights=weights)[0]
            events.append((day.replace(hour=9) + timedelta(minutes=rng.randint(0, 479)), "OUT", p,
                           rng.randint(1, MAX_EXPORT_QTY[p["category"]])))
        if draining:  # nhóm cạn dần: mỗi ngày bán thêm một phần đều đặn để tới mục tiêu vào ngày cuối
            days_left = DAYS - d
            for p in picks:
                planned = -(-(p["stockQuantity"] - target[p["productId"]]) // days_left)  # làm tròn lên
                cap = MAX_EXPORT_QTY[p["category"]] * 2
                while planned > 0:
                    q = min(planned, cap)
                    planned -= q
                    events.append((day.replace(hour=9) + timedelta(minutes=rng.randint(0, 479)), "OUT", p, q))
        for dt, kind, p, qty in sorted(events, key=lambda e: e[0]):
            if kind == "IN":
                do_import(dt, p, qty)
            else:
                floor = target.get(p["productId"], 0) if draining else 0
                qty = min(qty, p["stockQuantity"] - floor)  # không bao giờ xuất quá tồn
                if qty > 0:
                    do_export(dt, p, qty)

    # Chốt: nếu còn dư so với mục tiêu thì xuất nốt vào cuối ngày cuối
    t = END_DATE.replace(hour=17)
    for k, p in enumerate(picks):
        remove = p["stockQuantity"] - target[p["productId"]]
        if remove > 0:
            do_export(t + timedelta(minutes=10 * k), p, remove)

    # 4. Gán mã giao dịch theo schema backend, đổi tên trường
    raw.sort(key=lambda r: r["dt"])
    transactions = []
    for n, r in enumerate(raw, start=1):
        ts = _iso(r["dt"])
        tx = {
            "transactionId": _txn_id(r["performedBy"], f"seed-{n:04d}"),
            "timestamp": ts,
            "performedBy": r["performedBy"],
            "type": r["type"],
            "productId": r["p"]["productId"],
            "productName": r["p"]["name"],
            "amount": r["qty"],
            "supplierId": r.get("supplierId") if r["type"] == "IN" else None,
            "reason": r["reason"],
            "invoiceKey": None,  # chưa có file hóa đơn thật trên S3
        }
        tx["requestHash"] = _request_hash(tx)
        tx["gsi1pk"] = "TRANSACTION"
        tx["gsi1sk"] = f"{ts}#{tx['transactionId']}"
        transactions.append(tx)
        r["p"]["updatedAt"] = ts
    out_products = [{"productId": p["productId"], "name": p["name"], "category": p["category"], "price": p["price"],
                     "quantity": p["stockQuantity"], "minThreshold": p["minThreshold"], "supplierId": p["_sups"][0],
                     "imageKey": None, "updatedAt": p["updatedAt"]} for p in products]
    suppliers = [{"supplierId": s, "name": n, "phone": ph, "address": a} for s, n, ph, a in SUPPLIERS]
    return out_products, suppliers, transactions


def _dump(path, items):
    lines = ",\n".join("  " + json.dumps(it, ensure_ascii=False) for it in items)
    path.write_text("[\n" + lines + "\n]\n", encoding="utf-8")


def main():
    import argparse
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--end-date", default=None, help="ngày cuối của kỳ mô phỏng YYYY-MM-DD (mặc định: hôm nay, UTC)")
    ap.add_argument("--admin", default=ADMIN_USER, help="username Cognito ghi vào performedBy cho Admin")
    ap.add_argument("--staff", default=",".join(STAFF_USERS), help="các username Staff, cách nhau bằng dấu phẩy")
    args = ap.parse_args()
    end = datetime.strptime(args.end_date, "%Y-%m-%d") if args.end_date else None
    staff = tuple(u.strip() for u in args.staff.split(",") if u.strip())
    products, suppliers, transactions = build(end, args.admin, staff)
    OUT_DIR.mkdir(exist_ok=True)
    _dump(OUT_DIR / "products.json", products)
    _dump(OUT_DIR / "suppliers.json", suppliers)
    _dump(OUT_DIR / "transactions.json", transactions)
    low = sum(1 for p in products if p["quantity"] < p["minThreshold"])
    out = sum(1 for p in products if p["quantity"] == 0)
    print(f"[OK] {len(products)} sản phẩm | {len(suppliers)} nhà cung cấp | {len(transactions)} giao dịch")
    print(f"     sắp hết (quantity < minThreshold): {low} | trong đó hết hàng: {out} | ghi vào {OUT_DIR}")


if __name__ == "__main__":
    main()
