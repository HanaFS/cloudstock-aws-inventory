import pytest

PRODUCT = {"name": "Laptop Dell XPS 15", "category": "Laptop", "price": 32500000,
           "stockQuantity": 25, "minThreshold": 5, "imageUrl": ""}


def make_product(call, **over):
    status, data = call("products", "POST", "/products", body={**PRODUCT, **over}, role="Staff")
    assert status == 201, data
    return data


def test_create_product_tu_sinh_id_status_updatedat(clean, call):
    p = make_product(call)
    assert p["productId"].startswith("PRD-")
    assert p["status"] == "IN_STOCK"
    assert p["updatedAt"].endswith("Z")
    assert set(p) == {"productId", "name", "category", "price", "stockQuantity",
                      "minThreshold", "status", "imageUrl", "updatedAt"}  # đúng 9 trường


def test_create_product_het_hang_khi_ton_bang_0(clean, call):
    assert make_product(call, stockQuantity=0)["status"] == "OUT_OF_STOCK"


@pytest.mark.parametrize("bad", [
    {"name": ""}, {"name": None}, {"category": ""}, {"price": -1}, {"price": "abc"},
    {"stockQuantity": -5}, {"stockQuantity": 2.5}, {"minThreshold": -1}, {"price": True},
])
def test_create_product_du_lieu_sai_tra_400(clean, call, bad):
    status, data = call("products", "POST", "/products", body={**PRODUCT, **bad})
    assert status == 400 and data["message"]


def test_body_khong_phai_json_tra_400(clean, aws):
    from conftest import make_event
    ev = make_event("POST", "/products")
    ev["body"] = "{khong-phai-json"
    resp = aws["apps"]["products"].lambda_handler(ev, None)
    assert resp["statusCode"] == 400


def test_get_list_filter_va_get_one(clean, call):
    a = make_product(call, name="Chuột", category="Phụ kiện", stockQuantity=10)
    b = make_product(call, name="Laptop A", category="Laptop", stockQuantity=0)
    _, items = call("products", "GET", "/products")
    assert {i["productId"] for i in items} == {a["productId"], b["productId"]}
    _, items = call("products", "GET", "/products", query={"category": "Laptop"})
    assert [i["productId"] for i in items] == [b["productId"]]
    _, items = call("products", "GET", "/products", query={"status": "IN_STOCK"})
    assert [i["productId"] for i in items] == [a["productId"]]
    _, items = call("products", "GET", "/products", query={"q": "chuột"})
    assert [i["productId"] for i in items] == [a["productId"]]
    status, _ = call("products", "GET", "/products", query={"status": "SAI"})
    assert status == 400
    status, one = call("products", "GET", f"/products/{a['productId']}")
    assert status == 200 and one["name"] == "Chuột"
    assert call("products", "GET", "/products/PRD-KHONG-CO")[0] == 404


def test_update_chi_doi_truong_duoc_gui_va_tinh_lai_status(clean, call):
    p = make_product(call, stockQuantity=10)
    status, u = call("products", "PUT", f"/products/{p['productId']}", body={"price": 1000})
    assert status == 200 and u["price"] == 1000 and u["stockQuantity"] == 10 and u["name"] == p["name"]
    _, u = call("products", "PUT", f"/products/{p['productId']}", body={"stockQuantity": 0})
    assert u["status"] == "OUT_OF_STOCK"
    _, u = call("products", "PUT", f"/products/{p['productId']}", body={"stockQuantity": 3})
    assert u["status"] == "IN_STOCK"
    assert call("products", "PUT", f"/products/{p['productId']}", body={})[0] == 400
    assert call("products", "PUT", "/products/PRD-KHONG-CO", body={"price": 1})[0] == 404


def test_xoa_chi_admin_duoc(clean, call):
    p = make_product(call)
    status, data = call("products", "DELETE", f"/products/{p['productId']}", role="Staff")
    assert status == 403 and "quyền" in data["message"]
    assert call("products", "DELETE", f"/products/{p['productId']}", role="Admin")[0] == 200
    assert call("products", "DELETE", f"/products/{p['productId']}", role="Admin")[0] == 404


# ------------------------------------------------------------------ upload URL
def test_upload_url_products(call):
    status, d = call("products", "POST", "/products/upload-url", role="Staff",
                     body={"folder": "products", "fileName": "laptop.jpg", "contentType": "image/jpeg"})
    assert status == 200
    assert d["s3Key"].startswith("products/") and d["s3Key"].endswith("laptop.jpg")
    assert d["fileUrl"] == f"https://qlkho-test-bucket.s3.ap-southeast-1.amazonaws.com/{d['s3Key']}"
    assert "ap-southeast-1" in d["uploadUrl"] and "X-Amz-Signature" in d["uploadUrl"]
    assert "content-type" in d["uploadUrl"].lower() or "x-amz-signedheaders" in d["uploadUrl"].lower()


def test_upload_url_alias_get_va_invoices(call):
    status, d = call("products", "GET", "/products/presigned-url",
                     query={"folder": "invoices", "fileName": "hoa don.pdf", "contentType": "application/pdf"})
    assert status == 200 and d["s3Key"].startswith("invoices/") and " " not in d["s3Key"]


@pytest.mark.parametrize("body", [
    {"folder": "khac", "fileName": "a.jpg", "contentType": "image/jpeg"},
    {"folder": "products", "fileName": "a.pdf", "contentType": "application/pdf"},   # pdf không phải ảnh sản phẩm
    {"folder": "products", "fileName": "a.exe", "contentType": "application/x-msdownload"},
    {"folder": "products", "fileName": "", "contentType": "image/png"},
    {"fileName": "a.jpg", "contentType": "image/jpeg"},
])
def test_upload_url_sai_tra_400(call, body):
    assert call("products", "POST", "/products/upload-url", body=body)[0] == 400


def test_upload_url_ten_file_doc_hai_khong_thoat_thu_muc(call):
    _, d = call("products", "POST", "/products/upload-url",
                body={"folder": "products", "fileName": "../../invoices/secret.png", "contentType": "image/png"})
    assert d["s3Key"].startswith("products/") and ".." not in d["s3Key"]
    assert d["s3Key"].count("/") == 1


# ------------------------------------------------------------------- suppliers
def test_suppliers_crud_va_phan_quyen(clean, call):
    body = {"name": "Công ty ABC", "phone": "0909123456", "address": "123 Nguyễn Thị Minh Khai, Q.1"}
    status, s = call("products", "POST", "/suppliers", body=body, role="Staff")
    assert status == 201 and s["supplierId"].startswith("SUP-") and set(s) == {"supplierId", "name", "phone", "address"}
    assert call("products", "GET", f"/suppliers/{s['supplierId']}")[1]["name"] == "Công ty ABC"
    assert len(call("products", "GET", "/suppliers")[1]) == 1
    _, u = call("products", "PUT", f"/suppliers/{s['supplierId']}", body={"phone": "0911222333"}, role="Staff")
    assert u["phone"] == "0911222333" and u["name"] == "Công ty ABC"
    assert call("products", "DELETE", f"/suppliers/{s['supplierId']}", role="Staff")[0] == 403
    assert call("products", "DELETE", f"/suppliers/{s['supplierId']}", role="Admin")[0] == 200
    assert call("products", "GET", f"/suppliers/{s['supplierId']}")[0] == 404


@pytest.mark.parametrize("bad", [{"name": ""}, {"phone": "abc"}, {"address": ""}])
def test_suppliers_du_lieu_sai(clean, call, bad):
    body = {"name": "A", "phone": "0909123456", "address": "X", **bad}
    assert call("products", "POST", "/suppliers", body=body)[0] == 400


def test_route_la_va_ping(clean, call):
    assert call("products", "GET", "/khac")[0] == 404
    assert call("products", "PATCH", "/products/PRD-1")[0] == 405
    status, d = call("products", "GET", "/products/_ping")
    assert status == 200 and d["ok"] is True
