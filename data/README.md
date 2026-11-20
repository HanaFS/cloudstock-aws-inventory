# Phần Data – CloudStock

Dữ liệu mẫu và công cụ kiểm tra cho 3 bảng DynamoDB của backend (`cloudstock-<stage>-products | suppliers | transactions`). Schema bám theo code backend; xem [docs/data-model.md](docs/data-model.md).

| File | Việc |
|---|---|
| `seed/*.json` | Dữ liệu mẫu (24 sản phẩm, 6 nhà cung cấp, giao dịch 60 ngày) |
| `generate_seed.py` | Sinh lại dữ liệu mẫu, `--end-date YYYY-MM-DD` để dời mốc thời gian |
| `validate_data.py` | Kiểm tra dữ liệu đúng schema/quy tắc backend, tồn kho khớp lịch sử IN/OUT |
| `load_to_dynamodb.py` | Nạp seed vào DynamoDB Local hoặc AWS (`--dry-run`, `--wipe`) |
| `dashboard_stats.py` | Hàm tính số liệu Dashboard (bản tham chiếu, cùng định nghĩa với frontend) |
| `report_inventory.py` | Xuất báo cáo CSV và JSON vào `output/` |

## Chạy

```powershell
pip install -r data/requirements.txt
python data/validate_data.py
python data/report_inventory.py
```

## Nạp dữ liệu mẫu vào DynamoDB Local để thử với frontend

Làm theo `backend/README.md` để chạy DynamoDB Local và tạo bảng, rồi:

```powershell
python data/load_to_dynamodb.py --endpoint-url http://127.0.0.1:8000 --dry-run
python data/load_to_dynamodb.py --endpoint-url http://127.0.0.1:8000 --wipe
```

Nạp vào AWS thật (người có quyền AWS, đúng stage và region của stack đã deploy):

```powershell
python data/load_to_dynamodb.py --stage dev --region ap-southeast-1 --dry-run
```
