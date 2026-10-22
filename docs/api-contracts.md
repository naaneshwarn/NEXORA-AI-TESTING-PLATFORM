# NEXORA API contracts (v1)

The FastAPI foundation exposes a versioned API at `/api/v1` and uses a consistent JSON envelope for both success and failure responses.

## Response Envelope

All API endpoints encapsulate responses in a standard JSON envelope:

### Success Response
```json
{
  "success": true,
  "data": { ... },
  "error": null
}
```

### Error Response
```json
{
  "success": false,
  "data": null,
  "error": {
    "code": "validation_error",
    "message": "Request validation failed",
    "details": {
      "errors": [
        {
          "loc": ["body", "name"],
          "msg": "Field required",
          "type": "missing"
        }
      ]
    }
  }
}
```

Standard Error Codes:
- `validation_error` (422) – Request body or query parameters failed schema validation
- `not_found` (404) – The requested resource (agent, run, environment, report) was not found
- `conflict` (409) – A resource with the specified identifier already exists
- `invalid_state_transition` (400) – An illegal lifecycle transition was requested (e.g. cancelling a completed run)
- `internal_server_error` (500) – An unhandled internal server error occurred (stack traces are masked in production)

---

## Health & Discovery Endpoints

| Method | Path | Request | Response | Status codes | Description |
| --- | --- | --- | --- | --- | --- |
| GET | `/health` | none | `HealthResponse` | 200 | Root health endpoint |
| GET | `/api/v1/health` | none | `HealthResponse` | 200 | Versioned API health status |
| GET | `/docs` | none | HTML | 200 | Swagger UI interactive documentation |
| GET | `/redoc` | none | HTML | 200 | ReDoc documentation |
| GET | `/openapi.json` | none | OpenAPI JSON | 200 | Machine-readable OpenAPI 3.1 specification |

---

## Phase 2 Contracts

### 1. Register and Manage Target AI Agents

| Method | Path | Request schema | Response schema | Status codes | Description |
| --- | --- | --- | --- | --- | --- |
| POST | `/api/v1/agents` | `AgentConfig` | `ApiEnvelope[AgentConfig]` | 201, 409, 422 | Register agent (auto-generates `agent_id` if omitted; redacts secrets) |
| GET | `/api/v1/agents` | none | `ApiEnvelope[list[AgentConfig]]` | 200 | List all registered agents |
| GET | `/api/v1/agents/{agent_id}` | none | `ApiEnvelope[AgentConfig]` | 200, 404 | Retrieve an agent by ID (secrets redacted) |

`AgentConfig` Schema:
```python
class AgentConfig(BaseModel):
    agent_id: str | None = None  # Auto-generated (agent-xxxxxxxx) if omitted
    name: str                    # Required
    role: Literal["planner", "executor", "observer", "reporter"]
    model: str | None = None
    provider: str | None = None
    endpoint: str | None = None
    status: Literal["registered", "active", "disabled"] = "registered"
    config: dict[str, Any] = {}  # Keys like api_key, token, password are auto-redacted in responses
    created_at: datetime | None = None
```

### 2. Test-Run Orchestration & Trace Events

| Method | Path | Request schema | Response schema | Status codes | Description |
| --- | --- | --- | --- | --- | --- |
| POST | `/api/v1/test-runs` | `RunCreateRequest` | `ApiEnvelope[RunDetail]` | 201, 404, 422 | Create run (validates target agents exist) |
| GET | `/api/v1/test-runs` | none | `ApiEnvelope[list[RunDetail]]` | 200 | List all recorded test runs |
| GET | `/api/v1/test-runs/{run_id}` | none | `ApiEnvelope[RunDetail]` | 200, 404 | Retrieve run status and detail |
| POST | `/api/v1/test-runs/{run_id}/cancel` | none | `ApiEnvelope[ExecutionStatus]` | 200, 400, 404 | Cancel queued/running run (400 if already terminal) |
| GET | `/api/v1/test-runs/{run_id}/events` | none | `ApiEnvelope[list[ExecutionEvent]]` | 200, 404 | Retrieve chronological execution events |

`RunCreateRequest` Schema:
```python
class RunCreateRequest(BaseModel):
    suite_name: str
    scenario: ScenarioConfig | None = None
    environment: str = "local"
    tags: list[str] = []
    target_agents: list[str] = []
    config: dict[str, Any] = {}  # Set allow_mock: True to bypass target agent existence check
```

`RunDetail` Schema:
```python
class RunDetail(BaseModel):
    run_id: str
    suite_name: str
    environment: str
    state: Literal["queued", "running", "passed", "failed", "cancelled"] = "queued"
    target_agents: list[str]
    created_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    message: str | None = None
```

### 3. Request Synthetic Environment & Lifecycle

| Method | Path | Request schema | Response schema | Status codes | Description |
| --- | --- | --- | --- | --- | --- |
| POST | `/api/v1/environments` | `SyntheticEnvironmentRequest` | `ApiEnvelope[SyntheticEnvironment]` | 201, 422 | Provision environment request (`endpoint=null` until Docker confirms) |
| GET | `/api/v1/environments` | none | `ApiEnvelope[list[SyntheticEnvironment]]` | 200 | List tracked environments |
| GET | `/api/v1/environments/{environment_id}` | none | `ApiEnvelope[SyntheticEnvironment]` | 200, 404 | Retrieve environment state |
| POST | `/api/v1/environments/{environment_id}/stop` | none | `ApiEnvelope[SyntheticEnvironment]` | 200, 404 | Idempotent stop and deprovisioning |

`SyntheticEnvironmentRequest` Schema:
```python
class SyntheticEnvironmentRequest(BaseModel):
    environment_type: Literal["postgres", "mysql", "mongodb", "redis", "neo4j", "docker"]
    label: str
    config: dict[str, Any] = {}
```

`SyntheticEnvironment` Schema:
```python
class SyntheticEnvironment(BaseModel):
    environment_id: str
    environment_type: Literal["postgres", "mysql", "mongodb", "redis", "neo4j", "docker"]
    label: str
    status: Literal["provisioning", "ready", "stopped", "failed", "cancelled"]
    endpoint: str | None = None
    metadata: dict[str, Any] = {}
    created_at: datetime | None = None
    updated_at: datetime | None = None
```

### 4. Evaluation Submission & Report Retrieval

| Method | Path | Request schema | Response schema | Status codes | Description |
| --- | --- | --- | --- | --- | --- |
| POST | `/api/v1/evaluations` | `EvaluationSubmission` | `ApiEnvelope[ReportSummary]` | 201, 404, 422 | Submit evaluation (validates `run_id` exists) |
| GET | `/api/v1/reports/{report_id}` | none | `ApiEnvelope[ReportSummary]` | 200, 404 | Retrieve report by report ID |
| GET | `/api/v1/reports/runs/{run_id}` | none | `ApiEnvelope[ReportSummary]` | 200, 404 | Retrieve report by test run ID |

`EvaluationSubmission` Schema:
```python
class EvaluationSubmission(BaseModel):
    run_id: str
    agent_id: str | None = None
    score: float = Field(default=0.0, ge=0.0, le=100.0)
    status: Literal["pass", "fail", "partial"] = "partial"
    summary: str
    metrics: dict[str, float] = {}
    issues: list[str] = []
```

`ReportSummary` Schema:
```python
class ReportSummary(BaseModel):
    report_id: str
    run_id: str
    score: float = Field(default=0.0, ge=0.0, le=100.0)
    status: Literal["generated", "partial", "failed"] = "generated"
    summary: str
    metrics: dict[str, float] = {}
    generated_at: datetime | None = None
```

---

## Shared Integration Interfaces (`backend/app/services/interfaces.py`)

Python protocols define concrete boundaries with teammates:
- `DockerLifecycleProtocol`: Rajath's Docker container engine integration
- `AgentAdapterProtocol`: Prajwal's target-agent communication adapter
- `WorkflowOrchestratorProtocol`: Rahul's LangGraph test-run workflow engine
- `EvaluatorProtocol`: Rahul's scoring and reporting benchmark engine

