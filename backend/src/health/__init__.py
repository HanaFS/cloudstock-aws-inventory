import json
import os


def handler(event=None, context=None):
    return {
        "statusCode": 200,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": os.environ.get(
                "FRONTEND_ORIGIN", "http://localhost:8080"
            ),
            "Vary": "Origin",
        },
        "body": json.dumps(
            {
                "success": True,
                "data": {
                    "service": "cloudstock-api",
                    "status": "ok",
                    "stage": os.environ.get("STAGE", "dev"),
                },
            },
            separators=(",", ":"),
        ),
    }
