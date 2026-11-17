"""
Khung dùng chung cho 4 hàm Lambda (đóng gói thành Lambda Layer).

Trong mỗi hàm:   from common import *

Giữ nguyên tên hàm theo tài liệu nhóm: build_response, get_current_user,
get_iso_now, DecimalEncoder. Bổ sung thêm: parse_body, get_request_info,
require_role, not_implemented, run_ping.
"""
import os
import json
import base64
import boto3
from botocore.config import Config
from decimal import Decimal
from datetime import datetime, timezone

# 1. Biến môi trường (được gắn sẵn bởi template.yaml)
REGION = os.environ.get("AWS_REGION", "ap-southeast-1")
TABLE_PRODUCTS = os.environ.get("TABLE_PRODUCTS", "Products")
TABLE_SUPPLIERS = os.environ.get("TABLE_SUPPLIERS", "Suppliers")
TABLE_TRANSACTIONS = os.environ.get("TABLE_TRANSACTIONS", "Transactions")
USER_POOL_ID = os.environ.get("USER_POOL_ID", "")
BUCKET_NAME = os.environ.get("BUCKET_NAME", "")
LOG_GROUP_NAMES = [n for n in os.environ.get("LOG_GROUP_NAMES", "").split(",") if n]

dynamodb = boto3.resource("dynamodb", region_name=REGION)
products_table = dynamodb.Table(TABLE_PRODUCTS)
suppliers_table = dynamodb.Table(TABLE_SUPPLIERS)
transactions_table = dynamodb.Table(TABLE_TRANSACTIONS)

# s3v4 + region cụ thể: presigned URL trỏ đúng endpoint vùng Singapore,
# nếu không trình duyệt sẽ bị redirect và lỗi CORS khi upload.
s3_client = boto3.client("s3", region_name=REGION, config=Config(signature_version="s3v4"))
cognito_client = boto3.client("cognito-idp", region_name=REGION)
logs_client = boto3.client("logs", region_name=REGION)


# 2. Chuyển Decimal của DynamoDB sang int/float khi trả JSON
class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return int(obj) if obj % 1 == 0 else float(obj)
        return super(DecimalEncoder, self).default(obj)


# 3. Response chuẩn kèm CORS
def build_response(status_code, body_data):
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Content-Type,Authorization",
            "Access-Control-Allow-Methods": "GET,POST,PUT,DELETE,OPTIONS",
        },
        "body": json.dumps(body_data, cls=DecimalEncoder, ensure_ascii=False),
    }


# 4. Người đang gọi API (lấy từ JWT đã được API Gateway xác thực)
def get_current_user(event):
    auth = event.get("requestContext", {}).get("authorizer", {})
    claims = auth.get("jwt", {}).get("claims", {}) or auth.get("claims", {})
    email = claims.get("email") or claims.get("cognito:username") or "unknown@nhom4.com"
    groups = claims.get("cognito:groups", "")
    role = "Admin" if "Admin" in str(groups) else "Staff"
    return {"email": email, "role": role}


# 5. Thời gian ISO 8601 (createdAt / updatedAt)
def get_iso_now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---- Bổ sung -------------------------------------------------------
def get_request_info(event):
    """Trả về (METHOD, path) từ event của HTTP API (payload v2)."""
    http = event.get("requestContext", {}).get("http", {})
    return http.get("method", "GET").upper(), event.get("rawPath", "/")


def parse_body(event):
    """Trả về dict body JSON; {} nếu rỗng; None nếu JSON hỏng (nên trả 400)."""
    body = event.get("body")
    if not body:
        return {}
    if event.get("isBase64Encoded"):
        body = base64.b64decode(body).decode("utf-8")
    try:
        return json.loads(body, parse_float=Decimal)
    except json.JSONDecodeError:
        return None


def require_role(user, *roles):
    """JWT Authorizer chỉ xác thực, KHÔNG chặn theo group -> tự kiểm tra role ở đây.
    Trả về response 403 nếu không đủ quyền, None nếu hợp lệ."""
    if user["role"] not in roles:
        return build_response(403, {"message": "Bạn không có quyền thực hiện thao tác này"})
    return None


def not_implemented(handler_name, method, path):
    return build_response(501, {
        "message": f"Chưa triển khai: {method} {path}",
        "handler": handler_name,
    })


def run_ping(handler_name, user, check):
    """Kiểm tra nhanh: Lambda <-> quyền IAM <-> dịch vụ AWS hoạt động."""
    try:
        detail = check()
        return build_response(200, {"ok": True, "handler": handler_name, "user": user, "check": detail})
    except Exception as exc:  # noqa: BLE001
        return build_response(500, {"ok": False, "handler": handler_name,
                                    "error": f"{type(exc).__name__}: {exc}"})
