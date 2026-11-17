const {
  CreateTableCommand,
  DynamoDBClient,
  waitUntilTableExists,
} = require("@aws-sdk/client-dynamodb");

const endpoint = process.env.DYNAMODB_LOCAL_ENDPOINT || "http://127.0.0.1:8000";
const stage = process.env.STAGE || "dev";
const endpointUrl = new URL(endpoint);
const localHosts = new Set(["127.0.0.1", "localhost", "::1", "[::1]"]);

if (endpointUrl.protocol !== "http:" || !localHosts.has(endpointUrl.hostname)) {
  throw new Error("DYNAMODB_LOCAL_ENDPOINT must use http://localhost or http://127.0.0.1.");
}

const client = new DynamoDBClient({
  endpoint,
  region: "us-east-1",
  credentials: {
    accessKeyId: "local",
    secretAccessKey: "local",
  },
});

const tables = [
  {
    TableName: `cloudstock-${stage}-products`,
    BillingMode: "PAY_PER_REQUEST",
    AttributeDefinitions: [{ AttributeName: "productId", AttributeType: "S" }],
    KeySchema: [{ AttributeName: "productId", KeyType: "HASH" }],
  },
  {
    TableName: `cloudstock-${stage}-suppliers`,
    BillingMode: "PAY_PER_REQUEST",
    AttributeDefinitions: [{ AttributeName: "supplierId", AttributeType: "S" }],
    KeySchema: [{ AttributeName: "supplierId", KeyType: "HASH" }],
  },
  {
    TableName: `cloudstock-${stage}-transactions`,
    BillingMode: "PAY_PER_REQUEST",
    AttributeDefinitions: [
      { AttributeName: "transactionId", AttributeType: "S" },
      { AttributeName: "gsi1pk", AttributeType: "S" },
      { AttributeName: "gsi1sk", AttributeType: "S" },
    ],
    KeySchema: [{ AttributeName: "transactionId", KeyType: "HASH" }],
    GlobalSecondaryIndexes: [
      {
        IndexName: "ByTimestamp",
        KeySchema: [
          { AttributeName: "gsi1pk", KeyType: "HASH" },
          { AttributeName: "gsi1sk", KeyType: "RANGE" },
        ],
        Projection: { ProjectionType: "ALL" },
      },
    ],
  },
];

async function initializeTables() {
  for (const table of tables) {
    try {
      await client.send(new CreateTableCommand(table));
      console.log(`Created ${table.TableName}`);
    } catch (error) {
      if (error.name !== "ResourceInUseException") throw error;
      console.log(`${table.TableName} already exists`);
    }

    await waitUntilTableExists(
      { client, maxWaitTime: 30 },
      { TableName: table.TableName }
    );
  }
}

initializeTables()
  .catch((error) => {
    console.error("Could not initialize DynamoDB Local tables:", error);
    process.exitCode = 1;
  })
  .finally(() => client.destroy());
