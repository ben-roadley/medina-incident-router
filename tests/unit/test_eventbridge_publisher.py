import os
os.environ["INCIDENT_EVENT_BUS_NAME"] = "test-incident-bus"
import sys
import json
from unittest.mock import MagicMock, patch
import pytest

os.environ.setdefault("INCIDENTS_TABLE_NAME", "test-incidents-table")
os.environ.setdefault("SERVICE_NAME", "test-service")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../src"))

with patch("boto3.client"):
    import adapters.eventbridge_publisher as publisher_module
    from adapters.eventbridge_publisher import publish_incident_reported

@pytest.fixture
def mock_eventbridge_client(monkeypatch):
    client = MagicMock()
    monkeypatch.setattr(publisher_module, "eventbridge_client", client)
    return client


class TestPublishIncidentReported:
    def test_puts_expected_eventbridge_entry(self, mock_eventbridge_client):
        mock_eventbridge_client.put_events.return_value = {
            "FailedEntryCount": 0,
            "Entries": [{"EventId": "evt-123"}],
        }
        event_payload = {
            "eventType": "IncidentReported",
            "incidentId": "inc-123",
            "correlationId": "corr-123",
            "source": "sensor-1",
            "incidentType": "airlock",
            "severity": "critical",
            "reportedAt": "2026-05-22T10:15:00Z",
        }

        event_id = publish_incident_reported(event_payload)

        assert event_id == "evt-123"
        mock_eventbridge_client.put_events.assert_called_once_with(
            Entries=[
                {
                    "EventBusName": "test-incident-bus",
                    "Source": "test-service",
                    "DetailType": "IncidentReported",
                    "Detail": json.dumps(event_payload),
                }
            ]
        )

    def test_raises_runtime_error_when_eventbridge_rejects_event(self, mock_eventbridge_client):
        mock_eventbridge_client.put_events.return_value = {
            "FailedEntryCount": 1,
            "Entries": [
                {
                    "ErrorCode": "InternalFailure",
                    "ErrorMessage": "EventBridge unavailable",
                }
            ],
        }

        with pytest.raises(RuntimeError) as exc_info:
            publish_incident_reported({"incidentId": "inc-123"})

        assert str(exc_info.value) == (
            "Failed to publish IncidentReported: InternalFailure - EventBridge unavailable"
        )

    def test_uses_fallback_error_values_when_eventbridge_response_is_sparse(self, mock_eventbridge_client):
        mock_eventbridge_client.put_events.return_value = {
            "FailedEntryCount": 1,
            "Entries": [],
        }

        with pytest.raises(RuntimeError) as exc_info:
            publish_incident_reported({"incidentId": "inc-123"})

        assert str(exc_info.value) == (
            "Failed to publish IncidentReported: UnknownError - Unknown EventBridge error"
        )