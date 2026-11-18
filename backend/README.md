# Backend foundation

Backend hiện có AWS SAM template, Cognito User Pool, API Gateway, ba bảng DynamoDB, endpoint kiểm tra `/health`, CRUD danh mục sản phẩm/nhà cung cấp và API giao dịch nhập/xuất. Các API dashboard, user, log và upload chưa được triển khai.

Các route catalog đã có trong SAM:

- `GET /products` và `GET /products?filter=low-stock` (có `limit`/`nextToken`)
- `GET`, `POST /products` và `GET`, `PUT`, `DELETE /products/{productId}`
- `GET`, `POST /suppliers` và `GET`, `PUT`, `DELETE /suppliers/{supplierId}`
- `GET /transactions`, `GET /transactions/{transactionId}` và `POST /transactions`

Route catalog và giao dịch yêu cầu Cognito group `Admin` hoặc `Staff`. Cognito self-sign-up bị tắt; tài khoản phải được tạo/quản lý qua luồng Admin (chưa triển khai). Xóa sản phẩm/nhà cung cấp bị từ chối nếu còn lịch sử/tham chiếu. Các API chưa được deploy lên AWS; frontend có adapter local cho các route đã triển khai.

Giao dịch dùng DynamoDB `TransactWriteItems` để cập nhật tồn kho và lưu lịch sử nguyên tử. `OUT` có điều kiện chặn tồn âm; `POST /transactions` yêu cầu header `Idempotency-Key` để retry không ghi trùng. Danh sách giao dịch đọc qua GSI `ByTimestamp`.

Danh sách dùng DynamoDB `Scan` kèm cursor để tương thích bảng nhỏ ban đầu. Khi dữ liệu tăng, cần thêm index/query phù hợp để tránh scan toàn bảng. Tải ảnh/chứng từ chưa được hỗ trợ; request ghi sản phẩm không nhận URL/Base64 ảnh, cần triển khai presigned S3 ở bước sau.

## Yêu cầu

- Python 3.12 trở lên
- Các thư viện Python trong `requirements.txt` (`boto3`)
- AWS SAM CLI để validate/build và chạy Lambda fixture qua `sam local`
- Docker Desktop để chạy DynamoDB Local và Lambda container của SAM
- AWS CLI credentials chỉ cần khi deploy lên AWS

## Cài đặt và kiểm tra

Từ thư mục `backend`:

```powershell
python -m pip install -r requirements.txt
python -m unittest discover -s test -v
```

## Build và chạy API local

Sau khi cài SAM CLI và Docker:

```powershell
sam validate --lint --template-file template.yaml
sam build --template-file template.yaml
```

Khởi chạy DynamoDB Local trong Docker (chỉ cần tạo container một lần):

```powershell
docker run --name cloudstock-dynamodb-local -p 8000:8000 -d amazon/dynamodb-local:latest
```

Từ thư mục `backend`, tạo ba bảng local theo SAM template:

```powershell
python -m scripts.init_local_dynamodb
```

Để kết nối trình duyệt với các API đã triển khai, chạy local HTTP adapter tại thư mục `backend`:

```powershell
python -m scripts.local_api
```

Adapter Python gọi trực tiếp cùng các Lambda handler, kết nối DynamoDB Local qua `http://127.0.0.1:8000` và chỉ lắng nghe trên `127.0.0.1:3001` (có thể đổi bằng biến `PORT`). Nó chỉ nhận request từ origin `http://localhost:8080` và token local Admin/Staff. Đây là tiện ích phát triển local, không được deploy lên AWS. Health endpoint là `http://127.0.0.1:3001/health`.

Để chạy riêng các Lambda trong Docker bằng SAM, trước tiên build template. `local-env.json` trỏ Lambda container tới DynamoDB Local qua `host.docker.internal`; cấu hình này chỉ dành cho `sam local invoke`, không áp dụng khi chạy Lambda trên AWS:

```powershell
sam build --template-file .\template.yaml
```

## Kết nối frontend với backend local

Sau khi DynamoDB Local đã chạy và `python -m scripts.local_api` đang phục vụ tại cổng 3001, frontend được cấu hình sẵn trong `frontend/js/config.js` như sau:

```js
USE_MOCK_DATA: true,
USE_MOCK_AUTH: true,
USE_LOCAL_API: true,
USE_LOCAL_API_AUTH: true,
API_BASE_URL: "http://127.0.0.1:3001",
```

Chế độ này gửi hàng hóa, nhà cung cấp và giao dịch đến backend local; người dùng và logs vẫn dùng mock vì các API tương ứng chưa có. Dashboard lấy số liệu từ ba API local đã hỗ trợ. Đăng nhập bằng tài khoản demo `Admin` hoặc `Staff`; adapter chỉ chấp nhận token local khi request đến từ giao diện ở `http://localhost:8080`.

Mở PowerShell riêng tại thư mục `frontend`, chạy:

```powershell
python -m http.server 8080
```

Truy cập `http://localhost:8080` (không mở trang bằng `file:///`). Cơ sở dữ liệu local không tự nhận dữ liệu mock; hãy tạo nhà cung cấp/sản phẩm trong giao diện hoặc dùng các event fixture ở trên. Ảnh sản phẩm và chứng từ chưa hỗ trợ tải lên backend, nên bỏ tệp đính kèm khi thử tạo/cập nhật dữ liệu local.

## Cognito Hosted UI

SAM template cấu hình OAuth Authorization Code flow cho SPA, không tạo client secret. Khi deploy dev, `CognitoDomainPrefix` phải là prefix chưa được tài khoản AWS khác sử dụng. `FrontendOrigin` phải khớp chính xác origin của frontend; mặc định là `http://localhost:8080`, với callback/logout URL là `http://localhost:8080/login.html`.

Sau khi deploy, lấy các output `CognitoHostedUiDomain`, `UserPoolClientId` và `UserPoolId`, rồi điền vào `frontend/js/config.js`. Để chỉ bật đăng nhập Cognito mà vẫn giữ dữ liệu demo:

```js
USE_MOCK_AUTH: false,
USE_MOCK_DATA: true,
USE_LOCAL_API: false,
USE_LOCAL_API_AUTH: false,
API_BASE_URL: "<ApiBaseUrl output>",
COGNITO_USER_POOL_ID: "<UserPoolId output>",
COGNITO_CLIENT_ID: "<UserPoolClientId output>",
COGNITO_HOSTED_UI_DOMAIN: "<CognitoHostedUiDomain output>",
COGNITO_REDIRECT_URI: "http://localhost:8080/login.html",
COGNITO_LOGOUT_URI: "http://localhost:8080/login.html",
```

Giữ `USE_MOCK_DATA: true` cho đến khi các API dashboard, users và logs được triển khai. Callback/logout URI phải khớp chính xác với `FrontendOrigin` đã đăng ký trong Cognito.

User Pool chỉ cho phép Admin tạo tài khoản. Người dùng phải được tạo và thêm vào group `Admin` hoặc `Staff`; đăng nhập bằng tài khoản chưa có group này sẽ bị từ chối. Không đặt client secret trong frontend. Chưa có tài nguyên AWS nào được deploy; Cognito/API có thể phát sinh chi phí.

## Deploy

Chỉ deploy khi đã cấu hình AWS CLI đúng tài khoản/region:

```powershell
sam deploy --guided --template-file template.yaml
```

Stack tạo tài nguyên có thể phát sinh chi phí AWS. Không chạy lệnh deploy nếu chưa kiểm tra tài khoản, region và chi phí dự kiến.
