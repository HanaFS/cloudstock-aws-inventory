import json
import logging
import os
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlsplit

MAX_BODY_BYTES = 1024 * 1024
LOCAL_FRONTEND_ORIGIN = "http://localhost:8080"
_COLLECTION = re.compile(r"^/(products|suppliers|transactions)$")
_ITEM = re.compile(r"^/(products|suppliers|transactions)/([^/]+)$")
_PRODUCT_IMAGE_UPLOAD = re.compile(r"^/products/([^/]+)/image-uploads$")
_PRODUCT_IMAGE_ATTACH = re.compile(r"^/products/([^/]+)/image-uploads/([0-9a-f]{32})/complete$")
_INVOICE_UPLOAD = re.compile(r"^/transactions/invoice-uploads$")
_TRANSACTION_INVOICE = re.compile(r"^/transactions/([^/]+)/invoice$")
_DASHBOARD = re.compile(r"^/dashboard(?:/stats)?$")
_USERS = re.compile(r"^/users$")
_USER_ITEM = re.compile(r"^/users/([^/]+)$")
_USER_ROLE = re.compile(r"^/users/([^/]+)/role$")
_LOGS = {"/transactions/logs", "/logs"}


def resolve_route(method, pathname):
    if method == "GET" and pathname == "/health":
        return "health", {}
    if method == "GET" and _DASHBOARD.fullmatch(pathname):
        return "dashboard", {}
    if method == "GET" and pathname in _LOGS:
        return "logs", {}
    if method in ("GET", "POST") and _USERS.fullmatch(pathname):
        return "users", {}
    if method == "PUT":
        user_role = _USER_ROLE.fullmatch(pathname)
        if user_role:
            try:
                username = unquote(user_role.group(1))
            except (UnicodeDecodeError, ValueError):
                return None
            return "users", {"username": username}
    user = _USER_ITEM.fullmatch(pathname)
    if user and method in ("GET", "PUT", "DELETE"):
        try:
            username = unquote(user.group(1))
        except (UnicodeDecodeError, ValueError):
            return None
        return "users", {"username": username}
    if method == "POST" and _INVOICE_UPLOAD.fullmatch(pathname):
        return "transactions", {}
    if method == "GET":
        invoice = _TRANSACTION_INVOICE.fullmatch(pathname)
        if invoice:
            try:
                transaction_id = unquote(invoice.group(1))
            except (UnicodeDecodeError, ValueError):
                return None
            return "transactions", {"transactionId": transaction_id}
    if method == "POST":
        image_attach = _PRODUCT_IMAGE_ATTACH.fullmatch(pathname)
        if image_attach:
            return "product_images", {
                "productId": unquote(image_attach.group(1)),
                "reservationId": image_attach.group(2),
            }
        image_upload = _PRODUCT_IMAGE_UPLOAD.fullmatch(pathname)
        if image_upload:
            return "product_images", {"productId": unquote(image_upload.group(1))}
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
    }[resource]
    allowed = ("GET",) if resource == "transactions" else ("GET", "PUT", "DELETE")
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
    env["DYNAMODB_ENDPOINT"] = endpoint
    env["STAGE"] = "dev"
    env["FRONTEND_ORIGIN"] = LOCAL_FRONTEND_ORIGIN
    env.setdefault("PRODUCTS_TABLE", "cloudstock-dev-products")
    env.setdefault("SUPPLIERS_TABLE", "cloudstock-dev-suppliers")
    env.setdefault("TRANSACTIONS_TABLE", "cloudstock-dev-transactions")
    env.setdefault("PRODUCT_IMAGES_BUCKET", "cloudstock-dev-product-images-local")
    env.setdefault("INVOICES_BUCKET", env["PRODUCT_IMAGES_BUCKET"])
    return env


class LocalApiServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def create_local_api_server(handlers=None, frontend_origin=LOCAL_FRONTEND_ORIGIN):
    if handlers is None:
        from src.health import handler as health_handler
        from src.dashboard import handler as dashboard_handler
        from src.logs import handler as logs_handler
        from src.products import handler as products_handler
        from src.product_images import handler as product_images_handler
        from src.suppliers import handler as suppliers_handler
        from src.transactions import handler as transactions_handler
        from src.users import handler as users_handler

        handlers = {
            "health": health_handler,
            "dashboard": dashboard_handler,
            "logs": logs_handler,
            "products": products_handler,
            "product_images": product_images_handler,
            "suppliers": suppliers_handler,
            "transactions": transactions_handler,
            "users": users_handler,
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
