const assert = require("node:assert/strict");
const { test } = require("node:test");
const {
  GetCommand,
  DeleteCommand,
  PutCommand,
  ScanCommand,
  UpdateCommand,
} = require("@aws-sdk/lib-dynamodb");
const { createHandler } = require("../src/products");

function event(method, options = {}) {
  return {
    httpMethod: method,
    pathParameters: options.pathParameters || {},
    queryStringParameters: options.queryStringParameters || {},
    body: options.body ? JSON.stringify(options.body) : null,
    requestContext: {
      authorizer: {
        claims: { "cognito:groups": "Staff" },
      },
    },
  };
}

function body(response) {
  return JSON.parse(response.body);
}

test("POST /products creates a validated product and sets its timestamp", async () => {
  let putInput;
  const docClient = {
    async send(command) {
      if (command instanceof GetCommand) return {};
      if (command instanceof PutCommand) {
        putInput = command.input;
        return {};
      }
      throw new Error(`Unexpected command: ${command.constructor.name}`);
    },
  };
  const handler = createHandler({
    docClient,
    productsTableName: "products",
    suppliersTableName: "suppliers",
  });

  const response = await handler(
    event("POST", {
      body: {
        productId: "prod-013",
        name: "USB-C cable",
        category: "Accessories",
        price: 250000,
        quantity: 20,
        minThreshold: 5,
        supplierId: null,
        updatedAt: "client-value-is-ignored",
      },
    })
  );
  const result = body(response);

  assert.equal(response.statusCode, 201);
  assert.equal(result.data.productId, "prod-013");
  assert.notEqual(result.data.updatedAt, "client-value-is-ignored");
  assert.equal(putInput.ConditionExpression, "attribute_not_exists(productId)");
});

test("POST /products rejects invalid quantities without writing", async () => {
  let writeAttempted = false;
  const docClient = {
    async send(command) {
      if (command instanceof PutCommand) writeAttempted = true;
      return {};
    },
  };
  const handler = createHandler({
    docClient,
    productsTableName: "products",
    suppliersTableName: "suppliers",
  });

  const response = await handler(
    event("POST", {
      body: {
        productId: "prod-013",
        name: "USB-C cable",
        category: "Accessories",
        price: 250000,
        quantity: -1,
        minThreshold: 5,
      },
    })
  );

  assert.equal(response.statusCode, 400);
  assert.equal(body(response).code, "INVALID_QUANTITY");
  assert.equal(writeAttempted, false);
});

test("GET /products returns a nextToken when DynamoDB has another page", async () => {
  let scanInput;
  const docClient = {
    async send(command) {
      assert.ok(command instanceof ScanCommand);
      scanInput = command.input;
      return {
        Items: [],
        LastEvaluatedKey: { productId: "prod-001" },
      };
    },
  };
  const handler = createHandler({
    docClient,
    productsTableName: "products",
    suppliersTableName: "suppliers",
  });

  const response = await handler(
    event("GET", {
      queryStringParameters: { filter: "low-stock", limit: "25" },
    })
  );
  const result = body(response);

  assert.equal(response.statusCode, 200);
  assert.deepEqual(result.data, []);
  assert.ok(result.nextToken);
  assert.equal(scanInput.Limit, 25);
  assert.equal(scanInput.FilterExpression, "#quantity < #minThreshold");
});

test("PUT /products updates allowed fields and preserves the path ID", async () => {
  let updateInput;
  const docClient = {
    async send(command) {
      if (command instanceof GetCommand) {
        return {
          Item: {
            productId: "prod-001",
            name: "Paper",
            category: "Office",
            price: 1000,
            quantity: 5,
            minThreshold: 2,
            supplierId: null,
            imageKey: null,
          },
        };
      }
      if (command instanceof UpdateCommand) {
        updateInput = command.input;
        return {
          Attributes: {
            productId: "prod-001",
            name: "Paper",
            category: "Office",
            price: 1000,
            quantity: 8,
            minThreshold: 2,
            supplierId: null,
            imageKey: null,
            updatedAt: "2026-11-16T00:00:00.000Z",
          },
        };
      }
      throw new Error(`Unexpected command: ${command.constructor.name}`);
    },
  };
  const handler = createHandler({
    docClient,
    productsTableName: "products",
    suppliersTableName: "suppliers",
  });

  const response = await handler(
    event("PUT", {
      pathParameters: { productId: "prod-001" },
      body: { quantity: 8, productId: "client-cannot-change-id" },
    })
  );

  assert.equal(response.statusCode, 200);
  assert.equal(body(response).data.productId, "prod-001");
  assert.equal(body(response).data.quantity, 8);
  assert.match(updateInput.ConditionExpression, /attribute_exists/);
});

test("DELETE /products preserves items that have transaction history", async () => {
  let deleteAttempted = false;
  const docClient = {
    async send(command) {
      if (command instanceof GetCommand) {
        return {
          Item: {
            productId: "prod-001",
            name: "Paper",
            category: "Office",
            price: 1000,
            quantity: 5,
            minThreshold: 2,
            supplierId: null,
            imageKey: null,
          },
        };
      }
      if (command instanceof ScanCommand) {
        return { Items: [{ transactionId: "txn-001" }] };
      }
      if (command instanceof DeleteCommand) deleteAttempted = true;
      return {};
    },
  };
  const handler = createHandler({
    docClient,
    productsTableName: "products",
    suppliersTableName: "suppliers",
    transactionsTableName: "transactions",
  });

  const response = await handler(
    event("DELETE", { pathParameters: { productId: "prod-001" } })
  );

  assert.equal(response.statusCode, 409);
  assert.equal(body(response).code, "PRODUCT_HAS_HISTORY");
  assert.equal(deleteAttempted, false);
});

test("catalog endpoints reject requests without an allowed Cognito group", async () => {
  let dbCalled = false;
  const handler = createHandler({
    docClient: {
      async send() {
        dbCalled = true;
      },
    },
    productsTableName: "products",
    suppliersTableName: "suppliers",
  });
  const request = event("GET");
  request.requestContext.authorizer.claims["cognito:groups"] = "Other";

  const response = await handler(request);

  assert.equal(response.statusCode, 403);
  assert.equal(body(response).code, "FORBIDDEN");
  assert.equal(dbCalled, false);
});
