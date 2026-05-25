import json
import os
import time
from shared.constants import ET_INCIDENT_ACKNOWLEDGED, ET_INCIDENT_REPORTED, STATUS_ACKNOWLEDGED, STATUS_DISPATCHED, STATUS_REPORTED
from shared.logging import get_logger
from shared.responses import response
from shared.ids import get_correlation_id, generate_incident_id
from datetime import datetime, UTC
from adapters.dynamodb_registry import save_incident, get_incident
from adapters.eventbridge_publisher import publish_incident_acknowledged, publish_incident_reported

from aws_lambda_powertools.utilities.idempotency import (
    DynamoDBPersistenceLayer,
    IdempotencyConfig,
    idempotent,
)
from aws_lambda_powertools.utilities.typing import LambdaContext

idempotency_table = os.getenv("IDEMPOTENCY_TABLE", "")
persistence_layer = DynamoDBPersistenceLayer(table_name=idempotency_table)
config = IdempotencyConfig(
    event_key_jmespath='headers."x-idempotency-key"'
)


logger = get_logger()

REQUIRED_INCIDENT_FIELDS = ("source", "incidentType", "severity")


def validate_create_incident_request(incident_data):
    if not isinstance(incident_data, dict):
        return "Request body must be a JSON object"

    missing_fields = [
        field for field in REQUIRED_INCIDENT_FIELDS
        if not incident_data.get(field)
    ]

    if missing_fields:
        return f"Missing required fields: {', '.join(missing_fields)}"

    return None


def create_incident(incident_data, correlation_id):
    incident_id = generate_incident_id()
    source = incident_data["source"]
    incident_type = incident_data["incidentType"]
    severity = incident_data["severity"]
    description = incident_data.get("description", "")
    status = STATUS_REPORTED
    created_at = int(time.time())
    updated_at = created_at

    item = {
        "pk": f"INCIDENT#{incident_id}",
        "sk": "STATE",
        "incidentId": incident_id,
        "source": source,
        "incidentType": incident_type,
        "severity": severity,
        "description": description,
        "status": status,
        "createdAt": created_at,
        "updatedAt": updated_at,
        "correlationId": correlation_id,
    }
    save_incident(item)
    return item


def build_incident_reported_event(incident_item):
    return {
        "eventType": ET_INCIDENT_REPORTED,
        "incidentId": incident_item["incidentId"],
        "correlationId": incident_item["correlationId"],
        "source": incident_item["source"],
        "incidentType": incident_item["incidentType"],
        "severity": incident_item["severity"],
        "description": incident_item.get("description", ""),
        "reportedAt": datetime.fromtimestamp(incident_item["createdAt"], UTC).isoformat().replace("+00:00", "Z"),
    }


def build_incident_acknowledged_event(incident_item, correlation_id):
    return {
        "eventType": ET_INCIDENT_ACKNOWLEDGED,
        "incidentId": incident_item["incidentId"],
        "correlationId": correlation_id,
        "source": incident_item["source"],
        "incidentType": incident_item["incidentType"],
        "severity": incident_item["severity"],
        "description": incident_item.get("description", ""),
        "acknowledgedAt": datetime.fromtimestamp(incident_item["updatedAt"], UTC).isoformat().replace("+00:00", "Z"),
    }


def get_incident_by_id(incident_id):
    incident = get_incident(
        {
            "pk": f"INCIDENT#{incident_id}",
            "sk": "STATE",
        }
    )
    if not incident:
        return None
    
    incident_projection = get_incident(
        {
            "pk": f"PROJECTION#{incident_id}",
            "sk": "STATE",
        }
    )
    if not incident_projection:
        return {
            "incidentId": incident["incidentId"],
            "source": incident["source"],
            "incidentType": incident["incidentType"],
            "severity": incident["severity"],
            "description": incident.get("description", ""),
            "status": incident["status"],
            "createdAt": int(incident["createdAt"]),
            "updatedAt": int(incident["updatedAt"]),
        }
    return {
        "incidentId": incident["incidentId"],
        "source": incident["source"],
        "incidentType": incident["incidentType"],
        "severity": incident["severity"],
        "description": incident.get("description", ""),
        "status": incident_projection["status"],
        "createdAt": int(incident["createdAt"]),
        "updatedAt": int(incident["updatedAt"]),
    }


@idempotent(config=config, persistence_store=persistence_layer)
def lambda_handler(event: dict, context: LambdaContext):
    correlation_id = get_correlation_id(event)
    logger.info("Handling request", extra={"correlationId": correlation_id})

    method = event.get("httpMethod")

    if method == "POST":
        try:
            raw_body = event.get("body") or "{}"
            incident_data = json.loads(raw_body)
        except json.JSONDecodeError:
            return response(
                400,
                json.dumps({"message": "Invalid JSON"}),
                correlation_id
            )

        url = event.get("path", "")
        if url.endswith("/ack"):
            incident_id = url.split("/")[-2]
            return handle_post_ack(event, incident_id, incident_data, correlation_id)
        else:
            return handle_post(event, incident_data, correlation_id)
    elif method == "GET":
        return handle_get_incident(event, correlation_id)
    else:
        return response(
            405,
            json.dumps({"message": "Method not allowed"}),
            correlation_id
        )


def handle_post(event, incident_data, correlation_id):
    validation_error = validate_create_incident_request(incident_data)
    if validation_error:
        return response(
            400,
            json.dumps({"message": validation_error}),
            correlation_id
        )

    try:
        incident_item = create_incident(incident_data, correlation_id)
        event_id = publish_incident_reported(build_incident_reported_event(incident_item))
        logger.info(
            "Published IncidentReported event",
            extra={
                "incidentId": incident_item["incidentId"],
                "correlationId": correlation_id,
                "eventId": event_id,
            },
        )
        return response(
            201,
            json.dumps({"incidentId": incident_item["incidentId"]}),
            correlation_id
        )
    except Exception as exc:
        logger.exception("Failed to create incident", extra={"incidentData": incident_data})
        return response(
            500,
            json.dumps({"message": "Internal server error"}),
            correlation_id
        )


def handle_post_ack(event, incident_id, incident_data, correlation_id):
    logger.info("Received acknowledgment request")
    
    if not incident_id:
        logger.info(
            "Cannot acknowledge incident because incident ID is missing.",
            extra={
                "correlationId": correlation_id
            },
        )
        return response(
            400,
            json.dumps({"message": "Incident ID is required"}),
            correlation_id
        )

    incident = get_incident_by_id(incident_id)
    if not incident:
        logger.info(
            "Cannot acknowledge incident because incident does not exist.",
            extra={
                "correlationId": correlation_id,
                "incidentId": incident_id,
            },
        )
        return response(
            404,
            json.dumps({"message": "Incident not found"}),
            correlation_id
        )
    if incident["status"] == STATUS_DISPATCHED:
        logger.info(
            "Cannot acknowledge incident because it has already been dispatched.",
            extra={
                "correlationId": correlation_id,
                "incidentId": incident_id,
            },
        )
        return response(
            400,
            json.dumps({"message": "Incident cannot be acknowledged because it has already been dispatched"}),
            correlation_id
        )
    if incident["status"] == STATUS_ACKNOWLEDGED:
        logger.info(
            "Cannot acknowledge incident because it has already been acknowledged.",
            extra={
                "correlationId": correlation_id,
                "incidentId": incident_id,
            },
        )
        return response(
            400,
            json.dumps({"message": "Incident has already been acknowledged"}),
            correlation_id
        )
    try:
        event_id = publish_incident_acknowledged(build_incident_acknowledged_event(incident, correlation_id))
        logger.info(
            "Published IncidentAcknowledged event",
            extra={
                "incidentId": incident["incidentId"],
                "correlationId": correlation_id,
                "eventId": event_id,
            },
        )
        return response(
            201,
            json.dumps({"incidentId": incident["incidentId"]}),
            correlation_id
        )
    except Exception as exc:
        logger.exception("Failed to acknowledge incident", extra={"incidentData": incident_data})
        return response(
            500,
            json.dumps({"message": "Internal server error"}),
            correlation_id
        )


def handle_get_incident(event, correlation_id):
    incident_id = (event.get("pathParameters") or {}).get("id")
    if not incident_id:
        return response(
            400,
            json.dumps({"message": "Incident ID is required"}),
            correlation_id
        )

    try:
        incident = get_incident_by_id(incident_id)
    except Exception:
        logger.exception("Failed to fetch incident", extra={"incidentId": incident_id})
        return response(
            500,
            json.dumps({"message": "Internal server error"}),
            correlation_id
        )

    if incident is None:
        return response(
            404,
            json.dumps({"message": "Incident not found"}),
            correlation_id
        )

    return response(
        200,
        json.dumps(incident),
        correlation_id
    )
