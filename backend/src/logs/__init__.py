"""Admin-only, bounded retrieval of CloudStock Lambda log events."""

import base64
import json
import os
import re
import time

import boto3

from ..common.http import ApiError, require_any_group, success, with_error_handling

DEFAULT_WINDOW_MS = 60 * 60 * 1000
MAX_WINDOW_MS = 24 * 60 * 60 * 1000
DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 100
MAX_TOKEN_LENGTH = 2048
_SENSITIVE = re.compile(
    r"(?i)(\b[\w.-]*(?:password|passwd|secret|client[_-]?secret|access[_-]?key|"
    r"refresh[_-]?token|id[_-]?token|access[_-]?token|api[_-]?key|"
    r"authorization|credential|x-amz-signature|x-amz-credential|"
    r"x-amz-security-token)[\w.-]*\b\s*[:=]\s*)(\"[^\"]*\"|'[^']*'|[^\s,;&]+)"
)
_BEARER = re.compile(r"(?i)(\bBearer\s+)[A-Za-z0-9._~+/-]+=*")
_AWS_KEY_ID = re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b")


def _client():
    return boto3.client("logs")


def _groups():
    raw = os.environ.get("CLOUDSTOCK_LOG_GROUPS", "")
    groups = [value.strip() for value in raw.split(",") if value.strip()]
    if not groups or any(not name.startswith("/aws/lambda/") or "*" in name for name in groups):
        raise ApiError(500, "LOG_GROUPS_NOT_CONFIGURED", "Approved CloudStock log groups are not configured.")
    return groups


def _integer(value, name, minimum, maximum):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]+", value):
        raise ApiError(400, "INVALID_QUERY_PARAMETER", f"{name} must be a decimal integer.")
    parsed = int(value)
    if not minimum <= parsed <= maximum:
        raise ApiError(400, "INVALID_QUERY_PARAMETER", f"{name} is outside the allowed range.")
    return parsed


def _encode_cursor(index, service_token=None):
    raw = json.dumps({"i": index, "t": service_token}, separators=(",", ":")).encode()
    token = base64.urlsafe_b64encode(raw).decode().rstrip("=")
    if len(token) > MAX_TOKEN_LENGTH:
        raise ApiError(502, "LOGS_PAGINATION_ERROR", "CloudWatch returned an oversized pagination cursor.")
    return token


def _decode_cursor(value, group_count):
    if value is None:
        return 0, None
    if not isinstance(value, str) or not value or len(value) > MAX_TOKEN_LENGTH or not re.fullmatch(r"[A-Za-z0-9_-]+", value):
        raise ApiError(400, "INVALID_NEXT_TOKEN", "nextToken is invalid.")
    try:
        decoded = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
        cursor = json.loads(decoded)
        index, service_token = cursor["i"], cursor["t"]
        if type(index) is not int or not 0 <= index < group_count:
            raise ValueError
        if service_token is not None and (not isinstance(service_token, str) or not service_token):
            raise ValueError
        return index, service_token
    except (ValueError, KeyError, TypeError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ApiError(400, "INVALID_NEXT_TOKEN", "nextToken is invalid.") from error


def _redact(message):
    message = _BEARER.sub(r"\1[REDACTED]", message)
    message = _SENSITIVE.sub(r"\1[REDACTED]", message)
    return _AWS_KEY_ID.sub("[REDACTED]", message)


def _query(event, now_ms):
    multi = event.get("multiValueQueryStringParameters") or {}
    params = event.get("queryStringParameters") or {}
    allowed = {"startTime", "endTime", "limit", "nextToken"}
    if set(params) - allowed or set(multi) - allowed:
        raise ApiError(400, "INVALID_QUERY_PARAMETER", "Only startTime, endTime, limit, and nextToken are supported.")
    if any(not isinstance(values, list) or len(values) != 1 for values in multi.values()):
        raise ApiError(400, "INVALID_QUERY_PARAMETER", "Query parameters must not be repeated.")
    end = _integer(params["endTime"], "endTime", 1, now_ms) if params.get("endTime") is not None else now_ms
    start = _integer(params["startTime"], "startTime", 1, end) if params.get("startTime") is not None else max(1, end - DEFAULT_WINDOW_MS)
    if end <= start or end - start > MAX_WINDOW_MS:
        raise ApiError(400, "INVALID_TIME_RANGE", "The time range must be positive and no longer than 24 hours.")
    limit = _integer(params["limit"], "limit", 1, MAX_PAGE_SIZE) if params.get("limit") is not None else DEFAULT_PAGE_SIZE
    return start, end, limit, params.get("nextToken")


def _fetch(client, groups, start, end, limit, next_token):
    index, service_token = next_token
    events = []
    while index < len(groups) and len(events) < limit:
        request = {
            "logGroupName": groups[index],
            "startTime": start,
            "endTime": end,
            "limit": limit - len(events),
            "interleaved": True,
        }
        if service_token:
            request["nextToken"] = service_token
        result = client.filter_log_events(**request)
        for item in result.get("events", []):
            events.append({
                "timestamp": item.get("timestamp"),
                "ingestionTime": item.get("ingestionTime"),
                "logStreamName": item.get("logStreamName"),
                "logGroupName": groups[index],
                "message": _redact(str(item.get("message", ""))),
            })
        next_service = result.get("nextToken")
        if next_service:
            return events, _encode_cursor(index, next_service)
        index += 1
        service_token = None
    return events, (_encode_cursor(index, None) if index < len(groups) else None)


@with_error_handling
def handler(event, context=None):
    require_any_group(event, ["Admin"])
    if os.environ.get("DYNAMODB_ENDPOINT"):
        raise ApiError(501, "LOGS_UNAVAILABLE_LOCAL", "CloudWatch log retrieval is unavailable in local mode.")
    groups = _groups()
    start, end, limit, next_token = _query(event, int(time.time() * 1000))
    cursor = _decode_cursor(next_token, len(groups))
    events, cursor = _fetch(_client(), groups, start, end, limit, cursor)
    return success(events, extra={"nextToken": cursor})
