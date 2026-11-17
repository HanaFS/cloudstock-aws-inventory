const assert = require("node:assert/strict");
const { test } = require("node:test");
const {
  DeleteCommand,
  GetCommand,
  ScanCommand,
} = require("@aws-sdk/lib-dynamodb");
const { createHandler } = require("../src/suppliers");

function event(method, options = {}) {
  return {
    httpMethod: method,
    pathParameters: options.pathParameters || {},
    queryStringParameters: options.queryStringParameters || {},
    body: options.body ? JSON.stringify(options.body) : null,
    requestContext: {
      authorizer: {
        claims: { "cognito:groups": "Admin" },
      },
    },
  };
}

function body(response) {
  return JSON.parse(response.body);
}

test("DELETE /suppliers rejects a supplier linked to a product", async () => {
  let deleteAttempted = false;
  const docClient = {
    async send(command) {
      if (command instanceof GetCommand) {
        return { Item: { supplierId: "sup-001", name: "Supplier" } };
      }
      if (command instanceof ScanCommand) {
        return { Items: [{ productId: "prod-001" }] };
      }
      if (command instanceof DeleteCommand) deleteAttempted = true;
      return {};
    },
  };
  const handler = createHandler({
    docClient,
    suppliersTableName: "suppliers",
    productsTableName: "products",
    transactionsTableName: "transactions",
  });

  const response = await handler(
    event("DELETE", { pathParameters: { supplierId: "sup-001" } })
  );

  assert.equal(response.statusCode, 409);
  assert.equal(body(response).code, "SUPPLIER_IN_USE");
  assert.equal(deleteAttempted, false);
});

test("DELETE /suppliers succeeds when no products or transactions reference it", async () => {
  let deleteAttempted = false;
  const docClient = {
    async send(command) {
      if (command instanceof GetCommand) {
        return { Item: { supplierId: "sup-001", name: "Supplier" } };
      }
      if (command instanceof ScanCommand) return { Items: [] };
      if (command instanceof DeleteCommand) deleteAttempted = true;
      return {};
    },
  };
  const handler = createHandler({
    docClient,
    suppliersTableName: "suppliers",
    productsTableName: "products",
    transactionsTableName: "transactions",
  });

  const response = await handler(
    event("DELETE", { pathParameters: { supplierId: "sup-001" } })
  );

  assert.equal(response.statusCode, 200);
  assert.deepEqual(body(response).data, { deleted: true });
  assert.equal(deleteAttempted, true);
});
