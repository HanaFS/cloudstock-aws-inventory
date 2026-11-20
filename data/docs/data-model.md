# Mô hình dữ liệu – CloudStock (phần Data)

Bám đúng code backend trong repo (`backend/src/*`, `backend/template.yaml`). Khi backend đổi schema thì sửa `generate_seed.py` và `validate_data.py` theo.

## 1. Ba bảng DynamoDB

Tên bảng: `cloudstock-<stage>-products | suppliers | transactions` (stage mặc định `dev`).

### Products (khóa: `productId`)
| Trường | Kiểu | Ghi chú |
|---|---|---|
| productId | S | Khóa chính, dạng `PRD-001` (chỉ chữ, số, `_`, `-`, tối đa 64) |
| name | S | Bắt buộc, tối đa 200 ký tự |
| category | S | Bắt buộc, tối đa 100 ký tự |
| price | N | Số nguyên không âm (VND) |
| quantity | N | Tồn kho, số nguyên không âm; backend cập nhật khi có giao dịch |
| minThreshold | N | Ngưỡng cảnh báo; sắp hết khi `quantity < minThreshold` |
| supplierId | S/null | Nhà cung cấp chính, phải tồn tại trong Suppliers |
| imageKey | S/null | Khóa file ảnh trên S3 (dữ liệu mẫu để null) |
| updatedAt | S | ISO 8601 UTC có mili giây, ví dụ `2026-11-20T08:00:00.000Z` |

Không có trường `status`: trạng thái còn hàng/hết hàng được suy ra từ `quantity`.

### Suppliers (khóa: `supplierId`)
`supplierId`, `name` (bắt buộc), `phone`, `address` (tùy chọn).

### Transactions (khóa: `transactionId`; GSI `ByTimestamp`: `gsi1pk` + `gsi1sk`)
| Trường | Kiểu | Ghi chú |
|---|---|---|
| transactionId | S | Khóa chính, dạng `txn-` + 32 ký tự hex |
| timestamp | S | ISO 8601 UTC có mili giây |
| performedBy | S | Username Cognito của người thực hiện |
| type | S | `IN` (nhập) hoặc `OUT` (xuất) |
| productId, productName | S | Mã và tên sản phẩm tại thời điểm giao dịch |
| amount | N | Số lượng, số nguyên dương |
| supplierId | S/null | Chỉ với `IN`; `OUT` bắt buộc null |
| reason | S | Bắt buộc cho cả IN và OUT, tối đa 500 ký tự |
| invoiceKey | S/null | Khóa file hóa đơn trên S3 (dữ liệu mẫu để null) |
| requestHash | S | Mã băm nội dung request (phục vụ Idempotency-Key của backend) |
| gsi1pk | S | Luôn là `TRANSACTION` |
| gsi1sk | S | `<timestamp>#<transactionId>`; backend đọc danh sách giao dịch qua GSI này |

## 2. So với file cấu trúc của bạn Cloud
File cấu trúc đặt tên khác code backend thật. Dữ liệu mẫu theo **code backend**:

| File cấu trúc (Cloud) | Code backend (dùng) |
|---|---|
| `stockQuantity` | `quantity` |
| `status` (IN_STOCK / OUT_OF_STOCK) | Không lưu |
| `createdAt` | `timestamp` |
| `type`: IMPORT / EXPORT | `IN` / `OUT` |
| `quantity` (giao dịch) | `amount` |
| `invoiceUrl` | `invoiceKey` |
| Khóa Transactions: `transactionId` + `createdAt` | Chỉ `transactionId`, thêm GSI `ByTimestamp` |
| Tên bảng `Products`, `Suppliers`, `Transactions` | `cloudstock-<stage>-products/suppliers/transactions` |
| Biến môi trường `TABLE_PRODUCTS`... | `PRODUCTS_TABLE`, `SUPPLIERS_TABLE`, `TRANSACTIONS_TABLE` |
| Sắp hết: `<=` minThreshold | `<` minThreshold (giống frontend và backend) |

## 3. Quy tắc toàn vẹn (kiểm tra bằng `validate_data.py`)
- `quantity` = tổng `IN` − tổng `OUT` của sản phẩm; không bao giờ âm.
- `IN` có thể có `supplierId`; `OUT` không được có.
- `reason` bắt buộc; `amount` là số nguyên dương; `productId`/`supplierId` phải tồn tại.
- `gsi1pk`/`gsi1sk` đúng quy tắc để GSI `ByTimestamp` hoạt động.

## 4. Dữ liệu mẫu
- 24 sản phẩm (5 danh mục), 6 nhà cung cấp, 281 giao dịch trong 60 ngày kết thúc ở ngày sinh dữ liệu.
- Có sản phẩm sắp hết và hết hàng để demo cảnh báo.
- `performedBy` dùng `admin.nguyen`, `staff.tran`, `staff.le` (trùng tài khoản demo của frontend).
- Chạy lại `python generate_seed.py --end-date YYYY-MM-DD` để dời khoảng thời gian cho dashboard "7 ngày qua" có số liệu.

Ví dụ bản ghi giao dịch nhập và xuất:
```json
{
  "transactionId": "txn-b2ad7c2c5a3b555424d86e2e797326f8",
  "timestamp": "2026-10-23T09:30:00.000Z",
  "performedBy": "staff.tran",
  "type": "IN",
  "productId": "PRD-022",
  "amount": 44,
  "supplierId": "SUP-003",
  "reason": "Nhập bổ sung hàng sắp hết",
  "invoiceKey": null,
  "gsi1pk": "TRANSACTION",
  "gsi1sk": "2026-10-23T09:30:00.000Z#txn-b2ad7c2c5a3b555424d86e2e797326f8"
}
```
```json
{
  "transactionId": "txn-4ba7ee12e103f78cef93cd169a47ac0e",
  "timestamp": "2026-09-22T10:10:00.000Z",
  "performedBy": "admin.nguyen",
  "type": "OUT",
  "productId": "PRD-011",
  "amount": 5,
  "supplierId": null,
  "reason": "Xuất cho dự án doanh nghiệp #DH-490",
  "invoiceKey": null
}
```

## 5. Dashboard
Frontend tự tính số liệu từ 3 API (`frontend/js/dashboard.js`). `dashboard_stats.py` là bản tham chiếu cùng định nghĩa, dùng để đối chiếu và làm báo cáo: tổng mặt hàng, tổng giá trị kho, số phiếu nhập/xuất hôm nay, số mặt hàng sắp hết, nhập/xuất 7 ngày qua, tỷ trọng theo danh mục, danh sách cảnh báo.
