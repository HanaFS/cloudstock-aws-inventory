import json
import logging
import os
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlsplit

MAX_BODY_BYTES = 1024 * 1024
LOCAL_FRONTEND_ORIGIN = "http://localhost:8080"
_COLLECTION = re.compile(r"^/(products|suppliers|transactions)$")
_ITEM = re.compile(r"^/(products|suppliers|transactions|users)/([^/]+)$")


def resolve_route(method, pathname):
    if method == "GET" and pathname == "/health":
        return "health", {}
    if pathname in ("/dashboard", "/dashboard/stats") and method == "GET":
        return "dashboard", {}
    if pathname == "/logs" and method == "GET":
        return "logs", {}
    if pathname == "/products/upload-url" and method == "POST":
        return "products", {}
    if pathname == "/transactions/invoice-upload-url" and method == "POST":
        return "transactions", {}
    invoice = re.fullmatch(r"^/transactions/([^/]+)/invoice-url$", pathname)
    if invoice and method == "GET":
        return "transactions", {"transactionId": unquote(invoice.group(1))}
    if pathname == "/users" and method in ("GET", "POST"):
        return "users", {}
    password_reset = re.fullmatch(r"^/users/([^/]+)/reset-password$", pathname)
    if password_reset and method == "POST":
        return "users", {"userId": unquote(password_reset.group(1))}
    collection = _COLLECTION.fullmatch(pathname)
    if collection:
        resource = collection.group(1)
        if method in ("GET", "POST"):
            return resource, {}
        return None
    item = _ITEM.fullmatch(pathname)
    if not item:
        return None
    resource = item.group(1)
    parameter = {
        "products": "productId",
        "suppliers": "supplierId",
        "transactions": "transactionId",
        "users": "userId",
    }[resource]
    allowed = ("GET",) if resource == "transactions" else ("GET", "PUT", "DELETE")
    if resource == "users":
        allowed = ("GET", "PUT", "DELETE")
    if method not in allowed:
        return None
    try:
        item_id = unquote(item.group(2))
    except (UnicodeDecodeError, ValueError):
        return None
    return resource, {parameter: item_id}


def local_claims(authorization):
    match = re.fullmatch(r"Bearer local-dev:(Admin|Staff)", authorization or "")
    if not match:
        return None
    role = match.group(1)
    username = f"local-{role.lower()}"
    return {
        "sub": username,
        "username": username,
        "cognito:username": username,
        "cognito:groups": [role],
    }


def configure_local_environment(env=None):
    env = os.environ if env is None else env
    endpoint = env.get("DYNAMODB_ENDPOINT", "http://127.0.0.1:8000")
    parsed = urlsplit(endpoint)
    if (
        parsed.scheme != "http"
        or parsed.port != 8000
        or parsed.hostname not in ("localhost", "127.0.0.1")
    ):
        raise ValueError("Local API chỉ cho phép DynamoDB Local trên localhost:8000.")
    for variable, ports in (
        ("S3_ENDPOINT", {4566, 9000}),
        ("COGNITO_ENDPOINT", {4566}),
        ("CLOUDWATCH_ENDPOINT", {4566}),
    ):
        svc_endpoint = env.get(variable)
        if not svc_endpoint:
            continue
        service = urlsplit(svc_endpoint)
        if (
            service.scheme != "http"
            or service.hostname not in ("localhost", "127.0.0.1")
            or service.port not in ports
        ):
            allowed = ", ".join(str(port) for port in sorted(ports))
            raise ValueError(f"{variable} chỉ được trỏ tới localhost trên cổng {allowed}.")
    env["DYNAMODB_ENDPOINT"] = endpoint
    env["STAGE"] = "dev"
    env["LOCAL_API"] = "true"
    env["FRONTEND_ORIGIN"] = LOCAL_FRONTEND_ORIGIN
    env["TABLE_PRODUCTS"] = "cloudstock-dev-products"
    env["TABLE_SUPPLIERS"] = "cloudstock-dev-suppliers"
    env["TABLE_TRANSACTIONS"] = "cloudstock-dev-transactions"
    return env


class LocalApiServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def create_local_api_server(handlers=None, frontend_origin=LOCAL_FRONTEND_ORIGIN):
    if handlers is None:
        from src.catalog import handler as catalog_handler
        from src.dashboard import handler as dashboard_handler
        from src.health import handler as health_handler
        from src.logs import handler as logs_handler
        from src.transactions import handler as transactions_handler
        from src.users import handler as users_handler

        handlers = {
            "health": health_handler,
            "products": catalog_handler,
            "suppliers": catalog_handler,
            "transactions": transactions_handler,
            "users": users_handler,
            "dashboard": dashboard_handler,
            "logs": logs_handler,
        }

    class RequestHandler(BaseHTTPRequestHandler):
        def _write_json(self, status_code, payload, headers=None):
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status_code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", frontend_origin)
            self.send_header("Vary", "Origin")
            for name, value in (headers or {}).items():
                self.send_header(name, value)
            self.end_headers()
            self.wfile.write(body)

        def _dispatch(self):
            origin = self.headers.get("Origin")
            if origin and origin != frontend_origin:
                self._write_json(403, {
                    "success": False,
                    "message": "Origin không được phép truy cập API local.",
                    "code": "ORIGIN_NOT_ALLOWED",
                })
                return
            if self.command == "OPTIONS":
                if origin != frontend_origin:
                    self._write_json(403, {
                        "success": False,
                        "message": "Origin không được phép truy cập API local.",
                        "code": "ORIGIN_NOT_ALLOWED",
                    })
                    return
                self.send_response(204)
                self.send_header("Access-Control-Allow-Origin", frontend_origin)
                self.send_header("Access-Control-Allow-Methods", "GET,POST,PUT,DELETE,OPTIONS")
                self.send_header("Access-Control-Allow-Headers", "Content-Type,Authorization,Idempotency-Key")
                self.send_header("Access-Control-Max-Age", "600")
                self.send_header("Vary", "Origin")
                self.end_headers()
                return

            parsed = urlsplit(self.path)
            route = resolve_route(self.command, parsed.path)
            resource, path_parameters = route if route else (None, None)
            if not resource or not callable(handlers.get(resource)):
                self._write_json(404, {
                    "success": False,
                    "message": "Không tìm thấy endpoint.",
                    "code": "ROUTE_NOT_FOUND",
                })
                return

            claims = {}
            if resource != "health":
                claims = local_claims(self.headers.get("Authorization"))
                if not claims:
                    self._write_json(401, {
                        "success": False,
                        "message": "Cần đăng nhập bằng tài khoản mock Admin hoặc Staff.",
                        "code": "UNAUTHORIZED",
                    })
                    return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length < 0 or length > MAX_BODY_BYTES:
                    self._write_json(413, {
                        "success": False,
                        "message": "Request body vượt quá 1 MB.",
                        "code": "REQUEST_TOO_LARGE",
                    })
                    return
                body = self.rfile.read(length).decode("utf-8") if length else None
                query = parse_qs(parsed.query, keep_blank_values=True)
                event = {
                    "httpMethod": self.command,
                    "path": parsed.path,
                    "pathParameters": path_parameters,
                    "queryStringParameters": {key: values[-1] for key, values in query.items()},
                    "headers": {key.lower(): value for key, value in self.headers.items()},
                    "body": body,
                    "requestContext": {"authorizer": {"claims": claims}},
                }
                result = handlers[resource](event, None)
                self.send_response(result.get("statusCode", 200))
                for name, value in result.get("headers", {}).items():
                    if name.lower() not in ("access-control-allow-origin", "vary"):
                        self.send_header(name, value)
                self.send_header("Access-Control-Allow-Origin", frontend_origin)
                self.send_header("Vary", "Origin")
                self.end_headers()
                self.wfile.write((result.get("body") or "").encode("utf-8"))
            except (UnicodeDecodeError, ValueError):
                self._write_json(400, {
                    "success": False,
                    "message": "Đường dẫn hoặc request không hợp lệ.",
                    "code": "INVALID_PATH",
                })
            except Exception:
                logging.exception("Local API request failed")
                self._write_json(500, {
                    "success": False,
                    "message": "Đã xảy ra lỗi khi xử lý yêu cầu local.",
                    "code": "INTERNAL_ERROR",
                })

        do_GET = _dispatch
        do_POST = _dispatch
        do_PUT = _dispatch
        do_DELETE = _dispatch
        do_OPTIONS = _dispatch

        def log_message(self, format_string, *args):
            logging.info("%s - %s", self.address_string(), format_string % args)

    return LocalApiServer(("127.0.0.1", 0), RequestHandler)


def start_local_api():
    configure_local_environment()
    port = int(os.environ.get("PORT", "3001"))
    if not 1 <= port <= 65535:
        raise ValueError("PORT phải là số nguyên từ 1 đến 65535.")
    server = LocalApiServer(("127.0.0.1", port), _make_handler())
    logging.info("CloudStock local API chạy tại http://localhost:%s", port)
    server.serve_forever()


def _make_handler():
    server = create_local_api_server()
    handler = server.RequestHandlerClass
    server.server_close()
    return handler


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    try:
        start_local_api()
    except (OSError, ValueError, RuntimeError):
        logging.exception("Không thể khởi động CloudStock local API")
        raise SystemExit(1)
