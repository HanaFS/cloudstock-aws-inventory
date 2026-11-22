import json
import logging
import os
from decimal import Decimal
from functools import wraps


class ApiError(Exception):
    def __init__(self, status_code, code, message):
        super().__init__(message)
        self.status_code = status_code
        self.code = code


def _json_default(obj):
    if isinstance(obj, Decimal):
        return int(obj) if obj % 1 == 0 else float(obj)
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def response(status_code, payload):
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": os.environ.get(
                "FRONTEND_ORIGIN", "http://localhost:8080"
            ),
            "Vary": "Origin",
        },
        "body": json.dumps(
            payload, ensure_ascii=False, separators=(",", ":"), default=_json_default
        ),
    }


def success(data, status_code=200, extra=None):
    return response(status_code, {"success": True, "data": data, **(extra or {})})


def parse_body(event):
    raw_body = event.get("body")
    if not raw_body:
        return {}
    try:
        body = json.loads(raw_body)
    except (TypeError, ValueError) as error:
        raise ApiError(400, "INVALID_JSON", "Request body phải là JSON hợp lệ.") from error
    if not isinstance(body, dict):
        raise ApiError(400, "INVALID_BODY", "Request body phải là một object JSON.")
    return body


def require_any_group(event, allowed_groups):
    claims = (
        event.get("requestContext", {})
        .get("authorizer", {})
        .get("claims", {})
    )
    raw_groups = claims.get("cognito:groups", claims.get("groups", []))
    if isinstance(raw_groups, str):
        try:
            raw_groups = json.loads(raw_groups)
        except ValueError:
            raw_groups = [group.strip() for group in raw_groups.split(",")]
    if not isinstance(raw_groups, list) or not any(
        group in allowed_groups for group in raw_groups
    ):
        raise ApiError(403, "FORBIDDEN", "Tài khoản không có quyền thực hiện thao tác này.")


def with_error_handling(handler):
    @wraps(handler)
    def wrapped(event, context=None):
        try:
            return handler(event, context)
        except ApiError as error:
            return response(
                error.status_code,
                {"success": False, "message": str(error), "code": error.code},
            )
        except Exception:
            logging.exception("Unhandled API error")
            return response(
                500,
                {
                    "success": False,
                    "message": "Đã xảy ra lỗi khi xử lý yêu cầu.",
                    "code": "INTERNAL_ERROR",
                },
            )

    return wrapped
