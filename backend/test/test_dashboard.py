import json
import os
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import patch

from scripts.local_api import resolve_route
from src.dashboard import handler


class FakeDynamo:
    def Table(self, name):
        return name


def event(groups=None, method="GET", resource="/dashboard"):
    return {
        "httpMethod": method,
        "resource": resource,
        "requestContext": {"authorizer": {"claims": {
            "cognito:groups": groups if groups is not None else ["Staff"],
        }}},
    }


def payload(result):
    return json.loads(result["body"])


class DashboardHandlerTests(unittest.TestCase):
    def setUp(self):
        env = patch.dict(os.environ, {
            "PRODUCTS_TABLE": "products",
            "TRANSACTIONS_TABLE": "transactions",
        })
        env.start()
        self.addCleanup(env.stop)
        dynamo = patch("src.dashboard.dynamodb", FakeDynamo())
        dynamo.start()
        self.addCleanup(dynamo.stop)

    def test_dashboard_aggregates_canonical_stock_and_transaction_types(self):
        today = datetime.now(timezone.utc).date().isoformat()
        products = [
            {
                "productId": "p-1", "quantity": Decimal("5"),
                "stockQuantity": Decimal("5"), "minThreshold": Decimal("5"),
                "price": Decimal("2.5"),
            },
            {
                "productId": "p-2", "quantity": Decimal("0"),
                "minThreshold": Decimal("0"), "price": Decimal("10"),
            },
        ]
        transactions = [
            {
                "transactionId": "t-in", "timestamp": f"{today}T09:00:00Z",
                "createdAt": f"{today}T09:00:00Z", "type": "IN",
                "canonicalType": "IMPORT", "amount": Decimal("3"),
                "quantity": Decimal("3"), "productId": "p-1",
                "productName": "Cable", "performedBy": "staff",
            },
            {
                "transactionId": "t-out", "createdAt": f"{today}T10:00:00+00:00",
                "canonicalType": "EXPORT", "quantity": Decimal("2"),
                "productId": "p-1", "productName": "Cable", "performedBy": "staff",
            },
            {"transactionId": "UPLOAD#reservation", "recordType": "UPLOAD_RESERVATION"},
        ]
        with patch("src.dashboard.scan_all", side_effect=lambda table: {
            "products": products, "transactions": transactions,
        }[table]):
            result = handler(event())

        self.assertEqual(result["statusCode"], 200)
        self.assertEqual(payload(result)["data"], {
            "totalProducts": 2,
            "totalQuantity": 5,
            "totalValue": 12.5,
            "lowStockCount": 2,
            "outOfStockCount": 1,
            "todayIn": 3,
            "todayOut": 2,
            "todayTransactions": 2,
        })

    def test_conflicting_product_stock_is_reported(self):
        with patch("src.dashboard.scan_all", side_effect=[
            [{"productId": "p-1", "quantity": 4, "stockQuantity": 5,
              "minThreshold": 2, "price": 1}],
            [],
        ]):
            result = handler(event())
        self.assertEqual(result["statusCode"], 409)
        self.assertEqual(payload(result)["code"], "INVALID_DASHBOARD_DATA")

    def test_conflicting_transaction_aliases_are_reported(self):
        transaction = {
            "transactionId": "t-1", "timestamp": "2026-01-01T00:00:00Z",
            "createdAt": "2026-01-02T00:00:00Z", "type": "IN",
            "canonicalType": "IMPORT", "amount": 1, "quantity": 1,
            "productId": "p-1", "productName": "Cable", "performedBy": "staff",
        }
        with patch("src.dashboard.scan_all", side_effect=[[], [transaction]]):
            result = handler(event())
        self.assertEqual(result["statusCode"], 409)
        self.assertEqual(payload(result)["code"], "INVALID_DASHBOARD_DATA")

    def test_only_admin_and_staff_can_read_dashboard(self):
        with patch("src.dashboard.scan_all") as scan:
            result = handler(event(groups=["Viewer"]))
        self.assertEqual(result["statusCode"], 403)
        scan.assert_not_called()

    def test_dashboard_route_is_get_only(self):
        result = handler(event(method="POST"))
        self.assertEqual(result["statusCode"], 404)
        self.assertEqual(payload(result)["code"], "ROUTE_NOT_FOUND")

    def test_dashboard_routes_and_local_alias_resolution(self):
        for path in ("/dashboard", "/dashboard/stats"):
            self.assertEqual(resolve_route("GET", path), ("dashboard", {}))
            with patch("src.dashboard.scan_all", side_effect=[[], []]):
                result = handler(event(resource=path))
            self.assertEqual(result["statusCode"], 200)


if __name__ == "__main__":
    unittest.main()
