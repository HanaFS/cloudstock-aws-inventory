"""Nạp dữ liệu mẫu (seed/) vào 3 bảng DynamoDB của backend: cloudstock-<stage>-products|suppliers|transactions.

Dùng được với:
  - DynamoDB Local (theo hướng dẫn backend/README.md):
        python load_to_dynamodb.py --endpoint-url http://127.0.0.1:8000 --dry-run
        python load_to_dynamodb.py --endpoint-url http://127.0.0.1:8000 --wipe
    (cần chạy trước:  cd backend && python -m scripts.init_local_dynamodb)
  - AWS thật (người có quyền AWS chạy, region/stage đúng với stack đã deploy):
        python load_to_dynamodb.py --stage dev --region ap-southeast-1 --dry-run
        python load_to_dynamodb.py --stage dev --region ap-southeast-1 --wipe

--dry-run : chỉ kiểm tra và in số bản ghi, KHÔNG ghi.
--wipe    : xóa HẾT dữ liệu hiện có trong 3 bảng trước khi nạp (hỏi xác nhận, trừ khi có --yes).
Không có --wipe thì ghi đè theo khóa (item cùng khóa bị thay, item khác giữ nguyên).
"""
import argparse
import sys
from pathlib import Path

from validate_data import load_dir, validate

HERE = Path(__file__).resolve().parent
KEYS = {"products": ["productId"], "suppliers": ["supplierId"], "transactions": ["transactionId"]}


def table_names(stage):
    return {k: f"cloudstock-{stage}-{k}" for k in KEYS}


def get_resource(region, endpoint_url=None):
    import boto3
    if endpoint_url:
        return boto3.resource("dynamodb", endpoint_url=endpoint_url, region_name=region,
                              aws_access_key_id="local", aws_secret_access_key="local")
    return boto3.resource("dynamodb", region_name=region)


def wipe_table(table, key_names):
    deleted, kwargs = 0, {"ProjectionExpression": ", ".join(f"#k{i}" for i in range(len(key_names))),
                          "ExpressionAttributeNames": {f"#k{i}": k for i, k in enumerate(key_names)}}
    while True:
        resp = table.scan(**kwargs)
        with table.batch_writer() as batch:
            for item in resp["Items"]:
                batch.delete_item(Key={k: item[k] for k in key_names})
                deleted += 1
        if "LastEvaluatedKey" not in resp:
            return deleted
        kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]


def load(seed_dir, stage="dev", region="ap-southeast-1", endpoint_url=None, wipe=False, dry_run=False):
    products, suppliers, transactions = load_dir(seed_dir)
    errors = validate(products, suppliers, transactions)
    if errors:
        raise ValueError("Dữ liệu không hợp lệ: " + "; ".join(errors[:5]))
    data = {"products": products, "suppliers": suppliers, "transactions": transactions}
    names = table_names(stage)
    stats = {}
    ddb = None if dry_run else get_resource(region, endpoint_url)
    for kind, items in data.items():
        stats[kind] = {"table": names[kind], "written": 0, "wiped": 0}
        if dry_run:
            stats[kind]["written"] = len(items)
            continue
        table = ddb.Table(names[kind])
        if wipe:
            stats[kind]["wiped"] = wipe_table(table, KEYS[kind])
        with table.batch_writer() as batch:
            for item in items:
                batch.put_item(Item=item)
                stats[kind]["written"] += 1
    return stats


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--seed-dir", default=str(HERE / "seed"))
    ap.add_argument("--stage", default="dev", help="Stage của stack SAM (tên bảng cloudstock-<stage>-...), mặc định dev")
    ap.add_argument("--region", default="ap-southeast-1")
    ap.add_argument("--endpoint-url", default=None, help="vd http://127.0.0.1:8000 để nạp vào DynamoDB Local")
    ap.add_argument("--wipe", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--yes", action="store_true", help="bỏ qua bước hỏi xác nhận khi --wipe")
    a = ap.parse_args()
    target = a.endpoint_url or f"AWS {a.region}"
    print(f"Đích: {target} | bảng: {', '.join(table_names(a.stage).values())}" + (" | DRY-RUN" if a.dry_run else ""))
    if a.wipe and not a.dry_run and not a.yes:
        if input("--wipe sẽ XÓA HẾT dữ liệu hiện có trong 3 bảng. Gõ 'yes' để tiếp tục: ").strip().lower() != "yes":
            sys.exit("Đã hủy.")
    stats = load(a.seed_dir, a.stage, a.region, a.endpoint_url, a.wipe, a.dry_run)
    for kind, s in stats.items():
        print(f"  {s['table']}: {'sẽ ghi' if a.dry_run else 'đã ghi'} {s['written']}" + (f", đã xóa {s['wiped']} bản ghi cũ" if s["wiped"] else ""))
    print("[DRY-RUN] chưa ghi gì." if a.dry_run else "[OK] Nạp xong.")


if __name__ == "__main__":
    main()
