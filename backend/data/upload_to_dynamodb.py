import json
import boto3
import time
from decimal import Decimal
from datetime import datetime, timezone

REGION = 'ap-southeast-1'

TABLE_PRODUCTS     = 'Products'
TABLE_SUPPLIERS    = 'Suppliers'
TABLE_TRANSACTIONS = 'Transactions'

FILE_PRODUCTS     = 'products.py'   
FILE_SUPPLIERS    = 'suppliers.py'
FILE_TRANSACTIONS = 'reports.py'

# ==========================================


def to_decimal(val):
    if isinstance(val, float):
        return Decimal(str(val))
    if isinstance(val, int):
        return Decimal(val)
    return val


def fix_product(item):
    return {
        'productId':      item.get('productId', ''),
        'name':           item.get('name', ''),
        'category':       item.get('category', ''),
        'price':          to_decimal(item.get('price', 0)),
        'stockQuantity':  to_decimal(item.get('stockQuantity', item.get('quantity', 0))),
        'minThreshold':   to_decimal(item.get('minThreshold', 0)),
        'status':         item.get('status', 'IN_STOCK'),       # IN_STOCK / OUT_OF_STOCK ✓
        'imageUrl':       item.get('imageUrl', ''),
        'updatedAt':      item.get('updatedAt', datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')),
    }


def fix_supplier(item):
    supplier_id = item.get('supplierId', '')
    if supplier_id.startswith('sup-'):
        supplier_id = 'SUP-' + supplier_id[4:]

    return {
        'supplierId': supplier_id,
        'name':       item.get('name', ''),
        'phone':      item.get('phone', ''),
        'address':    item.get('address', ''),
    }


def fix_transaction(item):

    raw_type = item.get('type', 'IN')
    tx_type = 'IMPORT' if raw_type == 'IN' else 'EXPORT'

    created_at = item.get('createdAt') or item.get('timestamp', '')

    quantity = to_decimal(item.get('quantity') or item.get('amount', 0))

    result = {
        'transactionId': item.get('transactionId', ''),
        'createdAt':     created_at,
        'type':          tx_type,
        'productId':     item.get('productId', ''),
        'productName':   item.get('productName', ''),
        'quantity':      quantity,
        'performedBy':   item.get('performedBy', 'local-admin'),
    }

    # Trường tùy loại
    if tx_type == 'IMPORT':
        result['supplierId'] = item.get('supplierId')
        result['invoiceUrl'] = item.get('invoiceKey') or item.get('invoiceUrl')
    else:  # EXPORT
        result['reason'] = item.get('reason', '')

    # Bỏ các field None để DynamoDB không lỗi
    return {k: v for k, v in result.items() if v is not None}


def batch_upload(table, items, label):
    """Upload items lên DynamoDB dùng batch_writer (tối đa 25 item/lần)"""
    total = len(items)
    success = 0
    errors = 0

    print(f"\n Đang upload {total} {label}...")

    with table.batch_writer() as batch:
        for i, item in enumerate(items):
            try:
                batch.put_item(Item=item)
                success += 1
                if (i + 1) % 100 == 0:
                    print(f"    {i + 1}/{total} xong...")
            except Exception as e:
                errors += 1
                print(f"    Lỗi item {i}: {e}")

    print(f"    Hoàn tất {label}: {success} thành công, {errors} lỗi")
    return success, errors


def main():
    print("=" * 55)
    print("  CloudStock - Upload Data lên DynamoDB AWS")
    print("=" * 55)

    # Kết nối DynamoDB
    dynamodb = boto3.resource('dynamodb', region_name=REGION)

    # ---- BẢNG SUPPLIERS ----
    print(f"\n Đọc file {FILE_SUPPLIERS}...")
    with open(FILE_SUPPLIERS, 'r', encoding='utf-8') as f:
        raw = json.load(f)
    suppliers_raw = raw.get('suppliers', raw) if isinstance(raw, dict) else raw
    suppliers = [fix_supplier(s) for s in suppliers_raw]
    table_sup = dynamodb.Table(TABLE_SUPPLIERS)
    batch_upload(table_sup, suppliers, 'Suppliers')

    # ---- BẢNG PRODUCTS ----
    print(f"\n Đọc file {FILE_PRODUCTS}...")
    with open(FILE_PRODUCTS, 'r', encoding='utf-8') as f:
        raw = json.load(f)
    products_raw = raw.get('products', raw) if isinstance(raw, dict) else raw
    products = [fix_product(p) for p in products_raw]
    table_prod = dynamodb.Table(TABLE_PRODUCTS)
    batch_upload(table_prod, products, 'Products')

    # ---- BẢNG TRANSACTIONS ----
    print(f"\n Đọc file {FILE_TRANSACTIONS}...")
    with open(FILE_TRANSACTIONS, 'r', encoding='utf-8') as f:
        raw = json.load(f)
    tx_raw = (raw.get('transactions') or raw.get('reports') or raw) if isinstance(raw, dict) else raw
    transactions = [fix_transaction(t) for t in tx_raw]
    table_tx = dynamodb.Table(TABLE_TRANSACTIONS)
    batch_upload(table_tx, transactions, 'Transactions')

    print("\n" + "=" * 55)
    print("   Upload hoàn tất! Vào AWS Console kiểm tra nhé.")
    print("=" * 55)


if __name__ == '__main__':
    main()