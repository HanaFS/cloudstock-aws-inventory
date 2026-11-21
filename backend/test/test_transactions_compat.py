import json
import os
import unittest
from unittest.mock import patch

from src.transactions import _request_hash, _transaction_id


class FakeTable:
    def __init__(self, key_name, items=None, query_items=None):
        self.key_name = key_name
        self.items = {(item[key_name],): item for item in items or []}
        self.query_items = query_items or []

    def get_item(self, Key, **kwargs):
        key = tuple(Key.values())
        return {"Item": self.items[key]} if key in self.items else {}

    def query(self, **kwargs):
        return {"Items": list(self.query_items)}


class FakeDynamo:
    def __init__(self, tables, client):
        self.tables = tables
        self.meta = type("Meta", (), {"client": client})()

    def Table(self, name):
        return self.tables[name]


class FakeClient:
    def __init__(self):
        self.calls = []

    def transact_write_items(self, **kwargs):
        self.calls.append(kwargs)


def make_event(method, body=None, headers=None, path_parameters=None):
    return {
        "httpMethod": method,
        "pathParameters": path_parameters or {},
        "queryStringParameters": {},
        "headers": headers or {},
        "body": json.dumps(body) if body is not None else None,
        "requestContext": {"authorizer": {"claims": {
            "cognito:groups": ["Staff"],
            "cognito:username": "staff.one",
            "sub": "subject-one",
        }}},
    }


def body_of(result):
    return json.loads(result["body"])


class TransactionCompatibilityHandlerTests(unittest.TestCase):
    def make_dynamo(self, transaction_items=None, query_items=None, product=None):
        self.client = FakeClient()
        tables = {
            "transactions": FakeTable("transactionId", transaction_items, query_items),
            "products": FakeTable("productId", [product] if product else []),
            "suppliers": FakeTable("supplierId"),
        }
        return FakeDynamo(tables, self.client)

    def invoke(self, event, dynamo):
        with patch.dict(os.environ, {
            "TRANSACTIONS_TABLE": "transactions",
            "PRODUCTS_TABLE": "products",
            "SUPPLIERS_TABLE": "suppliers",
        }), patch("src.transactions.dynamodb", dynamo):
            from src.transactions import handler

            return handler(event)

    def test_import_and_export_writes_both_field_sets_and_keeps_gsi(self):
        for request_type, quantity, expected_type in (
            ("IMPORT", 2, "IMPORT"),
            ("EXPORT", 2, "EXPORT"),
        ):
            with self.subTest(request_type=request_type):
                dynamo = self.make_dynamo(product={
                    "productId": "p-1", "name": "Cable", "quantity": 5,
                })
                event = make_event("POST", {
                    "type": request_type,
                    "productId": "p-1",
                    "quantity": quantity,
                    "reason": "stock movement",
                }, headers={"Idempotency-Key": f"key-{request_type}"})
                result = self.invoke(event, dynamo)
                self.assertEqual(result["statusCode"], 201)
                data = body_of(result)["data"]
                self.assertEqual(data["type"], "IN" if request_type == "IMPORT" else "OUT")
                self.assertEqual(data["canonicalType"], expected_type)
                self.assertEqual(data["amount"], quantity)
                self.assertEqual(data["quantity"], quantity)
                self.assertEqual(data["timestamp"], data["createdAt"])

                operations = dynamo.meta.client.calls[0]["TransactItems"]
                stock_update = operations[0]["Update"]
                transaction_item = operations[1]["Put"]["Item"]
                self.assertIn("#stockQuantity", stock_update["ExpressionAttributeNames"])
                self.assertIn("#quantity = if_not_exists", stock_update["UpdateExpression"])
                self.assertIn("#stockQuantity = if_not_exists", stock_update["UpdateExpression"])
                self.assertEqual(transaction_item["canonicalType"]["S"], expected_type)
                created_at = transaction_item["createdAt"]["S"]
                transaction_id = transaction_item["transactionId"]["S"]
                self.assertEqual(transaction_item["timestamp"]["S"], created_at)
                self.assertEqual(transaction_item["gsi1sk"]["S"], f"{created_at}#{transaction_id}")

    def test_insufficient_export_does_not_write(self):
        dynamo = self.make_dynamo(product={"productId": "p-1", "name": "Cable", "stockQuantity": 1})
        result = self.invoke(make_event("POST", {
            "type": "EXPORT", "productId": "p-1", "quantity": 2,
            "reason": "order",
        }, headers={"Idempotency-Key": "key-export"}), dynamo)
        self.assertEqual(result["statusCode"], 409)
        self.assertEqual(body_of(result)["code"], "INSUFFICIENT_STOCK")
        self.assertEqual(dynamo.meta.client.calls, [])

    def test_canonical_retry_matches_existing_legacy_hash(self):
        subject = "subject-one"
        key = "retry-key"
        transaction_id = _transaction_id(subject, key)
        legacy_payload = {
            "type": "OUT",
            "productId": "p-1",
            "amount": 2,
            "supplierId": None,
            "reason": "order",
            "invoiceKey": None,
        }
        existing = {
            "transactionId": transaction_id,
            "timestamp": "2026-11-21T10:00:00Z",
            "type": "OUT",
            "productId": "p-1",
            "productName": "Cable",
            "amount": 2,
            "supplierId": None,
            "reason": "order",
            "invoiceKey": None,
            "performedBy": "staff.one",
            "requestHash": _request_hash(legacy_payload),
            "gsi1pk": "TRANSACTION",
            "gsi1sk": f"2026-11-21T10:00:00Z#{transaction_id}",
        }
        dynamo = self.make_dynamo(transaction_items=[existing])
        result = self.invoke(make_event("POST", {
            "type": "EXPORT", "productId": "p-1", "quantity": 2,
            "reason": "order",
        }, headers={"Idempotency-Key": key}), dynamo)
        self.assertEqual(result["statusCode"], 200)
        self.assertEqual(body_of(result)["data"]["canonicalType"], "EXPORT")
        self.assertEqual(dynamo.meta.client.calls, [])

    def test_reused_idempotency_key_with_different_payload_conflicts(self):
        subject = "subject-one"
        key = "retry-key"
        transaction_id = _transaction_id(subject, key)
        existing = {
            "transactionId": transaction_id,
            "timestamp": "2026-11-21T10:00:00Z",
            "type": "OUT",
            "productId": "p-1",
            "productName": "Cable",
            "amount": 2,
            "supplierId": None,
            "reason": "original order",
            "invoiceKey": None,
            "performedBy": "staff.one",
            "requestHash": _request_hash({
                "type": "OUT", "productId": "p-1", "amount": 2,
                "supplierId": None, "reason": "original order", "invoiceKey": None,
            }),
            "gsi1pk": "TRANSACTION",
            "gsi1sk": f"2026-11-21T10:00:00Z#{transaction_id}",
        }
        dynamo = self.make_dynamo(transaction_items=[existing])
        result = self.invoke(make_event("POST", {
            "type": "EXPORT", "productId": "p-1", "quantity": 2,
            "reason": "different order",
        }, headers={"Idempotency-Key": key}), dynamo)
        self.assertEqual(result["statusCode"], 409)
        self.assertEqual(body_of(result)["code"], "IDEMPOTENCY_KEY_REUSED")
        self.assertEqual(dynamo.meta.client.calls, [])

    def test_list_and_detail_exclude_upload_reservations(self):
        transaction = {
            "transactionId": "txn-1", "timestamp": "2026-11-21T10:00:00Z",
            "type": "IN", "productId": "p-1", "productName": "Cable",
            "amount": 1, "performedBy": "staff.one", "reason": "receipt",
            "gsi1pk": "TRANSACTION", "gsi1sk": "2026-11-21T10:00:00Z#txn-1",
        }
        reservation = {"transactionId": "UPLOAD#abc", "recordType": "UPLOAD_RESERVATION"}
        dynamo = self.make_dynamo(query_items=[transaction, reservation])
        listed = self.invoke(make_event("GET"), dynamo)
        self.assertEqual([row["transactionId"] for row in body_of(listed)["data"]], ["txn-1"])

        detail_dynamo = self.make_dynamo(transaction_items=[reservation])
        detail = self.invoke(make_event("GET", path_parameters={"transactionId": "UPLOAD#abc"}), detail_dynamo)
        self.assertEqual(detail["statusCode"], 404)


if __name__ == "__main__":
    unittest.main()
