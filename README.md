# CloudStock

Giao diện web quản lý kho viết bằng HTML, CSS và JavaScript thuần. Frontend mặc định nối các luồng hàng hóa, nhà cung cấp và giao dịch với backend local; người dùng và logs vẫn dùng dữ liệu giả lập trong `localStorage`. Backend Python 3.12 chưa được deploy lên AWS.

## Chạy giao diện

Từ thư mục `frontend`, chạy:

```powershell
python -m http.server 8080
```

Sau đó mở `http://localhost:8080`.

Để chạy đầy đủ luồng local, hãy khởi động DynamoDB Local và backend adapter bằng hướng dẫn trong [backend README](backend/README.md) trước khi mở giao diện.

## Tài liệu backend

- [Hợp đồng API và đối chiếu cấu trúc Cloud](backend/API_CONTRACT.md)
- [Khung backend AWS SAM](backend/README.md)
