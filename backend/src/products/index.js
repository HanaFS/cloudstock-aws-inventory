const {
  DeleteCommand,
  GetCommand,
  PutCommand,
  UpdateCommand,
} = require("@aws-sdk/lib-dynamodb");
const {
  ApiError,
  parseBody,
  requireAnyGroup,
  success,
  withErrorHandling,
} = require("../common/http");
const { documentClient, scanAll, scanPage } = require("../common/dynamodb");

const PRODUCT_ID_PATTERN = /^[A-Za-z0-9_-]{1,64}$/;

function validateProduct(input, existing, productId) {
  if (input.imageUrl !== undefined && input.imageUrl !== null && input.imageUrl !== "") {
    throw new ApiError(
      400,
      "UPLOAD_REQUIRED",
      "Hãy tải ảnh lên S3 và gửi imageKey; không gửi URL hoặc Base64 trong request."
    );
  }

  const values = { ...(existing || {}), ...input, productId };
  if (typeof productId !== "string" || !PRODUCT_ID_PATTERN.test(productId)) {
    throw new ApiError(400, "INVALID_PRODUCT_ID", "productId không hợp lệ.");
  }

  const name = typeof values.name === "string" ? values.name.trim() : "";
  const category = typeof values.category === "string" ? values.category.trim() : "";
  if (!name || name.length > 200) {
    throw new ApiError(400, "INVALID_NAME", "Tên sản phẩm là bắt buộc và tối đa 200 ký tự.");
  }
  if (!category || category.length > 100) {
    throw new ApiError(400, "INVALID_CATEGORY", "Danh mục là bắt buộc và tối đa 100 ký tự.");
  }

  for (const field of ["price", "quantity", "minThreshold"]) {
    if (!Number.isSafeInteger(values[field]) || values[field] < 0) {
      throw new ApiError(
        400,
        `INVALID_${field.toUpperCase()}`,
        `${field} phải là số nguyên không âm.`
      );
    }
  }

  const supplierId = values.supplierId || null;
  if (supplierId !== null && (typeof supplierId !== "string" || supplierId.length > 64)) {
    throw new ApiError(400, "INVALID_SUPPLIER_ID", "supplierId không hợp lệ.");
  }

  const imageKey = values.imageKey || null;
  if (imageKey !== null && (typeof imageKey !== "string" || imageKey.length > 1024)) {
    throw new ApiError(400, "INVALID_IMAGE_KEY", "imageKey không hợp lệ.");
  }

  return {
    productId,
    name,
    category,
    price: values.price,
    quantity: values.quantity,
    minThreshold: values.minThreshold,
    supplierId,
    imageKey,
    updatedAt: new Date().toISOString(),
  };
}

function serializeProduct(product) {
  return {
    productId: product.productId,
    name: product.name,
    category: product.category,
    price: product.price,
    quantity: product.quantity,
    minThreshold: product.minThreshold,
    supplierId: product.supplierId || null,
    imageKey: product.imageKey || null,
    imageUrl: product.imageUrl || null,
    updatedAt: product.updatedAt,
  };
}

async function assertSupplierExists(docClient, tableName, supplierId) {
  if (!supplierId) return;
  const result = await docClient.send(
    new GetCommand({
      TableName: tableName,
      Key: { supplierId },
    })
  );
  if (!result.Item) {
    throw new ApiError(400, "UNKNOWN_SUPPLIER", "Nhà cung cấp không tồn tại.");
  }
}

function isConditionalFailure(error) {
  return error.name === "ConditionalCheckFailedException";
}

function createHandler({
  docClient = documentClient,
  productsTableName = process.env.PRODUCTS_TABLE,
  suppliersTableName = process.env.SUPPLIERS_TABLE,
  transactionsTableName = process.env.TRANSACTIONS_TABLE,
} = {}) {
  return withErrorHandling(async (event) => {
    requireAnyGroup(event, ["Admin", "Staff"]);
    const method = event.httpMethod;
    const productId = event.pathParameters?.productId;

    if (method === "GET" && !productId) {
      const isLowStock = event.queryStringParameters?.filter === "low-stock";
      const filter = isLowStock
        ? {
            FilterExpression: "#quantity < #minThreshold",
            ExpressionAttributeNames: {
              "#quantity": "quantity",
              "#minThreshold": "minThreshold",
            },
          }
        : {};
      const page = await scanPage(docClient, productsTableName, event, "productId", filter);
      return success(
        page.items.map(serializeProduct),
        200,
        page.nextToken ? { nextToken: page.nextToken } : {}
      );
    }

    if (method === "GET" && productId) {
      const result = await docClient.send(
        new GetCommand({
          TableName: productsTableName,
          Key: { productId },
        })
      );
      if (!result.Item) {
        throw new ApiError(404, "PRODUCT_NOT_FOUND", "Không tìm thấy sản phẩm.");
      }
      return success(serializeProduct(result.Item));
    }

    if (method === "POST" && !productId) {
      const body = parseBody(event);
      const product = validateProduct(body, null, body.productId);
      await assertSupplierExists(docClient, suppliersTableName, product.supplierId);
      try {
        await docClient.send(
          new PutCommand({
            TableName: productsTableName,
            Item: product,
            ConditionExpression: "attribute_not_exists(productId)",
          })
        );
      } catch (error) {
        if (isConditionalFailure(error)) {
          throw new ApiError(409, "PRODUCT_EXISTS", "Mã sản phẩm đã tồn tại.");
        }
        throw error;
      }
      return success(serializeProduct(product), 201);
    }

    if (method === "PUT" && productId) {
      const current = await docClient.send(
        new GetCommand({
          TableName: productsTableName,
          Key: { productId },
        })
      );
      if (!current.Item) {
        throw new ApiError(404, "PRODUCT_NOT_FOUND", "Không tìm thấy sản phẩm.");
      }

      const product = validateProduct(parseBody(event), current.Item, productId);
      await assertSupplierExists(docClient, suppliersTableName, product.supplierId);

      try {
        const result = await docClient.send(
          new UpdateCommand({
            TableName: productsTableName,
            Key: { productId },
            UpdateExpression:
              "SET #name = :name, #category = :category, #price = :price, #quantity = :quantity, #minThreshold = :minThreshold, #supplierId = :supplierId, #imageKey = :imageKey, #updatedAt = :updatedAt",
            ConditionExpression: "attribute_exists(productId)",
            ExpressionAttributeNames: {
              "#name": "name",
              "#category": "category",
              "#price": "price",
              "#quantity": "quantity",
              "#minThreshold": "minThreshold",
              "#supplierId": "supplierId",
              "#imageKey": "imageKey",
              "#updatedAt": "updatedAt",
            },
            ExpressionAttributeValues: {
              ":name": product.name,
              ":category": product.category,
              ":price": product.price,
              ":quantity": product.quantity,
              ":minThreshold": product.minThreshold,
              ":supplierId": product.supplierId,
              ":imageKey": product.imageKey,
              ":updatedAt": product.updatedAt,
            },
            ReturnValues: "ALL_NEW",
          })
        );
        return success(serializeProduct(result.Attributes));
      } catch (error) {
        if (isConditionalFailure(error)) {
          throw new ApiError(404, "PRODUCT_NOT_FOUND", "Không tìm thấy sản phẩm.");
        }
        throw error;
      }
    }

    if (method === "DELETE" && productId) {
      const current = await docClient.send(
        new GetCommand({
          TableName: productsTableName,
          Key: { productId },
        })
      );
      if (!current.Item) {
        throw new ApiError(404, "PRODUCT_NOT_FOUND", "Không tìm thấy sản phẩm.");
      }

      const linkedTransactions = await scanAll(docClient, {
        TableName: transactionsTableName,
        FilterExpression: "#productId = :productId",
        ExpressionAttributeNames: { "#productId": "productId" },
        ExpressionAttributeValues: { ":productId": productId },
        ProjectionExpression: "transactionId",
      });
      if (linkedTransactions.length > 0) {
        throw new ApiError(
          409,
          "PRODUCT_HAS_HISTORY",
          "Không thể xóa sản phẩm đã có lịch sử giao dịch."
        );
      }

      try {
        await docClient.send(
          new DeleteCommand({
            TableName: productsTableName,
            Key: { productId },
            ConditionExpression: "attribute_exists(productId)",
          })
        );
      } catch (error) {
        if (isConditionalFailure(error)) {
          throw new ApiError(404, "PRODUCT_NOT_FOUND", "Không tìm thấy sản phẩm.");
        }
        throw error;
      }
      return success({ deleted: true });
    }

    throw new ApiError(404, "ROUTE_NOT_FOUND", "Không tìm thấy endpoint.");
  });
}

const handler = createHandler();

module.exports = { createHandler, handler };
