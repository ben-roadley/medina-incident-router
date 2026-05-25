def response(status_code, body, correlation_id):
    """
    Build a standard API Gateway response with status code, body, and correlation ID header.
    """
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "x-correlation-id": correlation_id
        },
        "body": body
    }
