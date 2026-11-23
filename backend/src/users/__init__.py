import os
import re

import boto3
from botocore.exceptions import ClientError

from ..common.dynamodb import parse_limit
from ..common.http import ApiError, parse_body, require_any_group, success, with_error_handling

ALLOWED_ROLES = {"Admin", "Staff"}
ALLOWED_STATUSES = {"ACTIVE", "DISABLED"}
SUBJECT_PATTERN = re.compile(r"^[0-9a-fA-F-]{36}$")


def _client():
    if os.environ.get("LOCAL_API") == "true" and not os.environ.get("COGNITO_ENDPOINT"):
        raise ApiError(503, "LOCAL_SERVICE_UNAVAILABLE", "Cognito API không được cấu hình cho chế độ local.")
    options = {}
    if os.environ.get("COGNITO_ENDPOINT"):
        options["endpoint_url"] = os.environ["COGNITO_ENDPOINT"]
    return boto3.client("cognito-idp", **options)


def _user_pool_id():
    value = os.environ.get("USER_POOL_ID")
    if not value:
        raise RuntimeError("USER_POOL_ID environment variable is required.")
    return value


def _attributes_map(user):
    return {item["Name"]: item["Value"] for item in user.get("Attributes", [])}


def _groups(client, username):
    groups = []
    token = None
    while True:
        request = {"UserPoolId": _user_pool_id(), "Username": username}
        if token:
            request["NextToken"] = token
        result = client.admin_list_groups_for_user(**request)
        groups.extend(item["GroupName"] for item in result.get("Groups", []))
        token = result.get("NextToken")
        if not token:
            return groups


def _serialize_user(client, user):
    attributes = _attributes_map(user)
    groups = _groups(client, user["Username"])
    role = next((group for group in groups if group in ALLOWED_ROLES), None)
    return {
        "id": attributes.get("sub", user["Username"]),
        "username": user["Username"],
        "fullName": attributes.get("name", user["Username"]),
        "email": attributes.get("email", ""),
        "role": role,
        "status": "ACTIVE" if user.get("Enabled", True) else "LOCKED",
    }


def _find_user(client, username):
    try:
        user = client.admin_get_user(UserPoolId=_user_pool_id(), Username=username)
    except ClientError as error:
        if error.response.get("Error", {}).get("Code") == "UserNotFoundException":
            if not SUBJECT_PATTERN.fullmatch(username):
                raise ApiError(404, "USER_NOT_FOUND", "Không tìm thấy người dùng.") from error
            result = client.list_users(
                UserPoolId=_user_pool_id(),
                Filter=f'sub = "{username}"',
                Limit=1,
            )
            matching_users = result.get("Users", [])
            if not matching_users:
                raise ApiError(404, "USER_NOT_FOUND", "Không tìm thấy người dùng.") from error
            user = client.admin_get_user(
                UserPoolId=_user_pool_id(),
                Username=matching_users[0]["Username"],
            )
        else:
            raise
    user["Enabled"] = user.get("Enabled", True)
    return user


def _remove_roles(client, username, groups):
    for group in groups:
        if group in ALLOWED_ROLES:
            client.admin_remove_user_from_group(
                UserPoolId=_user_pool_id(),
                Username=username,
                GroupName=group,
            )


def _replace_role(client, username, role):
    if role not in ALLOWED_ROLES:
        raise ApiError(400, "INVALID_ROLE", "role phải là Admin hoặc Staff.")
    groups = _groups(client, username)
    if role not in groups:
        client.admin_add_user_to_group(
            UserPoolId=_user_pool_id(),
            Username=username,
            GroupName=role,
        )
        _remove_roles(client, username, groups)


def _handle_client_error(error):
    code = error.response.get("Error", {}).get("Code")
    if code == "UsernameExistsException":
        raise ApiError(409, "USER_EXISTS", "Tên người dùng đã tồn tại.") from error
    if code == "UserNotFoundException":
        raise ApiError(404, "USER_NOT_FOUND", "Không tìm thấy người dùng.") from error
    if code in ("InvalidParameterException", "InvalidPasswordException"):
        raise ApiError(400, "INVALID_USER", "Thông tin người dùng không hợp lệ.") from error
    raise error


@with_error_handling
def handler(event, context=None):
    require_any_group(event, ["Admin"])
    client = _client()
    pool_id = _user_pool_id()
    method = event.get("httpMethod")
    username = (event.get("pathParameters") or {}).get("userId")

    if method == "GET" and not username:
        params = event.get("queryStringParameters") or {}
        limit = min(parse_limit(event), 60)
        request = {"UserPoolId": pool_id, "Limit": limit}
        token = params.get("nextToken")
        if token:
            request["PaginationToken"] = token
        result = client.list_users(**request)
        users = [_serialize_user(client, item) for item in result.get("Users", [])]
        next_token = result.get("PaginationToken")
        return success(users, extra={"nextToken": next_token} if next_token else None)

    if method == "GET" and username:
        return success(_serialize_user(client, _find_user(client, username)))

    if method == "POST" and not username:
        body = parse_body(event)
        username = body.get("username")
        email = body.get("email")
        full_name = body.get("fullName", username)
        role = body.get("role")
        if not isinstance(username, str) or not username.strip() or len(username) > 128:
            raise ApiError(400, "INVALID_USERNAME", "username là bắt buộc và tối đa 128 ký tự.")
        if not isinstance(email, str) or "@" not in email or len(email) > 320:
            raise ApiError(400, "INVALID_EMAIL", "email không hợp lệ.")
        if not isinstance(full_name, str) or not full_name.strip() or len(full_name) > 200:
            raise ApiError(400, "INVALID_NAME", "fullName là bắt buộc và tối đa 200 ký tự.")
        if role not in ALLOWED_ROLES:
            raise ApiError(400, "INVALID_ROLE", "role phải là Admin hoặc Staff.")
        try:
            client.admin_create_user(
                UserPoolId=pool_id,
                Username=username.strip(),
                UserAttributes=[
                    {"Name": "email", "Value": email.strip()},
                    {"Name": "name", "Value": full_name.strip()},
                    {"Name": "email_verified", "Value": "true"},
                ],
                DesiredDeliveryMediums=["EMAIL"],
            )
            client.admin_add_user_to_group(
                UserPoolId=pool_id,
                Username=username.strip(),
                GroupName=role,
            )
            created = _find_user(client, username.strip())
            return success(_serialize_user(client, created), 201)
        except ClientError as error:
            _handle_client_error(error)

    if method == "PUT" and username:
        body = parse_body(event)
        if body.get("status") == "LOCKED":
            body["status"] = "DISABLED"
        allowed_fields = {"email", "fullName", "role", "status"}
        if not body or set(body) - allowed_fields:
            raise ApiError(400, "INVALID_USER_UPDATE", "Gửi ít nhất một trường hợp lệ: email, fullName, role, status.")
        current = _serialize_user(client, _find_user(client, username))
        username = current["username"]
        claims = event.get("requestContext", {}).get("authorizer", {}).get("claims", {})
        actor = claims.get("cognito:username") or claims.get("username")
        if actor == username and body.get("role", current["role"]) != "Admin":
            raise ApiError(409, "SELF_ROLE_CHANGE", "Không thể tự hạ quyền Admin của chính mình.")
        try:
            attributes = []
            if "email" in body:
                if not isinstance(body["email"], str) or "@" not in body["email"]:
                    raise ApiError(400, "INVALID_EMAIL", "email không hợp lệ.")
                attributes.append({"Name": "email", "Value": body["email"].strip()})
            if "fullName" in body:
                if not isinstance(body["fullName"], str) or not body["fullName"].strip():
                    raise ApiError(400, "INVALID_NAME", "fullName không hợp lệ.")
                attributes.append({"Name": "name", "Value": body["fullName"].strip()})
            if attributes:
                client.admin_update_user_attributes(
                    UserPoolId=pool_id,
                    Username=username,
                    UserAttributes=attributes,
                )
            if "role" in body:
                _replace_role(client, username, body["role"])
            if "status" in body:
                if body["status"] not in ALLOWED_STATUSES:
                    raise ApiError(400, "INVALID_STATUS", "status phải là ACTIVE hoặc DISABLED.")
                action = "admin_enable_user" if body["status"] == "ACTIVE" else "admin_disable_user"
                getattr(client, action)(UserPoolId=pool_id, Username=username)
            return success(_serialize_user(client, _find_user(client, username)))
        except ClientError as error:
            _handle_client_error(error)

    if method == "POST" and username and event.get("path", "").endswith("/reset-password"):
        user = _find_user(client, username)
        try:
            client.admin_reset_user_password(
                UserPoolId=pool_id,
                Username=user["Username"],
            )
            return success({"passwordResetRequested": True})
        except ClientError as error:
            _handle_client_error(error)

    if method == "DELETE" and username:
        user = _find_user(client, username)
        username = user["Username"]
        claims = event.get("requestContext", {}).get("authorizer", {}).get("claims", {})
        actor = claims.get("cognito:username") or claims.get("username")
        if actor == username:
            raise ApiError(409, "SELF_DELETE", "Không thể tự xóa tài khoản đang đăng nhập.")
        try:
            client.admin_delete_user(UserPoolId=pool_id, Username=username)
            return success({"deleted": True})
        except ClientError as error:
            _handle_client_error(error)

    raise ApiError(404, "ROUTE_NOT_FOUND", "Không tìm thấy endpoint.")
