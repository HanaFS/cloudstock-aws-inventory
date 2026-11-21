import json
import os
import unittest
from unittest.mock import patch


class FakeProductsTable:
    def __init__(self, items=None):
        self.items = {item["productId"]: dict(item) for item in items or []}
        self.last_put = None

    def get_item(self, Key):
        item = self.items.get(Key["productId"])
        return {"Item": dict(item)} if item else {}

    def put_item(self, Item, **kwargs):
        self.last_put = dict(Item)
        self.items[Item["productId"]] = dict(Item)

    def update_item(self, Key, ExpressionAttributeNames, ExpressionAttributeValues, **kwargs):
        item = dict(self.items[Key["productId"]])
        for placeholder, field in ExpressionAttributeNames.items():
            value_placeholder = f":{field}"
            if value_placeholder in ExpressionAttributeValues:
                item[field] = ExpressionAttributeValues[value_placeholder]
        self.items[Key["productId"]] = item
        return {"Attributes": item}

    def scan(self, **kwargs):
        return {"Items": [dict(item) for item in self.items.values()]}


class FakeTableCollection:
    def __init__(self, products):
        self.tables = {"products": products, "suppliers": FakeProductsTable()}

    def Table(self, name):
        return self.tables[name]


def request(method, body=None, product_id=None, query=None):
    return {
        "httpMethod": method,
        "pathParameters": {"productId": product_id} if product_id else {},
        "queryStringParameters": query or {},
        "headers": {},
        "body": json.dumps(body) if body is not None else None,
        "requestContext": {"authorizer": {"claims": {"cognito:groups": ["Staff"]}}},
    }


def response_data(result):
    return json.loads(result["body"])


@patch.dict(os.environ, {"PRODUCTS_TABLE": "products", "SUPPLIERS_TABLE": "suppliers"})
class ProductCompatibilityHandlerTests(unittest.TestCase):
    def run_handler(self, products, event):
        with patch("src.products.dynamodb", FakeTableCollection(products)) as dynamodb:
            from src.products import handler

            result = handler(event)
            return result, dynamodb.tables["products"]

    def valid_body(self, **overrides):
        body = {
            "productId": "prod-101",
            "name": "Cable",
            "category": "Accessories",
            "price": 150,
            "minThreshold": 2,
        }
        body.update(overrides)
        return body

    def test_create_canonical_stock_dual_writes_legacy_and_derives_status(self):
        result, products = self.run_handler(
            FakeProductsTable(),
            request("POST", self.valid_body(stockQuantity=4)),
        )
        self.assertEqual(result["statusCode"], 201)
        self.assertEqual(products.last_put["stockQuantity"], 4)
        self.assertEqual(products.last_put["quantity"], 4)
        self.assertEqual(products.last_put["status"], "IN_STOCK")
        self.assertEqual(response_data(result)["data"]["stockQuantity"], 4)

    def test_create_legacy_stock_dual_writes_canonical_field(self):
        result, products = self.run_handler(
            FakeProductsTable(),
            request("POST", self.valid_body(quantity=0)),
        )
        self.assertEqual(result["statusCode"], 201)
        self.assertEqual(products.last_put["quantity"], 0)
        self.assertEqual(products.last_put["stockQuantity"], 0)
        self.assertEqual(products.last_put["status"], "OUT_OF_STOCK")

    def test_create_rejects_conflicting_stock_fields_without_write(self):
        result, products = self.run_handler(
            FakeProductsTable(),
            request("POST", self.valid_body(quantity=3, stockQuantity=5)),
        )
        self.assertEqual(result["statusCode"], 400)
        self.assertEqual(response_data(result)["code"], "FIELD_CONFLICT")
        self.assertIsNone(products.last_put)

    def test_update_canonical_stock_dual_writes_and_recomputes_status(self):
        current = {
            "productId": "prod-101",
            "name": "Cable",
            "category": "Accessories",
            "price": 150,
            "quantity": 4,
            "minThreshold": 2,
        }
        result, products = self.run_handler(
            FakeProductsTable([current]),
            request("PUT", {"stockQuantity": 0}, product_id="prod-101"),
        )
        saved = products.items["prod-101"]
        self.assertEqual(result["statusCode"], 200)
        self.assertEqual(saved["quantity"], 0)
        self.assertEqual(saved["stockQuantity"], 0)
        self.assertEqual(saved["status"], "OUT_OF_STOCK")

    def test_read_legacy_product_returns_both_fields_and_derived_status(self):
        current = {
            "productId": "prod-101",
            "name": "Cable",
            "category": "Accessories",
            "price": 150,
            "quantity": 2,
            "minThreshold": 2,
        }
        result, _ = self.run_handler(
            FakeProductsTable([current]),
            request("GET", product_id="prod-101"),
        )
        product = response_data(result)["data"]
        self.assertEqual(product["quantity"], 2)
        self.assertEqual(product["stockQuantity"], 2)
        self.assertEqual(product["status"], "IN_STOCK")

    def test_read_conflict_is_reported_without_selecting_a_value(self):
        current = {
            "productId": "prod-101",
            "name": "Cable",
            "category": "Accessories",
            "price": 150,
            "quantity": 2,
            "stockQuantity": 5,
            "minThreshold": 2,
        }
        result, _ = self.run_handler(
            FakeProductsTable([current]),
            request("GET", product_id="prod-101"),
        )
        self.assertEqual(result["statusCode"], 409)
        self.assertEqual(response_data(result)["code"], "PRODUCT_DATA_CONFLICT")

    def test_low_stock_filter_includes_product_at_threshold(self):
        products = FakeProductsTable([
            {
                "productId": "at-threshold", "name": "A", "category": "C",
                "price": 1, "quantity": 2, "minThreshold": 2,
            },
            {
                "productId": "above-threshold", "name": "B", "category": "C",
                "price": 1, "stockQuantity": 3, "minThreshold": 2,
            },
        ])
        result, _ = self.run_handler(
            products,
            request("GET", query={"filter": "low-stock"}),
        )
        items = response_data(result)["data"]
        self.assertEqual([item["productId"] for item in items], ["at-threshold"])


if __name__ == "__main__":
    unittest.main()
