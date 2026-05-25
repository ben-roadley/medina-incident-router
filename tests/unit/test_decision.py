import os
import sys
import json
from unittest.mock import patch, MagicMock
import pytest

os.environ.setdefault("LOG_LEVEL", "DEBUG")
os.environ.setdefault("SERVICE_NAME", "test-service")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../src"))

with patch("boto3.client"), patch("boto3.resource"):
    import handlers.decision as decision_module
    from handlers.decision import lambda_handler

def make_event(severity, event_type="IncidentReported"):
    return {
        "detail": {
            "incidentId": "inc-123",
            "correlationId": "corr-123",
            "source": "sensor-1",
            "incidentType": "fire",
            "severity": severity,
            "description": "desc",
            "eventType": event_type,
        }
    }

@pytest.fixture
def mock_logger(monkeypatch):
    logger = MagicMock()
    monkeypatch.setattr(decision_module, "logger", logger)
    return logger

@patch("handlers.decision.publish_incident_dispatched")
@patch("handlers.decision.publish_incident_monitored")
def test_critical_dispatches_and_logs(mock_monitored, mock_dispatched, mock_logger):
    event = make_event("critical")
    mock_dispatched.return_value = "event-123"
    lambda_handler(event, {})
    mock_dispatched.assert_called_once()
    mock_monitored.assert_not_called()
    mock_logger.info.assert_any_call(
        "Incident is critical, dispatching immediately",
        extra={
            "incidentId": "inc-123",
            "correlationId": "corr-123",
            "eventId": "event-123",
        },
    )

@patch("handlers.decision.publish_incident_dispatched")
@patch("handlers.decision.publish_incident_monitored")
def test_high_monitors_and_logs(mock_monitored, mock_dispatched, mock_logger):
    event = make_event("high")
    mock_monitored.return_value = "event-456"
    lambda_handler(event, {})
    mock_monitored.assert_called_once()
    mock_dispatched.assert_not_called()
    mock_logger.info.assert_any_call(
        "Incident is not critical, monitoring",
        extra={
            "incidentId": "inc-123",
            "correlationId": "corr-123",
            "eventId": "event-456",
        },
    )

@patch("handlers.decision.publish_incident_dispatched")
@patch("handlers.decision.publish_incident_monitored")
def test_low_monitors_and_logs(mock_monitored, mock_dispatched, mock_logger):
    event = make_event("low")
    mock_monitored.return_value = "event-789"
    lambda_handler(event, {})
    mock_monitored.assert_called_once()
    mock_dispatched.assert_not_called()
    mock_logger.info.assert_any_call(
        "Incident is not critical, monitoring",
        extra={
            "incidentId": "inc-123",
            "correlationId": "corr-123",
            "eventId": "event-789",
        },
    )

@patch("handlers.decision.publish_incident_dispatched")
@patch("handlers.decision.publish_incident_monitored")
def test_invalid_severity_logs_error(mock_monitored, mock_dispatched, mock_logger):
    event = make_event("invalid")
    lambda_handler(event, {})
    mock_monitored.assert_not_called()
    mock_dispatched.assert_not_called()
    mock_logger.error.assert_called_once()
    assert "Invalid severity level" in mock_logger.error.call_args.args[0]

@patch("handlers.decision.publish_incident_dispatched")
@patch("handlers.decision.publish_incident_monitored")
def test_non_incident_reported_event_skipped(mock_monitored, mock_dispatched, mock_logger):
    event = make_event("critical", event_type="OtherEvent")
    lambda_handler(event, {})
    mock_monitored.assert_not_called()
    mock_dispatched.assert_not_called()
    mock_logger.warning.assert_called_once_with("Event is not IncidentReported, skipping")

@patch("handlers.decision.publish_incident_dispatched")
@patch("handlers.decision.publish_incident_monitored")
def test_missing_detail_skipped(mock_monitored, mock_dispatched, mock_logger):
    event = {"detail": None}
    lambda_handler(event, {})
    mock_monitored.assert_not_called()
    mock_dispatched.assert_not_called()
    mock_logger.warning.assert_called_once_with("Event is not IncidentReported, skipping")
