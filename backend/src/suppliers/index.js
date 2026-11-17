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

const SUPPLIER_ID_PATTERN = /^[A-Za-z0-9_-]{1,64}$/;

function normalizeOptionalString(value, field, maxLength) {
  if (value === undefined || value === null || value === "") return null;
  if (typeof value !== "string" || value.trim().length > maxLength) {
    throw new ApiError(400, `INVALID_${field.toUpperCase()}`, `${field} không hợp lệ.`);
  }
  return value.trim();
}

function validateSupplier(input, existing, supplierId) {
  const values = { ...(existing || {}), ...input, supplierId };
  const name = typeof values.name === "string" ? values.name.trim() : "";

  if (typeof supplierId !== "string" || !SUPPLIER_ID_PATTERN.test(supplierId)) {
    throw new ApiError(400, "INVALID_SUPPLIER_ID", "supplierId không hợp lệ.");
  }
  if (!name || name.length > 200) {
    throw new ApiError(400, "INVALID_NAME", "Tên nhà cung cấp là bắt buộc và tối đa 200 ký tự.");
  }

  return {
    supplierId,
    name,
    phone: normalizeOptionalString(values.phone, "phone", 40),
    address: normalizeOptionalString(values.address, "address", 500),
  };
}

function isConditionalFailure(error) {
  return error.name === "ConditionalCheckFailedException";
}

function createHandler({
  docClient = documentClient,
  suppliersTableName = process.env.SUPPLIERS_TABLE,
  productsTableName = process.env.PRODUCTS_TABLE,
  transactionsTableName = process.env.TRANSACTIONS_TABLE,
} = {}) {
  return withErrorHandling(async (event) => {
    requireAnyGroup(event, ["Admin", "Staff"]);
    const method = event.httpMethod;
    const supplierId = event.pathParameters?.supplierId;

    if (method === "GET" && !supplierId) {
      const page = await scanPage(docClient, suppliersTableName, event, "supplierId");
      return success(page.items, 200, page.nextToken ? { nextToken: page.nextToken } : {});
    }

    if (method === "GET" && supplierId) {
      const result = await docClient.send(
        new GetCommand({
          TableName: suppliersTableName,
          Key: { supplierId },
        })
      );
      if (!result.Item) {
        throw new ApiError(404, "SUPPLIER_NOT_FOUND", "Không tìm thấy nhà cung cấp.");
      }
      return success(result.Item);
    }

    if (method === "POST" && !supplierId) {
      const body = parseBody(event);
      const supplier = validateSupplier(body, null, body.supplierId);
      try {
        await docClient.send(
          new PutCommand({
            TableName: suppliersTableName,
            Item: supplier,
            ConditionExpression: "attribute_not_exists(supplierId)",
          })
        );
      } catch (error) {
        if (isConditionalFailure(error)) {
          throw new ApiError(409, "SUPPLIER_EXISTS", "Mã nhà cung cấp đã tồn tại.");
        }
        throw error;
      }
      return success(supplier, 201);
    }

    if (method === "PUT" && supplierId) {
      const current = await docClient.send(
        new GetCommand({
          TableName: suppliersTableName,
          Key: { supplierId },
        })
      );
      if (!current.Item) {
        throw new ApiError(404, "SUPPLIER_NOT_FOUND", "Không tìm thấy nhà cung cấp.");
      }

      const supplier = validateSupplier(parseBody(event), current.Item, supplierId);
      try {
        const result = await docClient.send(
          new UpdateCommand({
            TableName: suppliersTableName,
            Key: { supplierId },
            UpdateExpression: "SET #name = :name, #phone = :phone, #address = :address",
            ConditionExpression: "attribute_exists(supplierId)",
            ExpressionAttributeNames: {
              "#name": "name",
              "#phone": "phone",
              "#address": "address",
            },
            ExpressionAttributeValues: {
              ":name": supplier.name,
              ":phone": supplier.phone,
              ":address": supplier.address,
            },
            ReturnValues: "ALL_NEW",
          })
        );
        return success(result.Attributes);
      } catch (error) {
        if (isConditionalFailure(error)) {
          throw new ApiError(404, "SUPPLIER_NOT_FOUND", "Không tìm thấy nhà cung cấp.");
        }
        throw error;
      }
    }

    if (method === "DELETE" && supplierId) {
      const current = await docClient.send(
        new GetCommand({
          TableName: suppliersTableName,
          Key: { supplierId },
        })
      );
      if (!current.Item) {
        throw new ApiError(404, "SUPPLIER_NOT_FOUND", "Không tìm thấy nhà cung cấp.");
      }

      const linkedProducts = await scanAll(docClient, {
        TableName: productsTableName,
        FilterExpression: "#supplierId = :supplierId",
        ExpressionAttributeNames: { "#supplierId": "supplierId" },
        ExpressionAttributeValues: { ":supplierId": supplierId },
        ProjectionExpression: "productId",
      });
      if (linkedProducts.length > 0) {
        throw new ApiError(
          409,
          "SUPPLIER_IN_USE",
          "Không thể xóa nhà cung cấp đang được liên kết với sản phẩm."
        );
      }

      const linkedTransactions = await scanAll(docClient, {
        TableName: transactionsTableName,
        FilterExpression: "#supplierId = :supplierId",
        ExpressionAttributeNames: { "#supplierId": "supplierId" },
        ExpressionAttributeValues: { ":supplierId": supplierId },
        ProjectionExpression: "transactionId",
      });
      if (linkedTransactions.length > 0) {
        throw new ApiError(
          409,
          "SUPPLIER_HAS_HISTORY",
          "Không thể xóa nhà cung cấp đã có lịch sử giao dịch."
        );
      }

      try {
        await docClient.send(
          new DeleteCommand({
            TableName: suppliersTableName,
            Key: { supplierId },
            ConditionExpression: "attribute_exists(supplierId)",
          })
        );
      } catch (error) {
        if (isConditionalFailure(error)) {
          throw new ApiError(404, "SUPPLIER_NOT_FOUND", "Không tìm thấy nhà cung cấp.");
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
