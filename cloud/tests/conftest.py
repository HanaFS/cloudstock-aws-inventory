"""Dựng AWS giả lập (moto) giống hệt template.yaml rồi nạp 4 Lambda để test."""
import importlib.util
import json
import os
import sys
from pathlib import Path

import boto3
import pytest

ROOT = Path(__file__).resolve().parent.parent
REGION = "ap-southeast-1"
BUCKET = "qlkho-test-bucket"

os.environ.update(AWS_ACCESS_KEY_ID="test", AWS_SECRET_ACCESS_KEY="test", AWS_SESSION_TOKEN="test",
                  AWS_REGION=REGION, AWS_DEFAULT_REGION=REGION, BUCKET_NAME=BUCKET,
                  TABLE_PRODUCTS="Products", TABLE_SUPPLIERS="Suppliers", TABLE_TRANSACTIONS="Transactions")


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="session")
def aws():
    from moto import mock_aws
    with mock_aws():
        ddb = boto3.resource("dynamodb", region_name=REGION)
        ddb.create_table(TableName="Products", BillingMode="PAY_PER_REQUEST",
                         AttributeDefinitions=[{"AttributeName": "productId", "AttributeType": "S"}],
                         KeySchema=[{"AttributeName": "productId", "KeyType": "HASH"}])
        ddb.create_table(TableName="Suppliers", BillingMode="PAY_PER_REQUEST",
                         AttributeDefinitions=[{"AttributeName": "supplierId", "AttributeType": "S"}],
                         KeySchema=[{"AttributeName": "supplierId", "KeyType": "HASH"}])
        ddb.create_table(
            TableName="Transactions", BillingMode="PAY_PER_REQUEST",
            AttributeDefinitions=[{"AttributeName": n, "AttributeType": "S"}
                                  for n in ("transactionId", "createdAt", "productId")],
            KeySchema=[{"AttributeName": "transactionId", "KeyType": "HASH"},
                       {"AttributeName": "createdAt", "KeyType": "RANGE"}],
            GlobalSecondaryIndexes=[{"IndexName": "productId-createdAt-index",
                                     "KeySchema": [{"AttributeName": "productId", "KeyType": "HASH"},
                                                   {"AttributeName": "createdAt", "KeyType": "RANGE"}],
                                     "Projection": {"ProjectionType": "ALL"}}])
        boto3.client("s3", region_name=REGION).create_bucket(
            Bucket=BUCKET, CreateBucketConfiguration={"LocationConstraint": REGION})

        cog = boto3.client("cognito-idp", region_name=REGION)
        pool = cog.create_user_pool(PoolName="t", UsernameAttributes=["email"],
                                    AutoVerifiedAttributes=["email"])["UserPool"]["Id"]
        for g in ("Admin", "Staff"):
            cog.create_group(UserPoolId=pool, GroupName=g)
        os.environ["USER_POOL_ID"] = pool

        logs = boto3.client("logs", region_name=REGION)
        groups = ["/aws/lambda/api-users-handler", "/aws/lambda/api-products-handler"]
        for g in groups:
            logs.create_log_group(logGroupName=g)
        os.environ["LOG_GROUP_NAMES"] = ",".join(groups)

        sys.path.insert(0, str(ROOT / "layers/common/python"))
        apps = {
            "users": _load("users_app", "src/api_users_handler/app.py"),
            "dashboard": _load("dashboard_app", "src/api_dashboard_handler/app.py"),
            "products": _load("products_app", "src/api_products_handler/app.py"),
            "transactions": _load("transactions_app", "src/api_transactions_handler/app.py"),
        }
        yield {"ddb": ddb, "cog": cog, "pool": pool, "logs": logs, "groups": groups, "apps": apps}


def make_event(method, path, body=None, query=None, email="admin@nhom4.com", groups="Admin"):
    return {
        "rawPath": path,
        "queryStringParameters": query,
        "body": json.dumps(body) if body is not None else None,
        "isBase64Encoded": False,
        "requestContext": {"http": {"method": method},
                           "authorizer": {"jwt": {"claims": {"email": email, "cognito:groups": groups}}}},
    }


@pytest.fixture()
def call(aws):
    """call('products', 'POST', '/products', body={...}, role='Staff') -> (status, json)"""
    def _call(app, method, path, body=None, query=None, role="Admin", email=None):
        email = email or f"{role.lower()}@nhom4.com"
        ev = make_event(method, path, body, query, email=email, groups=role)
        resp = aws["apps"][app].lambda_handler(ev, None)
        raw = json.loads(resp["body"])
        payload = raw["data"] if isinstance(raw, dict) and raw.get("success") is True and "data" in raw else raw
        return resp["statusCode"], payload
    return _call


@pytest.fixture()
def clean(aws):
    """Xóa sạch 3 bảng trước mỗi test cần dữ liệu sạch."""
    for table, keys in (("Products", ["productId"]), ("Suppliers", ["supplierId"]),
                        ("Transactions", ["transactionId", "createdAt"])):
        t = aws["ddb"].Table(table)
        for item in t.scan()["Items"]:
            t.delete_item(Key={k: item[k] for k in keys})
    return aws
