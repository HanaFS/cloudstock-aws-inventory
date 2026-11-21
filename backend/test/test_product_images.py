import json
import os
import re
import unittest
from pathlib import Path
from unittest.mock import patch

from botocore.exceptions import ClientError
from scripts.local_api import resolve_route


class FakeBody:
    def __init__(self, content):
        self.content = content

    def read(self, size=-1):
        return self.content[:size]

    def close(self):
        pass


class FakeS3:
    def __init__(self, content_type="image/png", content_length=8, content=b"\x89PNG\r\n\x1a\n"):
        self.content_type = content_type
        self.content_length = content_length
        self.content = content
        self.presign_calls = []
        self.head_calls = []
        self.get_calls = []
        self.missing = False

    def generate_presigned_url(self, operation, Params, ExpiresIn, HttpMethod):
        self.presign_calls.append((operation, Params, ExpiresIn, HttpMethod))
        return "https://upload.example.test/signed"

    def head_object(self, Bucket, Key):
        self.head_calls.append((Bucket, Key))
        if self.missing:
            raise ClientError({"Error": {"Code": "NoSuchKey", "Message": "missing"}}, "HeadObject")
        return {"ContentLength": self.content_length, "ContentType": self.content_type}

    def get_object(self, Bucket, Key, Range):
        self.get_calls.append((Bucket, Key, Range))
        if self.missing:
            raise ClientError({"Error": {"Code": "NoSuchKey", "Message": "missing"}}, "GetObject")
        return {"Body": FakeBody(self.content)}


class FakeTable:
    def __init__(self, key_name, items=None):
        self.key_name = key_name
        self.items = {item[key_name]: dict(item) for item in items or []}
        self.put_calls = []

    def get_item(self, Key):
        item = self.items.get(Key[self.key_name])
        return {"Item": dict(item)} if item else {}

    def put_item(self, **kwargs):
        self.put_calls.append(kwargs)
        item = kwargs["Item"]
        self.items[item[self.key_name]] = dict(item)


class FakeClient:
    def __init__(self, tables):
        self.tables = tables
        self.calls = []

    def transact_write_items(self, TransactItems):
        self.calls.append(TransactItems)
        for action in TransactItems:
            update = action["Update"]
            table = self.tables[update["TableName"]]
            key = next(iter(update["Key"].values()))["S"]
            if table.key_name == "transactionId":
                table.items[key]["state"] = "CONSUMED"
            elif table.key_name == "productId":
                values = update["ExpressionAttributeValues"]
                table.items[key]["imageUrl"] = values[":imageUrl"]["S"]
                table.items[key]["imageKey"] = values[":imageKey"]["S"]


class FakeDynamo:
    def __init__(self, tables):
        self.tables = tables
        self.meta = type("Meta", (), {"client": FakeClient(tables)})()

    def Table(self, name):
        return self.tables[name]


def make_event(method, path_parameters=None, body=None, subject="subject-1", groups=None):
    return {
        "httpMethod": method,
        "pathParameters": path_parameters or {},
        "body": json.dumps(body) if body is not None else None,
        "requestContext": {"authorizer": {"claims": {
            "sub": subject,
            "cognito:groups": groups if groups is not None else ["Staff"],
        }}},
    }


def body_of(result):
    return json.loads(result["body"])


class ProductImageUploadTests(unittest.TestCase):
    def setUp(self):
        self.product_id = "p-1"
        self.products = FakeTable("productId", [{"productId": self.product_id, "name": "Cable"}])
        self.transactions = FakeTable("transactionId")
        self.tables = {"products": self.products, "transactions": self.transactions}
        self.dynamo = FakeDynamo(self.tables)
        self.s3 = FakeS3()
        self.env = patch.dict(os.environ, {
            "PRODUCTS_TABLE": "products",
            "TRANSACTIONS_TABLE": "transactions",
            "PRODUCT_IMAGES_BUCKET": "cloudstock-test-images",
            "PRODUCT_IMAGES_PUBLIC_BASE_URL": "https://cloudstock-test-images.s3.us-east-1.amazonaws.com",
            "AWS_REGION": "us-east-1",
        })
        self.env.start()
        self.addCleanup(self.env.stop)
        self.dynamo_patch = patch("src.product_images.dynamodb", self.dynamo)
        self.dynamo_patch.start()
        self.addCleanup(self.dynamo_patch.stop)
        self.s3_patch = patch("src.product_images.boto3.client", return_value=self.s3)
        self.s3_patch.start()
        self.addCleanup(self.s3_patch.stop)

    def invoke(self, event):
        from src.product_images import handler

        return handler(event)

    def create_reservation(self):
        result = self.invoke(make_event("POST", {"productId": self.product_id}, {
            "filename": "cable.png", "contentType": "image/png", "sizeBytes": 8,
        }))
        self.assertEqual(result["statusCode"], 201)
        return body_of(result)["data"]["reservationId"]

    def test_create_generates_products_key_and_short_lived_presigned_put(self):
        result = self.invoke(make_event("POST", {"productId": self.product_id}, {
            "filename": "cable.png", "contentType": "image/png", "sizeBytes": 8,
        }))
        self.assertEqual(result["statusCode"], 201)
        data = body_of(result)["data"]
        reservation = self.transactions.put_calls[0]["Item"]
        self.assertRegex(reservation["transactionId"], r"^UPLOAD#[0-9a-f]{32}$")
        self.assertNotIn("gsi1pk", reservation)
        self.assertNotIn("gsi1sk", reservation)
        self.assertTrue(reservation["s3Key"].startswith("products/"))
        self.assertEqual(reservation["ownerSub"], "subject-1")
        self.assertEqual(reservation["contentType"], "image/png")
        self.assertEqual(reservation["sizeBytes"], 8)
        self.assertEqual(reservation["state"], "PENDING")
        self.assertIn("expiresAt", reservation)
        operation, params, expires, method = self.s3.presign_calls[0]
        self.assertEqual((operation, expires, method), ("put_object", 300, "PUT"))
        self.assertEqual(params["Bucket"], "cloudstock-test-images")
        self.assertEqual(params["Key"], reservation["s3Key"])
        self.assertEqual(params["ContentLength"], 8)
        self.assertEqual(params["IfNoneMatch"], "*")
        self.assertEqual(data["requiredHeaders"]["If-None-Match"], "*")
        self.assertNotIn("s3Key", data)
        self.assertTrue(data["uploadUrl"].startswith("https://"))

    def test_rejects_unsafe_filename_type_size_and_unauthorized_user(self):
        for body, code in (
            ({"filename": "../cable.png", "contentType": "image/png", "sizeBytes": 8}, "INVALID_FILENAME"),
            ({"filename": "cable.jpg", "contentType": "image/png", "sizeBytes": 8}, "UNSUPPORTED_IMAGE_TYPE"),
            ({"filename": "cable.png", "contentType": "image/png", "sizeBytes": 5 * 1024 * 1024 + 1}, "INVALID_IMAGE_SIZE"),
        ):
            result = self.invoke(make_event("POST", {"productId": self.product_id}, body))
            self.assertEqual(body_of(result)["code"], code)
        denied = self.invoke(make_event("POST", {"productId": self.product_id}, {
            "filename": "cable.png", "contentType": "image/png", "sizeBytes": 8,
        }, groups=["Viewer"]))
        self.assertEqual(denied["statusCode"], 403)
        self.assertEqual(self.transactions.put_calls, [])

    def test_attach_verifies_object_and_atomically_consumes_reservation_and_updates_product(self):
        identifier = self.create_reservation()
        result = self.invoke(make_event("POST", {
            "productId": self.product_id, "reservationId": identifier,
        }, subject="subject-1"))
        self.assertEqual(result["statusCode"], 200)
        data = body_of(result)["data"]
        self.assertEqual(data["imageKey"], self.transactions.put_calls[0]["Item"]["s3Key"])
        self.assertTrue(data["imageUrl"].startswith("https://cloudstock-test-images."))
        self.assertEqual(len(self.s3.head_calls), 1)
        self.assertEqual(len(self.s3.get_calls), 1)
        actions = self.dynamo.meta.client.calls[0]
        self.assertEqual(len(actions), 2)
        reservation_updates = [action["Update"] for action in actions if action["Update"]["TableName"] == "transactions"]
        self.assertEqual(len(reservation_updates), 1)
        self.assertEqual(
            reservation_updates[0]["Key"]["transactionId"]["S"],
            f"UPLOAD#{identifier}",
        )
        self.assertIn("#state = :pending", reservation_updates[0]["ConditionExpression"])
        self.assertIn("#ownerSub = :subject", reservation_updates[0]["ConditionExpression"])
        self.assertIn("#expiresAt > :now", reservation_updates[0]["ConditionExpression"])
        self.assertNotIn("ConditionCheck", str(actions))

    def test_other_user_and_expired_reservations_cannot_attach(self):
        identifier = self.create_reservation()
        denied = self.invoke(make_event("POST", {
            "productId": self.product_id, "reservationId": identifier,
        }, subject="other-subject"))
        self.assertEqual(denied["statusCode"], 403)

        reservation = next(iter(self.transactions.items.values()))
        reservation["expiresAt"] = 1
        expired = self.invoke(make_event("POST", {
            "productId": self.product_id, "reservationId": identifier,
        }))
        self.assertEqual(expired["statusCode"], 409)
        self.assertEqual(self.dynamo.meta.client.calls, [])

    def test_missing_object_or_metadata_or_content_rejects_attach(self):
        identifier = self.create_reservation()
        self.s3.content_length = 7
        wrong_size = self.invoke(make_event("POST", {
            "productId": self.product_id, "reservationId": identifier,
        }))
        self.assertEqual(body_of(wrong_size)["code"], "UPLOAD_SIZE_MISMATCH")
        self.assertEqual(self.dynamo.meta.client.calls, [])

        self.s3.content_length = 8
        self.s3.content_type = "application/octet-stream"
        wrong_type = self.invoke(make_event("POST", {
            "productId": self.product_id, "reservationId": identifier,
        }))
        self.assertEqual(body_of(wrong_type)["code"], "UPLOAD_TYPE_MISMATCH")

        self.s3.content_type = "image/png"
        self.s3.content = b"not an image"
        wrong_content = self.invoke(make_event("POST", {
            "productId": self.product_id, "reservationId": identifier,
        }))
        self.assertEqual(body_of(wrong_content)["code"], "INVALID_IMAGE_CONTENT")
        self.assertEqual(self.dynamo.meta.client.calls, [])

    def test_consumed_reservation_cannot_be_reused(self):
        identifier = self.create_reservation()
        path = {"productId": self.product_id, "reservationId": identifier}
        first = self.invoke(make_event("POST", path))
        second = self.invoke(make_event("POST", path))
        self.assertEqual(first["statusCode"], 200)
        self.assertEqual(second["statusCode"], 409)
        self.assertEqual(len(self.dynamo.meta.client.calls), 1)

    def test_missing_s3_object_is_not_attached(self):
        identifier = self.create_reservation()
        self.s3.missing = True
        result = self.invoke(make_event("POST", {
            "productId": self.product_id, "reservationId": identifier,
        }))
        self.assertEqual(result["statusCode"], 409)
        self.assertEqual(body_of(result)["code"], "UPLOAD_OBJECT_MISSING")
        self.assertEqual(self.dynamo.meta.client.calls, [])

    def test_local_adapter_resolves_both_upload_routes(self):
        identifier = "0123456789abcdef0123456789abcdef"
        self.assertEqual(
            resolve_route("POST", f"/products/{self.product_id}/image-uploads"),
            ("product_images", {"productId": self.product_id}),
        )
        self.assertEqual(
            resolve_route("POST", f"/products/{self.product_id}/image-uploads/{identifier}/complete"),
            ("product_images", {"productId": self.product_id, "reservationId": identifier}),
        )

    def test_template_scopes_image_upload_dynamodb_permissions(self):
        template_path = Path(__file__).resolve().parents[1] / "template.yaml"
        template = template_path.read_text(encoding="utf-8")
        function = template.split("  ProductImagesFunction:", 1)[1].split("  ProductImagesBucket:", 1)[0]
        statements = re.findall(
            r"(?ms)^            - Effect: Allow\n(.*?)(?=^            - Effect: Allow|\Z)",
            function,
        )

        def resources_for(action):
            matches = [statement for statement in statements if f"- {action}" in statement]
            self.assertEqual(len(matches), 1, f"Expected one IAM statement for {action}")
            return re.findall(r"!GetAtt ([A-Za-z0-9]+)\.Arn", matches[0])

        self.assertEqual(resources_for("dynamodb:PutItem"), ["TransactionsTable"])
        self.assertEqual(
            set(resources_for("dynamodb:TransactWriteItems")),
            {"ProductsTable", "TransactionsTable"},
        )
        self.assertNotRegex(function, r"dynamodb:[^\n]+\n\s+Resource:\s+\*")


if __name__ == "__main__":
    unittest.main()
