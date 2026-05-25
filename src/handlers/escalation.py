import os
from datetime import datetime, UTC
import json
from shared.constants import DECISION_NO_DECISION, DECISION_TIMEOUT, ET_INCIDENT_ESCALATED, ET_INCIDENT_NO_DECISION, ET_INCIDENT_TIMEOUT
from shared.logging import get_logger
from adapters.eventbridge_publisher import publish_incident_escalated

from aws_lambda_powertools.utilities.idempotency import (
    DynamoDBPersistenceLayer,
    idempotent,
)
from aws_lambda_powertools.utilities.typing import LambdaContext

idempotency_table = os.getenv("IDEMPOTENCY_TABLE", "")
persistence_layer = DynamoDBPersistenceLayer(table_name=idempotency_table)

logger = get_logger()


def build_incident_escalated_event(incident_item, correlation_id, escalation_reason, escalation_time):
    return {
        "eventType": ET_INCIDENT_ESCALATED,
        "incidentId": incident_item["incidentId"],
        "correlationId": correlation_id,
        "source": incident_item["source"],
        "incidentType": incident_item["incidentType"],
        "severity": incident_item["severity"],
        "description": incident_item.get("description", ""),
        "escalationReason": escalation_reason,
        "escalatedAt": escalation_time,
    }

@idempotent(persistence_store=persistence_layer)
def lambda_handler(event: dict, context: LambdaContext):
    detail = event.get("detail")
    if not detail or event.get("detail-type") not in (ET_INCIDENT_NO_DECISION, ET_INCIDENT_TIMEOUT):
        logger.warning("Event is not IncidentNoDecision/IncidentTimeout, skipping")
        return

    incident_id = detail["incidentId"]
    event_type = event.get("detail-type")
    escalation_time = event.get("time")

    if event_type == ET_INCIDENT_NO_DECISION:
        publish_incident_escalated(build_incident_escalated_event(detail, detail.get("correlationId"), DECISION_NO_DECISION, escalation_time))
        logger.info(
                "Published IncidentEscalated event",
                extra={
                    "incidentId": incident_id,
                    "correlationId": detail.get("correlationId"),
                    "eventId": event.get("id"),
                    "escalationReason": DECISION_NO_DECISION,
                },
            )
    else:
        publish_incident_escalated(build_incident_escalated_event(detail, detail.get("correlationId"), DECISION_TIMEOUT, escalation_time))
        logger.info(
                "Published IncidentTimeout event",
                extra={
                    "incidentId": incident_id,
                    "correlationId": detail.get("correlationId"),
                    "eventId": event.get("id"),
                    "escalationReason": DECISION_TIMEOUT,
                },
            )
