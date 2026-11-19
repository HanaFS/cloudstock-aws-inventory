import os
import re
from datetime import datetime, timezone

from boto3.dynamodb.conditions import Attr

from ..common.dynamodb import dynamodb, is_conditional_failure, scan_all, scan_page
from ..common.http import ApiError, parse_body, require_any_group, success, with_error_handling

PRODUCT_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def _table(name):
    return dynamodb.Table(os.environ[name])


def _validate_product(input_data, existing, product_id):
    if input_data.get("imageUrl") not in (None, ""):
        raise ApiError(400, "UPLOAD_REQUIRED", "Hãy tải ảnh lên S3 và gửi imageKey; không gửi URL hoặc Base64 trong request.")
    values = {**(existing or {}), **input_data, "productId": product_id}
    if not isinstance(product_id, str) or not PRODUCT_ID_PATTERN.fullmatch(product_id):
        raise ApiError(400, "INVALID_PRODUCT_ID", "productId không hợp lệ.")
    name = values.get("name", "").strip() if isinstance(values.get("name"), str) else ""
    category = values.get("category", "").strip() if isinstance(values.get("category"), str) else ""
    if not name or len(name) > 200:
        raise ApiError(400, "INVALID_NAME", "Tên sản phẩm là bắt buộc và tối đa 200 ký tự.")
    if not category or len(category) > 100:
        raise ApiError(400, "INVALID_CATEGORY", "Danh mục là bắt buộc và tối đa 100 ký tự.")
    for field in ("price", "quantity", "minThreshold"):
        value = values.get(field)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ApiError(400, f"INVALID_{field.upper()}", f"{field} phải là số nguyên không âm.")
    supplier_id = values.get("supplierId") or None
    if supplier_id is not None and (not isinstance(supplier_id, str) or len(supplier_id) > 64):
        raise ApiError(400, "INVALID_SUPPLIER_ID", "supplierId không hợp lệ.")
    image_key = values.get("imageKey") or None
    if image_key is not None and (not isinstance(image_key, str) or len(image_key) > 1024):
        raise ApiError(400, "INVALID_IMAGE_KEY", "imageKey không hợp lệ.")
    return {
        "productId": product_id,
        "name": name,
        "category": category,
        "price": values["price"],
        "quantity": values["quantity"],
        "minThreshold": values["minThreshold"],
        "supplierId": supplier_id,
        "imageKey": image_key,
        "updatedAt": datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
    }


def _serialize_product(product):
    return {
        "productId": product["productId"],
        "name": product["name"],
        "category": product["category"],
        "price": product["price"],
        "quantity": product["quantity"],
        "minThreshold": product["minThreshold"],
        "supplierId": product.get("supplierId"),
        "imageKey": product.get("imageKey"),
        "imageUrl": product.get("imageUrl"),
        "updatedAt": product.get("updatedAt"),
    }


def _assert_supplier_exists(supplier_id):
    if supplier_id and not _table("SUPPLIERS_TABLE").get_item(Key={"supplierId": supplier_id}).get("Item"):
        raise ApiError(400, "UNKNOWN_SUPPLIER", "Nhà cung cấp không tồn tại.")


@with_error_handling
def handler(event, context=None):
    require_any_group(event, ["Admin", "Staff"])
    products = _table("PRODUCTS_TABLE")
    method = event.get("httpMethod")
    product_id = (event.get("pathParameters") or {}).get("productId")

    if method == "GET" and not product_id:
        params = event.get("queryStringParameters") or {}
        filter_expression = Attr("quantity").lt(Attr("minThreshold")) if params.get("filter") == "low-stock" else None
        page = scan_page(products, event, "productId", filter_expression)
        return success([_serialize_product(item) for item in page["items"]], extra={"nextToken": page["nextToken"]} if page["nextToken"] else None)
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
            _table("TRANSACTIONS_TABLE"),
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
