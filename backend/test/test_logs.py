import base64
import json
import os
import unittest
from unittest.mock import patch

from scripts.local_api import resolve_route
from src.logs import handler


GROUPS = ",".join([
    "/aws/lambda/cloudstock-dev-ProductsFunction",
    "/aws/lambda/cloudstock-dev-TransactionsFunction",
])


def event(params=None, groups=None):
    return {
        "httpMethod": "GET",
        "path": "/transactions/logs",
        "queryStringParameters": params or {},
        "requestContext": {"authorizer": {"claims": {"cognito:groups": groups or ["Admin"]}}},
    }


class FakeLogs:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def filter_log_events(self, **kwargs):
        self.calls.append(kwargs)
        return self.responses.pop(0)


class LogsTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {"CLOUDSTOCK_LOG_GROUPS": GROUPS})
        self.env.start()
        self.addCleanup(self.env.stop)

    def payload(self, response):
        return json.loads(response["body"])

    def test_requires_admin_before_cloudwatch_client(self):
        with patch("src.logs._client") as client:
            response = handler(event(groups=["Staff"]))
        self.assertEqual(response["statusCode"], 403)
        client.assert_not_called()

    def test_local_mode_never_calls_cloudwatch(self):
        with patch.dict(os.environ, {"DYNAMODB_ENDPOINT": "http://127.0.0.1:8000"}), patch("src.logs._client") as client:
            response = handler(event())
        self.assertEqual(response["statusCode"], 501)
        client.assert_not_called()

    def test_fetches_only_configured_groups_and_redacts_secrets(self):
        logs = FakeLogs([{"events": [{
            "timestamp": 10,
            "ingestionTime": 11,
            "logStreamName": "stream",
            "message": 'AWS_SECRET_ACCESS_KEY=dont-show Authorization: Bearer abc.def.ghi AKIA1234567890ABCDEF',
        }]}, {"events": []}])
        with patch("src.logs._client", return_value=logs), patch("src.logs.time.time", return_value=100):
            response = handler(event({"startTime": "1", "endTime": "20000", "limit": "10"}))
        body = self.payload(response)
        self.assertEqual(response["statusCode"], 200)
        self.assertEqual(body["data"][0]["logGroupName"], "/aws/lambda/cloudstock-dev-ProductsFunction")
        self.assertNotIn("dont-show", body["data"][0]["message"])
        self.assertNotIn("abc.def.ghi", body["data"][0]["message"])
        self.assertNotIn("AKIA1234567890ABCDEF", body["data"][0]["message"])
        self.assertEqual(logs.calls[0]["logGroupName"], "/aws/lambda/cloudstock-dev-ProductsFunction")
        self.assertEqual(logs.calls[0]["startTime"], 1)

    def test_paginates_with_opaque_cursor_and_continues_to_next_group(self):
        logs = FakeLogs([
            {"events": [{"timestamp": 1, "message": "first"}], "nextToken": "service-token"},
            {"events": [{"timestamp": 2, "message": "second"}]},
            {"events": [{"timestamp": 3, "message": "third"}]},
        ])
        with patch("src.logs._client", return_value=logs), patch("src.logs.time.time", return_value=100):
            first = handler(event({"startTime": "1", "endTime": "100"}))
            first_body = self.payload(first)
            self.assertTrue(first_body["nextToken"])
            cursor = json.loads(base64.urlsafe_b64decode(
                first_body["nextToken"] + "=" * (-len(first_body["nextToken"]) % 4)
            ))
            self.assertEqual(cursor, {"i": 0, "t": "service-token"})
            second = handler(event({"startTime": "1", "endTime": "100", "nextToken": first_body["nextToken"]}))
        self.assertEqual(logs.calls[1]["nextToken"], "service-token")
        self.assertEqual(logs.calls[2]["logGroupName"], "/aws/lambda/cloudstock-dev-TransactionsFunction")
        self.assertEqual(self.payload(second)["data"][1]["logGroupName"], "/aws/lambda/cloudstock-dev-TransactionsFunction")

    def test_rejects_arbitrary_log_group_parameter(self):
        with patch("src.logs._client") as client, patch("src.logs.time.time", return_value=100):
            response = handler(event({"logGroupName": "/aws/lambda/other"}))
        self.assertEqual(response["statusCode"], 400)
        client.assert_not_called()

    def test_rejects_invalid_range_limit_and_cursor(self):
        cases = [
            {"startTime": "0"},
            {"startTime": "1", "endTime": "86400002"},
            {"limit": "101"},
            {"nextToken": "not a cursor"},
        ]
        for params in cases:
            with self.subTest(params=params), patch("src.logs._client") as client, patch("src.logs.time.time", return_value=100000000):
                response = handler(event(params))
            self.assertEqual(response["statusCode"], 400)
            client.assert_not_called()

    def test_routes_both_runbook_and_frontend_paths(self):
        self.assertEqual(resolve_route("GET", "/transactions/logs"), ("logs", {}))
        self.assertEqual(resolve_route("GET", "/logs"), ("logs", {}))
        self.assertIsNone(resolve_route("POST", "/logs"))

    def test_template_limits_logs_permission_to_approved_lambda_groups(self):
        with open("template.yaml", encoding="utf-8") as template_file:
            template = template_file.read()
        logs_function = template.split("  LogsFunction:\n", 1)[1].split("\n  ProductImagesBucket:", 1)[0]
        self.assertIn("Action:\n                - logs:FilterLogEvents", logs_function)
        self.assertEqual(logs_function.count(":log-group:/aws/lambda/"), 7)
        self.assertNotIn("logs:*", logs_function)
        self.assertIn("Path: /transactions/logs", logs_function)
        self.assertIn("Path: /logs", logs_function)


if __name__ == "__main__":
    unittest.main()
