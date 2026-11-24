import re
from datetime import datetime, timezone

from boto3.dynamodb.conditions import Attr

from ..common.dynamodb import dynamodb, is_conditional_failure, scan_all, scan_page, table_name
from ..common.http import ApiError, parse_body, require_any_group, success, with_error_handling

PRODUCT_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def _table(name):
    return dynamodb.Table(table_name(name))


def _validate_product(input_data, existing, product_id):
    input_data = dict(input_data)
    if "quantity" in input_data:
        quantity = input_data.pop("quantity")
        if "stockQuantity" in input_data and input_data["stockQuantity"] != quantity:
            raise ApiError(400, "CONFLICTING_QUANTITY", "quantity và stockQuantity phải có cùng giá trị.")
        input_data["stockQuantity"] = quantity
    values = {**(existing or {}), **input_data, "productId": product_id}
    if not isinstance(product_id, str) or not PRODUCT_ID_PATTERN.fullmatch(product_id):
        raise ApiError(400, "INVALID_PRODUCT_ID", "productId không hợp lệ.")
    name = values.get("name", "").strip() if isinstance(values.get("name"), str) else ""
    category = values.get("category", "").strip() if isinstance(values.get("category"), str) else ""
    if not name or len(name) > 200:
        raise ApiError(400, "INVALID_NAME", "Tên sản phẩm là bắt buộc và tối đa 200 ký tự.")
    if not category or len(category) > 100:
        raise ApiError(400, "INVALID_CATEGORY", "Danh mục là bắt buộc và tối đa 100 ký tự.")
    for field in ("price", "stockQuantity", "minThreshold"):
        value = values.get(field)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            error_field = "STOCK_QUANTITY" if field == "stockQuantity" else field.upper()
            raise ApiError(400, f"INVALID_{error_field}", f"{field} phải là số nguyên không âm.")
    supplier_id = values.get("supplierId") or None
    if supplier_id is not None and (not isinstance(supplier_id, str) or len(supplier_id) > 64):
        raise ApiError(400, "INVALID_SUPPLIER_ID", "supplierId không hợp lệ.")
    image_url = values.get("imageUrl") or None
    if image_url is not None and (
        not isinstance(image_url, str)
        or len(image_url) > 2048
        or not image_url.startswith("https://")
    ):
        raise ApiError(400, "INVALID_IMAGE_URL", "imageUrl phải là URL HTTPS hợp lệ.")
    return {
        "productId": product_id,
        "name": name,
        "category": category,
        "price": values["price"],
        "stockQuantity": values["stockQuantity"],
        "minThreshold": values["minThreshold"],
        "status": "IN_STOCK" if values["stockQuantity"] > 0 else "OUT_OF_STOCK",
        "supplierId": supplier_id,
        "imageUrl": image_url,
        "updatedAt": datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
    }


def _serialize_product(product):
    qty = product.get("stockQuantity")
    if qty is None:
        qty = product.get("quantity", 0)
    status = product.get("status") or ("IN_STOCK" if int(qty) > 0 else "OUT_OF_STOCK")
    return {
        "productId": product["productId"],
        "name": product.get("name", ""),
        "category": product.get("category", "Chưa phân loại"),
        "price": product.get("price", 0),
        "quantity": qty,
        "minThreshold": product.get("minThreshold", 5),
        "status": status,
        "supplierId": product.get("supplierId"),
        "imageUrl": product.get("imageUrl"),
        "updatedAt": product.get("updatedAt"),
    }


def _assert_supplier_exists(supplier_id):
    if supplier_id and not _table("TABLE_SUPPLIERS").get_item(Key={"supplierId": supplier_id}).get("Item"):
        raise ApiError(400, "UNKNOWN_SUPPLIER", "Nhà cung cấp không tồn tại.")


@with_error_handling
def handler(event, context=None):
    require_any_group(event, ["Admin", "Staff"])
    products = _table("TABLE_PRODUCTS")
    method = event.get("httpMethod")
    product_id = (event.get("pathParameters") or {}).get("productId")

    if method == "GET" and not product_id:
        params = event.get("queryStringParameters") or {}
        items = scan_all(products)
        if params.get("filter") == "low-stock":
            items = [
                item for item in items
                if int(item.get("stockQuantity") if item.get("stockQuantity") is not None else item.get("quantity", 0)) < int(item.get("minThreshold", 0))
            ]
        return success([_serialize_product(item) for item in items])
    if method == "GET" and product_id:
        item = products.get_item(Key={"productId": product_id}).get("Item")
        if not item:
            raise ApiError(404, "PRODUCT_NOT_FOUND", "Không tìm thấy sản phẩm.")
        return success(_serialize_product(item))
    if method == "POST" and not product_id:
        body = parse_body(event)
        product = _validate_product(body, None, body.get("productId"))
        _assert_supplier_exists(product["supplierId"])
        try:
            products.put_item(Item=product, ConditionExpression=Attr("productId").not_exists())
        except Exception as error:
            if is_conditional_failure(error):
                raise ApiError(409, "PRODUCT_EXISTS", "Mã sản phẩm đã tồn tại.") from error
            raise
        return success(_serialize_product(product), 201)
    if method == "PUT" and product_id:
        current = products.get_item(Key={"productId": product_id}).get("Item")
        if not current:
            raise ApiError(404, "PRODUCT_NOT_FOUND", "Không tìm thấy sản phẩm.")
        product = _validate_product(parse_body(event), current, product_id)
        _assert_supplier_exists(product["supplierId"])
        names = {f"#{field}": field for field in product if field != "productId"}
        values = {f":{field}": value for field, value in product.items() if field != "productId"}
        updates = ", ".join(f"#{field} = :{field}" for field in product if field != "productId")
        try:
            result = products.update_item(
                Key={"productId": product_id},
                UpdateExpression=f"SET {updates}",
                ConditionExpression=Attr("productId").exists(),
                ExpressionAttributeNames=names,
                ExpressionAttributeValues=values,
                ReturnValues="ALL_NEW",
            )
            return success(_serialize_product(result["Attributes"]))
        except Exception as error:
            if is_conditional_failure(error):
                raise ApiError(404, "PRODUCT_NOT_FOUND", "Không tìm thấy sản phẩm.") from error
            raise
    if method == "DELETE" and product_id:
        if not products.get_item(Key={"productId": product_id}).get("Item"):
            raise ApiError(404, "PRODUCT_NOT_FOUND", "Không tìm thấy sản phẩm.")
        history = scan_all(
            _table("TABLE_TRANSACTIONS"),
            FilterExpression=Attr("productId").eq(product_id),
            ProjectionExpression="transactionId",
        )
        if history:
            raise ApiError(409, "PRODUCT_HAS_HISTORY", "Không thể xóa sản phẩm đã có lịch sử giao dịch.")
        try:
            products.delete_item(Key={"productId": product_id}, ConditionExpression=Attr("productId").exists())
        except Exception as error:
            if is_conditional_failure(error):
                raise ApiError(404, "PRODUCT_NOT_FOUND", "Không tìm thấy sản phẩm.") from error
            raise
        return success({"deleted": True})
    raise ApiError(404, "ROUTE_NOT_FOUND", "Không tìm thấy endpoint.")
