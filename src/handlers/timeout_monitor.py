import json
import os
import time
from shared.constants import STATUS_REPORTED, TIMEOUT_THRESHOLD_MINUTES
from shared.logging import get_logger
from shared.ids import get_correlation_id
from datetime import datetime, UTC
from adapters.dynamodb_registry import get_stale_incidents, get_incident
from adapters.eventbridge_publisher import publish_incident_timeout

from aws_lambda_powertools.utilities.idempotency import (
    DynamoDBPersistenceLayer,
    idempotent,
)
from aws_lambda_powertools.utilities.typing import LambdaContext

idempotency_table = os.getenv("IDEMPOTENCY_TABLE", "")
persistence_layer = DynamoDBPersistenceLayer(table_name=idempotency_table)

logger = get_logger()


def build_incident_item(detail):
    return {
        "incidentId": detail["incidentId"],
        "correlationId": detail["correlationId"],
        "source": detail["source"],
        "incidentType": detail["incidentType"],
        "severity": detail["severity"],
        "description": detail.get("description", ""),
        "eventType": detail["eventType"],
        "createdAt": int(datetime.now(UTC).timestamp()),
    }

@idempotent(persistence_store=persistence_layer)
def lambda_handler(event: dict, context: LambdaContext):
    correlation_id = get_correlation_id(event)
    logger.info("Handling request", extra={"correlationId": correlation_id})

    threshold_time = int(time.time()) - TIMEOUT_THRESHOLD_MINUTES * 60
    stale_incidents = get_stale_incidents(threshold_time)
    logger.info(f"Found {len(stale_incidents)} stale incidents", extra={"correlationId": correlation_id})

    for incident in stale_incidents:
        logger.info(f"Processing stale incident {incident['incidentId']}", extra={"correlationId": correlation_id})
        # Re-fetch the incident to ensure we have the latest status
        current_incident = get_incident(
            {"pk": f"PROJECTION#{incident['incidentId']}", "sk": "STATE"}
        )

        if current_incident and current_incident.get("status") == STATUS_REPORTED   :
            publish_incident_timeout(incident)
            logger.info(f"Incident {incident['incidentId']} is still REPORTED, publishing IncidentTimeout event", extra={"correlationId": correlation_id})
