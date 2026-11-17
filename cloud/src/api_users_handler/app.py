"""api-users-handler - Module 1: Quản lý tài khoản Cognito & phân quyền.
Route: /users, /users/{proxy+}

TODO (backend) theo tài liệu nhóm:
  GET    /users                      (Admin) -> danh sách user + role + status
  POST   /users                      (Admin) body {email, password, role} -> tạo user + gán group
  PUT    /users/{username}/role      (Admin) body {role}
  DELETE /users/{username}           (Admin) xóa / vô hiệu hóa
Gợi ý: cognito_client.list_users / admin_create_user / admin_add_user_to_group ...
"""
from common import *


def lambda_handler(event, context):
    method, path = get_request_info(event)
    user = get_current_user(event)

    if path.endswith("/_ping"):
        return run_ping("api-users-handler", user, lambda: {
            "usersVisible": len(cognito_client.list_users(UserPoolId=USER_POOL_ID, Limit=1)["Users"]),
        })

    denied = require_role(user, "Admin")  # toàn bộ module này chỉ dành cho Admin
    if denied:
        return denied

    return not_implemented("api-users-handler", method, path)
