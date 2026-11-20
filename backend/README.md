# CloudStock backend

Backend dùng Python 3.12, AWS Lambda, API Gateway, Cognito, DynamoDB, S3 và
CloudWatch Logs. Các tên trường wire và DynamoDB đã được chuyển theo tài liệu
của người phụ trách Cloud; xem [API contract](API_CONTRACT.md) để biết các giả
định triển khai và khác biệt hạ tầng còn lại.

## Các API

- `GET /health`: health check công khai.
- `GET|POST /products`, `GET|PUT|DELETE /products/{productId}`.
- `GET|POST /suppliers`, `GET|PUT|DELETE /suppliers/{supplierId}`.
- `GET /transactions`, `GET /transactions/{transactionId}`, `POST /transactions`.
- `GET|POST /users`, `GET|PUT|DELETE /users/{userId}` (chỉ Admin).
- `GET /dashboard`.
- `GET /logs` (chỉ Admin).
- `POST /products/upload-url` tạo presigned POST cho ảnh sản phẩm.
- `POST /transactions/invoice-upload-url` tạo presigned POST cho hóa đơn nhập.
- `GET /transactions/{transactionId}/invoice-url` tạo URL đọc hóa đơn có hạn.

Các API trừ `/health` yêu cầu Cognito group `Admin` hoặc `Staff`; `/users` và
`/logs` yêu cầu `Admin`. Thành công trả JSON dạng
`{"success": true, "data": ...}`; danh sách hỗ trợ `limit` và `nextToken`.
`POST /transactions` yêu cầu `Idempotency-Key`. Nhập/xuất và ghi lịch sử giao
dịch được thực hiện trong một DynamoDB transaction; xung đột stock bị từ chối
để client có thể retry an toàn với cùng key.

Schema API dùng trực tiếp `stockQuantity`, `status`, `type=IMPORT|EXPORT`,
`quantity` và `createdAt` trên cả frontend lẫn backend. `status` sản phẩm do
backend tính: stock lớn hơn 0 là `IN_STOCK`, ngược lại `OUT_OF_STOCK`. Trạng
thái tài khoản dùng `ACTIVE` hoặc `DISABLED`.

Ảnh chỉ nhận JPEG/PNG/WebP tối đa 5 MB và lưu trong `products/` (public read).
Hóa đơn chỉ nhận PDF/JPEG/PNG tối đa 15 MB, lưu trong `invoices/` (private).
`invoiceUrl` lưu S3 object key, không lưu URL ký tạm thời; API chỉ cấp URL đọc
ngắn hạn sau khi xác thực quyền. Tài khoản không gửi mật khẩu qua API; Cognito
gửi mật khẩu khởi tạo đến email khi Admin tạo user.

Dashboard tổng hợp số liệu từ ba bảng. Danh sách sản phẩm, nhà cung cấp,
dashboard và các kiểm tra xóa dùng DynamoDB `Scan`; đây là cách triển khai cho
prototype/bảng nhỏ, không phù hợp workload lớn. Logs dùng `FilterLogEvents`
trên các nhóm được liệt kê trong biến `LOG_GROUPS`; không cho phép chọn tùy ý
log group qua request.

## Cài đặt và test

Từ thư mục `backend`:

```powershell
python -m pip install -r requirements.txt
python -m unittest discover -s test -v
python -m compileall -q src scripts test
sam validate --lint --template-file template.yaml
sam build --template-file template.yaml
```

`sam build` và `sam validate` không deploy tài nguyên. Không chạy
`sam deploy` nếu chưa được người phụ trách Cloud duyệt tài khoản, region, tên
tài nguyên, quyền IAM và chi phí.

## DynamoDB Local và API local

Cần Docker Desktop. Tạo DynamoDB Local một lần:

```powershell
docker run --name cloudstock-dynamodb-local -p 8000:8000 -d amazon/dynamodb-local:latest
```

Nếu container đã tồn tại và đang dừng:

```powershell
docker start cloudstock-dynamodb-local
```

Từ thư mục `backend`, tạo bảng local mới theo schema hiện tại:

```powershell
python -m scripts.init_local_dynamodb
```

Bảng giao dịch dùng khóa ghép `transactionId` + `createdAt` và GSI
`ByCreatedAt`. Database local cũ được tạo theo schema trước đó không tự migrate;
hãy giữ bản sao dữ liệu cần thiết và tạo một database local mới trước khi thử
schema này.

Chạy adapter local:

```powershell
python -m scripts.local_api
```

Adapter chỉ lắng nghe `127.0.0.1:3001`, chỉ nhận origin
`http://localhost:8080`, giới hạn request body 1 MB và dùng token local
`Bearer local-dev:Admin` hoặc `Bearer local-dev:Staff`. Nó cố định bảng vào
DynamoDB Local; các endpoint Cognito/S3/CloudWatch trả lỗi rõ ràng nếu chưa
cấu hình dịch vụ local tương ứng. Nếu cần dùng LocalStack/MinIO, chỉ chấp nhận
endpoint HTTP loopback: `COGNITO_ENDPOINT`/`CLOUDWATCH_ENDPOINT` cổng 4566,
`S3_ENDPOINT` cổng 4566 hoặc 9000. Không trỏ các endpoint này tới AWS hay host
bên ngoài.

Mở terminal riêng tại thư mục `frontend`:

```powershell
python -m http.server 8080
```

Truy cập `http://localhost:8080`. Mặc định giao diện vẫn dùng mock users/logs
và tự tính dashboard ở chế độ local; các dữ liệu products/suppliers/transactions
được lưu vào DynamoDB Local. Local adapter chưa mô phỏng Cognito, S3 hoặc
CloudWatch.

## SAM và môi trường Cloud

`template.yaml` là stack SAM độc lập để build/test: nó tạo User Pool, API
Gateway, các bảng theo schema mới và một S3 bucket mới; bốn module chức năng
được chia theo cấu trúc Cloud (`users`, `dashboard`, `catalog`, `transactions`)
cùng health endpoint. Template **không tham chiếu hoặc gắn vào API Gateway,
Cognito User Pool, DynamoDB tables hay S3 bucket đã tồn tại của nhóm**. Không
deploy template này lên tài khoản nhóm trước khi người phụ trách Cloud xác
nhận cách dùng tài nguyên hiện có và xử lý GSI `ByCreatedAt`.

Để nối với môi trường nhóm cần cấu hình/đối chiếu API Gateway integration,
API authorizer, table names, bucket name, `USER_POOL_ID`, `LOG_GROUPS`, public
image access, và quyền IAM. Tài liệu của Cloud chưa nêu route request/response
chi tiết cho tất cả module hoặc xác nhận GSI giao dịch; các lựa chọn hiện dùng
được ghi rõ trong [API contract](API_CONTRACT.md). Tài nguyên AWS chưa được
deploy bởi thay đổi này.
