import os
import uuid

import boto3
import pytest
import requests

"""
Make sure env variable AWS_SAM_STACK_NAME exists with the name of the stack we are going to test. 
"""


class TestApiGateway:

    @pytest.fixture()
    def api_gateway_url(self):
        """ Get the API Gateway URL from Cloudformation Stack outputs """
        stack_name = os.environ.get("AWS_SAM_STACK_NAME")

        if stack_name is None:
            raise ValueError('Please set the AWS_SAM_STACK_NAME environment variable to the name of your stack')

        client = boto3.client("cloudformation")

        try:
            response = client.describe_stacks(StackName=stack_name)
        except Exception as e:
            raise Exception(
                f"Cannot find stack {stack_name} \n" f'Please make sure a stack with the name "{stack_name}" exists'
            ) from e

        stacks = response["Stacks"]
        stack_outputs = stacks[0]["Outputs"]
        api_outputs = [output for output in stack_outputs if output["OutputKey"] == "IncidentsApiEndpoint"]

        if not api_outputs:
            raise KeyError(f"IncidentsApiEndpoint not found in stack {stack_name}")

        return api_outputs[0]["OutputValue"]  # Extract url from stack outputs

    def test_create_and_get_incident(self, api_gateway_url):
        """Create an incident through API Gateway and fetch it back."""
        payload = {
            "source": f"sensor-{uuid.uuid4()}",
            "incidentType": "airlock",
            "severity": "critical",
            "description": "Pressure anomaly detected near Bay 3",
        }

        create_response = requests.post(api_gateway_url, json=payload, timeout=10)
        assert create_response.status_code == 201

        create_body = create_response.json()
        assert "incidentId" in create_body

        incident_id = create_body["incidentId"]
        get_response = requests.get(f"{api_gateway_url}/{incident_id}", timeout=10)

        assert get_response.status_code == 200

        body = get_response.json()
        assert body["incidentId"] == incident_id
        assert body["source"] == payload["source"]
        assert body["incidentType"] == payload["incidentType"]
        assert body["severity"] == payload["severity"]
        assert body["description"] == payload["description"]
        assert body["status"] == "REPORTED"

    def test_create_incident_validation_error(self, api_gateway_url):
        """Posting an incomplete incident returns a validation error."""
        response = requests.post(
            api_gateway_url,
            json={"source": "sensor-1"},
            timeout=10,
        )

        assert response.status_code == 400
        assert response.json() == {"message": "Missing required fields: incidentType, severity"}
