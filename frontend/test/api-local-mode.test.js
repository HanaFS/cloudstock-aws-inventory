const assert = require("node:assert/strict");
const { test } = require("node:test");
const { readFileSync } = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const apiSource = readFileSync(
  path.join(__dirname, "..", "js", "api.js"),
  "utf8"
);

function createStorage(values = {}) {
  const store = new Map(Object.entries(values));
  return {
    getItem(key) {
      return store.has(key) ? store.get(key) : null;
    },
    setItem(key, value) {
      store.set(key, String(value));
    },
    removeItem(key) {
      store.delete(key);
    },
  };
}

function createApi(fetchImpl) {
  const config = {
    USE_MOCK_DATA: true,
    USE_MOCK_AUTH: true,
    USE_LOCAL_API: true,
    USE_LOCAL_API_AUTH: true,
    API_BASE_URL: "http://127.0.0.1:3000",
    PAGE_SIZE: 10,
    MOCK_DELAY_MS: 0,
  };
  const localStorage = createStorage({
    cloudstock_current_user: JSON.stringify({ username: "staff.tran", role: "Staff" }),
  });
  let mockReads = 0;
  const context = vm.createContext({
    CONFIG: config,
    MockDataStore: {
      getAll() {
        mockReads += 1;
        return [];
      },
    },
    localStorage,
    sessionStorage: createStorage(),
    URL,
    URLSearchParams,
    fetch: fetchImpl,
    setTimeout,
  });
  vm.runInContext(apiSource, context);

  return {
    api: vm.runInContext("ApiService", context),
    getMockReads: () => mockReads,
  };
}

test("local mode uses backend for supported resources and keeps other resources mocked", async () => {
  const requests = [];
  const { api, getMockReads } = createApi(async (url, options) => {
    requests.push({ url, options });
    return {
      ok: true,
      status: 200,
      json: async () => ({ success: true, data: [] }),
    };
  });

  await api.Products.getAll();
  await api.Suppliers.getAll();
  await api.Transactions.getAll();
  await api.Users.getAll();
  await api.SystemLogs.getAll();

  assert.equal(requests.length, 3);
  assert.ok(requests.some(({ url }) => url.startsWith("http://127.0.0.1:3000/products?")));
  assert.ok(requests.some(({ url }) => url.startsWith("http://127.0.0.1:3000/suppliers?")));
  assert.ok(requests.some(({ url }) => url.startsWith("http://127.0.0.1:3000/transactions?")));
  assert.equal(
    requests[0].options.headers.Authorization,
    "Bearer local-dev:Staff"
  );
  assert.equal(getMockReads(), 2);
});

test("local transaction request sends the backend contract and idempotency key", async () => {
  let request;
  const { api } = createApi(async (url, options) => {
    request = { url, options };
    return {
      ok: true,
      status: 201,
      json: async () => ({ success: true, data: {} }),
    };
  });

  await api.Transactions.create({
    transactionId: "txn-request-001",
    timestamp: "client-timestamp",
    performedBy: "client-user",
    type: "IN",
    productId: "prod-001",
    productName: "Paper",
    amount: 5,
    supplierId: "sup-001",
    reason: "Restock",
    invoiceUrl: "",
  });

  assert.equal(request.url, "http://127.0.0.1:3000/transactions");
  assert.equal(request.options.headers["Idempotency-Key"], "txn-request-001");
  assert.deepEqual(JSON.parse(request.options.body), {
    type: "IN",
    productId: "prod-001",
    amount: 5,
    supplierId: "sup-001",
    reason: "Restock",
  });
});
