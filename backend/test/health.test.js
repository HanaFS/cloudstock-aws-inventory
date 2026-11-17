const assert = require("node:assert/strict");
const { test } = require("node:test");
const { handler } = require("../src/health");

test("health handler returns a successful JSON response", async () => {
  const response = await handler();
  const body = JSON.parse(response.body);

  assert.equal(response.statusCode, 200);
  assert.equal(response.headers["Content-Type"], "application/json");
  assert.equal(body.success, true);
  assert.equal(body.data.service, "cloudstock-api");
  assert.equal(body.data.status, "ok");
});
