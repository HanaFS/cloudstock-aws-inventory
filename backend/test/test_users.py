import json
import os
import unittest
from unittest.mock import patch

from scripts.local_api import resolve_route

class FakeCognito:
    def __init__(self, users=None, groups=None):
        self.users = {user["Username"]: dict(user) for user in users or []}
        self.groups = {name: set(members) for name, members in (groups or {}).items()}
        self.calls = []

    def list_users(self, **kwargs):
        self.calls.append(("list_users", kwargs))
        return {"Users": [dict(user) for user in self.users.values()]}

    def list_users_in_group(self, UserPoolId, GroupName, Limit, **kwargs):
        self.calls.append(("list_users_in_group", GroupName))
        return {"Users": [
            dict(self.users[username]) for username in sorted(self.groups.get(GroupName, set()))
            if username in self.users
        ]}

    def admin_list_groups_for_user(self, UserPoolId, Username, Limit):
        self.calls.append(("admin_list_groups_for_user", Username))
        return {"Groups": [{"GroupName": role} for role, members in self.groups.items() if Username in members]}

    def admin_create_user(self, UserPoolId, Username, UserAttributes):
        self.calls.append(("admin_create_user", Username))
        user = {"Username": Username, "Enabled": True, "Attributes": UserAttributes}
        self.users[Username] = user
        return {"User": dict(user)}

    def admin_add_user_to_group(self, UserPoolId, Username, GroupName):
        self.calls.append(("admin_add_user_to_group", Username, GroupName))
        self.groups.setdefault(GroupName, set()).add(Username)

    def admin_remove_user_from_group(self, UserPoolId, Username, GroupName):
        self.calls.append(("admin_remove_user_from_group", Username, GroupName))
        self.groups.setdefault(GroupName, set()).discard(Username)

    def admin_get_user(self, UserPoolId, Username):
        self.calls.append(("admin_get_user", Username))
        return dict(self.users[Username])

    def admin_disable_user(self, UserPoolId, Username):
        self.calls.append(("admin_disable_user", Username))
        self.users[Username]["Enabled"] = False

    def admin_enable_user(self, UserPoolId, Username):
        self.calls.append(("admin_enable_user", Username))
        self.users[Username]["Enabled"] = True


def make_user(username, enabled=True, email=None):
    return {
        "Username": username,
        "Enabled": enabled,
        "UserStatus": "CONFIRMED" if enabled else "DISABLED",
        "Attributes": [
            {"Name": "sub", "Value": f"subject-{username}"},
            {"Name": "email", "Value": email or f"{username}@example.test"},
            {"Name": "name", "Value": username.title()},
            {"Name": "phone_number", "Value": "+10000000000"},
        ],
    }


def event(method, resource, body=None, username=None, groups=None, actor="admin.one"):
    return {
        "httpMethod": method,
        "resource": resource,
        "path": resource,
        "pathParameters": {"username": username} if username else {},
        "body": json.dumps(body) if body is not None else None,
        "requestContext": {"authorizer": {"claims": {
            "cognito:groups": groups if groups is not None else ["Admin"],
            "cognito:username": actor,
            "sub": f"subject-{actor}",
        }}},
    }


def payload(result):
    return json.loads(result["body"])


class UserManagementTests(unittest.TestCase):
    def setUp(self):
        env = patch.dict(os.environ, {"COGNITO_USER_POOL_ID": "pool-test"})
        env.start()
        self.addCleanup(env.stop)
        self.client = FakeCognito(
            users=[make_user("admin.one"), make_user("staff.one")],
            groups={"Admin": {"admin.one"}, "Staff": {"staff.one"}},
        )
        client = patch("src.users.boto3.client", return_value=self.client)
        client.start()
        self.addCleanup(client.stop)

    def invoke(self, request):
        from src.users import handler

        return handler(request)

    def test_non_admin_is_rejected_before_cognito_access(self):
        with patch("src.users.boto3.client") as cognito:
            result = self.invoke(event("GET", "/users", groups=["Staff"]))
        self.assertEqual(result["statusCode"], 403)
        cognito.assert_not_called()

    def test_list_users_returns_only_safe_fields_and_managed_roles(self):
        result = self.invoke(event("GET", "/users"))
        self.assertEqual(result["statusCode"], 200)
        users = payload(result)["data"]
        self.assertEqual({user["username"]: user["role"] for user in users}, {
            "admin.one": "Admin", "staff.one": "Staff",
        })
        self.assertTrue(all(set(user) == {"id", "username", "fullName", "email", "role", "status"} for user in users))
        self.assertNotIn("sub", json.dumps(users))
        self.assertNotIn("phone_number", json.dumps(users))

    def test_create_user_validates_fields_and_assigns_existing_role(self):
        result = self.invoke(event("POST", "/users", {
            "username": "staff.new", "fullName": "New Staff",
            "email": "new@example.test", "role": "Staff",
        }))
        self.assertEqual(result["statusCode"], 201)
        self.assertEqual(payload(result)["data"]["role"], "Staff")
        self.assertIn("staff.new", self.client.groups["Staff"])
        self.assertNotIn("password", json.dumps(payload(result)).lower())

        before = len(self.client.calls)
        invalid = self.invoke(event("POST", "/users", {
            "username": "bad/name", "fullName": "Name",
            "email": "new@example.test", "role": "Viewer",
        }))
        self.assertEqual(invalid["statusCode"], 400)
        self.assertEqual(len(self.client.calls), before)

    def test_role_update_moves_user_between_existing_groups(self):
        result = self.invoke(event(
            "PUT", "/users/{username}/role", {"role": "Admin"}, username="staff.one",
        ))
        self.assertEqual(result["statusCode"], 200)
        self.assertEqual(payload(result)["data"]["role"], "Admin")
        self.assertNotIn("staff.one", self.client.groups["Staff"])
        self.assertIn("staff.one", self.client.groups["Admin"])

    def test_last_admin_cannot_be_demoted_or_disabled(self):
        self.client.groups["Admin"] = {"admin.one"}
        demote = self.invoke(event(
            "PUT", "/users/{username}/role", {"role": "Staff"}, username="admin.one",
        ))
        disable = self.invoke(event(
            "DELETE", "/users/{username}", username="admin.one", actor="admin.two",
        ))
        self.assertEqual(demote["statusCode"], 409)
        self.assertEqual(disable["statusCode"], 409)
        self.assertIn("admin.one", self.client.groups["Admin"])
        self.assertTrue(self.client.users["admin.one"]["Enabled"])
        self.assertFalse(any(call[0] == "admin_disable_user" for call in self.client.calls))

    def test_self_disable_is_rejected(self):
        result = self.invoke(event("DELETE", "/users/{username}", username="admin.one"))
        self.assertEqual(result["statusCode"], 409)
        self.assertEqual(payload(result)["code"], "SELF_DISABLE_FORBIDDEN")
        self.assertTrue(self.client.users["admin.one"]["Enabled"])

    def test_disable_preserves_user_record_and_alias_can_reenable(self):
        result = self.invoke(event("DELETE", "/users/{username}", username="staff.one"))
        self.assertEqual(result["statusCode"], 200)
        self.assertEqual(result["body"], json.dumps({
            "success": True,
            "data": {"username": "staff.one", "status": "LOCKED"},
        }, ensure_ascii=False, separators=(",", ":")))
        self.assertIn("staff.one", self.client.users)
        self.assertIn(("admin_disable_user", "staff.one"), self.client.calls)
        self.assertFalse(any(call[0] == "admin_delete_user" for call in self.client.calls))

        enabled = self.invoke(event(
            "PUT", "/users/{username}", {"status": "ACTIVE"}, username="staff.one",
        ))
        self.assertEqual(enabled["statusCode"], 200)
        self.assertEqual(payload(enabled)["data"]["status"], "ACTIVE")
        self.assertTrue(self.client.users["staff.one"]["Enabled"])

    def test_compatibility_detail_route_returns_sanitized_user(self):
        result = self.invoke(event("GET", "/users/{username}", username="staff.one"))
        self.assertEqual(result["statusCode"], 200)
        data = payload(result)["data"]
        self.assertEqual(data["username"], "staff.one")
        self.assertEqual(data["role"], "Staff")
        self.assertEqual(set(data), {"id", "username", "fullName", "email", "role", "status"})

    def test_local_adapter_resolves_runbook_and_frontend_compatibility_routes(self):
        self.assertEqual(resolve_route("GET", "/users"), ("users", {}))
        self.assertEqual(resolve_route("POST", "/users"), ("users", {}))
        self.assertEqual(resolve_route("GET", "/users/staff.one"), ("users", {"username": "staff.one"}))
        self.assertEqual(resolve_route("PUT", "/users/staff.one/role"), ("users", {"username": "staff.one"}))
        self.assertEqual(resolve_route("PUT", "/users/staff.one"), ("users", {"username": "staff.one"}))
        self.assertEqual(resolve_route("DELETE", "/users/staff.one"), ("users", {"username": "staff.one"}))

    def test_template_scopes_user_management_actions_to_existing_pool(self):
        template = os.path.join(os.path.dirname(os.path.dirname(__file__)), "template.yaml")
        with open(template, encoding="utf-8") as source:
            text = source.read()
        users_function = text.split("  UsersFunction:", 1)[1].split("  ProductImagesBucket:", 1)[0]
        self.assertIn("Handler: src.users.handler", users_function)
        self.assertIn("ReservedConcurrentExecutions: 1", users_function)
        self.assertIn("COGNITO_USER_POOL_ID: !Ref CloudStockUserPool", users_function)
        self.assertIn("Resource: !GetAtt CloudStockUserPool.Arn", users_function)
        self.assertNotIn("Resource: \"*\"", users_function)
        for path in ("/users", "/users/{username}", "/users/{username}/role"):
            self.assertIn(f"Path: {path}", users_function)


if __name__ == "__main__":
    unittest.main()
