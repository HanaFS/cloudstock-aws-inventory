"""In ra nội dung frontend/js/config.js với giá trị THẬT của stack để gửi cho bạn làm frontend.

    python scripts/print_config.py
    python scripts/print_config.py --out config.generated.js
"""
import argparse

from _stack import DEFAULT_REGION, DEFAULT_STACK, get_outputs

TEMPLATE = """// File: frontend/js/config.js  (sinh tự động bởi scripts/print_config.py)
const AWS_CONFIG = {{
  REGION: '{region}',
  API_BASE_URL: '{api}',
  COGNITO: {{
    USER_POOL_ID: '{pool}',
    CLIENT_ID: '{client}',
    GROUPS: {{ ADMIN: 'Admin', STAFF: 'Staff' }}
  }},
  S3: {{
    BUCKET_NAME: '{bucket}',
    PUBLIC_PRODUCT_PREFIX: 'products/',
    PRIVATE_INVOICE_PREFIX: 'invoices/',
    PUBLIC_BASE_URL: 'https://{bucket}.s3.{region}.amazonaws.com'
  }},
  ENUMS: {{
    PRODUCT_STATUS: {{ IN_STOCK: 'IN_STOCK', OUT_OF_STOCK: 'OUT_OF_STOCK' }},
    TRANSACTION_TYPE: {{ IMPORT: 'IMPORT', EXPORT: 'EXPORT' }}
  }}
}};
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("--stack", default=DEFAULT_STACK)
    parser.add_argument("--region", default=DEFAULT_REGION)
    parser.add_argument("--out")
    args = parser.parse_args()

    o = get_outputs(args.stack, args.region)
    text = TEMPLATE.format(region=args.region, api=o["ApiBaseUrl"], pool=o["UserPoolId"],
                           client=o["UserPoolClientId"], bucket=o["BucketNameOut"])
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"[OK] Đã ghi {args.out}")
    else:
        print(text)


if __name__ == "__main__":
    main()
