from ..common.http import ApiError, with_error_handling


@with_error_handling
def handler(event, context=None):
    path = event.get("path", "")
    if path == "/products/upload-url":
        from ..uploads import product_image_upload_url

        return product_image_upload_url(event, context)
    if path.startswith("/suppliers"):
        from ..suppliers import handler as supplier_handler

        return supplier_handler(event, context)
    if path.startswith("/products"):
        from ..products import handler as product_handler

        return product_handler(event, context)
    raise ApiError(404, "ROUTE_NOT_FOUND", "Không tìm thấy endpoint.")
