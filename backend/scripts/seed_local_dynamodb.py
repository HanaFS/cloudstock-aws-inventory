# import os
# from datetime import datetime, timezone
# from urllib.parse import urlsplit
# import boto3


# def seed_data(env=None):
#     env = os.environ if env is None else env
#     endpoint = env.get("DYNAMODB_LOCAL_ENDPOINT", "http://127.0.0.1:8000")
#     stage = env.get("STAGE", "dev")
#     dynamodb = boto3.resource(
#         "dynamodb",
#         endpoint_url=endpoint,
#         region_name="us-east-1",
#         aws_access_key_id="local",
#         aws_secret_access_key="local",
#     )

#     suppliers_table = dynamodb.Table(f"cloudstock-{stage}-suppliers")
#     products_table = dynamodb.Table(f"cloudstock-{stage}-products")
#     transactions_table = dynamodb.Table(f"cloudstock-{stage}-transactions")

#     suppliers = [
#         {"supplierId": "sup-001", "name": "Công ty TNHH Phân Phối Công Nghệ FPT Synnex", "phone": "02873006688", "address": "Khu Công Nghệ Cao, TP. Thủ Đức, TP.HCM"},
#         {"supplierId": "sup-002", "name": "Công ty CP Thế Giới Số Digiworld", "phone": "02839290059", "address": "Số 195-197 Nguyễn Thái Bình, Quận 1, TP.HCM"},
#         {"supplierId": "sup-003", "name": "Công ty TNHH Tin Học Viễn Thông Viễn Sơn", "phone": "02838326085", "address": "Số 162 Bùi Thị Xuân, Quận 1, TP.HCM"},
#         {"supplierId": "sup-004", "name": "Công ty CP Tập Đoàn Thiên Long", "phone": "02837505555", "address": "KCN Tân Tạo, Bình Tân, TP.HCM"},
#         {"supplierId": "sup-005", "name": "Công ty TNHH Thiết Bị Văn Phòng Lê Bảo Minh", "phone": "02838330777", "address": "Số 184 Nam Kỳ Khởi Nghĩa, Quận 3, TP.HCM"},
#         {"supplierId": "sup-006", "name": "Công ty CP Bóng Đèn Phích Nước Rạng Đông", "phone": "02438584310", "address": "Số 87-89 Phố Hạ Đình, Thanh Xuân, Hà Nội"},
#     ]

#     products = [
#         {"productId": "prod-0001", "name": "Màn hình máy tính LG UltraGear 24 inch 2K IPS 165Hz", "category": "Máy tính & Laptop", "price": 4180000, "stockQuantity": 45, "quantity": 45, "minThreshold": 20, "status": "IN_STOCK", "supplierId": "sup-001"},
#         {"productId": "prod-0002", "name": "Máy in mã vạch tem nhãn nhiệt Epson HL-L2321D", "category": "Thiết bị văn phòng", "price": 4870000, "stockQuantity": 8, "quantity": 8, "minThreshold": 15, "status": "IN_STOCK", "supplierId": "sup-005"},
#         {"productId": "prod-0003", "name": "Bút bi gel Thiên Long 0.5mm xanh (Hộp 20 cây)", "category": "Văn phòng phẩm", "price": 120000, "stockQuantity": 1250, "quantity": 1250, "minThreshold": 200, "status": "IN_STOCK", "supplierId": "sup-004"},
#         {"productId": "prod-0004", "name": "Giấy in A4 Double A 70gsm (Ram 500 tờ)", "category": "Văn phòng phẩm", "price": 85000, "stockQuantity": 18, "quantity": 18, "minThreshold": 50, "status": "IN_STOCK", "supplierId": "sup-004"},
#         {"productId": "prod-0005", "name": "Bàn phím cơ không dây Logitech G Pro Wireless", "category": "Phụ kiện công nghệ", "price": 2150000, "stockQuantity": 14, "quantity": 14, "minThreshold": 10, "status": "IN_STOCK", "supplierId": "sup-002"},
#         {"productId": "prod-0006", "name": "Chuột quang văn phòng có dây Logitech B100 USB", "category": "Phụ kiện công nghệ", "price": 95000, "stockQuantity": 120, "quantity": 120, "minThreshold": 30, "status": "IN_STOCK", "supplierId": "sup-002"},
#         {"productId": "prod-0007", "name": "Router định tuyến doanh nghiệp Cisco RV340 Dual WAN Gigabit", "category": "Thiết bị mạng", "price": 6850000, "stockQuantity": 4, "quantity": 4, "minThreshold": 5, "status": "IN_STOCK", "supplierId": "sup-003"},
#         {"productId": "prod-0008", "name": "Ổ cứng thể rắn SSD Samsung 980 PRO 1TB PCIe NVMe M.2", "category": "Linh kiện PC", "price": 2490000, "stockQuantity": 35, "quantity": 35, "minThreshold": 15, "status": "IN_STOCK", "supplierId": "sup-001"},
#         {"productId": "prod-0009", "name": "Máy quét tài liệu để bàn Canon imageFORMULA DR-C225 II", "category": "Thiết bị văn phòng", "price": 8900000, "stockQuantity": 2, "quantity": 2, "minThreshold": 5, "status": "IN_STOCK", "supplierId": "sup-005"},
#         {"productId": "prod-0010", "name": "Switch mạng chia cổng TP-Link 24 Port Gigabit SG1024D", "category": "Thiết bị mạng", "price": 1650000, "stockQuantity": 28, "quantity": 28, "minThreshold": 10, "status": "IN_STOCK", "supplierId": "sup-003"},
#         {"productId": "prod-0011", "name": "Bộ lưu điện dự phòng UPS APC Back-UPS 650VA BX650LI-MS", "category": "Thiết bị điện & Chiếu sáng", "price": 1350000, "stockQuantity": 0, "quantity": 0, "minThreshold": 8, "status": "OUT_OF_STOCK", "supplierId": "sup-001"},
#         {"productId": "prod-0012", "name": "Camera IP thân trụ chống nước Hikvision 2MP hồng ngoại 30m", "category": "Thiết bị an ninh & Camera", "price": 950000, "stockQuantity": 60, "quantity": 60, "minThreshold": 20, "status": "IN_STOCK", "supplierId": "sup-003"},
#     ]

#     now = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")

#     for s in suppliers:
#         suppliers_table.put_item(Item=s)
#     print(f"✅ Đã nạp {len(suppliers)} nhà cung cấp vào DynamoDB Local.")

#     for p in products:
#         p["updatedAt"] = now
#         products_table.put_item(Item=p)
#     print(f"✅ Đã nạp {len(products)} sản phẩm vào DynamoDB Local.")

#     sample_txns = [
#         {
#             "transactionId": "txn-20261124-001",
#             "createdAt": now,
#             "performedBy": "thukho.nguyen",
#             "type": "IMPORT",
#             "productId": "prod-0008",
#             "productName": "Ổ cứng thể rắn SSD Samsung 980 PRO 1TB PCIe NVMe M.2",
#             "quantity": 20,
#             "amount": 20,
#             "supplierId": "sup-001",
#             "reason": "Nhập bổ sung linh kiện theo hợp đồng cung ứng số HD-FPT-Q4",
#             "invoiceUrl": "invoices/HD_FPT_SSD_20261124.pdf",
#             "invoiceKey": "invoices/HD_FPT_SSD_20261124.pdf",
#             "gsi1pk": "TRANSACTION",
#             "gsi1sk": f"{now}#txn-20261124-001",
#         },
#         {
#             "transactionId": "txn-20261124-002",
#             "createdAt": now,
#             "performedBy": "staff.tran",
#             "type": "EXPORT",
#             "productId": "prod-0003",
#             "productName": "Bút bi gel Thiên Long 0.5mm xanh (Hộp 20 cây)",
#             "quantity": 150,
#             "amount": 150,
#             "reason": "Xuất bán khách hàng - Đơn hàng bán sỉ doanh nghiệp #DH-9821",
#             "gsi1pk": "TRANSACTION",
#             "gsi1sk": f"{now}#txn-20261124-002",
#         },
#     ]

#     for t in sample_txns:
#         transactions_table.put_item(Item=t)
#     print(f"✅ Đã nạp {len(sample_txns)} phiếu giao dịch mẫu vào DynamoDB Local.")


# if __name__ == "__main__":
#     seed_data()
