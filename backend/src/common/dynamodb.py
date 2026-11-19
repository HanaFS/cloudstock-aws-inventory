import base64
import json
import os

import boto3
from boto3.dynamodb.conditions import Attr

from .http import ApiError


def create_dynamodb_resource(env=None):
    env = os.environ if env is None else env
    endpoint = env.get("DYNAMODB_ENDPOINT")
    if not endpoint:
        if env.get("AWS_SAM_LOCAL") == "true":
            raise RuntimeError("DYNAMODB_ENDPOINT is required when running with SAM local.")
        return boto3.resource(
            "dynamodb",
            region_name=env.get("AWS_REGION") or env.get("AWS_DEFAULT_REGION") or "us-east-1",
        )
    return boto3.resource(
        "dynamodb",
        endpoint_url=endpoint,
        region_name=env.get("AWS_REGION", "us-east-1"),
        aws_access_key_id="local",
        aws_secret_access_key="local",
    )


dynamodb = create_dynamodb_resource()
MAX_PAGE_SIZE = 100


def parse_limit(event):
    raw_limit = (event.get("queryStringParameters") or {}).get("limit")
    if raw_limit is None:
        return MAX_PAGE_SIZE
    if not raw_limit.isdigit() or not 1 <= int(raw_limit) <= MAX_PAGE_SIZE:
        raise ApiError(400, "INVALID_LIMIT", "limit phải là số nguyên từ 1 đến 100.")
    return int(raw_limit)


def decode_cursor(cursor, key_names):
    if not cursor:
        return None
    if len(cursor) > 2048:
        raise ApiError(400, "INVALID_CURSOR", "nextToken không hợp lệ.")
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        key = json.loads(base64.urlsafe_b64decode(padded).decode("utf-8"))
        names = key_names if isinstance(key_names, list) else [key_names]
        if not isinstance(key, dict) or any(
            not isinstance(key.get(name), str) for name in names
        ):
            raise ValueError("Invalid key")
        return key
    except (ValueError, TypeError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ApiError(400, "INVALID_CURSOR", "nextToken không hợp lệ.") from error


def encode_cursor(key):
    if not key:
        return None
    raw = json.dumps(key, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def scan_page(table, event, key_name, filter_expression=None):
    request = {"Limit": parse_limit(event)}
    cursor = decode_cursor(
        (event.get("queryStringParameters") or {}).get("nextToken"), key_name
    )
    if cursor:
        request["ExclusiveStartKey"] = cursor
    if filter_expression is not None:
        request["FilterExpression"] = filter_expression
    result = table.scan(**request)
    return {"items": result.get("Items", []), "nextToken": encode_cursor(result.get("LastEvaluatedKey"))}


def query_page(table, event, **query):
    query["Limit"] = parse_limit(event)
    cursor = decode_cursor(
        (event.get("queryStringParameters") or {}).get("nextToken"),
        ["transactionId", "gsi1pk", "gsi1sk"],
    )
    if cursor:
        query["ExclusiveStartKey"] = cursor
    result = table.query(**query)
    return {"items": result.get("Items", []), "nextToken": encode_cursor(result.get("LastEvaluatedKey"))}


def scan_all(table, **request):
    items = []
    while True:
        result = table.scan(**request)
        items.extend(result.get("Items", []))
        cursor = result.get("LastEvaluatedKey")
        if not cursor:
            return items
        request["ExclusiveStartKey"] = cursor


def is_conditional_failure(error):
    return (
        getattr(error, "response", {})
        .get("Error", {})
        .get("Code")
        == "ConditionalCheckFailedException"
    )
