import os
import json
from shared.constants import ET_INCIDENT_REPORTED
from shared.logging import get_logger
from adapters.eventbridge_publisher import publish_incident_dispatched, publish_incident_monitored, publish_incident_no_decision
from domain.incident_service import SEVERITY_LEVELS, handle_incident_by_severity

from aws_lambda_powertools.utilities.idempotency import (
    DynamoDBPersistenceLayer,
    idempotent,
)
from aws_lambda_powertools.utilities.typing import LambdaContext

idempotency_table = os.getenv("IDEMPOTENCY_TABLE", "")
persistence_layer = DynamoDBPersistenceLayer(table_name=idempotency_table)

logger = get_logger()


@idempotent(persistence_store=persistence_layer)
def lambda_handler(event: dict, context: LambdaContext):
    detail = event.get("detail")
    if not detail or detail.get("eventType") != ET_INCIDENT_REPORTED:
        logger.warning("Event is not IncidentReported, skipping")
        return
    
    severity = detail["severity"]

    if severity not in SEVERITY_LEVELS:
        incident_id = detail["incidentId"]
        logger.error(f"Invalid severity level: {severity} for incident {incident_id}")
        return

    action, event_id, incident_item = handle_incident_by_severity(
        detail, publish_incident_dispatched, publish_incident_monitored, publish_incident_no_decision
    )

    if action == "dispatched":
        logger.info(
            "Incident is critical, dispatching immediately",
            extra={
                "incidentId": incident_item["incidentId"],
                "correlationId": incident_item["correlationId"],
                "eventId": event_id,
            },
        )
    elif action == "monitored":
        logger.info(
            "Incident is not critical, monitoring",
            extra={
                "incidentId": incident_item["incidentId"],
                "correlationId": incident_item["correlationId"],
                "eventId": event_id,
            },
        )
    elif action == "no_decision":
        logger.info(
            "Incident severity is unknown, no confident decision",
            extra={
                "incidentId": incident_item["incidentId"],
                "correlationId": incident_item["correlationId"],
                "eventId": event_id,
            },
        )