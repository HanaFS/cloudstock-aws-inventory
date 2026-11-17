"""Đăng nhập Cognito và in ra IdToken để dán vào Postman (Authorization: Bearer <token>).

    python scripts/get_token.py --email ban@gmail.com
"""
import argparse
import getpass

import boto3

from _stack import DEFAULT_REGION, DEFAULT_STACK, get_outputs


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("--email", required=True)
    parser.add_argument("--stack", default=DEFAULT_STACK)
    parser.add_argument("--region", default=DEFAULT_REGION)
    args = parser.parse_args()

    client_id = get_outputs(args.stack, args.region)["UserPoolClientId"]
    cognito = boto3.client("cognito-idp", region_name=args.region)
    result = cognito.initiate_auth(
        ClientId=client_id,
        AuthFlow="USER_PASSWORD_AUTH",
        AuthParameters={"USERNAME": args.email, "PASSWORD": getpass.getpass("Mật khẩu: ")},
    )
    print(result["AuthenticationResult"]["IdToken"])


if __name__ == "__main__":
    main()
