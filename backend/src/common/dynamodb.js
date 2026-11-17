const { DynamoDBClient } = require("@aws-sdk/client-dynamodb");
const {
  DynamoDBDocumentClient,
  QueryCommand,
  ScanCommand,
} = require("@aws-sdk/lib-dynamodb");
const { ApiError } = require("./http");

function createDynamoDBClientConfig(env = process.env) {
  if (!env.DYNAMODB_ENDPOINT) {
    if (env.AWS_SAM_LOCAL === "true") {
      throw new Error("DYNAMODB_ENDPOINT is required when running with SAM local.");
    }
    return {};
  }

  return {
    endpoint: env.DYNAMODB_ENDPOINT,
    region: env.AWS_REGION || "us-east-1",
    credentials: {
      accessKeyId: "local",
      secretAccessKey: "local",
    },
  };
}

const documentClient = DynamoDBDocumentClient.from(
  new DynamoDBClient(createDynamoDBClientConfig())
);
const MAX_PAGE_SIZE = 100;

function parseLimit(event) {
  const rawLimit = event.queryStringParameters?.limit;
  if (rawLimit === undefined) return MAX_PAGE_SIZE;
  if (!/^\d+$/.test(rawLimit)) {
    throw new ApiError(400, "INVALID_LIMIT", "limit phải là số nguyên từ 1 đến 100.");
  }

  const limit = Number(rawLimit);
  if (limit < 1 || limit > MAX_PAGE_SIZE) {
    throw new ApiError(400, "INVALID_LIMIT", "limit phải là số nguyên từ 1 đến 100.");
  }
  return limit;
}

function decodeCursor(cursor, keyName) {
  if (!cursor) return undefined;
  if (cursor.length > 2048) {
    throw new ApiError(400, "INVALID_CURSOR", "nextToken không hợp lệ.");
  }

  try {
    const key = JSON.parse(Buffer.from(cursor, "base64url").toString("utf8"));
    const keyNames = Array.isArray(keyName) ? keyName : [keyName];
    if (
      !key ||
      typeof key !== "object" ||
      keyNames.some((name) => typeof key[name] !== "string")
    ) {
      throw new Error("Invalid key");
    }
    return key;
  } catch {
    throw new ApiError(400, "INVALID_CURSOR", "nextToken không hợp lệ.");
  }
}

function encodeCursor(key) {
  return key ? Buffer.from(JSON.stringify(key), "utf8").toString("base64url") : null;
}

async function scanPage(docClient, tableName, event, keyName, filter = {}) {
  const input = {
    TableName: tableName,
    Limit: parseLimit(event),
    ...filter,
  };

  const cursor = decodeCursor(event.queryStringParameters?.nextToken, keyName);
  if (cursor) input.ExclusiveStartKey = cursor;

  const result = await docClient.send(new ScanCommand(input));
  return {
    items: result.Items || [],
    nextToken: encodeCursor(result.LastEvaluatedKey),
  };
}

async function queryPage(docClient, event, input, keyNames) {
  const query = {
    ...input,
    Limit: parseLimit(event),
  };
  const cursor = decodeCursor(event.queryStringParameters?.nextToken, keyNames);
  if (cursor) query.ExclusiveStartKey = cursor;

  const result = await docClient.send(new QueryCommand(query));
  return {
    items: result.Items || [],
    nextToken: encodeCursor(result.LastEvaluatedKey),
  };
}

async function scanAll(docClient, input) {
  const items = [];
  let lastEvaluatedKey;

  do {
    const page = await docClient.send(
      new ScanCommand({
        ...input,
        ...(lastEvaluatedKey ? { ExclusiveStartKey: lastEvaluatedKey } : {}),
      })
    );
    items.push(...(page.Items || []));
    lastEvaluatedKey = page.LastEvaluatedKey;
  } while (lastEvaluatedKey);

  return items;
}

module.exports = {
  createDynamoDBClientConfig,
  documentClient,
  queryPage,
  scanAll,
  scanPage,
};
