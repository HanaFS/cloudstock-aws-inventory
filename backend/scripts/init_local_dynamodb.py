import os
from urllib.parse import urlsplit

import boto3
from botocore.exceptions import ClientError


def initialize_tables(env=None):
    env = os.environ if env is None else env
    endpoint = env.get("DYNAMODB_LOCAL_ENDPOINT", "http://127.0.0.1:8000")
    parsed = urlsplit(endpoint)
    if parsed.scheme != "http" or parsed.hostname not in ("localhost", "127.0.0.1", "::1"):
        raise ValueError("DYNAMODB_LOCAL_ENDPOINT must use http://localhost or http://127.0.0.1.")
    stage = env.get("STAGE", "dev")
    client = boto3.client(
        "dynamodb",
        endpoint_url=endpoint,
        region_name="us-east-1",
        aws_access_key_id="local",
        aws_secret_access_key="local",
    )
    tables = [
        {
            "TableName": f"cloudstock-{stage}-products",
            "BillingMode": "PAY_PER_REQUEST",
            "AttributeDefinitions": [{"AttributeName": "productId", "AttributeType": "S"}],
            "KeySchema": [{"AttributeName": "productId", "KeyType": "HASH"}],
        },
        {
            "TableName": f"cloudstock-{stage}-suppliers",
            "BillingMode": "PAY_PER_REQUEST",
            "AttributeDefinitions": [{"AttributeName": "supplierId", "AttributeType": "S"}],
            "KeySchema": [{"AttributeName": "supplierId", "KeyType": "HASH"}],
        },
        {
            "TableName": f"cloudstock-{stage}-transactions",
            "BillingMode": "PAY_PER_REQUEST",
            "AttributeDefinitions": [
                {"AttributeName": "transactionId", "AttributeType": "S"},
                {"AttributeName": "gsi1pk", "AttributeType": "S"},
                {"AttributeName": "gsi1sk", "AttributeType": "S"},
            ],
            "KeySchema": [{"AttributeName": "transactionId", "KeyType": "HASH"}],
            "GlobalSecondaryIndexes": [{
                "IndexName": "ByTimestamp",
                "KeySchema": [
                    {"AttributeName": "gsi1pk", "KeyType": "HASH"},
                    {"AttributeName": "gsi1sk", "KeyType": "RANGE"},
                ],
                "Projection": {"ProjectionType": "ALL"},
            }],
        },
    ]
    for table in tables:
        try:
            client.create_table(**table)
            print(f"Created {table['TableName']}")
        except ClientError as error:
            if error.response.get("Error", {}).get("Code") != "ResourceInUseException":
                raise
            print(f"{table['TableName']} already exists")
        waiter = client.get_waiter("table_exists")
        waiter.wait(TableName=table["TableName"], WaiterConfig={"Delay": 1, "MaxAttempts": 30})
    client.close()


if __name__ == "__main__":
    initialize_tables()
