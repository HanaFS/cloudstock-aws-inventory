import re

from boto3.dynamodb.conditions import Attr

from ..common.dynamodb import dynamodb, is_conditional_failure, scan_all, scan_page, table_name
from ..common.http import ApiError, parse_body, require_any_group, success, with_error_handling

SUPPLIER_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def _table(name):
    return dynamodb.Table(table_name(name))


def _optional_string(value, field, max_length):
    if value in (None, ""):
        return None
    if not isinstance(value, str) or len(value.strip()) > max_length:
        raise ApiError(400, f"INVALID_{field.upper()}", f"{field} không hợp lệ.")
    return value.strip()


def _validate_supplier(input_data, existing, supplier_id):
    values = {**(existing or {}), **input_data, "supplierId": supplier_id}
    name = values.get("name", "").strip() if isinstance(values.get("name"), str) else ""
    if not isinstance(supplier_id, str) or not SUPPLIER_ID_PATTERN.fullmatch(supplier_id):
        raise ApiError(400, "INVALID_SUPPLIER_ID", "supplierId không hợp lệ.")
    if not name or len(name) > 200:
        raise ApiError(400, "INVALID_NAME", "Tên nhà cung cấp là bắt buộc và tối đa 200 ký tự.")
    return {
        "supplierId": supplier_id,
        "name": name,
        "phone": _optional_string(values.get("phone"), "phone", 40),
        "address": _optional_string(values.get("address"), "address", 500),
    }


@with_error_handling
def handler(event, context=None):
    require_any_group(event, ["Admin", "Staff"])
    suppliers = _table("TABLE_SUPPLIERS")
    method = event.get("httpMethod")
    supplier_id = (event.get("pathParameters") or {}).get("supplierId")
    if method == "GET" and not supplier_id:
        page = scan_page(suppliers, event, "supplierId")
        return success(page["items"], extra={"nextToken": page["nextToken"]} if page["nextToken"] else None)
    if method == "GET" and supplier_id:
        item = suppliers.get_item(Key={"supplierId": supplier_id}).get("Item")
        if not item:
            raise ApiError(404, "SUPPLIER_NOT_FOUND", "Không tìm thấy nhà cung cấp.")
        return success(item)
    if method == "POST" and not supplier_id:
        body = parse_body(event)
        supplier = _validate_supplier(body, None, body.get("supplierId"))
        try:
            suppliers.put_item(Item=supplier, ConditionExpression=Attr("supplierId").not_exists())
        except Exception as error:
            if is_conditional_failure(error):
                raise ApiError(409, "SUPPLIER_EXISTS", "Mã nhà cung cấp đã tồn tại.") from error
            raise
        return success(supplier, 201)
    if method == "PUT" and supplier_id:
        current = suppliers.get_item(Key={"supplierId": supplier_id}).get("Item")
        if not current:
            raise ApiError(404, "SUPPLIER_NOT_FOUND", "Không tìm thấy nhà cung cấp.")
        supplier = _validate_supplier(parse_body(event), current, supplier_id)
        try:
            result = suppliers.update_item(
                Key={"supplierId": supplier_id},
                UpdateExpression="SET #name = :name, #phone = :phone, #address = :address",
                ConditionExpression=Attr("supplierId").exists(),
                ExpressionAttributeNames={"#name": "name", "#phone": "phone", "#address": "address"},
                ExpressionAttributeValues={":name": supplier["name"], ":phone": supplier["phone"], ":address": supplier["address"]},
                ReturnValues="ALL_NEW",
            )
            return success(result["Attributes"])
        except Exception as error:
            if is_conditional_failure(error):
                raise ApiError(404, "SUPPLIER_NOT_FOUND", "Không tìm thấy nhà cung cấp.") from error
            raise
    if method == "DELETE" and supplier_id:
        if not suppliers.get_item(Key={"supplierId": supplier_id}).get("Item"):
            raise ApiError(404, "SUPPLIER_NOT_FOUND", "Không tìm thấy nhà cung cấp.")
        if scan_all(_table("TABLE_PRODUCTS"), FilterExpression=Attr("supplierId").eq(supplier_id), ProjectionExpression="productId"):
            raise ApiError(409, "SUPPLIER_IN_USE", "Không thể xóa nhà cung cấp đang được liên kết với sản phẩm.")
        if scan_all(_table("TABLE_TRANSACTIONS"), FilterExpression=Attr("supplierId").eq(supplier_id), ProjectionExpression="transactionId"):
            raise ApiError(409, "SUPPLIER_HAS_HISTORY", "Không thể xóa nhà cung cấp đã có lịch sử giao dịch.")
        try:
            suppliers.delete_item(Key={"supplierId": supplier_id}, ConditionExpression=Attr("supplierId").exists())
        except Exception as error:
            if is_conditional_failure(error):
                raise ApiError(404, "SUPPLIER_NOT_FOUND", "Không tìm thấy nhà cung cấp.") from error
            raise
        return success({"deleted": True})
    raise ApiError(404, "ROUTE_NOT_FOUND", "Không tìm thấy endpoint.")
