const { createHash } = require("node:crypto");
const {
  GetCommand,
  TransactWriteCommand,
} = require("@aws-sdk/lib-dynamodb");
const {
  ApiError,
  parseBody,
  requireAnyGroup,
  success,
  withErrorHandling,
} = require("../common/http");
const { documentClient, queryPage } = require("../common/dynamodb");

const PRODUCT_ID_PATTERN = /^[A-Za-z0-9_-]{1,64}$/;

function getIdempotencyKey(event) {
  const headers = Object.entries(event.headers || {});
  const key = headers.find(([name]) => name.toLowerCase() === "idempotency-key")?.[1];
  if (typeof key !== "string" || key.length < 1 || key.length > 128) {
    throw new ApiError(
      400,
      "IDEMPOTENCY_KEY_REQUIRED",
      "Gửi Idempotency-Key dài từ 1 đến 128 ký tự."
    );
  }
  return key;
}

function getActor(claims) {
  const username = claims["cognito:username"] || claims.username || claims.sub;
  const subject = claims.sub || username;
  if (typeof username !== "string" || typeof subject !== "string") {
    throw new ApiError(401, "INVALID_IDENTITY", "Không đọc được danh tính từ Cognito token.");
  }
  return { username, subject };
}

function validateTransaction(input) {
  if (input.invoiceUrl !== undefined && input.invoiceUrl !== null && input.invoiceUrl !== "") {
    throw new ApiError(
      400,
      "UPLOAD_REQUIRED",
      "Tải chứng từ lên S3 trước; không gửi URL hoặc Base64 trong request."
    );
  }

  const type = input.type;
  if (type !== "IN" && type !== "OUT") {
    throw new ApiError(400, "INVALID_TYPE", "type phải là IN hoặc OUT.");
  }
  if (typeof input.productId !== "string" || !PRODUCT_ID_PATTERN.test(input.productId)) {
    throw new ApiError(400, "INVALID_PRODUCT_ID", "productId không hợp lệ.");
  }
  if (!Number.isSafeInteger(input.amount) || input.amount <= 0) {
    throw new ApiError(400, "INVALID_AMOUNT", "amount phải là số nguyên dương.");
  }

  const reason = typeof input.reason === "string" ? input.reason.trim() : "";
  if (!reason || reason.length > 500) {
    throw new ApiError(400, "INVALID_REASON", "reason là bắt buộc và tối đa 500 ký tự.");
  }

  let supplierId = input.supplierId || null;
  if (supplierId !== null && (typeof supplierId !== "string" || supplierId.length > 64)) {
    throw new ApiError(400, "INVALID_SUPPLIER_ID", "supplierId không hợp lệ.");
  }
  if (type === "OUT" && supplierId) {
    throw new ApiError(400, "INVALID_SUPPLIER_ID", "Giao dịch OUT không nhận supplierId.");
  }

  const invoiceKey = input.invoiceKey || null;
  if (invoiceKey !== null && (typeof invoiceKey !== "string" || invoiceKey.length > 1024)) {
    throw new ApiError(400, "INVALID_INVOICE_KEY", "invoiceKey không hợp lệ.");
  }

  return { type, productId: input.productId, amount: input.amount, supplierId, reason, invoiceKey };
}

function makeRequestHash(transaction) {
  return createHash("sha256").update(JSON.stringify(transaction)).digest("hex");
}

function makeTransactionId(subject, idempotencyKey) {
  const digest = createHash("sha256")
    .update(JSON.stringify([subject, idempotencyKey]))
    .digest("hex")
    .slice(0, 32);
  return `txn-${digest}`;
}

function serializeTransaction(transaction) {
  return {
    transactionId: transaction.transactionId,
    timestamp: transaction.timestamp,
    performedBy: transaction.performedBy,
    type: transaction.type,
    productId: transaction.productId,
    productName: transaction.productName,
    amount: transaction.amount,
    supplierId: transaction.supplierId || null,
    reason: transaction.reason,
    invoiceKey: transaction.invoiceKey || null,
  };
}

function isTransactionCanceled(error) {
  return error.name === "TransactionCanceledException";
}

function createHandler({
  docClient = documentClient,
  transactionsTableName = process.env.TRANSACTIONS_TABLE,
  productsTableName = process.env.PRODUCTS_TABLE,
  suppliersTableName = process.env.SUPPLIERS_TABLE,
} = {}) {
  return withErrorHandling(async (event) => {
    requireAnyGroup(event, ["Admin", "Staff"]);
    const method = event.httpMethod;
    const transactionId = event.pathParameters?.transactionId;

    if (method === "GET" && !transactionId) {
      const page = await queryPage(
        docClient,
        event,
        {
          TableName: transactionsTableName,
          IndexName: "ByTimestamp",
          KeyConditionExpression: "#gsi1pk = :partition",
          ExpressionAttributeNames: { "#gsi1pk": "gsi1pk" },
          ExpressionAttributeValues: { ":partition": "TRANSACTION" },
          ScanIndexForward: true,
        },
        ["transactionId", "gsi1pk", "gsi1sk"]
      );
      return success(
        page.items.map(serializeTransaction),
        200,
        page.nextToken ? { nextToken: page.nextToken } : {}
      );
    }

    if (method === "GET" && transactionId) {
      const result = await docClient.send(
        new GetCommand({
          TableName: transactionsTableName,
          Key: { transactionId },
          ConsistentRead: true,
        })
      );
      if (!result.Item) {
        throw new ApiError(404, "TRANSACTION_NOT_FOUND", "Không tìm thấy giao dịch.");
      }
      return success(serializeTransaction(result.Item));
    }

    if (method === "POST" && !transactionId) {
      const input = validateTransaction(parseBody(event));
      const claims = event.requestContext?.authorizer?.claims || {};
      const actor = getActor(claims);
      const idempotencyKey = getIdempotencyKey(event);
      const requestHash = makeRequestHash(input);
      const transactionId = makeTransactionId(actor.subject, idempotencyKey);

      const existing = await docClient.send(
        new GetCommand({
          TableName: transactionsTableName,
          Key: { transactionId },
          ConsistentRead: true,
        })
      );
      if (existing.Item) {
        if (existing.Item.requestHash !== requestHash) {
          throw new ApiError(
            409,
            "IDEMPOTENCY_KEY_REUSED",
            "Idempotency-Key này đã được dùng cho request khác."
          );
        }
        return success(serializeTransaction(existing.Item));
      }

      const productResult = await docClient.send(
        new GetCommand({
          TableName: productsTableName,
          Key: { productId: input.productId },
          ConsistentRead: true,
        })
      );
      const product = productResult.Item;
      if (!product) {
        throw new ApiError(404, "PRODUCT_NOT_FOUND", "Không tìm thấy sản phẩm.");
      }
      if (!Number.isSafeInteger(product.quantity) || product.quantity < 0) {
        throw new ApiError(409, "INVALID_STOCK_STATE", "Tồn kho sản phẩm không hợp lệ.");
      }
      if (input.type === "OUT" && product.quantity < input.amount) {
        throw new ApiError(
          409,
          "INSUFFICIENT_STOCK",
          `Không đủ tồn kho. Hiện có: ${product.quantity}, yêu cầu xuất: ${input.amount}.`
        );
      }
      if (!Number.isSafeInteger(product.quantity + (input.type === "IN" ? input.amount : -input.amount))) {
        throw new ApiError(409, "QUANTITY_LIMIT", "Số lượng tồn kho vượt giới hạn hỗ trợ.");
      }

      if (input.type === "IN" && input.supplierId) {
        const supplierResult = await docClient.send(
          new GetCommand({
            TableName: suppliersTableName,
            Key: { supplierId: input.supplierId },
          })
        );
        if (!supplierResult.Item) {
          throw new ApiError(400, "UNKNOWN_SUPPLIER", "Nhà cung cấp không tồn tại.");
        }
      }

      const timestamp = new Date().toISOString();
      const transaction = {
        transactionId,
        timestamp,
        performedBy: actor.username,
        type: input.type,
        productId: input.productId,
        productName: product.name,
        amount: input.amount,
        supplierId: input.supplierId,
        reason: input.reason,
        invoiceKey: input.invoiceKey,
        requestHash,
        gsi1pk: "TRANSACTION",
        gsi1sk: `${timestamp}#${transactionId}`,
      };

      try {
        await docClient.send(
          new TransactWriteCommand({
            TransactItems: [
              {
                Update: {
                  TableName: productsTableName,
                  Key: { productId: input.productId },
                  UpdateExpression: "SET #quantity = #quantity + :delta, #updatedAt = :timestamp",
                  ConditionExpression:
                    input.type === "OUT"
                      ? "attribute_exists(productId) AND #quantity >= :amount"
                      : "attribute_exists(productId) AND #quantity <= :maxQuantity",
                  ExpressionAttributeNames: {
                    "#quantity": "quantity",
                    "#updatedAt": "updatedAt",
                  },
                  ExpressionAttributeValues: {
                    ":delta": input.type === "IN" ? input.amount : -input.amount,
                    ":timestamp": timestamp,
                    ...(input.type === "OUT"
                      ? { ":amount": input.amount }
                      : { ":maxQuantity": Number.MAX_SAFE_INTEGER - input.amount }),
                  },
                },
              },
              {
                Put: {
                  TableName: transactionsTableName,
                  Item: transaction,
                  ConditionExpression: "attribute_not_exists(transactionId)",
                },
              },
            ],
          })
        );
        return success(serializeTransaction(transaction), 201);
      } catch (error) {
        if (!isTransactionCanceled(error)) throw error;

        const existing = await docClient.send(
          new GetCommand({
            TableName: transactionsTableName,
            Key: { transactionId: transaction.transactionId },
            ConsistentRead: true,
          })
        );
        if (existing.Item) {
          if (existing.Item.requestHash !== requestHash) {
            throw new ApiError(
              409,
              "IDEMPOTENCY_KEY_REUSED",
              "Idempotency-Key này đã được dùng cho request khác."
            );
          }
          return success(serializeTransaction(existing.Item));
        }

        const latestProduct = await docClient.send(
          new GetCommand({
            TableName: productsTableName,
            Key: { productId: input.productId },
            ConsistentRead: true,
          })
        );
        if (!latestProduct.Item) {
          throw new ApiError(404, "PRODUCT_NOT_FOUND", "Không tìm thấy sản phẩm.");
        }
        if (input.type === "OUT" && latestProduct.Item.quantity < input.amount) {
          throw new ApiError(
            409,
            "INSUFFICIENT_STOCK",
            `Không đủ tồn kho. Hiện có: ${latestProduct.Item.quantity}, yêu cầu xuất: ${input.amount}.`
          );
        }
        if (
          input.type === "IN" &&
          latestProduct.Item.quantity + input.amount > Number.MAX_SAFE_INTEGER
        ) {
          throw new ApiError(409, "QUANTITY_LIMIT", "Số lượng tồn kho vượt giới hạn hỗ trợ.");
        }
        throw new ApiError(
          409,
          "TRANSACTION_CONFLICT",
          "Giao dịch bị xung đột; có thể thử lại với cùng Idempotency-Key."
        );
      }
    }

    throw new ApiError(404, "ROUTE_NOT_FOUND", "Không tìm thấy endpoint.");
  });
}

const handler = createHandler();

module.exports = { createHandler, handler };
