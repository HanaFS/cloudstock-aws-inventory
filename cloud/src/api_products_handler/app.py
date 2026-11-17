"""api-products-handler - Module 3: Hàng hóa, nhà cung cấp, S3 pre-signed URL.
Route: /products, /products/{proxy+}, /suppliers, /suppliers/{proxy+}

TODO (backend) theo tài liệu nhóm:
  GET    /products, /products/{id}        (Admin, Staff)  ?category=&status=
  POST   /products                        (Admin, Staff)  tự sinh productId, status, updatedAt
  PUT    /products/{id}                   (Admin, Staff)
  DELETE /products/{id}                   (Admin)         -> dùng require_role(user, "Admin")
  POST   /products/upload-url             (Admin, Staff)  body {folder, fileName, contentType}
         -> s3_client.generate_presigned_url("put_object", ...) trả {uploadUrl, fileUrl, s3Key}
         folder chỉ nhận "products" hoặc "invoices"; ContentType phải khớp lúc frontend PUT
  GET/POST/PUT/DELETE /suppliers[/{id}]   (DELETE: Admin)
"""
from common import *


def lambda_handler(event, context):
    method, path = get_request_info(event)
    user = get_current_user(event)

    if path.endswith("/_ping"):
        def check():
            products_table.scan(Limit=1)
            suppliers_table.scan(Limit=1)
            url = s3_client.generate_presigned_url(
                "put_object", Params={"Bucket": BUCKET_NAME, "Key": "products/_ping.txt"}, ExpiresIn=60)
            return {"dynamodb": "ok", "presignedUrlSample": url.split("?")[0]}
        return run_ping("api-products-handler", user, check)

    return not_implemented("api-products-handler", method, path)
