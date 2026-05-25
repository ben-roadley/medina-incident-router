import os

import boto3

from shared.constants import STATUS_REPORTED

incidents_table_name = os.environ["INCIDENTS_TABLE_NAME"] # Fail fast if not set

dynamodb = boto3.resource('dynamodb')
incidents_table = dynamodb.Table(incidents_table_name)

def save_incident(incident: dict):
    return incidents_table.put_item(Item=incident)

def get_incident(key: dict):
    response = incidents_table.get_item(Key=key)
    return response.get("Item")

def get_stale_incidents(threshold_time: int):
    response = incidents_table.scan()
    items = response.get("Items", [])
    stale_incidents = []
    for item in items:
        if (
            item.get("pk", "").startswith("PROJECTION#") and
            item.get("sk") == "STATE" and
            item.get("status") == STATUS_REPORTED and
            item.get("createdAt", 0) < threshold_time
        ):
            stale_incidents.append(item)
    return stale_incidents