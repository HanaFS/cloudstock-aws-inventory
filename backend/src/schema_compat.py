"""Pure helpers for normalizing legacy and canonical CloudStock records.

These helpers do not read or write persistence and are intentionally not wired
into existing handlers. They retain both field spellings during migration and
raise CompatibilityError when values disagree or required values are invalid.
"""


class CompatibilityError(ValueError):
    """A record cannot be normalized without resolving invalid/conflicting data."""

    def __init__(self, code, field, message):
        super().__init__(message)
        self.code = code
        self.field = field


def _coalesce_aliases(record, legacy_name, canonical_name, validator):
    legacy_present = legacy_name in record
    canonical_present = canonical_name in record

    if not legacy_present and not canonical_present:
        raise CompatibilityError(
            "MISSING_FIELD",
            canonical_name,
            f"Missing required field: {legacy_name} or {canonical_name}.",
        )

    legacy_value = record.get(legacy_name)
    canonical_value = record.get(canonical_name)
    if legacy_present and canonical_present and legacy_value != canonical_value:
        raise CompatibilityError(
            "FIELD_CONFLICT",
            canonical_name,
            f"Conflicting values for {legacy_name} and {canonical_name}.",
        )

    value = canonical_value if canonical_present else legacy_value
    if not validator(value):
        raise CompatibilityError(
            "INVALID_FIELD",
            canonical_name,
            f"Invalid value for {canonical_name}.",
        )
    return value


def _nonnegative_integer(value):
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _positive_integer(value):
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _nonempty_string(value):
    return isinstance(value, str) and bool(value.strip())


def normalize_product(record):
    """Return a copy containing matching ``quantity`` and ``stockQuantity``.

    All unrelated product fields are preserved. The input mapping is not
    mutated, and no product status or business rule is inferred here.
    """
    if not isinstance(record, dict):
        raise CompatibilityError("INVALID_RECORD", "product", "Product must be an object.")
    product_id = record.get("productId")
    if not _nonempty_string(product_id):
        raise CompatibilityError("MISSING_FIELD", "productId", "Missing or invalid productId.")

    stock = _coalesce_aliases(
        record, "quantity", "stockQuantity", _nonnegative_integer
    )
    normalized = dict(record)
    normalized["quantity"] = stock
    normalized["stockQuantity"] = stock
    return normalized


_LEGACY_TO_CANONICAL_TYPE = {"IN": "IMPORT", "OUT": "EXPORT"}
_CANONICAL_TO_LEGACY_TYPE = {value: key for key, value in _LEGACY_TO_CANONICAL_TYPE.items()}


def _normalize_type(record):
    legacy_name = "type"
    canonical_name = "canonicalType"
    has_type = legacy_name in record
    has_canonical = canonical_name in record
    if not has_type and not has_canonical:
        raise CompatibilityError("MISSING_FIELD", "type", "Missing transaction type.")

    raw_type = record.get(legacy_name)
    canonical_type = record.get(canonical_name)
    if has_type:
        if raw_type in _LEGACY_TO_CANONICAL_TYPE:
            mapped = _LEGACY_TO_CANONICAL_TYPE[raw_type]
        elif raw_type in _CANONICAL_TO_LEGACY_TYPE:
            mapped = raw_type
        else:
            raise CompatibilityError("INVALID_TRANSACTION_TYPE", "type", "Unknown transaction type.")
    else:
        mapped = None

    if has_canonical and canonical_type not in _CANONICAL_TO_LEGACY_TYPE:
        raise CompatibilityError(
            "INVALID_TRANSACTION_TYPE", canonical_name, "Unknown canonical transaction type."
        )
    if mapped is not None and has_canonical and mapped != canonical_type:
        raise CompatibilityError(
            "FIELD_CONFLICT", canonical_name, "Conflicting legacy and canonical transaction types."
        )

    resolved = canonical_type if has_canonical else mapped
    if resolved is None:
        raise CompatibilityError("MISSING_FIELD", "type", "Missing transaction type.")
    return _CANONICAL_TO_LEGACY_TYPE[resolved], resolved


def normalize_transaction(record):
    """Return a copy with both legacy and canonical transaction fields.

    ``type`` remains IN/OUT for old consumers; ``canonicalType`` is IMPORT or
    EXPORT for new consumers. Existing requestHash is copied unchanged.
    """
    if not isinstance(record, dict):
        raise CompatibilityError(
            "INVALID_RECORD", "transaction", "Transaction must be an object."
        )
    for field in ("transactionId", "productId", "productName", "performedBy"):
        if not _nonempty_string(record.get(field)):
            raise CompatibilityError("MISSING_FIELD", field, f"Missing or invalid {field}.")

    quantity = _coalesce_aliases(record, "amount", "quantity", _positive_integer)
    created_at = _coalesce_aliases(
        record, "timestamp", "createdAt", _nonempty_string
    )
    legacy_type, canonical_type = _normalize_type(record)

    normalized = dict(record)
    normalized["amount"] = quantity
    normalized["quantity"] = quantity
    normalized["timestamp"] = created_at
    normalized["createdAt"] = created_at
    normalized["type"] = legacy_type
    normalized["canonicalType"] = canonical_type
    return normalized
