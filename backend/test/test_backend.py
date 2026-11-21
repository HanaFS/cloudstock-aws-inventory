import json
import os
import unittest
from datetime import datetime, timezone
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

    def query(self, **kwargs):
        return {"Items": list(self.items.values())[:kwargs.get("Limit", 100)]}


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
    @patch.dict(os.environ, {"TABLE_PRODUCTS": "products", "TABLE_SUPPLIERS": "suppliers"})
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
                "stockQuantity": 20,
                "minThreshold": 5,
                "updatedAt": "client-value",
            }))
        self.assertEqual(result["statusCode"], 201)
        self.assertEqual(response_body(result)["data"]["name"], "USB-C cable")
        self.assertEqual(response_body(result)["data"]["status"], "IN_STOCK")
        self.assertNotEqual(response_body(result)["data"]["updatedAt"], "client-value")
        self.assertIsNotNone(products.last_put["ConditionExpression"])

    @patch.dict(os.environ, {"TABLE_PRODUCTS": "products", "TABLE_SUPPLIERS": "suppliers"})
    def test_invalid_quantity_does_not_write(self):
        products = FakeTable()
        with patch("src.products.dynamodb", FakeDynamo({"products": products, "suppliers": FakeTable()})):
            from src.products import handler

            result = handler(event("POST", {
                "productId": "prod-013",
                "name": "Cable",
                "category": "Accessories",
                "price": 1,
                "stockQuantity": -1,
                "minThreshold": 0,
            }))
        self.assertEqual(result["statusCode"], 400)
        self.assertEqual(response_body(result)["code"], "INVALID_STOCK_QUANTITY")
        self.assertIsNone(products.last_put)

    @patch.dict(os.environ, {"TABLE_PRODUCTS": "products", "TABLE_SUPPLIERS": "suppliers"})
    def test_role_is_checked_before_database_access(self):
        with patch("src.products.dynamodb", FakeDynamo({})):
            from src.products import handler

            result = handler(event("GET", claims={"cognito:groups": ["Viewer"]}))
        self.assertEqual(result["statusCode"], 403)
        self.assertEqual(response_body(result)["code"], "FORBIDDEN")


class TransactionHandlerTests(unittest.TestCase):
    @patch.dict(os.environ, {
        "TABLE_TRANSACTIONS": "transactions",
        "TABLE_PRODUCTS": "products",
        "TABLE_SUPPLIERS": "suppliers",
    })
    def test_transaction_builds_atomic_stock_update_and_ignores_client_identity(self):
        transactions = FakeTable()
        products = FakeTable({("prod-001",): {
            "productId": "prod-001", "name": "Paper", "stockQuantity": 10,
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
                "createdAt": "client-time",
                "performedBy": "client-user",
                "type": "EXPORT",
                "productId": "prod-001",
                "quantity": 3,
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
        self.assertEqual(data["type"], "EXPORT")
        self.assertEqual(data["quantity"], 3)
        self.assertEqual(transaction_put["productName"]["S"], "Paper")
        self.assertEqual(
            calls[0]["TransactItems"][0]["Update"]["ExpressionAttributeValues"][":delta"]["N"],
            "-3",
        )

    @patch.dict(os.environ, {
        "TABLE_TRANSACTIONS": "transactions",
        "TABLE_PRODUCTS": "products",
        "TABLE_SUPPLIERS": "suppliers",
    })
    def test_missing_idempotency_key_is_rejected(self):
        with patch("src.transactions.dynamodb", FakeDynamo({})):
            from src.transactions import handler

            result = handler(event("POST", {
                "type": "IMPORT",
                "productId": "prod-001",
                "quantity": 1,
            }, headers={}, claims={"cognito:groups": ["Staff"], "sub": "user-sub-001"}))
        self.assertEqual(result["statusCode"], 400)
        self.assertEqual(response_body(result)["code"], "IDEMPOTENCY_KEY_REQUIRED")


class CloudFeatureHandlerTests(unittest.TestCase):
    @patch.dict(os.environ, {
        "TABLE_PRODUCTS": "products",
        "TABLE_SUPPLIERS": "suppliers",
        "TABLE_TRANSACTIONS": "transactions",
    })
    def test_dashboard_aggregates_cloud_schema_fields(self):
        today = datetime.now(timezone.utc).isoformat()
        tables = {
            "products": FakeTable({
                ("p1",): {"productId": "p1", "stockQuantity": 4, "price": 25, "minThreshold": 5},
                ("p2",): {"productId": "p2", "stockQuantity": 0, "price": 10, "minThreshold": 0},
            }),
            "suppliers": FakeTable({("s1",): {"supplierId": "s1"}}),
            "transactions": FakeTable({
                ("t1",): {"transactionId": "t1", "createdAt": today, "type": "IMPORT", "quantity": 8},
                ("t2",): {"transactionId": "t2", "createdAt": today, "type": "EXPORT", "quantity": 3},
            }),
        }
        with patch("src.dashboard.dynamodb", FakeDynamo(tables)):
            from src.dashboard import handler

            request = event("GET")
            request["path"] = "/dashboard"
            result = handler(request)
        self.assertEqual(response_body(result)["data"], {
            "totalProducts": 2,
            "totalQuantity": 4,
            "totalValue": 100,
            "lowStockCount": 1,
            "totalSuppliers": 1,
            "todayIn": 8,
            "todayOut": 3,
            "todayTransactions": 2,
        })

    def test_users_management_requires_admin_before_cognito_access(self):
        request = event("GET", claims={"cognito:groups": ["Staff"]})
        request["path"] = "/users"
        with patch("src.users._client") as cognito:
            from src.users import handler

            result = handler(request)
        self.assertEqual(result["statusCode"], 403)
        cognito.assert_not_called()

    @patch.dict(os.environ, {"BUCKET_NAME": "test-assets", "AWS_REGION": "ap-southeast-1"})
    def test_product_image_upload_is_scoped_and_size_limited(self):
        class FakeS3:
            def generate_presigned_post(self, **kwargs):
                self.request = kwargs
                return {"url": "https://s3.example.test", "fields": {"key": kwargs["Key"]}}

        s3 = FakeS3()
        request = event("POST", {"fileName": "photo.png", "contentType": "image/png"})
        request["path"] = "/products/upload-url"
        with patch("src.uploads._client", return_value=s3):
            from src.uploads import product_image_upload_url

            result = product_image_upload_url(request)
        data = response_body(result)["data"]
        self.assertTrue(data["objectKey"].startswith("products/"))
        self.assertEqual(s3.request["ExpiresIn"], 300)
        self.assertIn(["content-length-range", 1, 5 * 1024 * 1024], s3.request["Conditions"])

    def test_invoice_upload_rejects_unsupported_mime_before_s3_call(self):
        request = event("POST", {"fileName": "document.webp", "contentType": "image/webp"})
        request["path"] = "/transactions/invoice-upload-url"
        with patch("src.uploads._client") as s3:
            from src.uploads import invoice_upload_url

            result = invoice_upload_url(request)
        self.assertEqual(result["statusCode"], 400)
        self.assertEqual(response_body(result)["code"], "INVALID_CONTENT_TYPE")
        s3.assert_not_called()

    @patch.dict(os.environ, {"LOG_GROUPS": "/aws/lambda/app"})
    def test_logs_api_requires_admin(self):
        request = event("GET", claims={"cognito:groups": ["Staff"]})
        request["path"] = "/logs"
        with patch("src.logs._client") as logs:
            from src.logs import handler

            result = handler(request)
        self.assertEqual(result["statusCode"], 403)
        logs.assert_not_called()


class LocalApiTests(unittest.TestCase):
    def test_route_resolution_and_local_endpoint_validation(self):
        self.assertEqual(resolve_route("GET", "/products/prod-013"), ("products", {"productId": "prod-013"}))
        self.assertIsNone(resolve_route("POST", "/transactions/txn-1"))
        environment = {}
        self.assertEqual(configure_local_environment(environment)["STAGE"], "dev")
        self.assertEqual(environment["TABLE_PRODUCTS"], "cloudstock-dev-products")
        self.assertEqual(resolve_route("GET", "/dashboard"), ("dashboard", {}))
        self.assertEqual(resolve_route("POST", "/products/upload-url"), ("products", {}))
        self.assertEqual(
            resolve_route("GET", "/transactions/txn-1/invoice-url"),
            ("transactions", {"transactionId": "txn-1"}),
        )
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
