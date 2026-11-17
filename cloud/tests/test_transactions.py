import time

import pytest

SUPPLIER = {"name": "NCC A", "phone": "0909123456", "address": "HCM"}


@pytest.fixture()
def shop(clean, call):
    """1 sản phẩm tồn 10 (ngưỡng 3) + 1 nhà cung cấp."""
    _, p = call("products", "POST", "/products", body={
        "name": "Bàn phím Keychron", "category": "Phụ kiện", "price": 2450000,
        "stockQuantity": 10, "minThreshold": 3})
    _, s = call("products", "POST", "/suppliers", body=SUPPLIER)
    return {"pid": p["productId"], "sid": s["supplierId"]}


def stock(call, pid):
    return call("products", "GET", f"/products/{pid}")[1]


def tx(call, body, **kw):
    return call("transactions", "POST", "/transactions", body=body, **kw)


def test_nhap_kho_cong_ton_va_ghi_giao_dich(shop, call):
    status, t = tx(call, {"type": "IMPORT", "productId": shop["pid"], "quantity": 20,
                          "supplierId": shop["sid"], "invoiceUrl": "invoices/inv1.pdf"},
                   role="Staff", email="staff1@nhom4.com")
    assert status == 201, t
    assert t["transactionId"].startswith("TXN-") and t["type"] == "IMPORT"
    assert t["productName"] == "Bàn phím Keychron"           # tự lấy từ bảng Products
    assert t["performedBy"] == "staff1@nhom4.com"             # lấy từ JWT, không tin client
    assert t["supplierId"] == shop["sid"] and t["invoiceUrl"] == "invoices/inv1.pdf" and t["reason"] is None
    p = stock(call, shop["pid"])
    assert p["stockQuantity"] == 30 and p["status"] == "IN_STOCK"


def test_xuat_kho_tru_ton(shop, call):
    status, t = tx(call, {"type": "EXPORT", "productId": shop["pid"], "quantity": 4, "reason": "Xuất bán"})
    assert status == 201 and t["supplierId"] is None and t["invoiceUrl"] is None and t["reason"] == "Xuất bán"
    assert stock(call, shop["pid"])["stockQuantity"] == 6


def test_xuat_qua_ton_tra_400_va_khong_doi_ton(shop, call):
    status, d = tx(call, {"type": "EXPORT", "productId": shop["pid"], "quantity": 11, "reason": "x"})
    assert status == 400 and "tồn kho" in d["message"]
    assert stock(call, shop["pid"])["stockQuantity"] == 10
    assert call("transactions", "GET", "/transactions")[1] == []   # không ghi phiếu rác


def test_xuat_het_thi_out_of_stock_roi_nhap_lai_thi_in_stock(shop, call):
    assert tx(call, {"type": "EXPORT", "productId": shop["pid"], "quantity": 10, "reason": "x"})[0] == 201
    p = stock(call, shop["pid"])
    assert p["stockQuantity"] == 0 and p["status"] == "OUT_OF_STOCK"
    assert tx(call, {"type": "EXPORT", "productId": shop["pid"], "quantity": 1, "reason": "x"})[0] == 400
    tx(call, {"type": "IMPORT", "productId": shop["pid"], "quantity": 5, "supplierId": shop["sid"]})
    p = stock(call, shop["pid"])
    assert p["stockQuantity"] == 5 and p["status"] == "IN_STOCK"


@pytest.mark.parametrize("qty", [0, -1, 2.5, "abc", True, None])
def test_so_luong_sai_tra_400(shop, call, qty):
    status, _ = tx(call, {"type": "EXPORT", "productId": shop["pid"], "quantity": qty, "reason": "x"})
    assert status == 400
    assert stock(call, shop["pid"])["stockQuantity"] == 10


def test_so_luong_dang_chuoi_so_van_duoc_chap_nhan(shop, call):
    assert tx(call, {"type": "EXPORT", "productId": shop["pid"], "quantity": "2", "reason": "x"})[0] == 201
    assert stock(call, shop["pid"])["stockQuantity"] == 8


def test_validate_dau_vao_khac(shop, call):
    assert tx(call, {"type": "XYZ", "productId": shop["pid"], "quantity": 1})[0] == 400
    assert tx(call, {"productId": shop["pid"], "quantity": 1})[0] == 400
    assert tx(call, {"type": "EXPORT", "quantity": 1})[0] == 400
    assert tx(call, {"type": "EXPORT", "productId": "PRD-KHONG-CO", "quantity": 1})[0] == 404
    # nhập kho bắt buộc có nhà cung cấp hợp lệ
    assert tx(call, {"type": "IMPORT", "productId": shop["pid"], "quantity": 1})[0] == 400
    assert tx(call, {"type": "IMPORT", "productId": shop["pid"], "quantity": 1, "supplierId": "SUP-MA"})[0] == 400
    # hóa đơn phải nằm trong invoices/
    bad = {"type": "IMPORT", "productId": shop["pid"], "quantity": 1, "supplierId": shop["sid"]}
    assert tx(call, {**bad, "invoiceUrl": "products/a.png"})[0] == 400
    assert tx(call, {**bad, "invoiceUrl": "invoices/../secret"})[0] == 400
    assert stock(call, shop["pid"])["stockQuantity"] == 10


def test_invoice_url_dang_url_day_du_duoc_doi_ve_s3key(shop, call):
    full = "https://qlkho-test-bucket.s3.ap-southeast-1.amazonaws.com/invoices/a_hd.pdf?X=1"
    _, t = tx(call, {"type": "IMPORT", "productId": shop["pid"], "quantity": 1,
                     "supplierId": shop["sid"], "invoiceUrl": full})
    assert t["invoiceUrl"] == "invoices/a_hd.pdf"


# --------------------------------------------------------------- đồng thời
def test_hai_nguoi_xuat_cung_luc_van_khong_am_kho(shop, call, aws):
    """Mô phỏng: giữa lúc Lambda đọc tồn kho và lúc ghi, người khác đã xuất mất 6 cái.
    Điều kiện 'stockQuantity = giá trị đã đọc' làm lần ghi đầu thất bại, Lambda đọc lại (còn 4) và từ chối."""
    app = aws["apps"]["transactions"]
    real = app.products_table
    calls = {"n": 0}

    class Racy:
        def get_item(self, **kw):
            item = real.get_item(**kw)
            calls["n"] += 1
            if calls["n"] == 1:   # sau lần đọc đầu tiên, người khác chen vào
                real.update_item(Key=kw["Key"], UpdateExpression="SET stockQuantity = :s",
                                 ExpressionAttributeValues={":s": 4})
            return item

    app.products_table = Racy()
    try:
        status, d = tx(call, {"type": "EXPORT", "productId": shop["pid"], "quantity": 6, "reason": "x"})
    finally:
        app.products_table = real
    assert status == 400 and "tồn kho" in d["message"]           # đọc lại thấy chỉ còn 4
    assert stock(call, shop["pid"])["stockQuantity"] == 4         # không bị ghi đè, không âm
    assert call("transactions", "GET", "/transactions")[1] == []


def test_race_nhung_van_du_ton_thi_thu_lai_va_thanh_cong(shop, call, aws):
    app = aws["apps"]["transactions"]
    real = app.products_table
    calls = {"n": 0}

    class Racy:
        def get_item(self, **kw):
            item = real.get_item(**kw)
            calls["n"] += 1
            if calls["n"] == 1:
                real.update_item(Key=kw["Key"], UpdateExpression="SET stockQuantity = :s",
                                 ExpressionAttributeValues={":s": 8})
            return item

    app.products_table = Racy()
    try:
        status, t = tx(call, {"type": "EXPORT", "productId": shop["pid"], "quantity": 3, "reason": "x"})
    finally:
        app.products_table = real
    assert status == 201 and t["stockQuantity"] == 5             # 8 - 3, dựa trên số liệu mới nhất
    assert stock(call, shop["pid"])["stockQuantity"] == 5
    assert len(call("transactions", "GET", "/transactions")[1]) == 1   # đúng 1 phiếu


def test_nhieu_luong_xuat_cung_luc(shop, call, aws):
    """20 luồng cùng xuất 1 cái khi tồn = 10 -> tối đa 10 thành công, tồn không bao giờ âm."""
    import threading
    from concurrent.futures import ThreadPoolExecutor
    app = aws["apps"]["transactions"]
    real, lock = app._ddb_client, threading.Lock()

    class Atomic:
        """DynamoDB thật xử lý mỗi giao dịch theo kiểu nguyên tử; moto thì không an toàn khi chạy nhiều luồng,
        nên khóa riêng lệnh ghi để mô phỏng đúng. Vẫn để các luồng tranh nhau đọc -> thử lại như thật."""
        def transact_write_items(self, **kw):
            with lock:
                return real.transact_write_items(**kw)
        def __getattr__(self, name):
            return getattr(real, name)

    def one(_):
        return tx(call, {"type": "EXPORT", "productId": shop["pid"], "quantity": 1, "reason": "x"})[0]
    app._ddb_client = Atomic()
    try:
        with ThreadPoolExecutor(8) as ex:
            codes = list(ex.map(one, range(20)))
    finally:
        app._ddb_client = real
    ok = codes.count(201)
    final = stock(call, shop["pid"])["stockQuantity"]
    assert final >= 0 and final == 10 - ok
    assert len(call("transactions", "GET", "/transactions")[1]) == ok   # số phiếu = số lần trừ kho


# --------------------------------------------------------------------- truy vấn
def test_list_moi_nhat_len_dau_va_loc(shop, call, aws):
    t = aws["ddb"].Table("Transactions")
    for i, (typ, day) in enumerate([("IMPORT", "10"), ("EXPORT", "12"), ("IMPORT", "11")]):
        t.put_item(Item={"transactionId": f"T{i}", "createdAt": f"2026-11-{day}T08:00:00Z", "type": typ,
                         "productId": shop["pid"] if i != 2 else "PRD-KHAC", "productName": "x", "quantity": 1,
                         "performedBy": "a@b.c", "supplierId": None, "invoiceUrl": None, "reason": None})
    _, items = call("transactions", "GET", "/transactions")
    assert [i["createdAt"][8:10] for i in items] == ["12", "11", "10"]
    _, items = call("transactions", "GET", "/transactions", query={"type": "IMPORT"})
    assert [i["transactionId"] for i in items] == ["T2", "T0"]
    _, items = call("transactions", "GET", "/transactions", query={"productId": shop["pid"]})
    assert [i["transactionId"] for i in items] == ["T1", "T0"]               # qua GSI, mới nhất trước
    _, items = call("transactions", "GET", "/transactions",
                    query={"productId": shop["pid"], "type": "EXPORT"})
    assert [i["transactionId"] for i in items] == ["T1"]
    assert call("transactions", "GET", "/transactions", query={"type": "SAI"})[0] == 400
    status, one = call("transactions", "GET", "/transactions/T1")
    assert status == 200 and one["type"] == "EXPORT"
    assert call("transactions", "GET", "/transactions/KHONG-CO")[0] == 404


def test_invoice_url(call):
    status, d = call("transactions", "GET", "/transactions/invoice-url",
                     query={"key": "invoices/INV_001.pdf"}, role="Staff")
    assert status == 200 and "X-Amz-Signature" in d["viewUrl"] and "invoices/INV_001.pdf" in d["viewUrl"]
    assert call("transactions", "GET", "/transactions/invoice-url")[0] == 400
    assert call("transactions", "GET", "/transactions/invoice-url", query={"key": "products/a.png"})[0] == 400
    assert call("transactions", "GET", "/transactions/invoice-url", query={"key": "invoices/../x"})[0] == 400


def test_logs_chi_admin_va_loc_dong_nhieu(aws, call):
    now = int(time.time() * 1000)
    g = aws["groups"][0]
    aws["logs"].create_log_stream(logGroupName=g, logStreamName="s1")
    aws["logs"].put_log_events(logGroupName=g, logStreamName="s1", logEvents=[
        {"timestamp": now - 3000, "message": "START RequestId: abc Version: $LATEST"},
        {"timestamp": now - 2000, "message": "[INFO] tao san pham PRD-001"},
        {"timestamp": now - 1000, "message": "[ERROR] loi gi do"},
        {"timestamp": now, "message": "END RequestId: abc"},
    ])
    assert call("transactions", "GET", "/transactions/logs", role="Staff")[0] == 403
    status, logs = call("transactions", "GET", "/transactions/logs")
    assert status == 200
    msgs = [l["message"] for l in logs]
    assert msgs == ["[ERROR] loi gi do", "[INFO] tao san pham PRD-001"]      # mới nhất trước, bỏ START/END
    assert set(logs[0]) == {"timestamp", "message", "logStream", "logGroup"}
    _, only_err = call("transactions", "GET", "/transactions/logs", query={"q": "error"})
    assert [l["message"] for l in only_err] == ["[ERROR] loi gi do"]
    assert call("transactions", "GET", "/transactions/logs", query={"limit": "abc"})[0] == 400


def test_ping(call):
    status, d = call("transactions", "GET", "/transactions/_ping")
    assert status == 200 and d["ok"] is True and d["check"]["cloudwatchLogs"] == "ok"
