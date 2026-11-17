from datetime import datetime, timedelta, timezone

import pytest

VN = timezone(timedelta(hours=7))


def iso(dt):
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def put_product(aws, pid, cat, price, stock, minimum):
    aws["ddb"].Table("Products").put_item(Item={
        "productId": pid, "name": f"SP {pid}", "category": cat, "price": price, "stockQuantity": stock,
        "minThreshold": minimum, "status": "IN_STOCK" if stock > 0 else "OUT_OF_STOCK",
        "imageUrl": "", "updatedAt": "2026-11-16T00:00:00Z"})


def put_tx(aws, tid, when, typ, qty, pid="P1"):
    aws["ddb"].Table("Transactions").put_item(Item={
        "transactionId": tid, "createdAt": iso(when), "type": typ, "productId": pid, "productName": "x",
        "quantity": qty, "performedBy": "a@b.c", "supplierId": None, "invoiceUrl": None, "reason": None})


# ------------------------------------------------------------------ dashboard
def test_dashboard_so_lieu(clean, call):
    aws = clean
    put_product(aws, "P1", "Laptop", 1000, 10, 3)     # bình thường
    put_product(aws, "P2", "Laptop", 500, 3, 3)       # đúng ngưỡng -> sắp hết
    put_product(aws, "P3", "Phụ kiện", 200, 0, 5)     # hết hàng (cũng tính là sắp hết)
    for i in range(2):
        aws["ddb"].Table("Suppliers").put_item(Item={"supplierId": f"S{i}", "name": "n", "phone": "1", "address": "a"})
    now = datetime.now(VN)
    put_tx(aws, "T1", now, "IMPORT", 7)
    put_tx(aws, "T2", now, "EXPORT", 2)
    put_tx(aws, "T3", now - timedelta(days=3), "IMPORT", 10)
    put_tx(aws, "T4", now - timedelta(days=30), "IMPORT", 999)   # ngoài 7 ngày

    status, d = call("dashboard", "GET", "/dashboard", role="Staff")
    assert status == 200
    assert d["totalProducts"] == 3 and d["totalSuppliers"] == 2
    assert d["totalStockValue"] == 10 * 1000 + 3 * 500 + 0
    assert d["lowStockCount"] == 2 and d["outOfStockCount"] == 1
    assert [p["productId"] for p in d["lowStockItems"]] == ["P3", "P2"]      # ít nhất lên đầu
    assert d["todayImport"] == 1 and d["todayExport"] == 1
    assert [t["transactionId"] for t in d["recentTransactions"]][:2] in (["T1", "T2"], ["T2", "T1"])
    assert len(d["recentTransactions"]) == 4
    c = d["chartData"]
    assert c["importTotal"] == 17 and c["exportTotal"] == 2                  # 7 + 10, không tính 999
    assert len(c["last7Days"]) == 7 and c["last7Days"][-1]["import"] == 7
    cats = {x["category"]: x for x in c["byCategory"]}
    assert cats["Laptop"]["productCount"] == 2 and cats["Laptop"]["stockValue"] == 11500
    assert set(d) >= {"totalProducts", "totalSuppliers", "totalStockValue", "lowStockCount",
                      "outOfStockCount", "lowStockItems", "recentTransactions", "chartData"}


def test_dashboard_kho_trong_khong_loi(clean, call):
    status, d = call("dashboard", "GET", "/dashboard")
    assert status == 200 and d["totalProducts"] == 0 and d["totalStockValue"] == 0
    assert d["chartData"]["byCategory"] == [] and len(d["chartData"]["last7Days"]) == 7


def test_dashboard_chi_nhan_get(call):
    assert call("dashboard", "POST", "/dashboard")[0] == 405
    assert call("dashboard", "GET", "/khac")[0] == 404
    assert call("dashboard", "GET", "/dashboard/_ping")[1]["ok"] is True


# ----------------------------------------------------------------------- users
def make_user(call, email, role="Staff", password="Staff@123"):
    return call("users", "POST", "/users", body={"email": email, "password": password, "role": role})


def test_me_cho_moi_role(call):
    status, d = call("users", "GET", "/users/me", role="Staff", email="s@nhom4.com")
    assert status == 200 and d == {"email": "s@nhom4.com", "role": "Staff"}


def test_staff_khong_duoc_vao_quan_ly_user(call):
    for method, path in [("GET", "/users"), ("POST", "/users"), ("DELETE", "/users/x"), ("PUT", "/users/x/role")]:
        assert call("users", method, path, role="Staff")[0] == 403


def test_tao_user_va_liet_ke(aws, call):
    status, d = make_user(call, "Staff1@Gmail.com")
    assert status == 201 and d["email"] == "staff1@gmail.com" and d["role"] == "Staff"
    status, users = call("users", "GET", "/users")
    me = next(u for u in users if u["email"] == "staff1@gmail.com")
    assert me["role"] == "Staff" and me["status"] == "CONFIRMED" and me["enabled"] is True
    assert set(me) >= {"id", "username", "email", "role", "status", "createdAt"}
    # mật khẩu đã được đặt vĩnh viễn -> đăng nhập được ngay, không bị bắt đổi mật khẩu
    got = aws["cog"].admin_get_user(UserPoolId=aws["pool"], Username="staff1@gmail.com")
    assert got["UserStatus"] == "CONFIRMED"


def test_tao_user_tao_admin(aws, call):
    make_user(call, "boss@gmail.com", role="Admin", password="Admin@123")
    users = call("users", "GET", "/users")[1]
    assert next(u for u in users if u["email"] == "boss@gmail.com")["role"] == "Admin"


@pytest.mark.parametrize("body", [
    {"email": "khong-phai-email", "password": "Staff@123", "role": "Staff"},
    {"email": "a@b.com", "password": "", "role": "Staff"},
    {"email": "a@b.com", "password": "Staff@123", "role": "Boss"},
    {"password": "Staff@123", "role": "Staff"},
    {"email": "a@b.com", "password": "Staff@123"},
])
def test_tao_user_sai_tra_400(call, body):
    assert call("users", "POST", "/users", body=body)[0] == 400


def test_tao_user_trung_email_tra_409(call):
    assert make_user(call, "dup@gmail.com")[0] == 201
    assert make_user(call, "dup@gmail.com")[0] == 409


def test_doi_role_va_tu_bao_ve(aws, call):
    make_user(call, "nv@gmail.com")
    assert call("users", "PUT", "/users/nv@gmail.com/role", body={"role": "Admin"})[0] == 200
    u = call("users", "GET", "/users/nv@gmail.com")[1]
    assert u["role"] == "Admin"
    groups = aws["cog"].admin_list_groups_for_user(UserPoolId=aws["pool"], Username=u["username"])["Groups"]
    assert [g["GroupName"] for g in groups] == ["Admin"]           # đã gỡ khỏi nhóm Staff, không ở 2 nhóm
    assert call("users", "PUT", "/users/nv@gmail.com/role", body={"role": "Boss"})[0] == 400
    assert call("users", "PUT", "/users/khong-co@gmail.com/role", body={"role": "Staff"})[0] == 404
    # Admin không được tự hạ quyền chính mình
    make_user(call, "admin@nhom4.com", role="Admin", password="Admin@123")
    status, d = call("users", "PUT", "/users/admin@nhom4.com/role", body={"role": "Staff"}, email="admin@nhom4.com")
    assert status == 400 and "chính mình" in d["message"]


def test_khoa_mo_khoa_va_xoa(aws, call):
    make_user(call, "x@gmail.com")
    assert call("users", "PUT", "/users/x@gmail.com/status", body={"enabled": False})[0] == 200
    assert call("users", "GET", "/users/x@gmail.com")[1]["enabled"] is False
    assert call("users", "PUT", "/users/x@gmail.com/status", body={"enabled": True})[0] == 200
    assert call("users", "GET", "/users/x@gmail.com")[1]["enabled"] is True
    assert call("users", "PUT", "/users/x@gmail.com/status", body={"enabled": "yes"})[0] == 400
    assert call("users", "DELETE", "/users/x@gmail.com")[0] == 200
    assert call("users", "GET", "/users/x@gmail.com")[0] == 404
    assert call("users", "DELETE", "/users/x@gmail.com")[0] == 404


def test_admin_khong_tu_xoa_hay_tu_khoa_minh(call):
    make_user(call, "me@nhom4.com", role="Admin", password="Admin@123")
    assert call("users", "DELETE", "/users/me@nhom4.com", email="me@nhom4.com")[0] == 400
    assert call("users", "PUT", "/users/me@nhom4.com/status", body={"enabled": False}, email="me@nhom4.com")[0] == 400
    assert call("users", "GET", "/users/me@nhom4.com")[0] == 200     # vẫn còn nguyên


def test_ping(call):
    assert call("users", "GET", "/users/_ping")[1]["ok"] is True


def test_tao_user_that_bai_giua_chung_thi_khong_de_lai_tai_khoan(aws, call):
    """Mật khẩu bị Cognito từ chối -> trả 400 và tài khoản vừa tạo phải bị dọn đi."""
    from botocore.exceptions import ClientError
    app = aws["apps"]["users"]
    real = app.cognito_client

    class Weak:
        def __getattr__(self, name):
            if name == "admin_set_user_password":
                def boom(**kw):
                    raise ClientError({"Error": {"Code": "InvalidPasswordException",
                                                 "Message": "Password did not conform with policy"}}, name)
                return boom
            return getattr(real, name)

    app.cognito_client = Weak()
    try:
        status, d = make_user(call, "weak@gmail.com", password="123")
    finally:
        app.cognito_client = real
    assert status == 400 and "Password" in d["message"]
    assert call("users", "GET", "/users/weak@gmail.com")[0] == 404          # không còn tài khoản mồ côi


def test_duong_dan_co_tien_to_stage_van_chay(aws):
    from conftest import make_event
    import json
    ev = make_event("GET", "/prod/dashboard/_ping", groups="Staff")
    ev["requestContext"]["stage"] = "prod"
    resp = aws["apps"]["dashboard"].lambda_handler(ev, None)
    assert resp["statusCode"] == 200 and json.loads(resp["body"])["ok"] is True
