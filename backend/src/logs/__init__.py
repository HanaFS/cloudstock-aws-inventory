import os
import re
import time

import boto3

from ..common.dynamodb import decode_cursor, encode_cursor, parse_limit
from ..common.http import ApiError, require_any_group, success, with_error_handling

_LEVEL = re.compile(r"\b(DEBUG|INFO|WARN|WARNING|ERROR|CRITICAL)\b", re.IGNORECASE)


def _client():
    if os.environ.get("LOCAL_API") == "true" and not os.environ.get("CLOUDWATCH_ENDPOINT"):
        raise ApiError(503, "LOCAL_SERVICE_UNAVAILABLE", "CloudWatch Logs không được cấu hình cho chế độ local.")
    options = {}
    if os.environ.get("CLOUDWATCH_ENDPOINT"):
        options["endpoint_url"] = os.environ["CLOUDWATCH_ENDPOINT"]
    return boto3.client("logs", **options)


def _log_groups():
    groups = [
        group.strip()
        for group in os.environ.get("LOG_GROUPS", "").split(",")
        if group.strip()
    ]
    if not groups:
        raise ApiError(503, "LOGS_NOT_CONFIGURED", "Chưa cấu hình LOG_GROUPS cho CloudWatch Logs.")
    if len(groups) > 50:
        raise RuntimeError("LOG_GROUPS cannot contain more than 50 groups.")
    return groups


@with_error_handling
def handler(event, context=None):
    require_any_group(event, ["Admin"])
    if event.get("httpMethod") != "GET" or event.get("path") != "/logs":
        raise ApiError(404, "ROUTE_NOT_FOUND", "Không tìm thấy endpoint.")
    params = event.get("queryStringParameters") or {}
    request = {
        "logGroupNames": _log_groups(),
        "limit": parse_limit(event),
    }
    for parameter in ("startTime", "endTime"):
        value = params.get(parameter)
        if value is not None:
            if not value.isdigit():
                raise ApiError(400, "INVALID_TIME_RANGE", f"{parameter} phải là epoch milliseconds.")
            request[parameter] = int(value)
    if "startTime" not in request:
        request["startTime"] = max(0, int((time.time() - 7 * 24 * 60 * 60) * 1000))
    if request.get("endTime", int(time.time() * 1000)) < request["startTime"]:
        raise ApiError(400, "INVALID_TIME_RANGE", "endTime phải lớn hơn hoặc bằng startTime.")
    pattern = params.get("filterPattern")
    if pattern:
        if len(pattern) > 256:
            raise ApiError(400, "INVALID_FILTER_PATTERN", "filterPattern tối đa 256 ký tự.")
        request["filterPattern"] = pattern
    cursor = decode_cursor(params.get("nextToken"), "cloudWatchToken")
    if cursor:
        request["nextToken"] = cursor["cloudWatchToken"]
    result = _client().filter_log_events(**request)
    events = []
    for item in result.get("events", []):
        message = item.get("message", "")
        level_match = _LEVEL.search(message)
        events.append({
            "eventId": item.get("eventId"),
            "timestamp": item.get("timestamp"),
            "logStream": item.get("logStreamName"),
            "logGroup": item.get("logGroupName"),
            "level": level_match.group(1).upper() if level_match else "INFO",
            "message": message,
        })
    next_token = result.get("nextToken")
    return success(
        events,
        extra={"nextToken": encode_cursor({"cloudWatchToken": next_token})} if next_token else None,
    )
