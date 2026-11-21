import json
import os
import unittest
from unittest.mock import patch

from botocore.exceptions import ClientError

from src.common.http import ApiError
from src.invoices import load_invoice_reservation


class FakeBody:
    def __init__(self, data):
        self.data = data

    def read(self, size=-1):
        return self.data[:size]

    def close(self):
        pass


class FakeS3:
    def __init__(self):
        self.calls = []
        self.objects = {}

    def generate_presigned_url(self, operation, Params, ExpiresIn, HttpMethod):
        self.calls.append((operation, Params, ExpiresIn, HttpMethod))
        return f"https://private.example.test/{operation}"

    def head_object(self, Bucket, Key):
        value = self.objects.get(Key)
        if value is None:
            raise ClientError({"Error": {"Code": "NoSuchKey", "Message": "missing"}}, "HeadObject")
        return {"ContentLength": len(value[0]), "ContentType": value[1]}

    def get_object(self, Bucket, Key, Range):
        value = self.objects.get(Key)
        if value is None:
            raise ClientError({"Error": {"Code": "NoSuchKey", "Message": "missing"}}, "GetObject")
        return {"Body": FakeBody(value[0])}


class FakeTable:
    def __init__(self, items=None):
        self.items = {item["transactionId"]: dict(item) for item in items or []}
        self.put_calls = []

    def get_item(self, Key, **kwargs):
        item = self.items.get(Key["transactionId"])
        return {"Item": dict(item)} if item else {}

    def put_item(self, **kwargs):
        self.put_calls.append(kwargs)
        item = dict(kwargs["Item"])
        self.items[item["transactionId"]] = item


class FakeDynamo:
    def __init__(self, table):
        self.table = table

    def Table(self, name):
        return self.table


def make_event(method, resource, path_parameters=None, body=None, subject="user-1", groups=None):
    return {
        "httpMethod": method,
        "resource": resource,
        "pathParameters": path_parameters or {},
        "body": json.dumps(body) if body is not None else None,
        "requestContext": {"authorizer": {"claims": {
            "sub": subject,
            "cognito:groups": groups if groups is not None else ["Staff"],
        }}},
    }


def body_of(result):
    return json.loads(result["body"])


class InvoiceUploadTests(unittest.TestCase):
    def setUp(self):
        self.table = FakeTable()
        self.dynamo = FakeDynamo(self.table)
        self.s3 = FakeS3()
        env = patch.dict(os.environ, {
            "TRANSACTIONS_TABLE": "transactions",
            "INVOICES_BUCKET": "private-cloudstock-bucket",
            "AWS_REGION": "us-east-1",
        })
        env.start()
        self.addCleanup(env.stop)
        dynamo_patch = patch("src.invoices.dynamodb", self.dynamo)
        dynamo_patch.start()
        self.addCleanup(dynamo_patch.stop)
        s3_patch = patch("src.invoices.boto3.client", return_value=self.s3)
        s3_patch.start()
        self.addCleanup(s3_patch.stop)

    def invoke(self, event):
        from src.invoices import handler

        return handler(event)

    def create_upload(self, content_type="application/pdf", filename="invoice.pdf", data=b"%PDF-1.7\n"):
        result = self.invoke(make_event("POST", "/transactions/invoice-uploads", body={
            "filename": filename,
            "contentType": content_type,
            "sizeBytes": len(data),
        }))
        self.assertEqual(result["statusCode"], 201)
        return body_of(result)["data"], next(iter(self.table.items.values())), data

    def test_upload_reservation_is_private_generated_and_bound_to_subject(self):
        data, reservation, _ = self.create_upload()
        self.assertRegex(reservation["transactionId"], r"^UPLOAD#[0-9a-f]{32}$")
        self.assertEqual(reservation["recordType"], "UPLOAD_RESERVATION")
        self.assertEqual(reservation["reservationType"], "INVOICE")
        self.assertEqual(reservation["ownerSub"], "user-1")
        self.assertRegex(reservation["s3Key"], r"^invoices/[0-9a-f]{32}\.pdf$")
        self.assertEqual(reservation["state"], "PENDING")
        self.assertIn("expiresAt", reservation)
        self.assertNotIn("gsi1pk", reservation)
        self.assertNotIn("gsi1sk", reservation)
        operation, params, expires, method = self.s3.calls[0]
        self.assertEqual((operation, expires, method), ("put_object", 300, "PUT"))
        self.assertEqual(params["Bucket"], "private-cloudstock-bucket")
        self.assertEqual(params["Key"], reservation["s3Key"])
        self.assertEqual(data["reservationId"], reservation["transactionId"].split("#", 1)[1])
        self.assertNotIn("s3Key", data)

    def test_authorization_and_reservation_ownership_are_enforced(self):
        denied = self.invoke(make_event("POST", "/transactions/invoice-uploads", body={
            "filename": "invoice.pdf", "contentType": "application/pdf", "sizeBytes": 8,
        }, groups=["Viewer"]))
        self.assertEqual(denied["statusCode"], 403)
        _, reservation, _ = self.create_upload()
        with self.assertRaises(ApiError) as caught:
            load_invoice_reservation(reservation["transactionId"].split("#", 1)[1], "other-user")
        self.assertEqual(caught.exception.status_code, 403)

    def test_expired_reservation_is_rejected(self):
        _, reservation, _ = self.create_upload()
        self.table.items[reservation["transactionId"]]["expiresAt"] = 1
        with self.assertRaises(ApiError) as caught:
            load_invoice_reservation(reservation["transactionId"].split("#", 1)[1], "user-1")
        self.assertEqual(caught.exception.status_code, 409)

    def test_missing_object_prevents_attachment_verification(self):
        _, reservation, _ = self.create_upload()
        with patch.dict(os.environ, {"S3_ENDPOINT_URL": "http://localhost:4566", "DYNAMODB_ENDPOINT": "http://localhost:8000"}):
            from src.invoices import verify_invoice_object
            with self.assertRaises(ApiError) as caught:
                verify_invoice_object(reservation)
        self.assertEqual(caught.exception.code, "UPLOAD_OBJECT_MISSING")

    def test_retrieval_requires_existing_transaction_and_returns_temporary_presigned_get(self):
        key = "invoices/0123456789abcdef0123456789abcdef.pdf"
        transaction = {
            "transactionId": "txn-1", "invoiceKey": key, "invoiceUrl": key,
        }
        self.table.items["txn-1"] = transaction
        self.s3.objects[key] = (b"%PDF-1.7\n", "application/pdf")
        result = self.invoke(make_event("GET", "/transactions/{transactionId}/invoice", {
            "transactionId": "txn-1",
        }))
        self.assertEqual(result["statusCode"], 200)
        data = body_of(result)["data"]
        self.assertEqual(data["transactionId"], "txn-1")
        self.assertEqual(data["expiresIn"], 300)
        operation, params, expires, method = self.s3.calls[-1]
        self.assertEqual((operation, expires, method), ("get_object", 300, "GET"))
        self.assertEqual(params, {"Bucket": "private-cloudstock-bucket", "Key": key})

    def test_invoice_retrieval_is_available_to_authorized_staff_not_only_uploader(self):
        key = "invoices/0123456789abcdef0123456789abcdef.pdf"
        reservation_id = "abcdef0123456789abcdef0123456789"
        self.table.items["txn-3"] = {
            "transactionId": "txn-3", "invoiceKey": key,
            "invoiceReservationId": reservation_id,
        }
        self.table.items[f"UPLOAD#{reservation_id}"] = {
            "transactionId": f"UPLOAD#{reservation_id}",
            "recordType": "UPLOAD_RESERVATION", "reservationType": "INVOICE",
            "ownerSub": "original-uploader", "s3Key": key, "state": "CONSUMED",
            "attachedTransactionId": "txn-3",
        }
        self.s3.objects[key] = (b"%PDF-1.7\n", "application/pdf")
        result = self.invoke(make_event("GET", "/transactions/{transactionId}/invoice", {
            "transactionId": "txn-3",
        }, subject="another-staff-member"))
        self.assertEqual(result["statusCode"], 200)

    def test_missing_transaction_or_invoice_object_returns_not_found(self):
        missing_transaction = self.invoke(make_event("GET", "/transactions/{transactionId}/invoice", {
            "transactionId": "missing",
        }))
        self.assertEqual(missing_transaction["statusCode"], 404)
        key = "invoices/0123456789abcdef0123456789abcdef.pdf"
        self.table.items["txn-2"] = {"transactionId": "txn-2", "invoiceKey": key}
        missing_object = self.invoke(make_event("GET", "/transactions/{transactionId}/invoice", {
            "transactionId": "txn-2",
        }))
        self.assertEqual(missing_object["statusCode"], 404)


if __name__ == "__main__":
    unittest.main()
