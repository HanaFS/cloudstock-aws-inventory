import unittest

from src.schema_compat import (
    CompatibilityError,
    normalize_product,
    normalize_transaction,
)


class ProductCompatibilityTests(unittest.TestCase):
    def test_normalizes_legacy_only_stock(self):
        source = {"productId": "p-1", "quantity": 7, "name": "Cable"}
        original = dict(source)
        result = normalize_product(source)
        self.assertEqual(result["quantity"], 7)
        self.assertEqual(result["stockQuantity"], 7)
        self.assertEqual(source, original)

    def test_normalizes_canonical_only_stock(self):
        result = normalize_product({"productId": "p-1", "stockQuantity": 4})
        self.assertEqual(result["quantity"], 4)
        self.assertEqual(result["stockQuantity"], 4)

    def test_accepts_matching_dual_stock(self):
        result = normalize_product({
            "productId": "p-1", "quantity": 4, "stockQuantity": 4,
        })
        self.assertEqual(result["stockQuantity"], 4)

    def test_rejects_conflicting_dual_stock(self):
        source = {"productId": "p-1", "quantity": 4, "stockQuantity": 5}
        original = dict(source)
        with self.assertRaises(CompatibilityError) as error:
            normalize_product(source)
        self.assertEqual(error.exception.code, "FIELD_CONFLICT")
        self.assertEqual(source, original)

    def test_rejects_missing_or_invalid_stock(self):
        for record in ({"productId": "p-1"}, {"productId": "p-1", "quantity": True}):
            with self.subTest(record=record):
                with self.assertRaises(CompatibilityError):
                    normalize_product(record)


class TransactionCompatibilityTests(unittest.TestCase):
    def _base(self):
        return {
            "transactionId": "txn-1",
            "productId": "p-1",
            "productName": "Cable",
            "performedBy": "warehouse-user",
        }

    def test_normalizes_legacy_only_fields_and_preserves_request_hash(self):
        source = {
            **self._base(),
            "amount": 3,
            "timestamp": "2026-11-21T10:00:00Z",
            "type": "IN",
            "requestHash": "original-hash",
        }
        original = dict(source)
        result = normalize_transaction(source)
        self.assertEqual(result["quantity"], 3)
        self.assertEqual(result["createdAt"], source["timestamp"])
        self.assertEqual(result["type"], "IN")
        self.assertEqual(result["canonicalType"], "IMPORT")
        self.assertEqual(result["requestHash"], "original-hash")
        self.assertEqual(source, original)

    def test_maps_legacy_out_to_canonical_export(self):
        result = normalize_transaction({
            **self._base(),
            "amount": 1,
            "timestamp": "2026-11-21T10:00:00Z",
            "type": "OUT",
        })
        self.assertEqual(result["type"], "OUT")
        self.assertEqual(result["canonicalType"], "EXPORT")

    def test_accepts_canonical_only_fields(self):
        result = normalize_transaction({
            **self._base(),
            "quantity": 2,
            "createdAt": "2026-11-21T10:00:00Z",
            "canonicalType": "EXPORT",
        })
        self.assertEqual(result["amount"], 2)
        self.assertEqual(result["timestamp"], result["createdAt"])
        self.assertEqual(result["type"], "OUT")

    def test_accepts_matching_dual_fields(self):
        result = normalize_transaction({
            **self._base(),
            "amount": 2,
            "quantity": 2,
            "timestamp": "2026-11-21T10:00:00Z",
            "createdAt": "2026-11-21T10:00:00Z",
            "type": "OUT",
            "canonicalType": "EXPORT",
        })
        self.assertEqual(result["canonicalType"], "EXPORT")
        self.assertEqual(result["type"], "OUT")

    def test_rejects_conflicting_aliases_and_types(self):
        cases = [
            {"amount": 2, "quantity": 3},
            {"timestamp": "2026-11-21T10:00:00Z", "createdAt": "2026-11-22T10:00:00Z"},
            {"type": "IN", "canonicalType": "EXPORT"},
        ]
        for fields in cases:
            record = {**self._base(), **fields}
            record.setdefault("amount", 1)
            record.setdefault("timestamp", "2026-11-21T10:00:00Z")
            record.setdefault("type", "IN")
            original = dict(record)
            with self.subTest(fields=fields):
                with self.assertRaises(CompatibilityError) as error:
                    normalize_transaction(record)
                self.assertEqual(error.exception.code, "FIELD_CONFLICT")
                self.assertEqual(record, original)

    def test_rejects_invalid_types_and_missing_required_fields(self):
        invalid_type = {
            **self._base(), "amount": 1,
            "timestamp": "2026-11-21T10:00:00Z", "type": "TRANSFER",
        }
        with self.assertRaises(CompatibilityError) as error:
            normalize_transaction(invalid_type)
        self.assertEqual(error.exception.code, "INVALID_TRANSACTION_TYPE")

        for missing in (
            {**self._base(), "timestamp": "2026-11-21T10:00:00Z", "type": "IN"},
            {**self._base(), "amount": 1, "type": "IN"},
            {"productId": "p-1", "amount": 1, "timestamp": "2026-11-21T10:00:00Z", "type": "IN"},
        ):
            with self.subTest(record=missing):
                with self.assertRaises(CompatibilityError):
                    normalize_transaction(missing)


if __name__ == "__main__":
    unittest.main()
