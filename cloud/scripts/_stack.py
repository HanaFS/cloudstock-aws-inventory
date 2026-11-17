"""Hàm dùng chung: đọc Outputs của CloudFormation stack."""
import boto3

DEFAULT_STACK = "qlkho-nhom4"
DEFAULT_REGION = "ap-southeast-1"


def get_outputs(stack_name=DEFAULT_STACK, region=DEFAULT_REGION):
    cf = boto3.client("cloudformation", region_name=region)
    stack = cf.describe_stacks(StackName=stack_name)["Stacks"][0]
    return {o["OutputKey"]: o["OutputValue"] for o in stack.get("Outputs", [])}
