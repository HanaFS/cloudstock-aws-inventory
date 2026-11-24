"""Xuất báo cáo từ dữ liệu kho: tồn kho, nhập - xuất theo tháng, và JSON tham chiếu cho Dashboard.

    python report_inventory.py                          # từ seed/ (offline)
    python report_inventory.py --source dynamodb --stage dev [--endpoint-url http://127.0.0.1:8000]
    python report_inventory.py --as-of 2026-11-20       # chốt số liệu đến ngày

File CSV dùng UTF-8 có BOM nên mở bằng Excel không lỗi font tiếng Việt.
"""
import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path

from dashboard_stats import compute_dashboard
from load_to_dynamodb import get_resource, table_names
from validate_data import load_dir

HERE = Path(__file__).resolve().parent


def load_dynamodb(stage, region, endpoint_url):
    ddb = get_resource(region, endpoint_url)
    out = []
    for kind in ("products", "suppliers", "transactions"):
        table, items, kwargs = ddb.Table(table_names(stage)[kind]), [], {}
        while True:
            resp = table.scan(**kwargs)
            items += resp["Items"]
            if "LastEvaluatedKey" not in resp:
                break
            kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]
        out.append(items)
    return out


def write_csv(path, header, rows):
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def state_vi(p):
    q, m = int(p["quantity"]), int(p["minThreshold"])
    return "Hết hàng" if q == 0 else ("Sắp hết" if q < m else "Còn hàng")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--source", choices=["seed", "dynamodb"], default="seed")
    ap.add_argument("--seed-dir", default=str(HERE / "seed"))
    ap.add_argument("--stage", default="dev")
    ap.add_argument("--region", default="ap-southeast-1")
    ap.add_argument("--endpoint-url", default=None)
    ap.add_argument("--as-of", default=None, help="YYYY-MM-DD (mặc định: hôm nay UTC)")
    ap.add_argument("--out", default=str(HERE / "output"))
    a = ap.parse_args()

    products, suppliers, txns = load_dir(a.seed_dir) if a.source == "seed" else load_dynamodb(a.stage, a.region, a.endpoint_url)
    now = datetime.strptime(a.as_of + " 23:59:59", "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc) if a.as_of \
        else datetime.now(timezone.utc)
    out = Path(a.out)
    out.mkdir(exist_ok=True)

    rows = [[p["productId"], p["name"], p["category"], int(p["price"]), int(p["quantity"]), int(p["minThreshold"]),
             int(p["price"]) * int(p["quantity"]), state_vi(p)] for p in sorted(products, key=lambda x: (x["category"], x["name"]))]
    rows.append(["TỔNG", f"{len(products)} sản phẩm", "", "", sum(r[4] for r in rows), "", sum(r[6] for r in rows), ""])
    write_csv(out / "bao_cao_ton_kho.csv",
              ["Mã SP", "Tên sản phẩm", "Danh mục", "Đơn giá (VND)", "Tồn kho", "Ngưỡng tối thiểu", "Giá trị tồn (VND)", "Trạng thái"], rows)

    months = {}
    for t in txns:
        m = months.setdefault(str(t["timestamp"])[:7], {"inQ": 0, "outQ": 0, "inC": 0, "outC": 0})
        k = "in" if t["type"] == "IN" else "out"
        m[k + "Q"] += int(t["amount"])
        m[k + "C"] += 1
    write_csv(out / "bao_cao_nhap_xuat_theo_thang.csv", ["Tháng", "Số phiếu nhập", "SL nhập", "Số phiếu xuất", "SL xuất"],
              [[k, v["inC"], v["inQ"], v["outC"], v["outQ"]] for k, v in sorted(months.items())])

    dash = compute_dashboard(products, suppliers, txns, now=now)
    (out / "dashboard_sample.json").write_text(json.dumps(dash, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[OK] Đã ghi 3 file vào {out}")
    print(f"     {dash['totalProducts']} sản phẩm | tồn {dash['totalStockQuantity']} | sắp hết {dash['lowStockCount']} "
          f"(hết hàng {dash['outOfStockCount']}) | hôm nay: nhập {dash['today']['importCount']} phiếu, xuất {dash['today']['exportCount']} phiếu")


if __name__ == "__main__":
    main()
