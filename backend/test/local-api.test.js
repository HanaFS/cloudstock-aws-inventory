const assert = require("node:assert/strict");
const { test } = require("node:test");
const {
  configureLocalEnvironment,
  createLocalApiServer,
} = require("../scripts/local-api");

async function withServer(handlers, callback) {
  const server = createLocalApiServer({ handlers });
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  const { port } = server.address();
  try {
    await callback(`http://127.0.0.1:${port}`);
  } finally {
    await new Promise((resolve, reject) =>
      server.close((error) => (error ? reject(error) : resolve()))
    );
  }
}

test("local API maps browser requests to handlers with local role claims", async () => {
  let receivedEvent;
  await withServer(
    {
      products: async (event) => {
        receivedEvent = event;
        return {
          statusCode: 200,
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ success: true, data: [] }),
        };
      },
    },
    async (baseUrl) => {
      const response = await fetch(`${baseUrl}/products/prod-013?limit=10`, {
        headers: {
          Origin: "http://localhost:8080",
          Authorization: "Bearer local-dev:Staff",
        },
      });

      assert.equal(response.status, 200);
      assert.equal(response.headers.get("access-control-allow-origin"), "http://localhost:8080");
      assert.equal(receivedEvent.pathParameters.productId, "prod-013");
      assert.equal(receivedEvent.queryStringParameters.limit, "10");
      assert.deepEqual(receivedEvent.requestContext.authorizer.claims["cognito:groups"], ["Staff"]);
    }
  );
});

test("local API rejects untrusted origins and roles before invoking handlers", async () => {
  let invoked = false;
  await withServer(
    {
      products: async () => {
        invoked = true;
        return { statusCode: 200, body: "{}" };
      },
    },
    async (baseUrl) => {
      const wrongOrigin = await fetch(`${baseUrl}/products`, {
        headers: {
          Origin: "http://example.test",
          Authorization: "Bearer local-dev:Admin",
        },
      });
      const wrongRole = await fetch(`${baseUrl}/products`, {
        headers: {
          Origin: "http://localhost:8080",
          Authorization: "Bearer local-dev:Viewer",
        },
      });

      assert.equal(wrongOrigin.status, 403);
      assert.equal(wrongRole.status, 401);
      assert.equal(invoked, false);
    }
  );
});

test("local API environment refuses non-local DynamoDB endpoints", () => {
  const env = {};
  configureLocalEnvironment(env);
  assert.equal(env.DYNAMODB_ENDPOINT, "http://127.0.0.1:8000");
  assert.equal(env.STAGE, "dev");

  assert.throws(
    () =>
      configureLocalEnvironment({
        DYNAMODB_ENDPOINT: "https://dynamodb.us-east-1.amazonaws.com",
      }),
    /DynamoDB Local trên localhost:8000/
  );
});
