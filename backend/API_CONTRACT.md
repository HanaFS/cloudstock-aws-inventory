# CloudStock API Contract (Draft v1)

Tài liệu này chốt giao diện giữa frontend hiện có và backend AWS dự kiến. Đây là đặc tả để triển khai, **không có nghĩa backend đã tồn tại**.

## 1. Quy ước chung

- Base URL production dự kiến: `https://{api-id}.execute-api.{region}.amazonaws.com/prod`.
- Request/response dùng JSON và UTF-8.
- API nghiệp vụ yêu cầu `Authorization: Bearer <Cognito access or ID token>`; API Gateway/Cognito authorizer xác minh token.
- Thành công trả về `{ "success": true, "data": ... }`. Danh sách trả `data` là mảng để tương thích các module frontend hiện tại.
- Lỗi trả về `{ "success": false, "message": "...", "code": "..." }`.
- Với danh sách lớn, backend có thể trả thêm `nextToken` ngoài `data`; frontend cần được cập nhật để đọc hết các trang trước khi dùng dữ liệu quy mô production.
- Backend tự tạo ID và timestamp nghiệp vụ; không tin các giá trị này hoặc `performedBy` do client gửi.

### Mã trạng thái HTTP

| HTTP | Ý nghĩa |
| --- | --- |
| `400` | Request sai định dạng hoặc vi phạm validation |
| `401` | Thiếu hoặc không hợp lệ token |
| `403` | Đã đăng nhập nhưng không đủ quyền |
| `404` | Không tìm thấy tài nguyên |
| `409` | Trùng mã hoặc không đủ tồn kho |
| `500` | Lỗi không dự kiến; trả thông báo chung, chi tiết ghi ở CloudWatch |

## 2. Mô hình dữ liệu

### Product

| Trường | Kiểu | Quy tắc |
| --- | --- | --- |
| `productId` | string | ID duy nhất, ví dụ `prod-013` |
| `name` | string | Bắt buộc |
| `category` | string | Bắt buộc |
| `quantity` | integer | Số nguyên không âm |
| `minThreshold` | integer | Số nguyên không âm |
| `price` | number | Không âm, đơn vị VND |
| `supplierId` | string hoặc null | Tham chiếu `Supplier.supplierId` |
| `imageKey` | string hoặc null | S3 object key; không lưu Base64 |
| `imageUrl` | string hoặc null | URL đọc tạm thời nếu backend cấp; không phải giá trị lưu bền |
| `updatedAt` | ISO 8601 string | Backend tạo/cập nhật |

### Supplier

| Trường | Kiểu | Quy tắc |
| --- | --- | --- |
| `supplierId` | string | ID duy nhất, ví dụ `sup-001` |
| `name` | string | Bắt buộc |
| `phone` | string | Tùy chọn |
| `address` | string | Tùy chọn |

### Transaction

| Trường | Kiểu | Quy tắc |
| --- | --- | --- |
| `transactionId` | string | ID do backend tạo |
| `timestamp` | ISO 8601 string | Thời điểm do backend tạo |
| `performedBy` | string | Danh tính lấy từ token; không tin giá trị client gửi |
| `type` | string | `IN` hoặc `OUT` |
| `productId` | string | Sản phẩm được giao dịch |
| `productName` | string | Tên sản phẩm tại thời điểm giao dịch |
| `amount` | integer | Số nguyên dương |
| `supplierId` | string hoặc null | Có thể có với `IN`; thường null với `OUT` |
| `reason` | string | Lý do nghiệp vụ |
| `invoiceKey` | string hoặc null | S3 object key; không lưu `s3://` giả hoặc Base64 |

Giao dịch là bản ghi lịch sử bất biến: API không cung cấp sửa/xóa giao dịch. Cập nhật tồn kho và ghi transaction phải được thực hiện nguyên tử; giao dịch `OUT` phải có điều kiện `quantity >= amount` để ngăn tồn kho âm kể cả khi có request đồng thời.

Bảng giao dịch dùng GSI `ByTimestamp` để truy vấn danh sách theo thời gian; partition key nội bộ là `gsi1pk = "TRANSACTION"` và sort key `gsi1sk = timestamp#transactionId`.

### User

| Trường | Kiểu | Quy tắc |
| --- | --- | --- |
| `id` | string | Cognito `sub` |
| `username` | string | Username Cognito |
| `fullName` | string | Tên hiển thị |
| `email` | string | Email |
| `role` | string | `Admin` hoặc `Staff`, lấy từ Cognito group/claim đáng tin cậy |
| `status` | string | `ACTIVE` hoặc `LOCKED` |

Không trả mật khẩu hoặc token trong dữ liệu user. Tạo/đổi quyền/khóa tài khoản chỉ dành cho Admin. Quyền phải được kiểm tra ở backend, không chỉ ẩn chức năng trên giao diện.

### SystemLog

| Trường | Kiểu | Quy tắc |
| --- | --- | --- |
| `timestamp` | ISO 8601 string | Thời điểm log |
| `logStream` | string | Tên dịch vụ/stream |
| `level` | string | `INFO`, `WARN` hoặc `ERROR` |
| `message` | string | Nội dung đã loại bỏ dữ liệu nhạy cảm |

Log vận hành được ghi ở CloudWatch. API `/logs` chỉ là lớp truy vấn có phân quyền; không cấp quyền CloudWatch trực tiếp cho trình duyệt.

## 3. Endpoint nghiệp vụ

Mọi endpoint dưới đây yêu cầu Cognito token, trừ khi ghi chú khác.

Quyền CRUD sản phẩm/nhà cung cấp dưới đây tạm giữ theo UI hiện tại: Admin và Staff đều thấy các thao tác này. Cần xác nhận lại chính sách này trước khi triển khai production.

| Method | Path | Quyền | Hành vi |
| --- | --- | --- | --- |
| `GET` | `/products` | Admin, Staff | Danh sách sản phẩm |
| `GET` | `/products?filter=low-stock` | Admin, Staff | Sản phẩm có `quantity < minThreshold` |
| `GET` | `/products/{productId}` | Admin, Staff | Chi tiết sản phẩm |
| `POST` | `/products` | Admin, Staff | Tạo sản phẩm |
| `PUT` | `/products/{productId}` | Admin, Staff | Cập nhật thông tin sản phẩm |
| `DELETE` | `/products/{productId}` | Admin, Staff | Xóa sản phẩm nếu chưa có lịch sử giao dịch |
| `GET` | `/suppliers` | Admin, Staff | Danh sách nhà cung cấp |
| `GET` | `/suppliers/{supplierId}` | Admin, Staff | Chi tiết nhà cung cấp |
| `POST` | `/suppliers` | Admin, Staff | Tạo nhà cung cấp |
| `PUT` | `/suppliers/{supplierId}` | Admin, Staff | Cập nhật nhà cung cấp |
| `DELETE` | `/suppliers/{supplierId}` | Admin, Staff | Xóa nếu không còn sản phẩm liên kết hoặc lịch sử giao dịch |
| `GET` | `/transactions` | Admin, Staff | Lịch sử giao dịch |
| `GET` | `/transactions/{transactionId}` | Admin, Staff | Chi tiết giao dịch |
| `POST` | `/transactions` | Admin, Staff | Tạo giao dịch nhập/xuất và cập nhật tồn kho nguyên tử |
| `GET` | `/users` | Admin | Danh sách user |
| `GET` | `/users/{userId}` | Admin | Chi tiết user |
| `POST` | `/users` | Admin | Tạo tài khoản Cognito |
| `PUT` | `/users/{userId}` | Admin | Cập nhật role/status |
| `DELETE` | `/users/{userId}` | Admin | Xóa/vô hiệu hóa tài khoản theo chính sách |
| `GET` | `/dashboard/stats` | Admin, Staff | Thống kê tổng quan |
| `GET` | `/logs` | Admin | Truy vấn log qua backend |

### Request/response nghiệp vụ

`POST /transactions` nhận:

Header: `Idempotency-Key: <unique-request-key>`

```json
{
  "type": "OUT",
  "productId": "prod-001",
  "amount": 5,
  "supplierId": null,
  "reason": "Cấp phát cho phòng Kế toán",
  "invoiceKey": null
}
```

Request cần header `Idempotency-Key` (1-128 ký tự); client phải dùng lại cùng key khi retry cùng một giao dịch. Backend tạo `transactionId`, `timestamp`, `productName` và `performedBy` từ Cognito token, bỏ qua các trường cùng tên do client gửi, rồi cập nhật tồn kho và ghi transaction trong một DynamoDB transaction. Nếu key đã dùng cho payload khác trả `409`; nếu sản phẩm không tồn tại trả `404`; nếu xuất vượt tồn trả `409` với `code: "INSUFFICIENT_STOCK"`.

`GET /dashboard/stats` trả object trong `data` với các trường tương thích frontend: `totalProducts`, `totalQuantity`, `totalValue`, `lowStockCount`, `totalSuppliers`, `todayIn`, `todayOut`, `todayTransactions`.

## 4. Đăng nhập và tải file

- **Không triển khai `POST /auth/login` bằng một Lambda tự xử lý mật khẩu.** Đăng nhập qua Cognito Hosted UI/SDK; frontend gửi Cognito token cho API. Khi đổi từ mock sang thật, cần thay luồng `ApiService.Auth.login` hiện tại.
- `POST /uploads/presign` cấp URL tải lên S3 và trả `{ uploadUrl, key, expiresIn }`. Chỉ chấp nhận loại file/kích thước cho phép; frontend tải file trực tiếp lên URL đó.
- Sau khi upload, frontend gửi `key` (`imageKey` hoặc `invoiceKey`) cùng request nghiệp vụ. Không gửi/lưu chuỗi Base64.
- `POST /uploads/download-url` nhận object key và trả URL tải xuống tạm thời sau khi backend kiểm tra quyền truy cập.

## 5. Đối chiếu với frontend hiện tại

- `ApiService` đã định nghĩa các resource và đường dẫn ở trên, nhưng đang bật `USE_MOCK_DATA`.
- Frontend hiện gửi `imageUrl` dạng Data URL và tạo `invoiceUrl` giả dạng `s3://...`; khi tích hợp thật cần đổi sang flow presigned URL và các trường `imageKey`/`invoiceKey`.
- Frontend hiện tạo `transactionId`, `timestamp` và `performedBy`; backend phải bỏ qua các trường này khi tạo transaction và tự thiết lập giá trị đáng tin cậy.
- UI hiện lọc user theo role và có thao tác quản trị; mọi quyền tương ứng vẫn phải được xác minh trong backend.
- Seed data hiện nằm trong `frontend/js/mock-data.js`; không dùng làm dữ liệu production.

