const assert = require("node:assert/strict");
const { test } = require("node:test");
const {
  GetCommand,
  QueryCommand,
  TransactWriteCommand,
} = require("@aws-sdk/lib-dynamodb");
const { createHandler } = require("../src/transactions");

function event(method, options = {}) {
  return {
    httpMethod: method,
    pathParameters: options.pathParameters || {},
    queryStringParameters: options.queryStringParameters || {},
    headers: options.headers || { "Idempotency-Key": "request-001" },
    body: options.body ? JSON.stringify(options.body) : null,
    requestContext: {
      authorizer: {
        claims: {
          "cognito:groups": "Staff",
          "cognito:username": "staff.tran",
          sub: "user-sub-001",
        },
      },
    },
  };
}

function body(response) {
  return JSON.parse(response.body);
}

function transactionBody(overrides = {}) {
  return {
    transactionId: "client-id-is-ignored",
    timestamp: "client-time-is-ignored",
    performedBy: "client-user-is-ignored",
    type: "IN",
    productId: "prod-001",
    amount: 5,
    supplierId: null,
    reason: "Stock replenishment",
    invoiceUrl: "",
    ...overrides,
  };
}

test("POST /transactions atomically writes stock update and trusted history", async () => {
  let transactInput;
  const docClient = {
    async send(command) {
      if (command instanceof GetCommand && command.input.TableName === "products") {
        return {
          Item: {
            productId: "prod-001",
            name: "Paper",
            quantity: 10,
          },
        };
      }
      if (command instanceof GetCommand && command.input.TableName === "transactions") {
        return {};
      }
      if (command instanceof TransactWriteCommand) {
        transactInput = command.input;
        return {};
      }
      throw new Error(`Unexpected command: ${command.constructor.name}`);
    },
  };
  const handler = createHandler({
    docClient,
    transactionsTableName: "transactions",
    productsTableName: "products",
    suppliersTableName: "suppliers",
  });

  const response = await handler(
    event("POST", { body: transactionBody() })
  );
  const result = body(response);
  const operations = transactInput.TransactItems;
  const stockUpdate = operations[0].Update;
  const historyWrite = operations[1].Put.Item;

  assert.equal(response.statusCode, 201);
  assert.equal(operations.length, 2);
  assert.equal(stockUpdate.ExpressionAttributeValues[":delta"], 5);
  assert.equal(historyWrite.productName, "Paper");
  assert.equal(historyWrite.performedBy, "staff.tran");
  assert.notEqual(result.data.transactionId, "client-id-is-ignored");
  assert.notEqual(result.data.timestamp, "client-time-is-ignored");
  assert.notEqual(result.data.performedBy, "client-user-is-ignored");
  assert.equal(result.data.transactionId, historyWrite.transactionId);
  assert.equal(historyWrite.gsi1pk, "TRANSACTION");
});

test("POST /transactions rejects an outbound transaction when stock is insufficient", async () => {
  let transactAttempted = false;
  const docClient = {
    async send(command) {
      if (command instanceof GetCommand) {
        if (command.input.TableName === "products") {
          return {
            Item: { productId: "prod-001", name: "Paper", quantity: 2 },
          };
        }
        return {};
      }
      if (command instanceof TransactWriteCommand) transactAttempted = true;
      return {};
    },
  };
  const handler = createHandler({
    docClient,
    transactionsTableName: "transactions",
    productsTableName: "products",
    suppliersTableName: "suppliers",
  });

  const response = await handler(
    event("POST", {
      body: transactionBody({ type: "OUT", amount: 3 }),
    })
  );

  assert.equal(response.statusCode, 409);
  assert.equal(body(response).code, "INSUFFICIENT_STOCK");
  assert.equal(transactAttempted, false);
});

test("POST /transactions atomically subtracts stock for a valid outbound transaction", async () => {
  let stockUpdate;
  const docClient = {
    async send(command) {
      if (command instanceof GetCommand && command.input.TableName === "transactions") {
        return {};
      }
      if (command instanceof GetCommand && command.input.TableName === "products") {
        return {
          Item: { productId: "prod-001", name: "Paper", quantity: 10 },
        };
      }
      if (command instanceof TransactWriteCommand) {
        stockUpdate = command.input.TransactItems[0].Update;
        return {};
      }
      throw new Error(`Unexpected command: ${command.constructor.name}`);
    },
  };
  const handler = createHandler({
    docClient,
    transactionsTableName: "transactions",
    productsTableName: "products",
    suppliersTableName: "suppliers",
  });

  const response = await handler(
    event("POST", {
      body: transactionBody({ type: "OUT", amount: 4 }),
    })
  );

  assert.equal(response.statusCode, 201);
  assert.equal(stockUpdate.ExpressionAttributeValues[":delta"], -4);
  assert.match(stockUpdate.ConditionExpression, /#quantity >= :amount/);
});

test("POST /transactions returns the original record for an idempotent retry", async () => {
  let storedTransaction;
  let productReads = 0;
  let transactionWrites = 0;
  const docClient = {
    async send(command) {
      if (command instanceof GetCommand && command.input.TableName === "products") {
        productReads += 1;
        return {
          Item: { productId: "prod-001", name: "Paper", quantity: 5 },
        };
      }
      if (command instanceof TransactWriteCommand) {
        transactionWrites += 1;
        storedTransaction = command.input.TransactItems[1].Put.Item;
        const error = new Error("Transaction cancelled");
        error.name = "TransactionCanceledException";
        throw error;
      }
      if (command instanceof GetCommand && command.input.TableName === "transactions") {
        return { Item: storedTransaction };
      }
      throw new Error(`Unexpected command: ${command.constructor.name}`);
    },
  };
  const handler = createHandler({
    docClient,
    transactionsTableName: "transactions",
    productsTableName: "products",
    suppliersTableName: "suppliers",
  });

  const response = await handler(
    event("POST", {
      body: transactionBody({ type: "OUT", amount: 5 }),
    })
  );
  const retryResponse = await handler(
    event("POST", {
      body: transactionBody({ type: "OUT", amount: 5 }),
    })
  );

  assert.equal(response.statusCode, 200);
  assert.equal(body(response).data.transactionId, storedTransaction.transactionId);
  assert.equal(retryResponse.statusCode, 200);
  assert.equal(productReads, 1);
  assert.equal(transactionWrites, 1);
});

test("POST /transactions reports insufficient stock after a concurrent update", async () => {
  let productReads = 0;
  const docClient = {
    async send(command) {
      if (command instanceof GetCommand && command.input.TableName === "products") {
        productReads += 1;
        return {
          Item: {
            productId: "prod-001",
            name: "Paper",
            quantity: productReads === 1 ? 5 : 1,
          },
        };
      }
      if (command instanceof TransactWriteCommand) {
        const error = new Error("Conditional update failed");
        error.name = "TransactionCanceledException";
        throw error;
      }
      if (command instanceof GetCommand && command.input.TableName === "transactions") {
        return {};
      }
      throw new Error(`Unexpected command: ${command.constructor.name}`);
    },
  };
  const handler = createHandler({
    docClient,
    transactionsTableName: "transactions",
    productsTableName: "products",
    suppliersTableName: "suppliers",
  });

  const response = await handler(
    event("POST", {
      body: transactionBody({ type: "OUT", amount: 3 }),
    })
  );

  assert.equal(response.statusCode, 409);
  assert.equal(body(response).code, "INSUFFICIENT_STOCK");
  assert.equal(productReads, 2);
});

test("POST /transactions rejects reusing an idempotency key for a different payload", async () => {
  let existingTransaction;
  const docClient = {
    async send(command) {
      if (command instanceof GetCommand && command.input.TableName === "products") {
        return {
          Item: { productId: "prod-001", name: "Paper", quantity: 10 },
        };
      }
      if (command instanceof TransactWriteCommand) {
        if (!existingTransaction) {
          existingTransaction = command.input.TransactItems[1].Put.Item;
        }
        const error = new Error("Transaction cancelled");
        error.name = "TransactionCanceledException";
        throw error;
      }
      if (command instanceof GetCommand && command.input.TableName === "transactions") {
        return { Item: existingTransaction };
      }
      throw new Error(`Unexpected command: ${command.constructor.name}`);
    },
  };
  const handler = createHandler({
    docClient,
    transactionsTableName: "transactions",
    productsTableName: "products",
    suppliersTableName: "suppliers",
  });

  const firstResponse = await handler(
    event("POST", {
      body: transactionBody({ amount: 5 }),
    })
  );
  assert.equal(firstResponse.statusCode, 200);

  const response = await handler(
    event("POST", {
      body: transactionBody({ amount: 7 }),
    })
  );

  assert.equal(response.statusCode, 409);
  assert.equal(body(response).code, "IDEMPOTENCY_KEY_REUSED");
});

test("POST /transactions requires an idempotency key", async () => {
  let databaseCalled = false;
  const handler = createHandler({
    docClient: {
      async send() {
        databaseCalled = true;
      },
    },
    transactionsTableName: "transactions",
    productsTableName: "products",
    suppliersTableName: "suppliers",
  });

  const response = await handler(
    event("POST", {
      body: transactionBody(),
      headers: {},
    })
  );

  assert.equal(response.statusCode, 400);
  assert.equal(body(response).code, "IDEMPOTENCY_KEY_REQUIRED");
  assert.equal(databaseCalled, false);
});

test("GET /transactions uses the timestamp index and returns a cursor", async () => {
  let queryInput;
  const docClient = {
    async send(command) {
      assert.ok(command instanceof QueryCommand);
      queryInput = command.input;
      return {
        Items: [],
        LastEvaluatedKey: {
          transactionId: "txn-001",
          gsi1pk: "TRANSACTION",
          gsi1sk: "2026-11-16T00:00:00.000Z#txn-001",
        },
      };
    },
  };
  const handler = createHandler({
    docClient,
    transactionsTableName: "transactions",
    productsTableName: "products",
    suppliersTableName: "suppliers",
  });

  const response = await handler(
    event("GET", { queryStringParameters: { limit: "20" } })
  );

  assert.equal(response.statusCode, 200);
  assert.ok(body(response).nextToken);
  assert.equal(queryInput.IndexName, "ByTimestamp");
  assert.equal(queryInput.Limit, 20);
  assert.equal(queryInput.ScanIndexForward, true);
});
