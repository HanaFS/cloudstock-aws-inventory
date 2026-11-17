const assert = require("node:assert/strict");
const { test } = require("node:test");
const { createDynamoDBClientConfig } = require("../src/common/dynamodb");

test("DynamoDB client uses default AWS configuration without a local endpoint", () => {
  assert.deepEqual(createDynamoDBClientConfig({}), {});
});

test("DynamoDB client refuses AWS fallback when invoked by SAM local", () => {
  assert.throws(
    () => createDynamoDBClientConfig({ AWS_SAM_LOCAL: "true" }),
    /DYNAMODB_ENDPOINT is required when running with SAM local/
  );
});

test("DynamoDB client uses local endpoint and dummy credentials when configured", () => {
  assert.deepEqual(
    createDynamoDBClientConfig({
      DYNAMODB_ENDPOINT: "http://host.docker.internal:8000",
      AWS_REGION: "us-west-2",
    }),
    {
      endpoint: "http://host.docker.internal:8000",
      region: "us-west-2",
      credentials: {
        accessKeyId: "local",
        secretAccessKey: "local",
      },
    }
  );
});
