"""Nạp dữ liệu mẫu (seed/*.json) vào 3 bảng DynamoDB của stack.

    python scripts/seed.py
    python scripts/seed.py --stack qlkho-nhom4 --region ap-southeast-1
"""
import argparse
import json
from decimal import Decimal
from pathlib import Path

import boto3

from _stack import DEFAULT_REGION, DEFAULT_STACK, get_outputs

SEED_DIR = Path(__file__).resolve().parent.parent / "seed"


def load(name):
    with open(SEED_DIR / name, encoding="utf-8") as f:
        return json.load(f, parse_float=Decimal)


def seed_table(table, items):
    with table.batch_writer() as batch:
        for item in items:
            batch.put_item(Item=item)
    return len(items)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("--stack", default=DEFAULT_STACK)
    parser.add_argument("--region", default=DEFAULT_REGION)
    args = parser.parse_args()

    outputs = get_outputs(args.stack, args.region)
    dynamodb = boto3.resource("dynamodb", region_name=args.region)
    plan = [
        ("ProductsTableName", "products.json"),
        ("SuppliersTableName", "suppliers.json"),
        ("TransactionsTableName", "transactions.json"),
    ]
    for output_key, filename in plan:
        name = outputs[output_key]
        count = seed_table(dynamodb.Table(name), load(filename))
        print(f"[OK] {name}: {count} bản ghi")


if __name__ == "__main__":
    main()
