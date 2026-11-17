"""api-users-handler - Module 1: Quản lý tài khoản Cognito & phân quyền (Admin / Staff).
Route: /users, /users/{proxy+}

  GET    /users/me                       Admin, Staff   thông tin người đang đăng nhập (đọc từ JWT)
  GET    /users                          Admin          [{id, username, email, role, status, enabled, createdAt}]
  GET    /users/{username}               Admin          {username} có thể là email hoặc id (sub)
  POST   /users                          Admin          {email, password, role}
  PUT    /users/{username}/role          Admin          {role: Admin|Staff}
  PUT    /users/{username}/status        Admin          {enabled: true|false}  (khóa / mở khóa tài khoản)
  DELETE /users/{username}               Admin          xóa hẳn tài khoản

Lưu ý: JWT Authorizer chỉ xác thực, không chặn theo group -> mọi đường dẫn (trừ /users/me) tự kiểm tra Admin.
Không cho Admin tự xóa / tự khóa / tự hạ quyền chính mình (tránh khóa chết hệ thống).
"""
import re

from botocore.exceptions import ClientError
from common import *

ROLES = ("Admin", "Staff")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _attr(user, name):
    for a in user.get("Attributes") or user.get("UserAttributes") or []:
        if a["Name"] == name:
            return a["Value"]
    return None


def _shape(cog_user, role):
    return {
        "id": _attr(cog_user, "sub"),
        "username": cog_user["Username"],
        "email": _attr(cog_user, "email"),
        "role": role,
        "status": cog_user.get("UserStatus"),
        "enabled": cog_user.get("Enabled", True),
        "createdAt": cog_user["UserCreateDate"].strftime("%Y-%m-%dT%H:%M:%SZ")
        if cog_user.get("UserCreateDate") else None,
    }


def _call(fn, **kwargs):
    """Gọi Cognito và đổi các lỗi thường gặp thành mã HTTP dễ hiểu."""
    try:
        return fn(UserPoolId=USER_POOL_ID, **kwargs)
    except ClientError as exc:
        code = exc.response["Error"]["Code"]
        if code == "UserNotFoundException":
            raise ApiError(404, "Không tìm thấy người dùng")
        if code == "UsernameExistsException":
            raise ApiError(409, "Email này đã có tài khoản")
        if code in ("InvalidPasswordException", "InvalidParameterException"):
            raise ApiError(400, exc.response["Error"].get("Message", "Tham số không hợp lệ"))
        raise


def _group_of(username):
    groups = _call(cognito_client.admin_list_groups_for_user, Username=username)["Groups"]
    names = {g["GroupName"] for g in groups}
    return "Admin" if "Admin" in names else "Staff"


def _resolve(identifier):
    """Tìm user theo email hoặc id; trả về bản ghi chuẩn (Username thật trong pool)."""
    return _call(cognito_client.admin_get_user, Username=identifier)


def _is_self(cog_user, caller):
    return (_attr(cog_user, "email") or "").lower() == caller["email"].lower()


def _list_users():
    members = {}
    for role in ROLES:
        token = None
        while True:
            kw = {"GroupName": role}
            if token:
                kw["NextToken"] = token
            resp = _call(cognito_client.list_users_in_group, **kw)
            for u in resp["Users"]:
                members[u["Username"]] = role if members.get(u["Username"]) != "Admin" else "Admin"
            token = resp.get("NextToken")
            if not token:
                break
    users, token = [], None
    while True:
        kw = {"PaginationToken": token} if token else {}
        resp = _call(cognito_client.list_users, **kw)
        users.extend(resp["Users"])
        token = resp.get("PaginationToken")
        if not token:
            break
    out = [_shape(u, members.get(u["Username"], "Staff")) for u in users]
    out.sort(key=lambda u: (u["createdAt"] or ""), reverse=True)
    return build_response(200, out)


def _create_user(body):
    email = clean_str(body.get("email"), "email", max_len=254).lower()
    if not EMAIL_RE.match(email):
        raise ApiError(400, "Email không hợp lệ")
    password = body.get("password")
    if not isinstance(password, str) or not password:
        raise ApiError(400, "Thiếu trường bắt buộc: password")
    role = clean_str(body.get("role"), "role")
    if role not in ROLES:
        raise ApiError(400, "role chỉ nhận Admin hoặc Staff")

    created = _call(cognito_client.admin_create_user, Username=email, MessageAction="SUPPRESS",
                    UserAttributes=[{"Name": "email", "Value": email},
                                    {"Name": "email_verified", "Value": "true"}])["User"]
    username = created["Username"]
    try:
        # Đặt mật khẩu vĩnh viễn -> trạng thái CONFIRMED, đăng nhập được ngay, không bị bắt đổi mật khẩu
        _call(cognito_client.admin_set_user_password, Username=username, Password=password, Permanent=True)
        _call(cognito_client.admin_add_user_to_group, Username=username, GroupName=role)
    except Exception:
        # tránh để lại tài khoản "nửa vời" (không có mật khẩu hoặc chưa có role)
        try:
            cognito_client.admin_delete_user(UserPoolId=USER_POOL_ID, Username=username)
        except ClientError:
            logger.exception("Không dọn được user %s sau khi tạo lỗi", username)
        raise
    return build_response(201, {"message": "Created", "email": email, "role": role, "username": username})


def _set_role(identifier, body, caller):
    role = clean_str(body.get("role"), "role")
    if role not in ROLES:
        raise ApiError(400, "role chỉ nhận Admin hoặc Staff")
    target = _resolve(identifier)
    if _is_self(target, caller) and role != caller["role"]:
        raise ApiError(400, "Không thể tự đổi quyền của chính mình")
    username = target["Username"]
    _call(cognito_client.admin_add_user_to_group, Username=username, GroupName=role)
    for other in ROLES:
        if other != role:
            _call(cognito_client.admin_remove_user_from_group, Username=username, GroupName=other)
    return build_response(200, {"message": "Updated successfully", "username": username, "role": role})


def _set_status(identifier, enabled, caller):
    target = _resolve(identifier)
    if not enabled and _is_self(target, caller):
        raise ApiError(400, "Không thể tự khóa tài khoản của chính mình")
    fn = cognito_client.admin_enable_user if enabled else cognito_client.admin_disable_user
    _call(fn, Username=target["Username"])
    return build_response(200, {"message": "Updated successfully", "username": target["Username"],
                                "enabled": enabled})


def _delete_user(identifier, caller):
    target = _resolve(identifier)
    if _is_self(target, caller):
        raise ApiError(400, "Không thể tự xóa tài khoản của chính mình")
    _call(cognito_client.admin_delete_user, Username=target["Username"])
    return build_response(200, {"message": "Deleted successfully", "username": target["Username"]})


def _route(method, path, user, event):
    parts = path_segments(path)
    if not parts or parts[0] != "users":
        raise ApiError(404, "Không tìm thấy đường dẫn")
    ident = parts[1] if len(parts) > 1 else None
    action = parts[2] if len(parts) > 2 else None

    if ident == "_ping":
        return run_ping("api-users-handler", user, lambda: {
            "usersVisible": len(cognito_client.list_users(UserPoolId=USER_POOL_ID, Limit=1)["Users"])})
    if ident == "me" and method == "GET":
        return build_response(200, {"email": user["email"], "role": user["role"]})

    denied = require_role(user, "Admin")
    if denied:
        return denied

    if ident is None:
        if method == "GET":
            return _list_users()
        if method == "POST":
            return _create_user(body_or_400(event))
    elif action is None:
        if method == "GET":
            target = _resolve(ident)
            return build_response(200, _shape(target, _group_of(target["Username"])))
        if method == "DELETE":
            return _delete_user(ident, user)
    elif action == "role" and method == "PUT":
        return _set_role(ident, body_or_400(event), user)
    elif action == "status" and method == "PUT":
        enabled = body_or_400(event).get("enabled")
        if not isinstance(enabled, bool):
            raise ApiError(400, "enabled phải là true hoặc false")
        return _set_status(ident, enabled, user)
    raise ApiError(405, f"Không hỗ trợ {method} cho đường dẫn này")


def lambda_handler(event, context):
    return run_handler(event, _route)
