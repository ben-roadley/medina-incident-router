import json
import os
import sys
import uuid
from unittest.mock import MagicMock, patch

import pytest

# Set required environment variables before importing the handler module
os.environ.setdefault("INCIDENTS_TABLE_NAME", "test-incidents-table")
os.environ.setdefault("INCIDENT_EVENT_BUS_NAME", "test-incident-bus")
os.environ.setdefault("LOG_LEVEL", "DEBUG")
os.environ.setdefault("SERVICE_NAME", "test-service")

# Add src/ to the path and mock boto3 so module-level AWS calls don't fire
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../src"))

with patch("boto3.resource"), patch("boto3.client"):
    import handlers.incidents as incidents_module
    from handlers.incidents import (
        build_incident_reported_event,
        get_correlation_id,
        lambda_handler,
        validate_create_incident_request,
    )


SAMPLE_CORRELATION_ID = "test-correlation-id"
SAMPLE_INCIDENT_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------





import handlers.incidents as incidents_module_for_patch
from unittest.mock import patch as real_patch

@pytest.fixture
def mock_publisher():
    with real_patch("handlers.incidents.publish_incident_reported", return_value="event-123") as publisher:
        yield publisher


@pytest.fixture
def mock_logger(monkeypatch):
    logger = MagicMock()
    monkeypatch.setattr(incidents_module, "logger", logger)
    return logger


@pytest.fixture
def post_event():
    return {
        "httpMethod": "POST",
        "headers": {"x-correlation-id": SAMPLE_CORRELATION_ID},
        "body": json.dumps({
            "source": "sensor-1",
            "incidentType": "FIRE",
            "severity": "HIGH",
            "description": "Fire detected in sector 7",
        }),
        "pathParameters": None,
    }


@pytest.fixture
def get_event():
    return {
        "httpMethod": "GET",
        "headers": {"x-correlation-id": SAMPLE_CORRELATION_ID},
        "body": None,
        "pathParameters": {"id": SAMPLE_INCIDENT_ID},
    }


@pytest.fixture
def stored_item():
    return {
        "pk": f"INCIDENT#{SAMPLE_INCIDENT_ID}",
        "sk": "STATE",
        "incidentId": SAMPLE_INCIDENT_ID,
        "source": "sensor-1",
        "incidentType": "FIRE",
        "severity": "HIGH",
        "description": "Fire detected in sector 7",
        "status": "REPORTED",
        "createdAt": 1000,
        "updatedAt": 1000,
    }


# ---------------------------------------------------------------------------
# validate_create_incident_request
# ---------------------------------------------------------------------------

class TestValidateCreateIncidentRequest:
    def test_valid_request_returns_none(self):
        data = {"source": "s", "incidentType": "FIRE", "severity": "HIGH"}
        assert validate_create_incident_request(data) is None

    def test_non_dict_returns_error(self):
        assert validate_create_incident_request("not a dict") is not None

    def test_missing_all_required_fields_returns_all_names(self):
        error = validate_create_incident_request({})
        assert "source" in error
        assert "incidentType" in error
        assert "severity" in error

    def test_missing_one_field_returns_that_field(self):
        data = {"source": "s", "incidentType": "FIRE"}
        error = validate_create_incident_request(data)
        assert "severity" in error

    def test_empty_string_field_counts_as_missing(self):
        data = {"source": "", "incidentType": "FIRE", "severity": "HIGH"}
        error = validate_create_incident_request(data)
        assert "source" in error


# ---------------------------------------------------------------------------
# get_correlation_id
# ---------------------------------------------------------------------------

class TestGetCorrelationId:
    def test_reads_lowercase_header(self):
        event = {"headers": {"x-correlation-id": "abc-123"}}
        assert get_correlation_id(event) == "abc-123"

    def test_reads_mixed_case_header(self):
        event = {"headers": {"X-Correlation-Id": "abc-123"}}
        assert get_correlation_id(event) == "abc-123"

    def test_reads_uppercase_header(self):
        event = {"headers": {"X-Correlation-ID": "abc-123"}}
        assert get_correlation_id(event) == "abc-123"

    def test_generates_uuid_when_no_matching_header(self):
        result = get_correlation_id({"headers": {}})
        uuid.UUID(result)  # raises ValueError if not a valid UUID

    def test_generates_uuid_when_headers_key_absent(self):
        result = get_correlation_id({})
        uuid.UUID(result)


# ---------------------------------------------------------------------------
# lambda_handler – POST
# ---------------------------------------------------------------------------


class TestLambdaHandlerPost:
    @real_patch("handlers.incidents.save_incident")
    def test_creates_incident_and_returns_201(self, mock_save_incident, mock_publisher, mock_logger, post_event):
        resp = lambda_handler(post_event, {})
        assert resp["statusCode"] == 201
        body = json.loads(resp["body"])
        assert "incidentId" in body
        uuid.UUID(body["incidentId"])

    @real_patch("handlers.incidents.save_incident")
    def test_put_item_called_with_correct_fields(self, mock_save_incident, mock_publisher, mock_logger, post_event):
        lambda_handler(post_event, {})
        item = mock_save_incident.call_args.args[0]
        assert item["source"] == "sensor-1"
        assert item["incidentType"] == "FIRE"
        assert item["severity"] == "HIGH"
        assert item["status"] == "REPORTED"

    @real_patch("handlers.incidents.save_incident")
    def test_publishes_incident_reported_event(self, mock_save_incident, mock_publisher, mock_logger, post_event):
        resp = lambda_handler(post_event, {})
        incident_id = json.loads(resp["body"])["incidentId"]
        published_event = mock_publisher.call_args.args[0]
        assert published_event["eventType"] == "IncidentReported"
        assert published_event["incidentId"] == incident_id
        assert published_event["correlationId"] == SAMPLE_CORRELATION_ID
        assert published_event["source"] == "sensor-1"
        assert published_event["incidentType"] == "FIRE"
        assert published_event["severity"] == "HIGH"
        assert published_event["description"] == "Fire detected in sector 7"
        assert published_event["reportedAt"].endswith("Z")

    @real_patch("handlers.incidents.save_incident")
    def test_logs_publish_success_with_identifiers(self, mock_save_incident, mock_publisher, mock_logger, post_event):
        resp = lambda_handler(post_event, {})
        incident_id = json.loads(resp["body"])["incidentId"]
        mock_logger.info.assert_any_call(
            "Published IncidentReported event",
            extra={
                "incidentId": incident_id,
                "correlationId": SAMPLE_CORRELATION_ID,
                "eventId": "event-123",
            },
        )

    @real_patch("handlers.incidents.save_incident")
    def test_correlation_id_propagated_to_response_header(self, mock_save_incident, mock_publisher, mock_logger, post_event):
        resp = lambda_handler(post_event, {})
        assert resp["headers"]["x-correlation-id"] == SAMPLE_CORRELATION_ID

    @real_patch("handlers.incidents.save_incident")
    def test_invalid_json_body_returns_400(self, mock_save_incident, mock_publisher, mock_logger, post_event):
        post_event["body"] = "{ not valid json }"
        resp = lambda_handler(post_event, {})
        assert resp["statusCode"] == 400
        assert "Invalid JSON" in resp["body"]

    @real_patch("handlers.incidents.save_incident")
    def test_missing_required_fields_returns_400(self, mock_save_incident, mock_publisher, mock_logger, post_event):
        post_event["body"] = json.dumps({"source": "sensor-1"})
        resp = lambda_handler(post_event, {})
        assert resp["statusCode"] == 400

    @real_patch("handlers.incidents.save_incident")
    def test_null_body_treated_as_empty_object_returns_400(self, mock_save_incident, mock_publisher, mock_logger, post_event):
        post_event["body"] = None
        resp = lambda_handler(post_event, {})
        assert resp["statusCode"] == 400

    @real_patch("handlers.incidents.save_incident")
    def test_dynamodb_error_returns_500(self, mock_save_incident, mock_publisher, mock_logger, post_event):
        mock_save_incident.side_effect = Exception("DynamoDB unavailable")
        resp = lambda_handler(post_event, {})
        assert resp["statusCode"] == 500
        assert "Internal server error" in resp["body"]

    @real_patch("handlers.incidents.save_incident")
    def test_publish_error_returns_500(self, mock_save_incident, mock_publisher, mock_logger, post_event):
        mock_publisher.side_effect = RuntimeError("EventBridge unavailable")
        resp = lambda_handler(post_event, {})
        assert resp["statusCode"] == 500
        assert "Internal server error" in resp["body"]


# ---------------------------------------------------------------------------
# lambda_handler – GET
# ---------------------------------------------------------------------------

from unittest.mock import patch as real_patch

class TestLambdaHandlerGet:
    @real_patch("handlers.incidents.get_incident")
    def test_returns_200_with_incident_when_found(self, mock_get_incident, get_event, stored_item):
        mock_get_incident.return_value = stored_item
        resp = lambda_handler(get_event, {})
        assert resp["statusCode"] == 200
        body = json.loads(resp["body"])
        assert body["incidentId"] == SAMPLE_INCIDENT_ID
        assert body["source"] == "sensor-1"

    @real_patch("handlers.incidents.get_incident")
    def test_response_excludes_internal_keys(self, mock_get_incident, get_event, stored_item):
        mock_get_incident.return_value = stored_item
        resp = lambda_handler(get_event, {})
        body = json.loads(resp["body"])
        assert "pk" not in body
        assert "sk" not in body

    @real_patch("handlers.incidents.get_incident")
    def test_returns_404_when_incident_not_found(self, mock_get_incident, get_event):
        mock_get_incident.return_value = None
        resp = lambda_handler(get_event, {})
        assert resp["statusCode"] == 404

    def test_missing_path_parameter_returns_400(self, get_event):
        get_event["pathParameters"] = None
        resp = lambda_handler(get_event, {})
        assert resp["statusCode"] == 400

    def test_empty_path_parameters_returns_400(self, get_event):
        get_event["pathParameters"] = {}
        resp = lambda_handler(get_event, {})
        assert resp["statusCode"] == 400

    @real_patch("handlers.incidents.get_incident")
    def test_dynamodb_error_returns_500(self, mock_get_incident, get_event):
        mock_get_incident.side_effect = Exception("DynamoDB unavailable")
        resp = lambda_handler(get_event, {})
        assert resp["statusCode"] == 500

    @real_patch("handlers.incidents.get_incident")
    def test_correlation_id_propagated_to_response_header(self, mock_get_incident, get_event, stored_item):
        mock_get_incident.return_value = stored_item
        resp = lambda_handler(get_event, {})
        assert resp["headers"]["x-correlation-id"] == SAMPLE_CORRELATION_ID


# ---------------------------------------------------------------------------
# lambda_handler – unsupported HTTP methods
# ---------------------------------------------------------------------------

class TestLambdaHandlerUnsupportedMethods:
    @pytest.mark.parametrize("method", ["PUT", "PATCH", "DELETE", "OPTIONS"])
    def test_unsupported_method_returns_405(self, method):
        event = {"httpMethod": method, "headers": {}}
        resp = lambda_handler(event, {})
        assert resp["statusCode"] == 405
        assert "Method not allowed" in resp["body"]


class TestBuildIncidentReportedEvent:
    def test_builds_expected_payload(self):
        incident_item = {
            "incidentId": SAMPLE_INCIDENT_ID,
            "correlationId": SAMPLE_CORRELATION_ID,
            "source": "sensor-1",
            "incidentType": "FIRE",
            "severity": "HIGH",
            "description": "Fire detected in sector 7",
            "createdAt": 1000,
        }

        event = build_incident_reported_event(incident_item)

        assert event == {
            "eventType": "IncidentReported",
            "incidentId": SAMPLE_INCIDENT_ID,
            "correlationId": SAMPLE_CORRELATION_ID,
            "source": "sensor-1",
            "incidentType": "FIRE",
            "severity": "HIGH",
            "description": "Fire detected in sector 7",
            "reportedAt": "1970-01-01T00:16:40Z",
        }
