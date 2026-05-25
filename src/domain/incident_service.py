# Domain logic for incident handling
from datetime import datetime, UTC

from shared.constants import SEVERITY__LOW, SEVERITY__HIGH, SEVERITY__CRITICAL, SEVERITY_LEVELS


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

def handle_incident_by_severity(detail, publish_dispatched, publish_monitored, publish_no_decision):
    severity = detail["severity"]
    incident_item = build_incident_item(detail)

    if severity == SEVERITY__CRITICAL:
        event_id = publish_dispatched(incident_item)
        return ("dispatched", event_id, incident_item)
    elif severity in (SEVERITY__HIGH, SEVERITY__LOW):
        event_id = publish_monitored(incident_item)
        return ("monitored", event_id, incident_item)
    else:
        event_id = publish_no_decision(incident_item)
        return ("no_decision", event_id, incident_item)
