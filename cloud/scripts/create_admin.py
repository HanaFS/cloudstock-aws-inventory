"""Tạo (hoặc cập nhật) tài khoản Cognito và gán vào group Admin/Staff.
Mật khẩu được nhập tại dòng lệnh, KHÔNG lưu trong code hay trên GitHub.

    python scripts/create_admin.py --email ban@gmail.com
    python scripts/create_admin.py --email nv1@gmail.com --role Staff
"""
import argparse
import getpass
import sys

import boto3

from _stack import DEFAULT_REGION, DEFAULT_STACK, get_outputs


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("--email", required=True)
    parser.add_argument("--role", choices=["Admin", "Staff"], default="Admin")
    parser.add_argument("--stack", default=DEFAULT_STACK)
    parser.add_argument("--region", default=DEFAULT_REGION)
    args = parser.parse_args()

    password = getpass.getpass("Mật khẩu (>= 8 ký tự, có hoa, thường, số): ")
    if password != getpass.getpass("Nhập lại mật khẩu: "):
        sys.exit("Hai lần nhập mật khẩu không khớp.")

    pool_id = get_outputs(args.stack, args.region)["UserPoolId"]
    cognito = boto3.client("cognito-idp", region_name=args.region)

    try:
        cognito.admin_create_user(
            UserPoolId=pool_id,
            Username=args.email,
            UserAttributes=[
                {"Name": "email", "Value": args.email},
                {"Name": "email_verified", "Value": "true"},
            ],
            MessageAction="SUPPRESS",
        )
        print(f"[OK] Đã tạo user {args.email}")
    except cognito.exceptions.UsernameExistsException:
        print(f"[i] User {args.email} đã tồn tại, cập nhật mật khẩu & group")

    try:
        cognito.admin_set_user_password(
            UserPoolId=pool_id, Username=args.email, Password=password, Permanent=True)
    except cognito.exceptions.InvalidPasswordException as exc:
        sys.exit(f"Mật khẩu không hợp lệ: {exc}")

    for group in ("Admin", "Staff"):  # mỗi user chỉ thuộc 1 group
        if group != args.role:
            cognito.admin_remove_user_from_group(UserPoolId=pool_id, Username=args.email, GroupName=group)
    cognito.admin_add_user_to_group(UserPoolId=pool_id, Username=args.email, GroupName=args.role)
    print(f"[OK] {args.email} thuộc group {args.role}")


if __name__ == "__main__":
    main()
