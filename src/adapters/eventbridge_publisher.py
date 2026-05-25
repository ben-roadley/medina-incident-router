import json
import os

import boto3

from shared.constants import (
    ET_INCIDENT_DISPATCHED, 
    ET_INCIDENT_ESCALATED,
    ET_INCIDENT_MONITORED, 
    ET_INCIDENT_ACKNOWLEDGED,
    ET_INCIDENT_NO_DECISION,
    ET_INCIDENT_TIMEOUT, 
    ET_INCIDENT_REPORTED,
    )


eventbridge_client = boto3.client("events")

def get_service_name():
    return os.environ.get("SERVICE_NAME", "medina-incident-router")

def get_event_bus_name():
    return os.environ.get("INCIDENT_EVENT_BUS_NAME", "medina-incident-bus")

def publish_incident(event_payload, detail_type):
    response = eventbridge_client.put_events(
        Entries=[
            {
                "EventBusName": get_event_bus_name(),
                "Source": get_service_name(),
                "DetailType": detail_type,
                "Detail": json.dumps(event_payload),
            }
        ]
    )

    if response.get("FailedEntryCount", 0):
        error_entry = (response.get("Entries") or [{}])[0]
        error_code = error_entry.get("ErrorCode", "UnknownError")
        error_message = error_entry.get("ErrorMessage", "Unknown EventBridge error")
        raise RuntimeError(f"Failed to publish {detail_type}: {error_code} - {error_message}")

    return response["Entries"][0]["EventId"]

def publish_incident_reported(event_payload):
    return publish_incident(event_payload, ET_INCIDENT_REPORTED)

def publish_incident_acknowledged(event_payload):
    return publish_incident(event_payload, ET_INCIDENT_ACKNOWLEDGED)

def publish_incident_escalated(event_payload):
    return publish_incident(event_payload, ET_INCIDENT_ESCALATED)

def publish_incident_dispatched(event_payload):
    return publish_incident(event_payload, ET_INCIDENT_DISPATCHED)

def publish_incident_monitored(event_payload):
    return publish_incident(event_payload, ET_INCIDENT_MONITORED)

def publish_incident_no_decision(event_payload):
    return publish_incident(event_payload, ET_INCIDENT_NO_DECISION)

def publish_incident_timeout(event_payload):
    return publish_incident(event_payload, ET_INCIDENT_TIMEOUT)
