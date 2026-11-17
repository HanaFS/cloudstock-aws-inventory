const http = require("node:http");
const { URL } = require("node:url");

const MAX_BODY_BYTES = 1024 * 1024;
const LOCAL_FRONTEND_ORIGIN = "http://localhost:8080";

function resolveRoute(method, pathname) {
  if (method === "GET" && pathname === "/health") {
    return { handler: "health", pathParameters: {} };
  }

  const collectionMatch = /^\/(products|suppliers|transactions)$/.exec(pathname);
  if (collectionMatch) {
    const resource = collectionMatch[1];
    if (["GET", "POST"].includes(method)) {
      return { handler: resource, pathParameters: {} };
    }
    return null;
  }

  const itemMatch = /^\/(products|suppliers|transactions)\/([^/]+)$/.exec(pathname);
  if (!itemMatch) return null;

  let id;
  try {
    id = decodeURIComponent(itemMatch[2]);
  } catch {
    return null;
  }

  const [resource, parameterName] =
    itemMatch[1] === "products"
      ? ["products", "productId"]
      : itemMatch[1] === "suppliers"
        ? ["suppliers", "supplierId"]
        : ["transactions", "transactionId"];
  const allowedMethods =
    resource === "transactions" ? ["GET"] : ["GET", "PUT", "DELETE"];
  if (!allowedMethods.includes(method)) return null;

  return {
    handler: resource,
    pathParameters: { [parameterName]: id },
  };
}

function localClaims(authorization) {
  const match =
    typeof authorization === "string" &&
    /^Bearer local-dev:(Admin|Staff)$/.exec(authorization);
  if (!match) return null;

  const role = match[1];
  const username = `local-${role.toLowerCase()}`;
  return {
    sub: username,
    username,
    "cognito:username": username,
    "cognito:groups": [role],
  };
}

async function readBody(request) {
  const chunks = [];
  let length = 0;
  for await (const chunk of request) {
    length += chunk.length;
    if (length > MAX_BODY_BYTES) {
      const error = new Error("Request body vượt quá 1 MB.");
      error.statusCode = 413;
      throw error;
    }
    chunks.push(chunk);
  }
  return chunks.length ? Buffer.concat(chunks).toString("utf8") : null;
}

function writeJson(response, statusCode, payload, headers = {}) {
  response.writeHead(statusCode, {
    "Content-Type": "application/json",
    "Access-Control-Allow-Origin": LOCAL_FRONTEND_ORIGIN,
    Vary: "Origin",
    ...headers,
  });
  response.end(JSON.stringify(payload));
}

function createLocalApiServer({ handlers, frontendOrigin = LOCAL_FRONTEND_ORIGIN }) {
  return http.createServer(async (request, response) => {
    const origin = request.headers.origin;
    if (origin && origin !== frontendOrigin) {
      writeJson(response, 403, {
        success: false,
        message: "Origin không được phép truy cập API local.",
        code: "ORIGIN_NOT_ALLOWED",
      });
      return;
    }

    if (request.method === "OPTIONS") {
      if (origin !== frontendOrigin) {
        writeJson(response, 403, {
          success: false,
          message: "Origin không được phép truy cập API local.",
          code: "ORIGIN_NOT_ALLOWED",
        });
        return;
      }
      response.writeHead(204, {
        "Access-Control-Allow-Origin": frontendOrigin,
        "Access-Control-Allow-Methods": "GET,POST,PUT,DELETE,OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type,Authorization,Idempotency-Key",
        "Access-Control-Max-Age": "600",
        Vary: "Origin",
      });
      response.end();
      return;
    }

    let url;
    try {
      url = new URL(request.url, "http://localhost");
    } catch {
      writeJson(response, 400, {
        success: false,
        message: "Đường dẫn request không hợp lệ.",
        code: "INVALID_PATH",
      });
      return;
    }

    const route = resolveRoute(request.method, url.pathname);
    if (!route || typeof handlers[route.handler] !== "function") {
      writeJson(response, 404, {
        success: false,
        message: "Không tìm thấy endpoint.",
        code: "ROUTE_NOT_FOUND",
      });
      return;
    }

    let claims = {};
    if (route.handler !== "health") {
      claims = localClaims(request.headers.authorization);
      if (!claims) {
        writeJson(response, 401, {
          success: false,
          message: "Cần đăng nhập bằng tài khoản mock Admin hoặc Staff.",
          code: "UNAUTHORIZED",
        });
        return;
      }
    }

    try {
      const event = {
        httpMethod: request.method,
        path: url.pathname,
        pathParameters: route.pathParameters,
        queryStringParameters: Object.fromEntries(url.searchParams.entries()),
        headers: request.headers,
        body: await readBody(request),
        requestContext: { authorizer: { claims } },
      };
      const result = await handlers[route.handler](event);
      response.writeHead(result.statusCode || 200, {
        ...result.headers,
        "Access-Control-Allow-Origin": frontendOrigin,
        Vary: "Origin",
      });
      response.end(result.body || "");
    } catch (error) {
      if (error.statusCode === 413) {
        writeJson(response, 413, {
          success: false,
          message: error.message,
          code: "REQUEST_TOO_LARGE",
        });
        return;
      }
      console.error("Local API request failed", error);
      writeJson(response, 500, {
        success: false,
        message: "Đã xảy ra lỗi khi xử lý yêu cầu local.",
        code: "INTERNAL_ERROR",
      });
    }
  });
}

function configureLocalEnvironment(env = process.env) {
  const endpoint = env.DYNAMODB_ENDPOINT || "http://127.0.0.1:8000";
  let endpointUrl;
  try {
    endpointUrl = new URL(endpoint);
  } catch {
    throw new Error("DYNAMODB_ENDPOINT không hợp lệ.");
  }
  if (
    endpointUrl.protocol !== "http:" ||
    endpointUrl.port !== "8000" ||
    !["localhost", "127.0.0.1"].includes(endpointUrl.hostname)
  ) {
    throw new Error("Local API chỉ cho phép DynamoDB Local trên localhost:8000.");
  }

  env.DYNAMODB_ENDPOINT = endpoint;
  env.STAGE = "dev";
  env.FRONTEND_ORIGIN = LOCAL_FRONTEND_ORIGIN;
  env.PRODUCTS_TABLE = env.PRODUCTS_TABLE || "cloudstock-dev-products";
  env.SUPPLIERS_TABLE = env.SUPPLIERS_TABLE || "cloudstock-dev-suppliers";
  env.TRANSACTIONS_TABLE = env.TRANSACTIONS_TABLE || "cloudstock-dev-transactions";
  return env;
}

function startLocalApi() {
  configureLocalEnvironment();
  const handlers = {
    health: require("../src/health").handler,
    products: require("../src/products").handler,
    suppliers: require("../src/suppliers").handler,
    transactions: require("../src/transactions").handler,
  };
  const server = createLocalApiServer({ handlers });
  server.on("error", (error) => {
    console.error("Local API server error:", error.message);
    process.exitCode = 1;
  });
  const port = Number(process.env.PORT || 3001);
  if (!Number.isInteger(port) || port < 1 || port > 65535) {
    throw new Error("PORT phải là số nguyên từ 1 đến 65535.");
  }
  server.listen(port, "127.0.0.1", () => {
    console.log(`CloudStock local API chạy tại http://localhost:${port}`);
  });
  return server;
}

if (require.main === module) {
  try {
    startLocalApi();
  } catch (error) {
    console.error("Không thể khởi động CloudStock local API:", error.message);
    process.exitCode = 1;
  }
}

module.exports = {
  configureLocalEnvironment,
  createLocalApiServer,
  resolveRoute,
};
