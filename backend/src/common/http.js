class ApiError extends Error {
  constructor(statusCode, code, message) {
    super(message);
    this.name = "ApiError";
    this.statusCode = statusCode;
    this.code = code;
  }
}

function response(statusCode, payload) {
  return {
    statusCode,
    headers: {
      "Content-Type": "application/json",
      "Access-Control-Allow-Origin": process.env.FRONTEND_ORIGIN || "http://localhost:8080",
      Vary: "Origin",
    },
    body: JSON.stringify(payload),
  };
}

function success(data, statusCode = 200, extra = {}) {
  return response(statusCode, { success: true, data, ...extra });
}

function parseBody(event) {
  if (!event.body) return {};

  let body;
  try {
    body = JSON.parse(event.body);
  } catch {
    throw new ApiError(400, "INVALID_JSON", "Request body phải là JSON hợp lệ.");
  }

  if (!body || typeof body !== "object" || Array.isArray(body)) {
    throw new ApiError(400, "INVALID_BODY", "Request body phải là một object JSON.");
  }

  return body;
}

function requireAnyGroup(event, allowedGroups) {
  const claims = event.requestContext?.authorizer?.claims || {};
  const rawGroups = claims["cognito:groups"] || claims.groups || [];
  let groups = rawGroups;

  if (typeof rawGroups === "string") {
    try {
      groups = JSON.parse(rawGroups);
    } catch {
      groups = rawGroups.split(",").map((group) => group.trim());
    }
  }
  if (!Array.isArray(groups) || !groups.some((group) => allowedGroups.includes(group))) {
    throw new ApiError(403, "FORBIDDEN", "Tài khoản không có quyền thực hiện thao tác này.");
  }
}

function withErrorHandling(handler) {
  return async (event) => {
    try {
      return await handler(event);
    } catch (error) {
      if (error instanceof ApiError) {
        return response(error.statusCode, {
          success: false,
          message: error.message,
          code: error.code,
        });
      }

      console.error("Unhandled API error", error);
      return response(500, {
        success: false,
        message: "Đã xảy ra lỗi khi xử lý yêu cầu.",
        code: "INTERNAL_ERROR",
      });
    }
  };
}

module.exports = {
  ApiError,
  parseBody,
  requireAnyGroup,
  success,
  withErrorHandling,
};
