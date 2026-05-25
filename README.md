# Medina Incident Router

Medina Incident Router is a small AWS serverless backend that demonstrates Pub/Sub architecture through a space-station incident workflow inspired by Medina Station from The Expanse.

The system receives incidents through an HTTP API, publishes domain events to EventBridge, routes them to multiple consumers, and applies a conservative fallback strategy when automated decisioning is unavailable, delayed, or inconclusive.

This project is designed as a one-week solo build to demonstrate:

- Event-driven backend design
- Pub/Sub patterns with fan-out consumers
- Idempotency, retries, and conservative fallback behavior
- Observability and state tracking in a serverless architecture

## Table of Contents

- Domain
- Architecture
- Event Catalog
- API
- Incident Lifecycle & Data Model
- Engineering Concerns
- Development & Deployment
- Testing
- Cleanup
- Resources

---

## Domain

Medina Incident Router models critical incidents on Medina Station.

**Incident types:**  
- `airlock`, `radiation`, `fire`, `intrusion`

**Severity levels:**  
- `low`, `high`, `critical`

**Incident sources:**  
- Docking bay sensors, life support monitors, maintenance terminals, security subsystems

**Automated decision outcomes:**  
- `dispatch`: send response teams immediately  
- `monitor`: keep the incident under observation  
- `no-decision`: insufficient confidence, escalate conservatively

A core rule: if the automated decision service fails, times out, or cannot decide, the system escalates the incident for manual intervention.

---

## Architecture

1. **API Gateway** receives HTTP commands.
2. **Command Lambda** validates requests, applies idempotency checks, stores initial incident state.
3. **EventBridge** receives domain events and routes them to consumers.
4. **Consumer Lambdas** update incident state, simulate automated decisioning, and trigger escalation when needed.
5. **DynamoDB** stores incident state, processing markers, and idempotency records.

**AWS Services Used:**
- API Gateway
- Lambda
- EventBridge
- DynamoDB
- CloudWatch

---

## Event Catalog

### API Commands

- `POST /incidents`
- `POST /incidents/{id}/ack`
- `GET /incidents/{id}`

### Core Domain Events

- `IncidentReported`
- `IncidentAcknowledged`
- `IncidentDispatched`
- `IncidentMonitored`
- `IncidentNoDecision`
- `IncidentEscalated`

### Internal Workflow Event

- `IncidentDecisionRequested`

**Example event payload:**
```json
{
  "eventType": "IncidentReported",
  "incidentId": "inc_01",
  "correlationId": "corr_01",
  "source": "docking-bay-sensor",
  "incidentType": "airlock",
  "severity": "critical",
  "reportedAt": "2026-05-20T10:15:00Z"
}
```

---

## API

### `POST /incidents`
Creates a new incident and publishes `IncidentReported`.

**Example request:**
```json
{
  "source": "docking-bay-sensor",
  "incidentType": "airlock",
  "severity": "critical",
  "description": "Pressure anomaly detected near Bay 3"
}
```

### `POST /incidents/{id}/ack`
Acknowledges an incident and publishes `IncidentAcknowledged`.

### `GET /incidents/{id}`
Returns the current incident state from DynamoDB.

---


## Happy Path

A typical successful flow looks like this:

1. A client reports a critical incident through `POST /incidents`.
2. The command Lambda validates the request, applies idempotency checks, stores the initial incident state in DynamoDB, and publishes `IncidentReported`.
3. EventBridge fans out the event to a projection consumer and a decision consumer.
4. The decision consumer evaluates the incident and emits `IncidentDispatched` or `IncidentMonitored`.
5. The projection consumer updates the incident state in DynamoDB.
6. A client calls `GET /incidents/{id}` and sees the incident in its final state.

---

## Failure Path

A typical conservative failure flow looks like this:

1. A client reports an incident.
2. The command Lambda stores the initial incident state and publishes `IncidentReported`.
3. The decision consumer fails, times out, or returns insufficient confidence.
4. The system emits `IncidentNoDecision`.
5. An escalation consumer publishes `IncidentEscalated` with an explicit escalation reason such as `decision-timeout`, `consumer-failure`, or `no-decision`.
6. The projection consumer marks the incident as requiring manual intervention.
7. A client calls `GET /incidents/{id}` and sees the incident marked as escalated.

This is an intentional design choice. The system should prefer conservative escalation over unsafe automation.

---

## Incident Lifecycle & Data Model

**Incident states:**
- `REPORTED`
- `ACKNOWLEDGED`
- `DISPATCHED`
- `MONITORED`
- `ESCALATED`

**Incident state item example:**
- `pk`: `INCIDENT#<incidentId>`
- `sk`: `STATE`
- `incidentId`, `status`, `incidentType`, `severity`, `source`, `description`, `decision`, `escalationReason`, `statusReason`, `createdAt`, `updatedAt`, `correlationId`

**Idempotency item example:**
- `pk`: `IDEMPOTENCY#<idempotencyKey>`
- `sk`: `REQUEST`
- `createdAt`, `ttl`

**Event processing marker example:**
- `pk`: `EVENT#<eventId>`
- `sk`: `PROCESSED#<consumerName>`
- `processedAt`

---

## Engineering Concerns

- **Idempotency:** Safe under retries and duplicate delivery using DynamoDB conditional writes and processing markers.
- **At-least-once delivery:** Consumers tolerate duplicate events.
- **Conservative fallback:** Escalate if automation is unavailable or inconclusive.
- **Observability:** Correlation IDs and structured logs for traceability.
- **Small, explicit event contracts:** Avoid vague or overgrown schemas.

---

## Development & Deployment

This project uses the AWS Serverless Application Model (SAM) for infrastructure as code and deployment.

### Prerequisites

- [SAM CLI](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/serverless-sam-cli-install.html)
- [Python 3](https://www.python.org/downloads/)
- [Docker](https://hub.docker.com/search/?type=edition&offering=community)

### Build and Deploy

```bash
sam build --use-container
sam deploy --guided
```

- **Stack Name:** Unique name for your CloudFormation stack.
- **AWS Region:** Region to deploy your app.
- **IAM Role Creation:** Allow if prompted.
- **Save arguments:** Recommended for future deployments.

After deployment, your API Gateway endpoint URL will be displayed in the output.

### Local Development

Build your application:

```bash
sam build --use-container
```

Run a function locally with a test event:

```bash
sam local invoke <FunctionName> --event events/incident-reported.json
```

Start the local API:

```bash
sam local start-api
curl http://localhost:3000/
```

---

## Testing

Install test dependencies and run tests:

```bash
pip install -r tests/requirements.txt --user
# Unit tests
python -m pytest tests/unit -v
# Integration tests (requires deployed stack)
AWS_SAM_STACK_NAME="medina-incident-router" python -m pytest tests/integration -v
```

---

## Cleanup

To delete the deployed application:

```bash
sam delete --stack-name "medina-incident-router"
```

---

## Resources

- [AWS SAM developer guide](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/what-is-sam.html)
- [AWS Serverless Application Repository](https://aws.amazon.com/serverless/serverlessrepo/)
- [AWS Toolkit for VS Code](https://docs.aws.amazon.com/toolkit-for-vscode/latest/userguide/welcome.html)

---

## Project Status

The code is working, but does not include:

- authentication and authorization
- real AI processing
- full production security hardening
- advanced dashboards and alerting
- complex orchestration engines
- frontend UI

The code is partially refactored, code is being moved from lambda_handlers to service files for separation of concerns and easier testing.

The project needs unit tests and integration tests (these are currently outdated).
