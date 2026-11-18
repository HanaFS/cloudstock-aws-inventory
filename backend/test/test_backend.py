import json
import os
import unittest
from unittest.mock import patch

from scripts.local_api import configure_local_environment, create_local_api_server, resolve_route
from src.common.dynamodb import decode_cursor, encode_cursor
from src.common.http import ApiError, parse_body, require_any_group
from src.health import handler as health_handler


class FakeTable:
    def __init__(self, items=None):
        self.items = items or {}
        self.last_put = None

    def get_item(self, Key, **kwargs):
        return {"Item": self.items.get(tuple(Key.values()))}

    def put_item(self, **kwargs):
        self.last_put = kwargs
        self.items[tuple(kwargs["Item"].values())] = kwargs["Item"]

    def scan(self, **kwargs):
        return {"Items": list(self.items.values())}


class FakeDynamo:
    def __init__(self, tables, client=None):
        self.tables = tables
        self.meta = type("Meta", (), {"client": client})()

    def Table(self, name):
        return self.tables[name]


def event(method, body=None, path_parameters=None, headers=None, claims=None, query=None):
    return {
        "httpMethod": method,
        "pathParameters": path_parameters or {},
        "queryStringParameters": query or {},
        "headers": headers or {},
        "body": json.dumps(body) if body is not None else None,
        "requestContext": {"authorizer": {"claims": claims or {"cognito:groups": ["Staff"]}}},
    }


def response_body(response):
    return json.loads(response["body"])


class HttpHelpersTests(unittest.TestCase):
    def test_parse_body_rejects_non_object_json(self):
        with self.assertRaises(ApiError) as error:
            parse_body({"body": "[]"})
        self.assertEqual(error.exception.code, "INVALID_BODY")

    def test_group_claim_accepts_json_string_and_rejects_other_roles(self):
        require_any_group(
            {"requestContext": {"authorizer": {"claims": {"cognito:groups": '["Staff"]'}}}},
            ["Admin", "Staff"],
        )
        with self.assertRaises(ApiError):
            require_any_group(
                {"requestContext": {"authorizer": {"claims": {"cognito:groups": "Viewer"}}}},
                ["Admin", "Staff"],
            )

    def test_cursor_round_trip_and_reject_malformed_keys(self):
        key = {"productId": "prod-001"}
        self.assertEqual(decode_cursor(encode_cursor(key), "productId"), key)
        with self.assertRaises(ApiError):
            decode_cursor(encode_cursor({"wrong": "key"}), "productId")

    def test_health_response_is_compatible(self):
        result = response_body(health_handler())
        self.assertTrue(result["success"])
        self.assertEqual(result["data"]["service"], "cloudstock-api")


class ProductHandlerTests(unittest.TestCase):
    @patch.dict(os.environ, {"PRODUCTS_TABLE": "products", "SUPPLIERS_TABLE": "suppliers"})
    def test_create_product_uses_validated_values_and_conditional_write(self):
        products = FakeTable()
        dynamo = FakeDynamo({"products": products, "suppliers": FakeTable()})
        with patch("src.products.dynamodb", dynamo):
            from src.products import handler

            result = handler(event("POST", {
                "productId": "prod-013",
                "name": " USB-C cable ",
                "category": "Accessories",
                "price": 250000,
                "quantity": 20,
                "minThreshold": 5,
                "updatedAt": "client-value",
            }))
        self.assertEqual(result["statusCode"], 201)
        self.assertEqual(response_body(result)["data"]["name"], "USB-C cable")
        self.assertNotEqual(response_body(result)["data"]["updatedAt"], "client-value")
        self.assertIsNotNone(products.last_put["ConditionExpression"])

    @patch.dict(os.environ, {"PRODUCTS_TABLE": "products", "SUPPLIERS_TABLE": "suppliers"})
    def test_invalid_quantity_does_not_write(self):
        products = FakeTable()
        with patch("src.products.dynamodb", FakeDynamo({"products": products, "suppliers": FakeTable()})):
            from src.products import handler

            result = handler(event("POST", {
                "productId": "prod-013",
                "name": "Cable",
                "category": "Accessories",
                "price": 1,
                "quantity": -1,
                "minThreshold": 0,
            }))
        self.assertEqual(result["statusCode"], 400)
        self.assertEqual(response_body(result)["code"], "INVALID_QUANTITY")
        self.assertIsNone(products.last_put)

    @patch.dict(os.environ, {"PRODUCTS_TABLE": "products", "SUPPLIERS_TABLE": "suppliers"})
    def test_role_is_checked_before_database_access(self):
        with patch("src.products.dynamodb", FakeDynamo({})):
            from src.products import handler

            result = handler(event("GET", claims={"cognito:groups": ["Viewer"]}))
        self.assertEqual(result["statusCode"], 403)
        self.assertEqual(response_body(result)["code"], "FORBIDDEN")


class TransactionHandlerTests(unittest.TestCase):
    @patch.dict(os.environ, {
        "TRANSACTIONS_TABLE": "transactions",
        "PRODUCTS_TABLE": "products",
        "SUPPLIERS_TABLE": "suppliers",
    })
    def test_transaction_builds_atomic_stock_update_and_ignores_client_identity(self):
        transactions = FakeTable()
        products = FakeTable({("prod-001",): {
            "productId": "prod-001", "name": "Paper", "quantity": 10,
        }})
        calls = []

        class FakeClient:
            def transact_write_items(self, **kwargs):
                calls.append(kwargs)

        with patch("src.transactions.dynamodb", FakeDynamo(
            {"transactions": transactions, "products": products, "suppliers": FakeTable()},
            FakeClient(),
        )):
            from src.transactions import handler

            result = handler(event("POST", {
                "transactionId": "client-id",
                "timestamp": "client-time",
                "performedBy": "client-user",
                "type": "OUT",
                "productId": "prod-001",
                "amount": 3,
                "reason": "warehouse use",
            }, headers={"Idempotency-Key": "request-001"}, claims={
                "cognito:groups": ["Staff"],
                "cognito:username": "staff.tran",
                "sub": "user-sub-001",
            }))
        self.assertEqual(result["statusCode"], 201)
        data = response_body(result)["data"]
        transaction_put = calls[0]["TransactItems"][1]["Put"]["Item"]
        self.assertEqual(data["performedBy"], "staff.tran")
        self.assertNotEqual(data["transactionId"], "client-id")
        self.assertEqual(transaction_put["productName"]["S"], "Paper")
        self.assertEqual(
            calls[0]["TransactItems"][0]["Update"]["ExpressionAttributeValues"][":delta"]["N"],
            "-3",
        )

    @patch.dict(os.environ, {
        "TRANSACTIONS_TABLE": "transactions",
        "PRODUCTS_TABLE": "products",
        "SUPPLIERS_TABLE": "suppliers",
    })
    def test_missing_idempotency_key_is_rejected(self):
        with patch("src.transactions.dynamodb", FakeDynamo({})):
            from src.transactions import handler

            result = handler(event("POST", {
                "type": "IN",
                "productId": "prod-001",
                "amount": 1,
                "reason": "replenishment",
            }, headers={}, claims={"cognito:groups": ["Staff"], "sub": "user-sub-001"}))
        self.assertEqual(result["statusCode"], 400)
        self.assertEqual(response_body(result)["code"], "IDEMPOTENCY_KEY_REQUIRED")


class LocalApiTests(unittest.TestCase):
    def test_route_resolution_and_local_endpoint_validation(self):
        self.assertEqual(resolve_route("GET", "/products/prod-013"), ("products", {"productId": "prod-013"}))
        self.assertIsNone(resolve_route("POST", "/transactions/txn-1"))
        environment = {}
        self.assertEqual(configure_local_environment(environment)["STAGE"], "dev")
        with self.assertRaises(ValueError):
            configure_local_environment({"DYNAMODB_ENDPOINT": "https://example.com:8000"})

    def test_local_api_blocks_wrong_origin_and_accepts_local_role(self):
        server = create_local_api_server({
            "health": health_handler,
            "products": lambda request, context: {
                "statusCode": 200,
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps({"role": request["requestContext"]["authorizer"]["claims"]["cognito:groups"]}),
            },
        })
        import threading
        import urllib.error
        import urllib.request

        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base_url = f"http://127.0.0.1:{server.server_address[1]}/products"
            request = urllib.request.Request(base_url, headers={
                "Origin": "http://localhost:8080",
                "Authorization": "Bearer local-dev:Staff",
            })
            with urllib.request.urlopen(request) as response:
                self.assertEqual(json.loads(response.read())["role"], ["Staff"])
            blocked = urllib.request.Request(base_url, headers={
                "Origin": "http://example.test",
                "Authorization": "Bearer local-dev:Staff",
            })
            with self.assertRaises(urllib.error.HTTPError) as error:
                urllib.request.urlopen(blocked)
            self.assertEqual(error.exception.code, 403)
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == "__main__":
    unittest.main()
