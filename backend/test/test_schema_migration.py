import unittest

from scripts.schema_migration import build_report, plan_product, plan_transaction


class ProductMigrationPlanTests(unittest.TestCase):
    def test_maps_stock_and_derives_status_without_writing(self):
        plan = plan_product({
            "productId": "p-1",
            "name": "Part",
            "category": "Hardware",
            "price": 10,
            "quantity": 0,
            "minThreshold": 3,
            "imageUrl": "",
            "updatedAt": "2026-11-21T10:00:00Z",
        })
        self.assertEqual(plan["disposition"], "ready")
        self.assertEqual(plan["changes"]["stockQuantity"], 0)
        self.assertEqual(plan["changes"]["status"], "OUT_OF_STOCK")

    def test_conflicting_stock_values_require_review(self):
        plan = plan_product({
            "productId": "p-1",
            "name": "Part",
            "category": "Hardware",
            "price": 10,
            "quantity": 2,
            "stockQuantity": 4,
            "minThreshold": 3,
            "imageUrl": "",
            "updatedAt": "2026-11-21T10:00:00Z",
        })
        self.assertEqual(plan["disposition"], "review_required")
        self.assertIn("FIELD_CONFLICT:quantity:stockQuantity", plan["issues"])

    def test_image_reference_requires_external_object_verification(self):
        plan = plan_product({
            "productId": "p-1",
            "name": "Part",
            "category": "Hardware",
            "price": 10,
            "stockQuantity": 2,
            "minThreshold": 3,
            "imageKey": "products/p-1.png",
            "updatedAt": "2026-11-21T10:00:00Z",
        })
        self.assertIn("S3_OBJECT_VERIFICATION_REQUIRED:imageUrl", plan["issues"])
        self.assertNotIn("imageUrl", plan["changes"])


class TransactionMigrationPlanTests(unittest.TestCase):
    def test_maps_fields_type_and_gsi_without_changing_keys_or_hash(self):
        record = {
            "transactionId": "txn-1",
            "productId": "p-1",
            "productName": "Paper",
            "performedBy": "warehouse-user",
            "timestamp": "2026-11-21T10:00:00Z",
            "type": "IN",
            "amount": 3,
            "supplierId": "s-1",
            "gsi1pk": "TRANSACTION",
            "gsi1sk": "legacy-sort-key",
            "requestHash": "preserve-me",
        }
        plan = plan_transaction(record)
        self.assertEqual(plan["disposition"], "ready")
        self.assertEqual(plan["changes"]["createdAt"], record["timestamp"])
        self.assertEqual(plan["changes"]["quantity"], 3)
        self.assertEqual(plan["changes"]["canonicalType"], "IMPORT")
        self.assertEqual(
            plan["changes"]["gsi1sk"],
            f"{record['timestamp']}#{record['transactionId']}",
        )
        self.assertNotIn("transactionId", plan["changes"])
        self.assertNotIn("requestHash", plan["changes"])

    def test_invalid_timestamp_and_unknown_type_require_review(self):
        plan = plan_transaction({
            "transactionId": "txn-1",
            "productId": "p-1",
            "productName": "Paper",
            "performedBy": "warehouse-user",
            "timestamp": "not-a-time",
            "type": "TRANSFER",
            "amount": 1,
            "gsi1pk": "TRANSACTION",
            "gsi1sk": "legacy",
        })
        self.assertEqual(plan["disposition"], "review_required")
        self.assertIn("INVALID_TIMESTAMP:createdAt", plan["issues"])
        self.assertIn("UNKNOWN_TRANSACTION_TYPE:type", plan["issues"])

    def test_invoice_reference_requires_external_object_verification(self):
        plan = plan_transaction({
            "transactionId": "txn-1",
            "productId": "p-1",
            "productName": "Paper",
            "performedBy": "warehouse-user",
            "createdAt": "2026-11-21T10:00:00Z",
            "type": "OUT",
            "quantity": 1,
            "reason": "Order",
            "supplierId": None,
            "gsi1pk": "TRANSACTION",
            "gsi1sk": "2026-11-21T10:00:00Z#txn-1",
            "invoiceKey": "invoices/i-1.pdf",
        })
        self.assertIn("S3_OBJECT_VERIFICATION_REQUIRED:invoiceUrl", plan["issues"])
        self.assertEqual(plan["changes"]["invoiceUrl"], "invoices/i-1.pdf")

    def test_report_is_dry_run_and_validates_input_shape(self):
        report = build_report({"products": [], "transactions": []})
        self.assertEqual(report["mode"], "dry-run")
        self.assertFalse(report["writesPerformed"])
        self.assertEqual(report["summary"]["records"], 0)
        with self.assertRaises(ValueError):
            build_report({"products": {}, "transactions": []})

    def test_report_flags_transaction_without_product_reference(self):
        report = build_report({
            "products": [],
            "transactions": [{
                "transactionId": "txn-1",
                "productId": "missing-product",
                "productName": "Historical name",
                "performedBy": "warehouse-user",
                "createdAt": "2026-11-21T10:00:00Z",
                "type": "OUT",
                "quantity": 1,
                "reason": "Order",
                "supplierId": None,
                "gsi1pk": "TRANSACTION",
                "gsi1sk": "2026-11-21T10:00:00Z#txn-1",
            }],
        })
        self.assertEqual(report["summary"]["reviewRequired"], 1)
        self.assertIn(
            "MISSING_PRODUCT_REFERENCE:productId",
            report["plans"][0]["issues"],
        )


if __name__ == "__main__":
    unittest.main()
