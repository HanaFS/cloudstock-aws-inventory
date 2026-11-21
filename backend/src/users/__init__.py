import os
import re

import boto3

from ..common.http import ApiError, parse_body, require_any_group, success, with_error_handling

USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_+=,.@-]{1,128}$")
EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
ALLOWED_ROLES = {"Admin", "Staff"}
PAGE_SIZE = 60


def _client():
    return boto3.client("cognito-idp")


def _pool_id():
    pool_id = os.environ.get("COGNITO_USER_POOL_ID")
    if not pool_id:
        raise ApiError(500, "USER_POOL_NOT_CONFIGURED", "Cognito User Pool is not configured.")
    return pool_id


def _validate_username(username):
    if not isinstance(username, str) or not USERNAME_PATTERN.fullmatch(username):
        raise ApiError(400, "INVALID_USERNAME", "username is invalid.")
    return username


def _attributes(user):
    return {
        item.get("Name"): item.get("Value")
        for item in user.get("Attributes", [])
        if isinstance(item, dict)
    }


def _user_response(user, role=None):
    username = user.get("Username")
    attributes = _attributes(user)
    if not isinstance(username, str):
        raise ApiError(502, "INVALID_COGNITO_RESPONSE", "Cognito returned an invalid user record.")
    return {
        "id": username,
        "username": username,
        "fullName": attributes.get("name", ""),
        "email": attributes.get("email", ""),
        "role": role,
        "status": "ACTIVE" if user.get("Enabled", True) else "LOCKED",
    }


def _list_users_in_group(client, pool_id, group_name):
    usernames = {}
    next_token = None
    while True:
        request = {"UserPoolId": pool_id, "GroupName": group_name, "Limit": PAGE_SIZE}
        if next_token:
            request["NextToken"] = next_token
        result = client.list_users_in_group(**request)
        for user in result.get("Users", []):
            username = user.get("Username")
            if isinstance(username, str):
                usernames[username] = group_name
        next_token = result.get("NextToken")
        if not next_token:
            return usernames


def _list_all_users(client, pool_id):
    users = []
    next_token = None
    while True:
        request = {"UserPoolId": pool_id, "Limit": PAGE_SIZE}
        if next_token:
            request["PaginationToken"] = next_token
        result = client.list_users(**request)
        users.extend(result.get("Users", []))
        next_token = result.get("PaginationToken")
        if not next_token:
            return users


def _managed_groups(client, pool_id, username):
    groups = client.admin_list_groups_for_user(
        UserPoolId=pool_id, Username=username, Limit=PAGE_SIZE
    ).get("Groups", [])
    managed = {group.get("GroupName") for group in groups}
    managed.intersection_update(ALLOWED_ROLES)
    if len(managed) > 1:
        raise ApiError(409, "USER_ROLE_CONFLICT", "User belongs to multiple managed role groups.")
    return managed


def _active_admin_usernames(client, pool_id):
    usernames = set()
    next_token = None
    while True:
        request = {"UserPoolId": pool_id, "GroupName": "Admin", "Limit": PAGE_SIZE}
        if next_token:
            request["NextToken"] = next_token
        result = client.list_users_in_group(**request)
        usernames.update(
            user.get("Username")
            for user in result.get("Users", [])
            if user.get("Enabled", True) and isinstance(user.get("Username"), str)
        )
        next_token = result.get("NextToken")
        if not next_token:
            return usernames


def _assert_another_admin_remains(client, pool_id):
    if len(_active_admin_usernames(client, pool_id)) <= 1:
        raise ApiError(409, "LAST_ADMIN", "The last active Admin account cannot be disabled or demoted.")


def _cognito_error(error):
    code = getattr(error, "response", {}).get("Error", {}).get("Code")
    if code == "UserNotFoundException":
        raise ApiError(404, "USER_NOT_FOUND", "User not found.") from error
    if code == "UsernameExistsException":
        raise ApiError(409, "USER_EXISTS", "Username already exists.") from error
    if code in ("InvalidParameterException", "InvalidPasswordException"):
        raise ApiError(400, "INVALID_USER_REQUEST", "Cognito rejected the user request.") from error
    raise error


def _list_users(client, pool_id):
    users = _list_all_users(client, pool_id)
    role_by_user = {}
    for role in sorted(ALLOWED_ROLES):
        for username in _list_users_in_group(client, pool_id, role):
            if username in role_by_user and role_by_user[username] != role:
                raise ApiError(409, "USER_ROLE_CONFLICT", "User belongs to multiple managed role groups.")
            role_by_user[username] = role
    return [_user_response(user, role_by_user.get(user.get("Username"))) for user in users]


def _create_user(client, pool_id, event):
    body = parse_body(event)
    username = _validate_username(body.get("username"))
    full_name = body.get("fullName")
    email = body.get("email")
    role = body.get("role", "Staff")
    if not isinstance(full_name, str) or not full_name.strip() or len(full_name) > 256:
        raise ApiError(400, "INVALID_FULL_NAME", "fullName must contain 1 to 256 characters.")
    if not isinstance(email, str) or len(email) > 254 or not EMAIL_PATTERN.fullmatch(email):
        raise ApiError(400, "INVALID_EMAIL", "email is invalid.")
    if role not in ALLOWED_ROLES:
        raise ApiError(400, "INVALID_ROLE", "role must be Admin or Staff.")
    try:
        created = client.admin_create_user(
            UserPoolId=pool_id,
            Username=username,
            UserAttributes=[
                {"Name": "email", "Value": email},
                {"Name": "name", "Value": full_name.strip()},
            ],
        )["User"]
    except Exception as error:
        _cognito_error(error)
    actual_username = created.get("Username", username)
    try:
        client.admin_add_user_to_group(
            UserPoolId=pool_id, Username=actual_username, GroupName=role
        )
    except Exception as error:
        try:
            client.admin_disable_user(UserPoolId=pool_id, Username=actual_username)
        except Exception as disable_error:
            raise ApiError(
                502, "USER_SETUP_INCOMPLETE", "User setup failed and the account could not be disabled."
            ) from disable_error
        raise ApiError(
            502, "USER_ROLE_ASSIGNMENT_FAILED", "User setup failed; the account was disabled."
        ) from error
    created.setdefault("Username", username)
    created.setdefault("Attributes", [
        {"Name": "email", "Value": email},
        {"Name": "name", "Value": full_name.strip()},
    ])
    created.setdefault("Enabled", True)
    return success(_user_response(created, role), 201)


def _change_role(client, pool_id, username, event):
    body = parse_body(event)
    role = body.get("role")
    if role not in ALLOWED_ROLES:
        raise ApiError(400, "INVALID_ROLE", "role must be Admin or Staff.")
    try:
        current_groups = _managed_groups(client, pool_id, username)
        current_role = next(iter(current_groups), None)
        if current_role == "Admin" and role != "Admin":
            _assert_another_admin_remains(client, pool_id)
        if current_role != role:
            if current_role:
                client.admin_remove_user_from_group(
                    UserPoolId=pool_id, Username=username, GroupName=current_role
                )
            try:
                client.admin_add_user_to_group(
                    UserPoolId=pool_id, Username=username, GroupName=role
                )
            except Exception as error:
                if current_role:
                    try:
                        client.admin_add_user_to_group(
                            UserPoolId=pool_id, Username=username, GroupName=current_role
                        )
                    except Exception as rollback_error:
                        raise ApiError(
                            502, "USER_ROLE_UPDATE_INCOMPLETE", "Role update failed and the previous group could not be restored."
                        ) from rollback_error
                _cognito_error(error)
        user = client.admin_get_user(UserPoolId=pool_id, Username=username)
    except ApiError:
        raise
    except Exception as error:
        _cognito_error(error)
    return success(_user_response(user, role))


def _read_user(client, pool_id, username):
    try:
        user = client.admin_get_user(UserPoolId=pool_id, Username=username)
        groups = _managed_groups(client, pool_id, username)
    except ApiError:
        raise
    except Exception as error:
        _cognito_error(error)
    return success(_user_response(user, next(iter(groups), None)))


def _update_user_status(client, pool_id, username, status, event):
    if status == "LOCKED":
        return _disable_user(client, pool_id, username, event)
    if status != "ACTIVE":
        raise ApiError(400, "INVALID_STATUS", "status must be ACTIVE or LOCKED.")
    try:
        client.admin_enable_user(UserPoolId=pool_id, Username=username)
        user = client.admin_get_user(UserPoolId=pool_id, Username=username)
        groups = _managed_groups(client, pool_id, username)
    except ApiError:
        raise
    except Exception as error:
        _cognito_error(error)
    return success(_user_response(user, next(iter(groups), None)))


def _update_user_compat(client, pool_id, username, event):
    body = parse_body(event)
    if "role" in body and "status" in body:
        raise ApiError(400, "FIELD_CONFLICT", "Update either role or status in one request.")
    if "role" in body:
        return _change_role(client, pool_id, username, event)
    if "status" in body:
        return _update_user_status(client, pool_id, username, body["status"], event)
    raise ApiError(400, "INVALID_USER_UPDATE", "Send either role or status.")


def _disable_user(client, pool_id, username, event):
    claims = event.get("requestContext", {}).get("authorizer", {}).get("claims", {})
    actor = claims.get("cognito:username") or claims.get("username")
    if isinstance(actor, str) and actor.casefold() == username.casefold():
        raise ApiError(409, "SELF_DISABLE_FORBIDDEN", "You cannot disable your own account.")
    try:
        user = client.admin_get_user(UserPoolId=pool_id, Username=username)
        groups = _managed_groups(client, pool_id, username)
        enabled = user.get("Enabled", True)
        if enabled and "Admin" in groups:
            _assert_another_admin_remains(client, pool_id)
        if enabled:
            client.admin_disable_user(UserPoolId=pool_id, Username=username)
    except ApiError:
        raise
    except Exception as error:
        _cognito_error(error)
    return success({"username": username, "status": "LOCKED"})


@with_error_handling
def handler(event, context=None):
    require_any_group(event, ["Admin"])
    pool_id = _pool_id()
    method = event.get("httpMethod")
    resource = event.get("resource") or event.get("path", "")
    path_parameters = event.get("pathParameters") or {}
    client = _client()

    if method == "GET" and resource == "/users":
        try:
            return success(_list_users(client, pool_id))
        except ApiError:
            raise
        except Exception as error:
            _cognito_error(error)
    if method == "POST" and resource == "/users":
        return _create_user(client, pool_id, event)
    if method == "PUT" and (
        resource == "/users/{username}/role"
        or re.fullmatch(r"/users/[^/]+/role", resource)
    ):
        username = _validate_username(path_parameters.get("username") or resource.split("/")[-2])
        return _change_role(client, pool_id, username, event)
    if method == "GET" and (
        resource == "/users/{username}"
        or re.fullmatch(r"/users/[^/]+", resource)
    ):
        username = _validate_username(path_parameters.get("username") or resource.rsplit("/", 1)[-1])
        return _read_user(client, pool_id, username)
    if method == "PUT" and (
        resource == "/users/{username}"
        or re.fullmatch(r"/users/[^/]+", resource)
    ):
        username = _validate_username(path_parameters.get("username") or resource.rsplit("/", 1)[-1])
        return _update_user_compat(client, pool_id, username, event)
    if method == "DELETE" and (
        resource == "/users/{username}"
        or re.fullmatch(r"/users/[^/]+", resource)
    ):
        username = _validate_username(path_parameters.get("username") or resource.rsplit("/", 1)[-1])
        return _disable_user(client, pool_id, username, event)
    raise ApiError(404, "ROUTE_NOT_FOUND", "User management endpoint not found.")
