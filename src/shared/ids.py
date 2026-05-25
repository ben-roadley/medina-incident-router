import uuid

def get_correlation_id(event):
    """
    Extracts or generates a correlation ID from the event headers.
    """
    headers = event.get("headers") or {}
    correlation_id = (
        headers.get("x-correlation-id")
        or headers.get("X-Correlation-Id")
        or headers.get("X-Correlation-ID")
    )
    if correlation_id:
        return correlation_id
    return str(uuid.uuid4())


def generate_incident_id():
    """
    Generates a new unique incident ID.
    """
    return str(uuid.uuid4())
