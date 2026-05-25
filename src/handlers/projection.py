import os
import json
from shared.constants import (
    ET_INCIDENT_ACKNOWLEDGED, 
    ET_INCIDENT_DISPATCHED, 
    ET_INCIDENT_ESCALATED, 
    ET_INCIDENT_MONITORED, 
    ET_INCIDENT_REPORTED, 
    STATUS_ACKNOWLEDGED, 
    STATUS_DISPATCHED, 
    STATUS_ESCALATED, 
    STATUS_MONITORED, 
    STATUS_REPORTED,
    )
from shared.logging import get_logger
from adapters.dynamodb_registry import save_incident

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
    if not detail or event.get("detail-type") not in (ET_INCIDENT_REPORTED, ET_INCIDENT_DISPATCHED, ET_INCIDENT_MONITORED, ET_INCIDENT_ACKNOWLEDGED, ET_INCIDENT_ESCALATED):
        logger.warning("Event is not IncidentReported, IncidentDispatched, IncidentMonitored, IncidentAcknowledged, or IncidentEscalated, skipping")
        return

    incident_id = detail["incidentId"]
    event_type = event.get("detail-type")
    
    if event_type == ET_INCIDENT_REPORTED:
        status = STATUS_REPORTED
    elif event_type == ET_INCIDENT_DISPATCHED:
        status = STATUS_DISPATCHED
    elif event_type == ET_INCIDENT_MONITORED:
        status = STATUS_MONITORED
    elif event_type == ET_INCIDENT_ACKNOWLEDGED:
        status = STATUS_ACKNOWLEDGED
    elif event_type == ET_INCIDENT_ESCALATED:
        status = STATUS_ESCALATED
        escalation_reason = detail.get("escalationReason", "Unknown")
    item = {
        "pk": f"PROJECTION#{incident_id}",
        "sk": "STATE",
        "incidentId": incident_id,
        "status": status,
        "source": detail.get("source"),
        "incidentType": detail.get("incidentType"),
        "severity": detail.get("severity"),
        "description": detail.get("description", ""),
        "reportedAt": detail.get("reportedAt"),
        "correlationId": detail.get("correlationId"),
    }
    if event_type == ET_INCIDENT_ESCALATED:
        item["escalationReason"] = escalation_reason
    save_incident(item)
    logger.info(f"Projection updated for incident {incident_id}")
