"""Kiểm tra dữ liệu mẫu có đúng schema và quy tắc của backend (backend/src/*) không, và tồn kho có khớp lịch sử không.

    python validate_data.py              # kiểm tra thư mục seed/
    python validate_data.py --dir seed
Thoát mã 0 nếu hợp lệ, 1 nếu có lỗi.
"""
import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")                       # PRODUCT_ID_PATTERN / SUPPLIER_ID_PATTERN của backend
TXN_ID = re.compile(r"^txn-[0-9a-f]{32}$")
TS = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z$")
PRODUCT_FIELDS = {"productId", "name", "category", "price", "quantity", "minThreshold", "supplierId", "imageKey", "updatedAt"}
SUPPLIER_FIELDS = {"supplierId", "name", "phone", "address"}
TXN_FIELDS = {"transactionId", "timestamp", "performedBy", "type", "productId", "productName", "amount",
              "supplierId", "reason", "invoiceKey", "requestHash", "gsi1pk", "gsi1sk"}


def load_dir(directory):
    d = Path(directory)
    return [json.loads((d / f).read_text(encoding="utf-8")) for f in ("products.json", "suppliers.json", "transactions.json")]


def _int(v):
    return isinstance(v, int) and not isinstance(v, bool)


def validate(products, suppliers, transactions):
    errors = []
    err = errors.append

    for kind, items, key, fields in (("Products", products, "productId", PRODUCT_FIELDS),
                                     ("Suppliers", suppliers, "supplierId", SUPPLIER_FIELDS),
                                     ("Transactions", transactions, "transactionId", TXN_FIELDS)):
        ids = [i.get(key) for i in items]
        if len(ids) != len(set(ids)):
            err(f"{kind}: có {key} bị trùng")
        for i in items:
            if set(i) != fields:
                err(f"{kind} {i.get(key)}: sai tập trường (thừa {sorted(set(i) - fields)}, thiếu {sorted(fields - set(i))})")

    sup_ids = {s["supplierId"] for s in suppliers}
    for s in suppliers:
        if not ID.fullmatch(s["supplierId"]):
            err(f"{s['supplierId']}: supplierId không hợp lệ")
        if not s.get("name") or len(s["name"]) > 200:
            err(f"{s['supplierId']}: name bắt buộc, tối đa 200 ký tự")
        if len(s.get("phone") or "") > 40 or len(s.get("address") or "") > 500:
            err(f"{s['supplierId']}: phone/address quá dài")

    pmap = {p["productId"]: p for p in products}
    for p in products:
        pid = p["productId"]
        if not ID.fullmatch(pid):
            err(f"{pid}: productId không hợp lệ")
        if not p.get("name") or len(p["name"]) > 200:
            err(f"{pid}: name bắt buộc, tối đa 200 ký tự")
        if not p.get("category") or len(p["category"]) > 100:
            err(f"{pid}: category bắt buộc, tối đa 100 ký tự")
        for f in ("price", "quantity", "minThreshold"):
            if not _int(p[f]) or p[f] < 0:
                err(f"{pid}: {f} phải là số nguyên không âm")
        if p["supplierId"] is not None and p["supplierId"] not in sup_ids:
            err(f"{pid}: supplierId {p['supplierId']} không tồn tại")
        if p["imageKey"] is not None and not isinstance(p["imageKey"], str):
            err(f"{pid}: imageKey phải là chuỗi hoặc null")

    running = {pid: 0 for pid in pmap}
    for t in sorted(transactions, key=lambda x: x["gsi1sk"]):
        tid = t["transactionId"]
        if not TXN_ID.fullmatch(tid):
            err(f"{tid}: transactionId không đúng dạng txn-<32 hex>")
        if not TS.fullmatch(t["timestamp"]):
            err(f"{tid}: timestamp phải dạng ISO có mili giây và Z")
        if t["gsi1pk"] != "TRANSACTION" or t["gsi1sk"] != f"{t['timestamp']}#{tid}":
            err(f"{tid}: gsi1pk/gsi1sk không khớp quy tắc của GSI ByTimestamp")
        if t["type"] not in ("IN", "OUT"):
            err(f"{tid}: type phải là IN hoặc OUT")
        if not _int(t["amount"]) or t["amount"] <= 0:
            err(f"{tid}: amount phải là số nguyên dương")
        if not isinstance(t["reason"], str) or not t["reason"].strip() or len(t["reason"]) > 500:
            err(f"{tid}: reason bắt buộc, tối đa 500 ký tự")
        if t["type"] == "OUT" and t["supplierId"] is not None:
            err(f"{tid}: giao dịch OUT không được có supplierId")
        if t["type"] == "IN" and t["supplierId"] is not None and t["supplierId"] not in sup_ids:
            err(f"{tid}: supplierId không tồn tại")
        p = pmap.get(t["productId"])
        if p is None:
            err(f"{tid}: productId {t['productId']} không tồn tại")
            continue
        if t["productName"] != p["name"]:
            err(f"{tid}: productName không khớp Products")
        running[t["productId"]] += t["amount"] if t["type"] == "IN" else -t["amount"]
        if running[t["productId"]] < 0:
            err(f"{tid}: làm tồn kho {t['productId']} âm ({running[t['productId']]})")

    for pid, p in pmap.items():
        if p["quantity"] != running[pid]:
            err(f"{pid}: quantity={p['quantity']} nhưng IN - OUT = {running[pid]}")
    return errors


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--dir", default=str(HERE / "seed"))
    args = ap.parse_args()
    errors = validate(*load_dir(args.dir))
    if errors:
        print(f"[FAIL] {len(errors)} lỗi:")
        for e in errors[:50]:
            print("  -", e)
        sys.exit(1)
    print("[PASS] Dữ liệu hợp lệ: đúng schema backend, khóa duy nhất, khóa ngoại đúng, tồn kho khớp lịch sử IN/OUT, không âm kho.")


if __name__ == "__main__":
    main()
