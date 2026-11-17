"""api-products-handler - Module 3: Hàng hóa, nhà cung cấp, S3 pre-signed URL.
Route: /products, /products/{proxy+}, /suppliers, /suppliers/{proxy+}

  GET    /products                  Admin, Staff   ?category=&status=&q=
  GET    /products/{id}             Admin, Staff
  POST   /products                  Admin, Staff   tự sinh productId, status, updatedAt
  PUT    /products/{id}             Admin, Staff   chỉ cập nhật các trường được gửi lên
  DELETE /products/{id}             Admin
  POST   /products/upload-url       Admin, Staff   body {folder, fileName, contentType}
  GET    /products/presigned-url    Admin, Staff   ?folder=&fileName=&contentType=   (tên gọi khác của upload-url)
  GET    /suppliers, /suppliers/{id}                Admin, Staff
  POST   /suppliers, PUT /suppliers/{id}            Admin, Staff
  DELETE /suppliers/{id}                            Admin
"""
import re

from botocore.exceptions import ClientError
from common import *

ALLOWED_UPLOAD_TYPES = {
    "products": {"image/jpeg", "image/png", "image/webp"},
    "invoices": {"application/pdf", "image/jpeg", "image/png"},
}
UPLOAD_URL_TTL = 300  # giây


def _status(stock):
    return "IN_STOCK" if stock > 0 else "OUT_OF_STOCK"


# ----------------------------------------------------------------- products
def _normalize_prod(item):
    if not item:
        return item
    qty = int(item.get("stockQuantity", item.get("quantity", 0)))
    item["stockQuantity"] = qty
    item["quantity"] = qty
    return item


def _list_products(query):
    items = scan_all(products_table)
    category = query.get("category")
    status = query.get("status")
    text = (query.get("q") or "").strip().lower()
    if category:
        items = [i for i in items if i.get("category") == category]
    if status:
        if status not in ("IN_STOCK", "OUT_OF_STOCK"):
            raise ApiError(400, "status chỉ nhận IN_STOCK hoặc OUT_OF_STOCK")
        items = [i for i in items if i.get("status") == status]
    if text:
        items = [i for i in items
                 if text in str(i.get("name", "")).lower() or text in str(i.get("productId", "")).lower()]
    items.sort(key=lambda i: i.get("updatedAt", ""), reverse=True)
    return build_response(200, [_normalize_prod(i) for i in items])


def _get_product(product_id):
    item = products_table.get_item(Key={"productId": product_id}).get("Item")
    if not item:
        raise ApiError(404, f"Không tìm thấy sản phẩm {product_id}")
    return build_response(200, _normalize_prod(item))


def _create_product(body):
    raw_stock = body.get("stockQuantity") if "stockQuantity" in body else body.get("quantity", 0)
    stock = to_int(raw_stock, "quantity")
    item = {
        "productId": clean_str(body.get("productId"), "productId", required=False) or new_id("PRD"),
        "name": clean_str(body.get("name"), "name"),
        "category": clean_str(body.get("category"), "category", max_len=100),
        "price": to_number(body.get("price"), "price"),
        "stockQuantity": stock,
        "quantity": stock,
        "minThreshold": to_int(body.get("minThreshold", 0), "minThreshold"),
        "status": _status(stock),
        "imageUrl": clean_str(body.get("imageUrl"), "imageUrl", required=False, max_len=1000) or "",
        "updatedAt": get_iso_now(),
    }
    if "supplierId" in body and body["supplierId"]:
        item["supplierId"] = clean_str(body.get("supplierId"), "supplierId", max_len=64)
    products_table.put_item(Item=item, ConditionExpression="attribute_not_exists(productId)")
    return build_response(201, item)


def _update_product(product_id, body):
    sets, names, values = [], {}, {}

    def add(field, value):
        sets.append(f"#{field} = :{field}")
        names[f"#{field}"] = field
        values[f":{field}"] = value

    if "name" in body:
        add("name", clean_str(body["name"], "name"))
    if "category" in body:
        add("category", clean_str(body["category"], "category", max_len=100))
    if "price" in body:
        add("price", to_number(body["price"], "price"))
    if "minThreshold" in body:
        add("minThreshold", to_int(body["minThreshold"], "minThreshold"))
    if "imageUrl" in body:
        add("imageUrl", clean_str(body["imageUrl"], "imageUrl", required=False, max_len=1000) or "")
    if "supplierId" in body:
        add("supplierId", clean_str(body.get("supplierId"), "supplierId", required=False, max_len=64) or "")
    if "stockQuantity" in body or "quantity" in body:
        raw_stock = body.get("stockQuantity") if "stockQuantity" in body else body.get("quantity")
        stock = to_int(raw_stock, "quantity")
        add("stockQuantity", stock)
        add("quantity", stock)
        add("status", _status(stock))  # luôn tính lại status theo tồn kho mới
    if not sets:
        raise ApiError(400, "Không có trường nào để cập nhật")
    add("updatedAt", get_iso_now())

    try:
        resp = products_table.update_item(
            Key={"productId": product_id},
            UpdateExpression="SET " + ", ".join(sets),
            ExpressionAttributeNames=names,
            ExpressionAttributeValues=values,
            ConditionExpression="attribute_exists(productId)",
            ReturnValues="ALL_NEW",
        )
    except ClientError as exc:
        if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
            raise ApiError(404, f"Không tìm thấy sản phẩm {product_id}")
        raise
    return build_response(200, _normalize_prod(resp["Attributes"]))


def _delete_product(product_id):
    try:
        products_table.delete_item(Key={"productId": product_id},
                                   ConditionExpression="attribute_exists(productId)")
    except ClientError as exc:
        if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
            raise ApiError(404, f"Không tìm thấy sản phẩm {product_id}")
        raise
    return build_response(200, {"message": "Deleted successfully", "productId": product_id})


# --------------------------------------------------------------- upload URL
def _safe_filename(name):
    name = name.replace("\\", "/").split("/")[-1]           # bỏ đường dẫn
    stem, dot, ext = name.rpartition(".")
    if not dot:
        stem, ext = name, ""
    stem = re.sub(r"[^A-Za-z0-9._-]+", "-", stem).strip("-._")[:60] or "file"
    ext = re.sub(r"[^A-Za-z0-9]", "", ext)[:8].lower()
    return f"{stem}.{ext}" if ext else stem


def _upload_url(params):
    folder = clean_str(params.get("folder"), "folder")
    if folder not in ALLOWED_UPLOAD_TYPES:
        raise ApiError(400, "folder chỉ nhận 'products' hoặc 'invoices'")
    file_name = clean_str(params.get("fileName"), "fileName", max_len=200)
    content_type = clean_str(params.get("contentType"), "contentType", max_len=100).lower()
    if content_type not in ALLOWED_UPLOAD_TYPES[folder]:
        allowed = ", ".join(sorted(ALLOWED_UPLOAD_TYPES[folder]))
        raise ApiError(400, f"contentType không hợp lệ cho thư mục {folder}. Cho phép: {allowed}")

    key = f"{folder}/{uuid.uuid4().hex[:8]}_{_safe_filename(file_name)}"
    upload_url = s3_client.generate_presigned_url(
        "put_object",
        Params={"Bucket": BUCKET_NAME, "Key": key, "ContentType": content_type},
        ExpiresIn=UPLOAD_URL_TTL,
    )
    return build_response(200, {
        "uploadUrl": upload_url,      # frontend PUT file vào đây, header Content-Type phải = contentType đã gửi
        "fileUrl": public_url(key),   # với products/: lưu vào imageUrl. Với invoices/: private, không mở trực tiếp được
        "s3Key": key,                 # với invoices/: lưu vào invoiceUrl của giao dịch
        "expiresIn": UPLOAD_URL_TTL,
    })


# ---------------------------------------------------------------- suppliers
def _supplier_fields(body, partial=False):
    out = {}
    for field, max_len in (("name", 200), ("phone", 30), ("address", 500)):
        if partial and field not in body:
            continue
        out[field] = clean_str(body.get(field), field, max_len=max_len)
    if "phone" in out and not re.fullmatch(r"[0-9+\-. ()]{6,30}", out["phone"]):
        raise ApiError(400, "Số điện thoại không hợp lệ")
    return out


def _supplier_crud(method, parts, body_fn, user):
    sid = parts[1] if len(parts) > 1 else None
    if method == "GET" and sid is None:
        items = scan_all(suppliers_table)
        items.sort(key=lambda i: str(i.get("name", "")).lower())
        return build_response(200, items)
    if method == "GET":
        item = suppliers_table.get_item(Key={"supplierId": sid}).get("Item")
        if not item:
            raise ApiError(404, f"Không tìm thấy nhà cung cấp {sid}")
        return build_response(200, item)
    if method == "POST" and sid is None:
        item = {"supplierId": new_id("SUP"), **_supplier_fields(body_fn())}
        suppliers_table.put_item(Item=item, ConditionExpression="attribute_not_exists(supplierId)")
        return build_response(201, item)
    if method == "PUT" and sid:
        fields = _supplier_fields(body_fn(), partial=True)
        if not fields:
            raise ApiError(400, "Không có trường nào để cập nhật")
        names = {f"#{k}": k for k in fields}
        values = {f":{k}": v for k, v in fields.items()}
        try:
            resp = suppliers_table.update_item(
                Key={"supplierId": sid},
                UpdateExpression="SET " + ", ".join(f"#{k} = :{k}" for k in fields),
                ExpressionAttributeNames=names, ExpressionAttributeValues=values,
                ConditionExpression="attribute_exists(supplierId)", ReturnValues="ALL_NEW")
        except ClientError as exc:
            if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
                raise ApiError(404, f"Không tìm thấy nhà cung cấp {sid}")
            raise
        return build_response(200, resp["Attributes"])
    if method == "DELETE" and sid:
        denied = require_role(user, "Admin")
        if denied:
            return denied
        try:
            suppliers_table.delete_item(Key={"supplierId": sid},
                                        ConditionExpression="attribute_exists(supplierId)")
        except ClientError as exc:
            if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
                raise ApiError(404, f"Không tìm thấy nhà cung cấp {sid}")
            raise
        return build_response(200, {"message": "Deleted successfully", "supplierId": sid})
    raise ApiError(405, f"Không hỗ trợ {method} cho đường dẫn này")


# ------------------------------------------------------------------- router
def _route(method, path, user, event):
    parts = path_segments(path)
    if not parts:
        raise ApiError(404, "Không tìm thấy đường dẫn")
    body_fn = lambda: body_or_400(event)  # noqa: E731

    if parts[-1] == "_ping":
        return run_ping("api-products-handler", user, lambda: {
            "dynamodb": [products_table.scan(Limit=1) and "Products ok",
                         suppliers_table.scan(Limit=1) and "Suppliers ok"],
            "presignedUrlSample": s3_client.generate_presigned_url(
                "put_object", Params={"Bucket": BUCKET_NAME, "Key": "products/_ping.txt"},
                ExpiresIn=60).split("?")[0],
        })

    if parts[0] in ("upload-url", "presigned-url"):
        if method == "POST":
            return _upload_url(body_fn())
        if method == "GET":
            return _upload_url(get_query(event))
        raise ApiError(405, f"Không hỗ trợ {method} cho đường dẫn này")

    if parts[0] == "suppliers":
        return _supplier_crud(method, parts, body_fn, user)

    if parts[0] != "products":
        raise ApiError(404, "Không tìm thấy đường dẫn")
    pid = parts[1] if len(parts) > 1 else None

    # đường dẫn đặc biệt phải xét trước {productId}
    if pid in ("upload-url", "presigned-url"):
        if method == "POST":
            return _upload_url(body_fn())
        if method == "GET":
            return _upload_url(get_query(event))
        raise ApiError(405, f"Không hỗ trợ {method} cho đường dẫn này")

    if method == "GET":
        return _get_product(pid) if pid else _list_products(get_query(event))
    if method == "POST" and pid is None:
        return _create_product(body_fn())
    if method == "PUT" and pid:
        return _update_product(pid, body_fn())
    if method == "DELETE" and pid:
        denied = require_role(user, "Admin")
        if denied:
            return denied
        return _delete_product(pid)
    raise ApiError(405, f"Không hỗ trợ {method} cho đường dẫn này")


def lambda_handler(event, context):
    return run_handler(event, _route)
