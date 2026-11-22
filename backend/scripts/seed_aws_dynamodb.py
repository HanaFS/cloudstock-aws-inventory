import json
from decimal import Decimal
import boto3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
PRODUCTS_AND_SUPPLIERS_FILE = BASE_DIR / "data" / "products.py"
REPORTS_FILE = BASE_DIR / "data" / "reports.py"                  

REGION = "ap-southeast-1"
PRODUCTS_TABLE = "cloudstock-dev-products"
SUPPLIERS_TABLE = "cloudstock-dev-suppliers"
TRANSACTIONS_TABLE = "cloudstock-dev-transactions"


def seed_all():
    dynamodb = boto3.resource("dynamodb", region_name=REGION)
    suppliers_table = dynamodb.Table(SUPPLIERS_TABLE)
    products_table = dynamodb.Table(PRODUCTS_TABLE)
    transactions_table = dynamodb.Table(TRANSACTIONS_TABLE)

    # 1. Đọc & nạp Suppliers + Products
    with open(PRODUCTS_AND_SUPPLIERS_FILE, "r", encoding="utf-8") as f:
        catalog_data = json.load(f, parse_float=Decimal)

    suppliers = catalog_data.get("suppliers", [])
    products = catalog_data.get("products", [])

    print(f"1/3. Đang nạp {len(suppliers)} nhà cung cấp vào {SUPPLIERS_TABLE}...")
    with suppliers_table.batch_writer() as batch:
        for sup in suppliers:
            batch.put_item(Item=sup)
    print("   -> Xong Suppliers!")

    print(f"2/3. Đang nạp {len(products)} sản phẩm vào {PRODUCTS_TABLE}...")
    with products_table.batch_writer() as batch:
        for idx, prod in enumerate(products, start=1):
            batch.put_item(Item=prod)
            if idx % 250 == 0:
                print(f"      Đã nạp {idx}/{len(products)} sản phẩm...")
    print("   -> Xong Products!")

    # 2. Đọc, chuẩn hóa khóa DynamoDB & nạp Transactions từ file reports
    with open(REPORTS_FILE, "r", encoding="utf-8") as f:
        raw_txns = json.load(f, parse_float=Decimal)

    print(f"3/3. Đang chuyển đổi & nạp {len(raw_txns)} giao dịch vào {TRANSACTIONS_TABLE}...")
    with transactions_table.batch_writer() as batch:
        for item in raw_txns:
            txn_id = item.get("transactionId") or item.get("transaction_id")
            created_at = item.get("createdAt") or item.get("timestamp")
            # Đảm bảo chuẩn ISO 8601 có hậu tố Z nếu chưa có
            if created_at and not created_at.endswith("Z"):
                created_at = f"{created_at}.000Z"

            formatted_txn = {
                "transactionId": txn_id,
                "createdAt": created_at,
                "gsi1pk": "TXN",
                "gsi1sk": f"{created_at}#{txn_id}",
                "type": item.get("type", "IMPORT"),
                "productId": item.get("productId") or item.get("product_id", ""),
                "productName": item.get("productName") or item.get("product_name", ""),
                "quantity": item.get("quantity", 0),
                "totalValue": item.get("totalValue") or item.get("total_value", 0),
                "status": item.get("status", "COMPLETED"),
                "createdBy": item.get("createdBy") or item.get("user", "admin"),
                "note": item.get("note", ""),
            }
            batch.put_item(Item=formatted_txn)
    print("   -> Xong Transactions! Toàn bộ dữ liệu đã lên AWS DynamoDB thành công.")


if __name__ == "__main__":
    seed_all()