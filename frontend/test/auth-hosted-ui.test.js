const assert = require("node:assert/strict");
const { test } = require("node:test");
const { Buffer } = require("node:buffer");
const { readFileSync } = require("node:fs");
const path = require("node:path");
const { webcrypto } = require("node:crypto");
const { TextDecoder, TextEncoder } = require("node:util");
const vm = require("node:vm");

const apiSource = readFileSync(
  path.join(__dirname, "..", "js", "api.js"),
  "utf8"
);

function createStorage() {
  const values = new Map();
  return {
    getItem(key) {
      return values.has(key) ? values.get(key) : null;
    },
    setItem(key, value) {
      values.set(key, String(value));
    },
    removeItem(key) {
      values.delete(key);
    },
  };
}

function createApi(fetchImpl = async () => ({ ok: true, status: 200, json: async () => ({ data: [] }) })) {
  const location = {
    href: "http://localhost:8080/login.html",
    assigned: "",
    assign(url) {
      this.assigned = url;
    },
  };
  const window = {
    crypto: webcrypto,
    location,
    history: {
      replacedUrl: null,
      replaceState(_state, _title, url) {
        this.replacedUrl = url;
      },
    },
  };
  const context = vm.createContext({
    CONFIG: {
      USE_MOCK_DATA: false,
      USE_MOCK_AUTH: false,
      API_BASE_URL: "https://api.example.test",
      COGNITO_CLIENT_ID: "test-client-id",
      COGNITO_HOSTED_UI_DOMAIN:
        "https://cloudstock-dev.auth.ap-southeast-1.amazoncognito.com",
      COGNITO_REDIRECT_URI: "http://localhost:8080/login.html",
      COGNITO_LOGOUT_URI: "http://localhost:8080/login.html",
      COGNITO_SCOPES: ["openid", "email", "profile"],
      PAGE_SIZE: 10,
      MOCK_DELAY_MS: 0,
    },
    MockDataStore: { getAll: () => [] },
    window,
    document: { title: "CloudStock" },
    sessionStorage: createStorage(),
    localStorage: createStorage(),
    URL,
    URLSearchParams,
    Uint8Array,
    TextDecoder,
    TextEncoder,
    fetch: fetchImpl,
    setTimeout,
    btoa: (value) => Buffer.from(value, "binary").toString("base64"),
    atob: (value) => Buffer.from(value, "base64").toString("binary"),
  });
  vm.runInContext(apiSource, context);

  return {
    api: vm.runInContext("ApiService", context),
    context,
    location,
    sessionStorage: context.sessionStorage,
    window,
  };
}

function makeIdToken(groups = ["Staff"]) {
  const claims = {
    sub: "local-user-001",
    exp: Math.floor(Date.now() / 1000) + 3600,
    "cognito:username": "local.staff",
    "cognito:groups": groups,
    email: "staff@example.test",
  };
  const payload = Buffer.from(JSON.stringify(claims)).toString("base64url");
  return `header.${payload}.signature`;
}

test("Hosted UI login redirects with OAuth state and a PKCE challenge", async () => {
  const { api, location, sessionStorage } = createApi();

  await api.Auth.login();

  const authorizationUrl = new URL(location.assigned);
  assert.equal(authorizationUrl.pathname, "/oauth2/authorize");
  assert.equal(authorizationUrl.searchParams.get("response_type"), "code");
  assert.equal(authorizationUrl.searchParams.get("code_challenge_method"), "S256");
  assert.equal(authorizationUrl.searchParams.get("scope"), "openid email profile");
  assert.ok(authorizationUrl.searchParams.get("state"));
  assert.ok(authorizationUrl.searchParams.get("code_challenge"));
  assert.equal(sessionStorage.getItem("cloudstock_oauth_state"), authorizationUrl.searchParams.get("state"));
  assert.ok(sessionStorage.getItem("cloudstock_pkce_verifier"));
});

test("Hosted UI callback stores the ID token and API calls send it", async () => {
  const idToken = makeIdToken();
  const requests = [];
  const { api, location, sessionStorage, window } = createApi(async (url, options) => {
    requests.push({ url, options });
    if (url.endsWith("/oauth2/token")) {
      return { ok: true, status: 200, json: async () => ({ id_token: idToken }) };
    }
    return { ok: true, status: 200, json: async () => ({ data: [] }) };
  });
  sessionStorage.setItem("cloudstock_oauth_state", "state-001");
  sessionStorage.setItem("cloudstock_pkce_verifier", "verifier-001");
  location.href =
    "http://localhost:8080/login.html?code=auth-code&state=state-001";

  assert.equal(await api.Auth.handleHostedUiCallback(), true);
  assert.equal(api.Auth.isAuthenticated(), true);
  assert.equal(api.Auth.getCurrentUser().role, "Staff");
  assert.equal(window.history.replacedUrl, "/login.html");

  await api.Products.getAll();
  const apiRequest = requests.find((request) => request.url.startsWith("https://api.example.test"));
  assert.equal(apiRequest.options.headers.Authorization, `Bearer ${idToken}`);
});

test("Hosted UI callback rejects state mismatches", async () => {
  const { api, location, sessionStorage } = createApi();
  sessionStorage.setItem("cloudstock_oauth_state", "expected-state");
  sessionStorage.setItem("cloudstock_pkce_verifier", "verifier-001");
  location.href = "http://localhost:8080/login.html?code=auth-code&state=wrong-state";

  await assert.rejects(api.Auth.handleHostedUiCallback(), /OAuth state không hợp lệ/);
  assert.equal(sessionStorage.getItem("cloudstock_id_token"), null);
});

test("Hosted UI callback rejects users outside the Admin and Staff groups", async () => {
  const idToken = makeIdToken(["Viewer"]);
  const { api, location, sessionStorage } = createApi(async () => ({
    ok: true,
    status: 200,
    json: async () => ({ id_token: idToken }),
  }));
  sessionStorage.setItem("cloudstock_oauth_state", "state-001");
  sessionStorage.setItem("cloudstock_pkce_verifier", "verifier-001");
  location.href =
    "http://localhost:8080/login.html?code=auth-code&state=state-001";

  await assert.rejects(
    api.Auth.handleHostedUiCallback(),
    /Tài khoản Cognito cần thuộc nhóm Admin hoặc Staff/
  );
  assert.equal(sessionStorage.getItem("cloudstock_id_token"), null);
});

test("mock authentication remains available independently from API data mode", async () => {
  const { api, context } = createApi();
  context.CONFIG.USE_MOCK_AUTH = true;
  context.MockDataStore.getAll = () => [
    {
      id: "mock-user-001",
      username: "demo.staff",
      role: "Staff",
      status: "ACTIVE",
    },
  ];

  const result = await api.Auth.login("demo.staff", "password");

  assert.equal(result.data.user.username, "demo.staff");
  assert.equal(api.Auth.getCurrentUser().role, "Staff");
  assert.ok(context.localStorage.getItem("cloudstock_id_token"));
});
