# NEXORA API contracts (v1)

The FastAPI foundation exposes a versioned API at `/api/v1` and uses a consistent JSON envelope for both success and failure responses.

## Response envelope

Success responses follow this shape:

```json
{
  "success": true,
  "data": { ... },
  "error": null
}
```

Error responses follow this shape:

```json
{
  "success": false,
  "error": {
    "code": "validation_error",
    "message": "Request validation failed",
    "details": {
      "errors": [
        {
          "loc": ["body", "agent_id"],
          "msg": "Field required",
          "type": "missing"
        }
      ]
    }
  }
}
```

## Health endpoint

| Method | Path | Request | Response | Status codes | Responsible module |
| --- | --- | --- | --- | --- | --- |
| GET | `/api/v1/health` | none | `HealthResponse` | 200 | Naaneshwar |

## Phase 2 contracts

### 1. Register and configure a target AI agent

| Method | Path | Request schema | Response schema | Status codes | Responsible module |
| --- | --- | --- | --- | --- | --- |
| POST | `/api/v1/agents` | `AgentConfig` | `ApiEnvelope[AgentConfig]` | 201, 409, 422 | Naaneshwar |
| GET | `/api/v1/agents/{agent_id}` | none | `ApiEnvelope[AgentConfig]` | 200, 404 | Naaneshwar |

`AgentConfig` fields:

```python
class AgentConfig(BaseModel):
    agent_id: str
    name: str
    role: Literal["planner", "executor", "observer", "reporter"]
    model: str | None = None
    provider: str | None = None
    endpoint: str | None = None
    status: Literal["registered", "active", "disabled"] = "registered"
    config: dict[str, Any] = {}
    created_at: datetime | None = None
```

### 2. Create a test run using a scenario configuration

| Method | Path | Request schema | Response schema | Status codes | Responsible module |
| --- | --- | --- | --- | --- | --- |
| POST | `/api/v1/test-runs` | `RunCreateRequest` | `ApiEnvelope[RunDetail]` | 201, 422 | Rahul |
| GET | `/api/v1/test-runs/{run_id}` | none | `ApiEnvelope[RunDetail]` | 200, 404 | Rahul |
| POST | `/api/v1/test-runs/{run_id}/cancel` | none | `ApiEnvelope[ExecutionStatus]` | 200, 404 | Rahul |

`RunCreateRequest` fields:

```python
class RunCreateRequest(BaseModel):
    suite_name: str
    scenario: ScenarioConfig | None = None
    environment: str = "local"
    tags: list[str] = []
    target_agents: list[str] = []
    config: dict[str, Any] = {}
```

`RunDetail` fields:

```python
class RunDetail(BaseModel):
    run_id: str
    suite_name: str
    environment: str
    state: Literal["queued", "running", "passed", "failed", "cancelled"]
    target_agents: list[str]
    created_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    message: str | None = None
```

### 3. Request a synthetic environment and track lifecycle

| Method | Path | Request schema | Response schema | Status codes | Responsible module |
| --- | --- | --- | --- | --- | --- |
| POST | `/api/v1/environments` | `SyntheticEnvironmentRequest` | `ApiEnvelope[SyntheticEnvironment]` | 201, 422 | Rajath |
| GET | `/api/v1/environments/{environment_id}` | none | `ApiEnvelope[SyntheticEnvironment]` | 200, 404 | Rajath |
| POST | `/api/v1/environments/{environment_id}/stop` | none | `ApiEnvelope[SyntheticEnvironment]` | 200, 404 | Rajath |

`SyntheticEnvironmentRequest` fields:

```python
class SyntheticEnvironmentRequest(BaseModel):
    environment_type: Literal["postgres", "mysql", "mongodb", "redis", "neo4j", "docker"]
    label: str
    config: dict[str, Any] = {}
```

`SyntheticEnvironment` fields:

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

### 4. Execution events and tool-call traces

| Method | Path | Request schema | Response schema | Status codes | Responsible module |
| --- | --- | --- | --- | --- | --- |
| GET | `/api/v1/test-runs/{run_id}/events` | none | `ApiEnvelope[list[ExecutionEvent]]` | 200, 404 | Prajwal |

`ExecutionEvent` fields:

```python
class ExecutionEvent(BaseModel):
    event_id: str
    run_id: str
    event_type: Literal["created", "started", "heartbeat", "tool_call", "result", "error", "completed"]
    sequence: int
    message: str
    payload: dict[str, Any] = {}
    timestamp: datetime | None = None
    tool_calls: list[ToolCallTrace] = []
```

`ToolCallTrace` fields:

```python
class ToolCallTrace(BaseModel):
    call_id: str
    tool_name: str
    status: Literal["started", "success", "failed"]
    payload: dict[str, Any] = {}
```

### 5. Submit evaluation results and retrieve final report

| Method | Path | Request schema | Response schema | Status codes | Responsible module |
| --- | --- | --- | --- | --- | --- |
| POST | `/api/v1/evaluations` | `EvaluationSubmission` | `ApiEnvelope[ReportSummary]` | 201, 422 | Rahul |
| GET | `/api/v1/reports/{report_id}` | none | `ApiEnvelope[ReportSummary]` | 200, 404 | Rahul |

`EvaluationSubmission` fields:

```python
class EvaluationSubmission(BaseModel):
    run_id: str
    agent_id: str | None = None
    score: float = Field(ge=0, le=100)
    status: Literal["pass", "fail", "partial"]
    summary: str
    metrics: dict[str, float] = {}
    issues: list[str] = []
```

`ReportSummary` fields:

```python
class ReportSummary(BaseModel):
    report_id: str
    run_id: str
    score: float
    status: Literal["generated", "partial", "failed"]
    summary: str
    metrics: dict[str, float] = {}
    generated_at: datetime | None = None
```

## Phase 3 workflow contracts (Work Package D — Rahul)

These endpoints are additive. The Phase 2 contracts above are unchanged: `POST /api/v1/test-runs` still returns `201` with `state: "queued"`, and `GET /api/v1/reports/{report_id}` still serves `ReportSummary`.

### 6. Execute a queued workflow run on demand

| Method | Path | Request schema | Response schema | Status codes | Responsible module |
| --- | --- | --- | --- | --- | --- |
| POST | `/api/v1/test-runs/{run_id}/execute` | none | `ApiEnvelope[RunDetail]` | 200, 404, 409 | Rahul |

Behavior:

- Runs the registered scenario through the deterministic workflow engine and returns the terminal `RunDetail` (`passed` / `failed` / `cancelled`).
- `404` — the run does not exist.
- `409` — the run is not in the `queued` state (including runs that already auto-executed), or its scenario name is not registered in `app/workflow/scenarios.py`. The `409` body lists the registered scenario ids so callers can self-correct.
- Auto-execution note: `POST /api/v1/test-runs` schedules this same execution as a FastAPI `BackgroundTasks` job **only** when `scenario.name` matches a registered scenario id. Unknown or missing scenarios keep the legacy `queued` behavior asserted by the Phase 2 contract tests.

### 7. Retrieve the rich workflow report for a run

| Method | Path | Request schema | Response schema | Status codes | Responsible module |
| --- | --- | --- | --- | --- | --- |
| GET | `/api/v1/test-runs/{run_id}/report` | none | `ApiEnvelope[WorkflowReport]` | 200, 404 | Rahul |

`WorkflowReport` fields (schema: `backend/app/schemas/workflow_report.py`):

```python
class CriterionScore(BaseModel):
    criterion: Literal["task_completion", "factual_correctness", "trace_integrity"]
    weight: float          # 40 / 40 / 20
    score: float           # 0-100
    rationale: str

class Finding(BaseModel):
    severity: Literal["info", "warning", "critical"]
    code: str              # e.g. unsupported_fact, secret_leak, tool_error
    message: str
    evidence_ref: str | None = None   # tool-call id, never raw secret material

class ReportEvidence(BaseModel):
    scenario_id: str
    agent_ids: list[str]
    tool_call_ids: list[str]
    event_ids: list[str]

class WorkflowReport(BaseModel):
    report_id: str
    run_id: str
    scenario_id: str
    status: Literal["pass", "fail"]
    score: float                       # weighted total, 0-100
    pass_threshold: float              # per-run config, default 70.0
    summary: str
    criteria: list[CriterionScore]
    findings: list[Finding]
    evidence: ReportEvidence
    workflow_state: str                # terminal graph state
    duration_ms: float
    generated_at: datetime | None = None
```

Evaluation rules (implemented in `backend/app/workflow/evaluator.py`):

- Weighted score = `task_completion * 0.40 + factual_correctness * 0.40 + trace_integrity * 0.20`.
- `pass` requires `score >= pass_threshold` **and** zero `critical` findings — a critical finding (e.g. a secret leak or an unsupported fact) always forces `fail`, regardless of score.
- Invalid `config.pass_threshold` (non-numeric or outside 0–100) fails the run before evaluation with a clear `pass_threshold` message and publishes no report (`GET .../report` → `404`).
- All secrets supplied through `scenario.variables` are redacted before storage; reports, traces, and events never contain raw secret values.

Compatibility with the Phase 2 report surface: publishing a workflow run also writes a `ReportSummary` projection into the existing `REPORTS` store, so `GET /api/v1/reports/{report_id}` keeps working for workflow runs (`score`, `run_id`, `summary` are mirrored; the rich detail lives only behind `/test-runs/{run_id}/report`).

## Shared contract decisions pending team approval

- Whether run lifecycle should expose a richer state machine beyond queued/running/passed/failed/cancelled.
- Whether report scoring should be bounded to 0-100 or use a different domain-specific scale for security and input validation tasks.
- Whether environment provisioning should return a concrete endpoint or only a lifecycle identifier initially.
- Whether tool-call traces should be streamed in real time or retrieved via paged query endpoints.

The current contract is intentionally minimal and intentionally does not claim integration with live LLM providers, Neo4j, Redis, or remote infrastructure.
