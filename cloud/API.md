# Đặc tả API – CloudStock

Base URL = giá trị `ApiBaseUrl` sau khi deploy (chạy `python scripts/print_config.py`). **Không có tiền tố `/prod`.**
Mọi request đều cần header `Authorization: Bearer <IdToken>` (IdToken của Cognito, **không phải** AccessToken) và `Content-Type: application/json` khi có body.

**Lỗi** luôn có dạng `{ "message": "..." }` với mã: `400` dữ liệu sai · `401` thiếu/sai token · `403` không đủ quyền · `404` không tìm thấy · `405` sai method · `409` xung đột · `500` lỗi hệ thống.
**Thành công**: trả thẳng JSON (không bọc `{success, data}`), tạo mới trả `201`.

## Đăng nhập (không qua API Gateway)
Frontend gọi thẳng Cognito (`InitiateAuth`, luồng `USER_PASSWORD_AUTH`) bằng `UserPoolId` / `ClientId` từ `print_config.py`, lấy `IdToken` rồi gắn vào header. Có thể thử bằng `python scripts/get_token.py --email ...`.
Role nằm trong claim `cognito:groups` của token (`Admin` hoặc `Staff`).

## Users – `api-users-handler`
| Method & đường dẫn | Quyền | Body / Query | Trả về |
|---|---|---|---|
| `GET /users/me` | Admin, Staff | – | `{email, role}` của người đang đăng nhập |
| `GET /users` | Admin | – | `[{id, username, email, role, status, enabled, createdAt}]` |
| `GET /users/{username}` | Admin | `{username}` là email hoặc id | 1 user như trên |
| `POST /users` | Admin | `{email, password, role: "Admin"\|"Staff"}` | `201 {message, email, role, username}` |
| `PUT /users/{username}/role` | Admin | `{role}` | `{message, username, role}` |
| `PUT /users/{username}/status` | Admin | `{enabled: true\|false}` (khóa / mở khóa) | `{message, username, enabled}` |
| `DELETE /users/{username}` | Admin | – | `{message, username}` |

Mật khẩu tối thiểu 8 ký tự, có chữ hoa, chữ thường, số. Email trùng → `409`. Admin không thể tự xóa / khóa / hạ quyền chính mình (`400`).

## Dashboard – `api-dashboard-handler`
`GET /dashboard` (Admin, Staff) →
```json
{
  "totalProducts": 12, "totalSuppliers": 4, "totalStockValue": 450000000,
  "lowStockCount": 4, "outOfStockCount": 1, "todayImport": 1, "todayExport": 2,
  "lowStockItems": [ /* sản phẩm có stockQuantity <= minThreshold, ít nhất lên đầu */ ],
  "recentTransactions": [ /* 10 giao dịch mới nhất */ ],
  "chartData": {
    "importTotal": 120, "exportTotal": 85,
    "last7Days": [ { "date": "2026-11-11", "import": 20, "export": 5 } ],
    "byCategory": [ { "category": "Laptop", "productCount": 3, "stockQuantity": 20, "stockValue": 900000000 } ]
  }
}
```
`importTotal` / `exportTotal` là tổng **số lượng** trong 7 ngày gần nhất; `todayImport` / `todayExport` là số **phiếu** trong ngày (theo giờ Việt Nam).

## Products & Suppliers – `api-products-handler`
| Method & đường dẫn | Quyền | Ghi chú |
|---|---|---|
| `GET /products` | Admin, Staff | Lọc: `?category=&status=IN_STOCK\|OUT_OF_STOCK&q=` (q tìm theo tên/mã). Trả mảng, mới cập nhật lên đầu |
| `GET /products/{id}` | Admin, Staff | `404` nếu không có |
| `POST /products` | Admin, Staff | Body `{name, category, price, stockQuantity, minThreshold, imageUrl?}`. Tự sinh `productId`, `status`, `updatedAt` |
| `PUT /products/{id}` | Admin, Staff | Chỉ cần gửi trường muốn đổi. Đổi `stockQuantity` thì `status` tự tính lại |
| `DELETE /products/{id}` | **Admin** | |
| `POST /products/upload-url` | Admin, Staff | Xem mục Upload bên dưới. Có thể gọi `GET /products/presigned-url?folder=&fileName=&contentType=` |
| `GET /suppliers`, `GET /suppliers/{id}` | Admin, Staff | |
| `POST /suppliers`, `PUT /suppliers/{id}` | Admin, Staff | Body `{name, phone, address}` |
| `DELETE /suppliers/{id}` | **Admin** | |

Product: `{productId, name, category, price, stockQuantity, minThreshold, status, imageUrl, updatedAt}` · Supplier: `{supplierId, name, phone, address}`.

### Upload file (2 bước)
1. `POST /products/upload-url` body `{folder: "products"|"invoices", fileName, contentType}` → `{uploadUrl, fileUrl, s3Key, expiresIn}`.
   `products` nhận `image/jpeg|png|webp`; `invoices` nhận `application/pdf`, `image/jpeg|png`.
2. Frontend `PUT <uploadUrl>` với **body là file** và header `Content-Type` **đúng bằng** `contentType` đã gửi ở bước 1 (sai là S3 từ chối). Link hết hạn sau 5 phút.
3. Ảnh sản phẩm: lưu `fileUrl` vào `imageUrl`. Hóa đơn: lưu `s3Key` vào `invoiceUrl` của giao dịch (hóa đơn là private, không mở trực tiếp bằng `fileUrl`).

## Transactions – `api-transactions-handler`
| Method & đường dẫn | Quyền | Ghi chú |
|---|---|---|
| `GET /transactions` | Admin, Staff | Lọc `?type=IMPORT\|EXPORT&productId=`. Mới nhất lên đầu |
| `GET /transactions/{transactionId}` | Admin, Staff | |
| `POST /transactions` | Admin, Staff | Xem bên dưới |
| `GET /transactions/invoice-url?key=invoices/xxx.pdf` | Admin, Staff | → `{viewUrl, s3Key, expiresIn}` (link xem hóa đơn, hết hạn sau 5 phút) |
| `GET /transactions/logs?hours=24&limit=100&q=` | **Admin** | → `[{timestamp, message, logStream, logGroup}]` đọc từ CloudWatch, mới nhất lên đầu |

**Nhập kho** `{type:"IMPORT", productId, quantity, supplierId, invoiceUrl?}` – `supplierId` bắt buộc và phải tồn tại.
**Xuất kho** `{type:"EXPORT", productId, quantity, reason?}` – nếu `quantity` lớn hơn tồn kho → `400 "Không đủ tồn kho..."`, không ghi gì.
`quantity` phải là số nguyên dương. `performedBy` luôn lấy từ token, client không gửi được.
Trả về `201` gồm đủ 10 trường của giao dịch + `message`, `stockQuantity` (tồn mới), `status` (của sản phẩm).
