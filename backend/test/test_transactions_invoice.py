import json
import os
import threading
import unittest
from unittest.mock import patch

from boto3.dynamodb.types import TypeDeserializer, TypeSerializer
from botocore.exceptions import ClientError

from scripts.local_api import resolve_route
from src.transactions import _request_hash, _transaction_id


class FakeBody:
    def __init__(self, data):
        self.data = data

    def read(self, size=-1):
        return self.data[:size]

    def close(self):
        pass


class FakeS3:
    def __init__(self):
        self.objects = {}
        self.presign_calls = []
        self.head_calls = []
        self.get_calls = []

    def generate_presigned_url(self, operation, Params, ExpiresIn, HttpMethod):
        self.presign_calls.append((operation, Params, ExpiresIn, HttpMethod))
        return f"https://signed.example.test/{operation}/{len(self.presign_calls)}"

    def head_object(self, Bucket, Key):
        self.head_calls.append((Bucket, Key))
        value = self.objects.get(Key)
        if value is None:
            raise ClientError({"Error": {"Code": "NoSuchKey", "Message": "missing"}}, "HeadObject")
        return {"ContentLength": len(value[0]), "ContentType": value[1]}

    def get_object(self, Bucket, Key, Range):
        self.get_calls.append((Bucket, Key, Range))
        value = self.objects.get(Key)
        if value is None:
            raise ClientError({"Error": {"Code": "NoSuchKey", "Message": "missing"}}, "GetObject")
        return {"Body": FakeBody(value[0])}


class FakeTable:
    def __init__(self, key_name, items=None):
        self.key_name = key_name
        self.items = {item[key_name]: dict(item) for item in items or []}
        self.put_calls = []

    def get_item(self, Key, **kwargs):
        item = self.items.get(Key[self.key_name])
        return {"Item": dict(item)} if item else {}

    def put_item(self, **kwargs):
        self.put_calls.append(kwargs)
        item = dict(kwargs["Item"])
        self.items[item[self.key_name]] = item


class FakeDynamoClient:
    def __init__(self, tables):
        self.tables = tables
        self.calls = []
        self.deserializer = TypeDeserializer()
        self.lock = threading.Lock()
        self.fail_after_validation = False

    def _decode(self, item):
        return {name: self.deserializer.deserialize(value) for name, value in item.items()}

    def transact_write_items(self, TransactItems):
        with self.lock:
            self.calls.append(TransactItems)
            decoded = []
            for action in TransactItems:
                if "Put" in action:
                    write = action["Put"]
                    item = self._decode(write["Item"])
                    table = self.tables[write["TableName"]]
                    if item[table.key_name] in table.items:
                        self._cancel()
                    decoded.append(("Put", table, item))
                else:
                    write = action["Update"]
                    key = self._decode(write["Key"])
                    table = self.tables[write["TableName"]]
                    values = self._decode(write["ExpressionAttributeValues"])
                    if table.key_name == "transactionId":
                        current = table.items.get(key[table.key_name])
                        if (
                            not current
                            or current.get("state") != values[":pending"]
                            or current.get("ownerSub") != values[":subject"]
                            or current.get("expiresAt", 0) <= values[":now"]
                            or current.get("recordType") != values[":recordType"]
                            or current.get("reservationType") != values[":reservationType"]
                            or current.get("s3Key") != values[":s3Key"]
                            or current.get("contentType") != values[":contentType"]
                            or current.get("sizeBytes") != values[":sizeBytes"]
                            or current.get("productId") != values[":productId"]
                        ):
                            self._cancel()
                        decoded.append(("ReservationUpdate", table, key, values))
                    else:
                        decoded.append(("ProductUpdate", table, key, values))

            if self.fail_after_validation:
                raise RuntimeError("simulated transaction failure")

            for action in decoded:
                if action[0] == "Put":
                    _, table, item = action
                    table.items[item[table.key_name]] = item
                elif action[0] == "ReservationUpdate":
                    _, table, key, values = action
                    item = table.items[key[table.key_name]]
                    item.update({
                        "state": values[":consumed"],
                        "consumedAt": values[":now"],
                        "attachedTransactionId": values[":transactionId"],
                    })
                else:
                    _, table, key, values = action
                    item = table.items[key[table.key_name]]
                    new_quantity = values[":currentQuantity"] + values[":delta"]
                    item["quantity"] = new_quantity
                    item["stockQuantity"] = new_quantity

    @staticmethod
    def _cancel():
        raise ClientError({"Error": {"Code": "TransactionCanceledException", "Message": "conditional check failed"}}, "TransactWriteItems")


class FakeDynamo:
    def __init__(self, tables):
        self.tables = tables
        self.meta = type("Meta", (), {"client": FakeDynamoClient(tables)})()

    def Table(self, name):
        return self.tables[name]


def make_event(method, resource, body=None, path_parameters=None, subject="subject-1", groups=None, key="invoice-key-1"):
    return {
        "httpMethod": method,
        "resource": resource,
        "path": resource,
        "pathParameters": path_parameters or {},
        "queryStringParameters": {},
        "headers": {"Idempotency-Key": key},
        "body": json.dumps(body) if body is not None else None,
        "requestContext": {"authorizer": {"claims": {
            "sub": subject,
            "cognito:username": "staff.one",
            "cognito:groups": groups if groups is not None else ["Staff"],
        }}},
    }


def body_of(result):
    return json.loads(result["body"])


class TransactionInvoiceTests(unittest.TestCase):
    def setUp(self):
        self.products = FakeTable("productId", [{
            "productId": "p-1", "name": "Cable", "quantity": 5, "stockQuantity": 5,
        }])
        self.transactions = FakeTable("transactionId")
        self.suppliers = FakeTable("supplierId")
        self.tables = {"products": self.products, "transactions": self.transactions, "suppliers": self.suppliers}
        self.dynamo = FakeDynamo(self.tables)
        self.s3 = FakeS3()
        env = patch.dict(os.environ, {
            "PRODUCTS_TABLE": "products",
            "TRANSACTIONS_TABLE": "transactions",
            "SUPPLIERS_TABLE": "suppliers",
            "INVOICES_BUCKET": "cloudstock-test-bucket",
            "AWS_REGION": "us-east-1",
        })
        env.start()
        self.addCleanup(env.stop)
        dynamo_patch = patch("src.transactions.dynamodb", self.dynamo)
        dynamo_patch.start()
        self.addCleanup(dynamo_patch.stop)
        s3_patch = patch("src.transactions.boto3.client", return_value=self.s3)
        s3_patch.start()
        self.addCleanup(s3_patch.stop)

    def invoke(self, event):
        from src.transactions import handler

        return handler(event)

    def create_invoice_reservation(self, payload=None, subject="subject-1"):
        data = payload or {
            "productId": "p-1",
            "filename": "invoice.pdf",
            "contentType": "application/pdf",
            "sizeBytes": len(b"%PDF-1.7\n"),
        }
        result = self.invoke(make_event("POST", "/transactions/invoice-uploads", body=data, subject=subject))
        self.assertEqual(result["statusCode"], 201)
        identifier = body_of(result)["data"]["reservationId"]
        reservation = self.transactions.items[f"UPLOAD#{identifier}"]
        self.s3.objects[reservation["s3Key"]] = (b"%PDF-1.7\n", "application/pdf")
        return identifier, reservation

    def transaction_event(self, identifier, subject="subject-1", key="create-1", product_id="p-1", groups=None):
        return make_event("POST", "/transactions", {
            "type": "IMPORT",
            "productId": product_id,
            "quantity": 2,
            "reason": "received shipment",
            "invoiceReservationId": identifier,
        }, subject=subject, key=key, groups=groups)

    def test_invoice_upload_uses_private_generated_key_and_bound_reservation(self):
        identifier, reservation = self.create_invoice_reservation()
        self.assertRegex(identifier, r"^[0-9a-f]{32}$")
        self.assertEqual(reservation["transactionId"], f"UPLOAD#{identifier}")
        self.assertEqual(reservation["recordType"], "UPLOAD_RESERVATION")
        self.assertEqual(reservation["reservationType"], "INVOICE")
        self.assertEqual(reservation["ownerSub"], "subject-1")
        self.assertEqual(reservation["productId"], "p-1")
        self.assertTrue(reservation["s3Key"].startswith("invoices/"))
        self.assertEqual(reservation["contentType"], "application/pdf")
        self.assertEqual(reservation["sizeBytes"], len(b"%PDF-1.7\n"))
        self.assertGreater(reservation["expiresAt"], 0)
        self.assertEqual(reservation["state"], "PENDING")
        self.assertNotIn("gsi1pk", reservation)
        self.assertNotIn("gsi1sk", reservation)
        operation, params, expires, method = self.s3.presign_calls[0]
        self.assertEqual((operation, expires, method), ("put_object", 300, "PUT"))
        self.assertEqual(params["Bucket"], "cloudstock-test-bucket")
        self.assertEqual(params["Key"], reservation["s3Key"])

    def test_transaction_consumes_reservation_once_atomically_with_stock_and_put(self):
        identifier, reservation = self.create_invoice_reservation()
        result = self.invoke(self.transaction_event(identifier))
        self.assertEqual(result["statusCode"], 201, result["body"])
        transaction = body_of(result)["data"]
        self.assertEqual(transaction["invoiceKey"], reservation["s3Key"])
        self.assertEqual(transaction["invoiceUrl"], reservation["s3Key"])
        self.assertNotIn("signed.example.test", json.dumps(transaction))
        self.assertEqual(self.products.items["p-1"]["quantity"], 7)
        stored_reservation = self.transactions.items[f"UPLOAD#{identifier}"]
        self.assertEqual(stored_reservation["state"], "CONSUMED")
        transaction_id = transaction["transactionId"]
        self.assertEqual(stored_reservation["attachedTransactionId"], transaction_id)
        self.assertEqual(self.transactions.items[transaction_id]["invoiceReservationId"], identifier)
        self.assertEqual(self.transactions.items[transaction_id]["productId"], stored_reservation["productId"])

        actions = self.dynamo.meta.client.calls[0]
        self.assertEqual(len(actions), 3)
        self.assertIn("Update", actions[0])
        reservation_updates = [
            action["Update"] for action in actions
            if action.get("Update", {}).get("TableName") == "transactions"
        ]
        self.assertEqual(len(reservation_updates), 1)
        self.assertIn("#state = :pending", reservation_updates[0]["ConditionExpression"])
        self.assertIn("#ownerSub = :subject", reservation_updates[0]["ConditionExpression"])
        self.assertIn("#expiresAt > :now", reservation_updates[0]["ConditionExpression"])
        self.assertIn("#productId = :productId", reservation_updates[0]["ConditionExpression"])
        self.assertEqual(
            self.dynamo.meta.client._decode(reservation_updates[0]["ExpressionAttributeValues"])[":productId"],
            "p-1",
        )
        self.assertNotIn("ConditionCheck", str(actions))
        self.assertIn("Put", actions[2])

        duplicate = self.invoke(self.transaction_event(identifier))
        self.assertEqual(duplicate["statusCode"], 200, duplicate["body"])
        self.assertEqual(len(self.dynamo.meta.client.calls), 1)
        self.assertEqual(self.products.items["p-1"]["quantity"], 7)

    def test_reservation_cannot_be_used_by_another_user_or_transaction(self):
        identifier, _ = self.create_invoice_reservation()
        other_user = self.invoke(self.transaction_event(identifier, subject="subject-2", key="other-user"))
        self.assertEqual(other_user["statusCode"], 403)
        self.assertEqual(self.dynamo.meta.client.calls, [])

        first = self.invoke(self.transaction_event(identifier, key="first-transaction"))
        second = self.invoke(self.transaction_event(identifier, key="second-transaction"))
        self.assertEqual(first["statusCode"], 201)
        self.assertEqual(second["statusCode"], 409)
        self.assertEqual(len(self.dynamo.meta.client.calls), 1)

    def test_expired_or_missing_invoice_object_does_not_change_stock(self):
        identifier, reservation = self.create_invoice_reservation()
        reservation["expiresAt"] = 1
        expired = self.invoke(self.transaction_event(identifier))
        self.assertEqual(expired["statusCode"], 409)
        self.assertEqual(self.dynamo.meta.client.calls, [])
        self.assertEqual(self.products.items["p-1"]["quantity"], 5)

    def test_invalid_invoice_metadata_or_content_does_not_consume_reservation(self):
        identifier, reservation = self.create_invoice_reservation()
        self.s3.objects[reservation["s3Key"]] = (b"%PDF-1.7\n", "text/plain")
        wrong_type = self.invoke(self.transaction_event(identifier, key="wrong-invoice-type"))
        self.assertEqual(wrong_type["statusCode"], 400)
        self.assertEqual(body_of(wrong_type)["code"], "UPLOAD_TYPE_MISMATCH")

        self.s3.objects[reservation["s3Key"]] = (b"not a PDF", "application/pdf")
        wrong_content = self.invoke(self.transaction_event(identifier, key="wrong-invoice-content"))
        self.assertEqual(wrong_content["statusCode"], 400)
        self.assertEqual(body_of(wrong_content)["code"], "INVALID_INVOICE_CONTENT")
        self.assertEqual(self.transactions.items[f"UPLOAD#{identifier}"]["state"], "PENDING")
        self.assertEqual(self.dynamo.meta.client.calls, [])

        identifier, reservation = self.create_invoice_reservation()
        self.s3.objects.pop(reservation["s3Key"])
        missing = self.invoke(self.transaction_event(identifier, key="missing-object"))
        self.assertEqual(missing["statusCode"], 409)
        self.assertEqual(body_of(missing)["code"], "UPLOAD_OBJECT_MISSING")
        self.assertEqual(self.dynamo.meta.client.calls, [])
        self.assertEqual(self.products.items["p-1"]["quantity"], 5)

    def test_idempotent_invoice_retry_preserves_hash_and_stock(self):
        identifier, _ = self.create_invoice_reservation()
        event = self.transaction_event(identifier, key="retry-invoice")
        first = self.invoke(event)
        retry = self.invoke(event)
        self.assertEqual(first["statusCode"], 201)
        self.assertEqual(retry["statusCode"], 200, retry["body"])
        transaction_id = _transaction_id("subject-1", "retry-invoice")
        stored = self.transactions.items[transaction_id]
        expected_hash = _request_hash({
            "type": "IN", "productId": "p-1", "amount": 2,
            "supplierId": None, "reason": "received shipment",
            "invoiceKey": stored["invoiceKey"],
        })
        self.assertEqual(stored["requestHash"], expected_hash)
        self.assertEqual(self.products.items["p-1"]["quantity"], 7)

    def test_reservation_cannot_be_attached_to_a_different_product(self):
        identifier, _ = self.create_invoice_reservation()
        self.products.items["p-2"] = {
            "productId": "p-2", "name": "Adapter", "quantity": 4, "stockQuantity": 4,
        }
        result = self.invoke(self.transaction_event(identifier, product_id="p-2"))
        self.assertEqual(result["statusCode"], 409)
        self.assertEqual(body_of(result)["code"], "UPLOAD_PRODUCT_MISMATCH")
        self.assertEqual(self.products.items["p-1"]["quantity"], 5)
        self.assertEqual(self.products.items["p-2"]["quantity"], 4)
        self.assertEqual(self.transactions.items[f"UPLOAD#{identifier}"]["state"], "PENDING")
        self.assertEqual(self.dynamo.meta.client.calls, [])

    def test_idempotency_key_mismatch_and_insufficient_stock_do_not_consume_invoice(self):
        identifier, reservation = self.create_invoice_reservation()
        event = self.transaction_event(identifier, key="mismatch-invoice")
        first = self.invoke(event)
        mismatched = self.transaction_event(identifier, key="mismatch-invoice")
        mismatched["body"] = json.dumps({
            "type": "IMPORT", "productId": "p-1", "quantity": 3,
            "reason": "received shipment", "invoiceReservationId": identifier,
        })
        replay = self.invoke(mismatched)
        self.assertEqual(first["statusCode"], 201)
        self.assertEqual(replay["statusCode"], 409)
        self.assertEqual(body_of(replay)["code"], "IDEMPOTENCY_KEY_REUSED")

        other_id, other_reservation = self.create_invoice_reservation()
        self.products.items["p-1"]["quantity"] = 0
        self.products.items["p-1"]["stockQuantity"] = 0
        insufficient_event = self.transaction_event(other_id, key="insufficient-invoice")
        insufficient_event["body"] = json.dumps({
            "type": "EXPORT", "productId": "p-1", "quantity": 2,
            "reason": "order", "invoiceReservationId": other_id,
        })
        insufficient = self.invoke(insufficient_event)
        self.assertEqual(insufficient["statusCode"], 409)
        self.assertEqual(body_of(insufficient)["code"], "INSUFFICIENT_STOCK")
        self.assertEqual(self.transactions.items[f"UPLOAD#{other_id}"]["state"], "PENDING")
        self.assertEqual(len(self.dynamo.meta.client.calls), 1)

    def test_concurrent_attempts_consume_reservation_at_most_once(self):
        identifier, _ = self.create_invoice_reservation()
        barrier = threading.Barrier(2)
        results = []
        errors = []

        def attempt(key):
            try:
                barrier.wait(timeout=2)
                results.append(self.invoke(self.transaction_event(identifier, key=key)))
            except Exception as error:
                errors.append(error)

        first = threading.Thread(target=attempt, args=("concurrent-one",))
        second = threading.Thread(target=attempt, args=("concurrent-two",))
        first.start()
        second.start()
        first.join(timeout=5)
        second.join(timeout=5)

        self.assertFalse(first.is_alive())
        self.assertFalse(second.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(sorted(result["statusCode"] for result in results), [201, 409])
        self.assertEqual(self.products.items["p-1"]["quantity"], 7)
        self.assertEqual(self.transactions.items[f"UPLOAD#{identifier}"]["state"], "CONSUMED")
        created = [key for key in self.transactions.items if key.startswith("txn-")]
        self.assertEqual(len(created), 1)
        transaction = self.transactions.items[created[0]]
        self.assertEqual(transaction["productId"], "p-1")
        self.assertEqual(self.transactions.items[f"UPLOAD#{identifier}"]["attachedTransactionId"], created[0])

    def test_transaction_failure_keeps_stock_reservation_and_transaction_unchanged(self):
        identifier, _ = self.create_invoice_reservation()
        reservation_key = f"UPLOAD#{identifier}"
        before_stock = dict(self.products.items["p-1"])
        before_reservation = dict(self.transactions.items[reservation_key])
        self.dynamo.meta.client.fail_after_validation = True

        result = self.invoke(self.transaction_event(identifier))

        self.assertEqual(result["statusCode"], 500)
        self.assertEqual(self.products.items["p-1"], before_stock)
        self.assertEqual(self.transactions.items[reservation_key], before_reservation)
        self.assertNotIn(_transaction_id("subject-1", "create-1"), self.transactions.items)
        actions = self.dynamo.meta.client.calls[-1]
        reservation_updates = [
            action["Update"] for action in actions
            if "Update" in action
            and action["Update"]["TableName"] == "transactions"
        ]
        self.assertEqual(len(reservation_updates), 1)

    def test_direct_invoice_key_cannot_create_new_transaction(self):
        result = self.invoke(make_event("POST", "/transactions", {
            "type": "IN", "productId": "p-1", "amount": 1,
            "reason": "legacy", "invoiceKey": "invoices/supplied.pdf",
        }))
        self.assertEqual(result["statusCode"], 400)
        self.assertEqual(body_of(result)["code"], "UPLOAD_REQUIRED")
        self.assertEqual(self.dynamo.meta.client.calls, [])

    def test_legacy_invoice_key_retry_remains_idempotent(self):
        key = "legacy-invoice-retry"
        subject = "subject-1"
        object_key = "invoices/legacy-invoice.pdf"
        payload = {
            "type": "IN", "productId": "p-1", "amount": 1,
            "supplierId": None, "reason": "legacy receipt", "invoiceKey": object_key,
        }
        transaction_id = _transaction_id(subject, key)
        self.transactions.items[transaction_id] = {
            "transactionId": transaction_id,
            "timestamp": "2026-11-21T10:00:00Z",
            "createdAt": "2026-11-21T10:00:00Z",
            "performedBy": "staff.one",
            "type": "IN", "canonicalType": "IMPORT",
            "productId": "p-1", "productName": "Cable",
            "amount": 1, "quantity": 1,
            "supplierId": None, "reason": "legacy receipt",
            "invoiceKey": object_key, "invoiceUrl": object_key,
            "requestHash": _request_hash(payload),
        }
        result = self.invoke(make_event("POST", "/transactions", {
            "type": "IN", "productId": "p-1", "amount": 1,
            "reason": "legacy receipt", "invoiceKey": object_key,
        }, subject=subject, key=key))
        self.assertEqual(result["statusCode"], 200)
        self.assertEqual(self.dynamo.meta.client.calls, [])
        self.s3.objects[object_key] = (b"%PDF-1.7\n", "application/pdf")
        invoice = self.invoke(make_event(
            "GET", "/transactions/{transactionId}/invoice",
            path_parameters={"transactionId": transaction_id},
        ))
        self.assertEqual(invoice["statusCode"], 200)

    def test_invoice_retrieval_authorizes_and_returns_short_lived_url_by_transaction(self):
        identifier, reservation = self.create_invoice_reservation()
        created = self.invoke(self.transaction_event(identifier))
        self.assertEqual(created["statusCode"], 201)
        transaction_id = body_of(created)["data"]["transactionId"]
        presign_count = len(self.s3.presign_calls)
        unauthorized = self.invoke(make_event(
            "GET", "/transactions/{transactionId}/invoice",
            path_parameters={"transactionId": transaction_id}, groups=["Viewer"],
        ))
        self.assertEqual(unauthorized["statusCode"], 403)
        self.assertEqual(len(self.s3.presign_calls), presign_count)

        for role in ("Admin", "Staff"):
            result = self.invoke(make_event(
                "GET", "/transactions/{transactionId}/invoice",
                path_parameters={"transactionId": transaction_id}, groups=[role],
            ))
            self.assertEqual(result["statusCode"], 200, result["body"])
            response = body_of(result)["data"]
            self.assertEqual(response["transactionId"], transaction_id)
            self.assertEqual(response["expiresIn"], 300)
            self.assertNotIn("s3Key", response)
            operation, params, expires, method = self.s3.presign_calls[-1]
            self.assertEqual((operation, expires, method), ("get_object", 300, "GET"))
            self.assertEqual(params, {"Bucket": "cloudstock-test-bucket", "Key": reservation["s3Key"]})

    def test_invoice_retrieval_rejects_missing_transaction_and_missing_object(self):
        missing_transaction = self.invoke(make_event(
            "GET", "/transactions/{transactionId}/invoice",
            path_parameters={"transactionId": "txn-missing"},
        ))
        self.assertEqual(missing_transaction["statusCode"], 404)
        self.assertEqual(body_of(missing_transaction)["code"], "TRANSACTION_NOT_FOUND")
        self.assertEqual(self.s3.presign_calls, [])

        identifier, reservation = self.create_invoice_reservation()
        created = self.invoke(self.transaction_event(identifier))
        transaction_id = body_of(created)["data"]["transactionId"]
        self.s3.objects.pop(reservation["s3Key"])
        missing_object = self.invoke(make_event(
            "GET", "/transactions/{transactionId}/invoice",
            path_parameters={"transactionId": transaction_id},
        ))
        self.assertEqual(missing_object["statusCode"], 404)
        self.assertEqual(body_of(missing_object)["code"], "INVOICE_NOT_FOUND")
        self.assertEqual(self.s3.presign_calls, [
            call for call in self.s3.presign_calls if call[0] == "put_object"
        ])

    def test_local_routes_and_private_bucket_iam_scope(self):
        self.assertEqual(resolve_route("POST", "/transactions/invoice-uploads"), ("transactions", {}))
        self.assertEqual(
            resolve_route("GET", "/transactions/txn-1/invoice"),
            ("transactions", {"transactionId": "txn-1"}),
        )
        template = (os.path.dirname(os.path.dirname(__file__)) + "/template.yaml")
        with open(template, encoding="utf-8") as source:
            text = source.read()
        transactions_function = text.split("  TransactionsFunction:", 1)[1].split("  ProductImagesFunction:", 1)[0]
        self.assertIn(
            "            - Effect: Allow\n"
            "              Action:\n"
            "                - dynamodb:PutItem\n"
            "              Resource: !GetAtt TransactionsTable.Arn",
            transactions_function,
        )
        self.assertEqual(transactions_function.count("- dynamodb:PutItem"), 1)
        self.assertIn(
            "                - dynamodb:TransactWriteItems\n"
            "              Resource: !GetAtt ProductsTable.Arn",
            transactions_function,
        )
        self.assertIn(
            "                - dynamodb:TransactWriteItems\n"
            "              Resource: !GetAtt TransactionsTable.Arn",
            transactions_function,
        )
        self.assertIn(
            "            - Effect: Allow\n"
            "              Action:\n"
            "                - s3:PutObject\n"
            "                - s3:GetObject\n"
            '              Resource: !Sub "${ProductImagesBucket.Arn}/invoices/*"',
            transactions_function,
        )
        public_policy = text.split("  ProductImagesBucketPolicy:", 1)[1].split("  ProductsTable:", 1)[0]
        public_allow = public_policy.split("Sid: DenyInsecureTransport", 1)[0]
        self.assertIn("Action: s3:GetObject", public_allow)
        self.assertIn('Resource: !Sub "${ProductImagesBucket.Arn}/products/*"', public_allow)
        self.assertNotIn("invoices/*", public_allow)
        self.assertNotIn('Resource: !Sub "${ProductImagesBucket.Arn}/*"', public_allow)

    def test_local_s3_requires_loopback_endpoint_and_never_falls_back(self):
        from src.transactions import _s3_client

        with patch.dict(os.environ, {"DYNAMODB_ENDPOINT": "http://127.0.0.1:8000", "AWS_SAM_LOCAL": "true"}, clear=False):
            os.environ.pop("S3_ENDPOINT_URL", None)
            with patch("src.transactions.boto3.client") as client:
                with self.assertRaises(Exception) as caught:
                    _s3_client()
                self.assertEqual(getattr(caught.exception, "code", None), "LOCAL_S3_NOT_CONFIGURED")
                client.assert_not_called()
            with patch.dict(os.environ, {"S3_ENDPOINT_URL": "http://127.0.0.1:4566"}, clear=False):
                with patch("src.transactions.boto3.client") as client:
                    _s3_client()
                    client.assert_called_once_with(
                        "s3", region_name="us-east-1", endpoint_url="http://127.0.0.1:4566",
                        aws_access_key_id="local", aws_secret_access_key="local",
                    )


if __name__ == "__main__":
    unittest.main()
