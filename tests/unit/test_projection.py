import os
import sys
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault("INCIDENTS_TABLE_NAME", "test-incidents-table")
os.environ.setdefault("SERVICE_NAME", "test-service")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../src"))

with patch("boto3.resource"):
    import handlers.projection as projection_module
    from handlers.projection import lambda_handler

@pytest.fixture
def mock_table(monkeypatch):
    table = MagicMock()
    monkeypatch.setattr(projection_module, "incidents_table", table)
    return table

@pytest.fixture
def mock_logger(monkeypatch):
    logger = MagicMock()
    monkeypatch.setattr(projection_module, "logger", logger)
    return logger

@patch("handlers.projection.save_incident")
def test_projection_upserts_on_incident_reported(mock_save_incident, mock_logger):
    event = {
        "detail-type": "IncidentReported",
        "detail": {
            "incidentId": "inc-123",
            "correlationId": "corr-123",
            "source": "sensor-1",
            "incidentType": "airlock",
            "severity": "critical",
            "description": "desc",
            "reportedAt": "2026-05-22T10:15:00Z",
        }
    }
    mock_logger  # ensure fixture is used
    lambda_handler(event, {})
    item = mock_save_incident.call_args.args[0]
    assert item["pk"] == "PROJECTION#inc-123"
    assert item["incidentId"] == "inc-123"
    assert item["status"] == "REPORTED"
    assert item["source"] == "sensor-1"
    assert item["incidentType"] == "airlock"
    assert item["severity"] == "critical"
    assert item["description"] == "desc"
    assert item["reportedAt"] == "2026-05-22T10:15:00Z"
    assert item["correlationId"] == "corr-123"


@patch("handlers.projection.save_incident")
def test_projection_upserts_on_incident_dispatched(mock_save_incident, mock_logger):
    event = {
        "detail-type": "IncidentDispatched",
        "detail": {
            "incidentId": "inc-456",
            "correlationId": "corr-456",
            "source": "sensor-2",
            "incidentType": "fire",
            "severity": "high",
            "description": "fire in sector 7",
            "reportedAt": "2026-05-22T11:00:00Z",
        }
    }
    mock_logger  # ensure fixture is used
    lambda_handler(event, {})
    item = mock_save_incident.call_args.args[0]
    assert item["pk"] == "PROJECTION#inc-456"
    assert item["incidentId"] == "inc-456"
    assert item["status"] == "DISPATCHED"
    assert item["source"] == "sensor-2"
    assert item["incidentType"] == "fire"
    assert item["severity"] == "high"
    assert item["description"] == "fire in sector 7"
    assert item["reportedAt"] == "2026-05-22T11:00:00Z"
    assert item["correlationId"] == "corr-456"


@patch("handlers.projection.save_incident")
def test_projection_upserts_on_incident_monitored(mock_save_incident, mock_logger):
    event = {
        "detail-type": "IncidentMonitored",
        "detail": {
            "incidentId": "inc-789",
            "correlationId": "corr-789",
            "source": "sensor-3",
            "incidentType": "intrusion",
            "severity": "medium",
            "description": "intruder detected",
            "reportedAt": "2026-05-22T12:00:00Z",
        }
    }
    mock_logger  # ensure fixture is used
    lambda_handler(event, {})
    item = mock_save_incident.call_args.args[0]
    assert item["pk"] == "PROJECTION#inc-789"
    assert item["incidentId"] == "inc-789"
    assert item["status"] == "MONITORED"
    assert item["source"] == "sensor-3"
    assert item["incidentType"] == "intrusion"
    assert item["severity"] == "medium"
    assert item["description"] == "intruder detected"
    assert item["reportedAt"] == "2026-05-22T12:00:00Z"
    assert item["correlationId"] == "corr-789"


@patch("handlers.projection.save_incident")
def test_projection_skips_unrelated_event_type(mock_save_incident, mock_logger):
    event = {
        "detail-type": "OtherEvent",
        "detail": {
            "incidentId": "inc-000"
        }
    }
    mock_logger  # ensure fixture is used
    lambda_handler(event, {})
    mock_save_incident.assert_not_called()


@patch("handlers.projection.save_incident")
def test_projection_skips_missing_detail(mock_save_incident, mock_logger):
    event = {
        "detail-type": "IncidentReported"
        # No detail
    }
    mock_logger  # ensure fixture is used
    lambda_handler(event, {})
    mock_save_incident.assert_not_called()