"""Read-only dry-run planner for the CloudStock schema migration.

This module never connects to AWS and never writes data. It plans field changes
for JSON records supplied by the caller and flags S3 references that require
separate object verification before they can be migrated.
"""

import argparse
import json
from datetime import datetime
from pathlib import Path


def _iso_timestamp(value):
    if not isinstance(value, str) or not value:
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() is not None


def _required_string(item, field, issues, allow_empty=False):
    value = item.get(field)
    if not isinstance(value, str) or (not allow_empty and not value.strip()):
        issues.append(f"INVALID_VALUE:{field}")
        return False
    return True


def _nonnegative_integer(item, field, issues):
    value = item.get(field)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        issues.append(f"INVALID_VALUE:{field}")
        return False
    return True


def _rename_field(item, old_name, new_name, changes, issues):
    old_present = old_name in item
    new_present = new_name in item
    if old_present and new_present:
        if item[old_name] != item[new_name]:
            issues.append(f"FIELD_CONFLICT:{old_name}:{new_name}")
        return item[new_name]
    if new_present:
        return item[new_name]
    if old_present:
        changes[new_name] = item[old_name]
        return item[old_name]
    issues.append(f"MISSING_FIELD:{old_name}|{new_name}")
    return None


def plan_product(item):
    """Return proposed product changes without accessing DynamoDB or S3."""
    changes = {}
    issues = []
    product_id = item.get("productId")
    if not isinstance(product_id, str) or not product_id:
        issues.append("INVALID_KEY:productId")

    _required_string(item, "name", issues)
    _required_string(item, "category", issues)
    _nonnegative_integer(item, "price", issues)
    _nonnegative_integer(item, "minThreshold", issues)
    if not _iso_timestamp(item.get("updatedAt")):
        issues.append("INVALID_TIMESTAMP:updatedAt")

    stock = _rename_field(item, "quantity", "stockQuantity", changes, issues)
    if isinstance(stock, bool) or not isinstance(stock, int) or stock < 0:
        issues.append("INVALID_VALUE:stockQuantity")
    else:
        derived_status = "IN_STOCK" if stock > 0 else "OUT_OF_STOCK"
        existing_status = item.get("status")
        if existing_status not in (None, "IN_STOCK", "OUT_OF_STOCK"):
            issues.append("INVALID_VALUE:status")
        elif existing_status is not None and existing_status != derived_status:
            issues.append("STATUS_CONFLICT:status")
        elif existing_status is None:
            changes["status"] = derived_status

    image_key = item.get("imageKey")
    image_url = item.get("imageUrl")
    if image_key and image_url and image_key != image_url:
        issues.append("FIELD_CONFLICT:imageKey:imageUrl")
    if image_key or image_url:
        # Presence and metadata cannot establish S3 object existence or content.
        issues.append("S3_OBJECT_VERIFICATION_REQUIRED:imageUrl")
    elif "imageUrl" not in item:
        changes["imageUrl"] = ""

    return _plan("product", product_id, changes, issues)


def _canonical_type(item, changes, issues):
    legacy_type = item.get("type")
    mapped = {"IN": "IMPORT", "OUT": "EXPORT"}.get(legacy_type)
    canonical_shadow = item.get("canonicalType")
    if mapped is None and legacy_type not in ("IMPORT", "EXPORT"):
        issues.append("UNKNOWN_TRANSACTION_TYPE:type")
        return
    expected = mapped or legacy_type
    if canonical_shadow is not None and canonical_shadow != expected:
        issues.append("FIELD_CONFLICT:type:canonicalType")
    elif canonical_shadow is None:
        changes["canonicalType"] = expected


def plan_transaction(item):
    """Return proposed transaction changes, preserving physical/index keys."""
    changes = {}
    issues = []
    transaction_id = item.get("transactionId")
    if not isinstance(transaction_id, str) or not transaction_id:
        issues.append("INVALID_KEY:transactionId")

    _required_string(item, "productId", issues)
    _required_string(item, "productName", issues)
    _required_string(item, "performedBy", issues)

    quantity = _rename_field(item, "amount", "quantity", changes, issues)
    if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity <= 0:
        issues.append("INVALID_VALUE:quantity")
    created_at = _rename_field(item, "timestamp", "createdAt", changes, issues)
    if not _iso_timestamp(created_at):
        issues.append("INVALID_TIMESTAMP:createdAt")

    _canonical_type(item, changes, issues)

    reason = item.get("reason")
    effective_type = item.get("canonicalType") or {
        "IN": "IMPORT",
        "OUT": "EXPORT",
    }.get(item.get("type"), item.get("type"))
    if effective_type == "EXPORT" and (not isinstance(reason, str) or not reason.strip()):
        issues.append("MISSING_EXPORT_REASON:reason")

    supplier_id = item.get("supplierId")
    if effective_type == "IMPORT" and not isinstance(supplier_id, str):
        issues.append("MISSING_IMPORT_SUPPLIER:supplierId")
    if effective_type == "EXPORT" and supplier_id not in (None, ""):
        issues.append("INVALID_EXPORT_SUPPLIER:supplierId")

    invoice_key = item.get("invoiceKey")
    invoice_url = item.get("invoiceUrl")
    if invoice_key and invoice_url and invoice_key != invoice_url:
        issues.append("FIELD_CONFLICT:invoiceKey:invoiceUrl")
    if invoice_key and not invoice_url:
        changes["invoiceUrl"] = invoice_key
    if invoice_key or invoice_url:
        # The planner cannot verify S3 ownership, prefix, or object existence.
        issues.append("S3_OBJECT_VERIFICATION_REQUIRED:invoiceUrl")

    if item.get("gsi1pk") != "TRANSACTION":
        issues.append("INVALID_GSI_PARTITION:gsi1pk")
    if _iso_timestamp(created_at) and isinstance(transaction_id, str) and transaction_id:
        expected_gsi_sk = f"{created_at}#{transaction_id}"
        if item.get("gsi1sk") != expected_gsi_sk:
            changes["gsi1sk"] = expected_gsi_sk

    # requestHash and transactionId are deliberately preserved and never rewritten.
    return _plan("transaction", transaction_id, changes, issues)


def _plan(record_type, record_id, changes, issues):
    return {
        "recordType": record_type,
        "recordId": record_id,
        "disposition": "review_required" if issues else "ready",
        "changes": changes,
        "issues": issues,
    }


def build_report(document):
    """Plan records from {products: [...], transactions: [...]} JSON input."""
    products = document.get("products", [])
    transactions = document.get("transactions", [])
    if not isinstance(products, list) or not isinstance(transactions, list):
        raise ValueError("products and transactions must be JSON arrays")

    if any(not isinstance(item, dict) for item in products + transactions):
        raise ValueError("each product and transaction must be a JSON object")

    plans = [plan_product(item) for item in products]
    product_ids = {
        item.get("productId")
        for item in products
        if isinstance(item.get("productId"), str)
    }
    for item in transactions:
        plan = plan_transaction(item)
        if item.get("productId") not in product_ids:
            plan["issues"].append("MISSING_PRODUCT_REFERENCE:productId")
            plan["disposition"] = "review_required"
        plans.append(plan)
    return {
        "mode": "dry-run",
        "writesPerformed": False,
        "summary": {
            "records": len(plans),
            "ready": sum(plan["disposition"] == "ready" for plan in plans),
            "reviewRequired": sum(
                plan["disposition"] == "review_required" for plan in plans
            ),
        },
        "plans": plans,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="JSON file containing products and transactions arrays")
    args = parser.parse_args(argv)

    # This command intentionally has no execution/write option and emits only to stdout.
    document = json.loads(Path(args.input).read_text(encoding="utf-8"))
    print(json.dumps(build_report(document), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
