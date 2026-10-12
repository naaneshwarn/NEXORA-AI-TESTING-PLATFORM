# NEXORA AI Testing Platform — Changes & Inspection Log

## 1. Branch & Context
- **Branch**: `feature/synthetic-api`
- **Latest Commit**: `9a1d71a` (*feat(adapters): implement protocol adapter layer, tool registry, and agent execution dispatcher*)
- **Upstream Base**: `25dab08` (*Publish NEXORA AI Testing Platform source code*)
- **Focus**:
  1. Synthetic Environment lifecycle state transitions (`provisioning` → `ready` → `stopped`) and `/ready` endpoint.
  2. Stateful synthetic CRM Lead management API (`/api/v1/leads`).
  3. Deterministic fault simulation and latency injection on CRM read endpoints.
  4. Protocol adapters for agent communication (`REST`, `OpenAI`, `LangChain`) via `/synthetic/agent/execute/{protocol}`.
  5. Agent profiling, tool-call telemetry with sensitive data redaction, and run trace retrieval (`/test-runs/{run_id}/traces`).

---

## 2. Summary of Changes

### A. In-Memory Store (`backend/app/core/store.py`)
1. **Added `update_environment`**:
   - Updates `updated_at` to the current UTC timestamp (`utc_now()`).
   - Persists the modified `SyntheticEnvironment` object into the `ENVIRONMENTS` store.
2. **Refactored `stop_environment`**:
   - Sets `env.status = "stopped"` and delegates timestamp refresh and persistence to `update_environment(env)`.
3. **Added `Store` Class & `store` Instance**:
   - Defines a `Store` class exposing package store helpers (`get_environment`, `update_environment`, `create_environment`, `stop_environment`, `register_agent`, `get_agent`, `create_test_run`, `get_test_run`, `cancel_test_run`, `get_events_for_run`, `submit_evaluation`, `get_report`).
   - Exports a singleton instance `store = Store()`.

### B. Environment Routes (`backend/app/api/routes/environments.py`)
1. **Added `mark_environment_ready` Endpoint**:
   - **Path**: `POST /api/v1/environments/{environment_id}/ready`
   - **Response Model**: `ApiEnvelope[SyntheticEnvironment]`
   - **Status Codes**:
     - `200 OK` on successful state transition to `"ready"`.
     - `404 Not Found` with standard error detail envelope (`{"message": f"Environment '{environment_id}' was not found."}`) if the environment does not exist.
   - **Behavior**: Retrieves environment via `get_environment(environment_id)`, updates status to `"ready"`, persists using `update_environment(env)`, and returns the wrapped `ApiEnvelope`.

---

## 3. Code Modifications (Git Diff)

```diff
diff --git a/backend/app/api/routes/environments.py b/backend/app/api/routes/environments.py
index da2a735..6950a5f 100644
--- a/backend/app/api/routes/environments.py
+++ b/backend/app/api/routes/environments.py
@@ -5,7 +5,7 @@ from uuid import uuid4
 
 from fastapi import APIRouter, HTTPException
 
-from app.core.store import create_environment, get_environment, stop_environment
+from app.core.store import create_environment, get_environment, stop_environment, update_environment
 from app.schemas.common import ApiEnvelope
 from app.schemas.environment import SyntheticEnvironment, SyntheticEnvironmentRequest
 
@@ -45,3 +45,22 @@ async def stop_environment_endpoint(environment_id: str) -> ApiEnvelope[Syntheti
 
     updated = stop_environment(environment_id)
     return ApiEnvelope(success=True, data=updated)
+
+
+@router.post("/environments/{environment_id}/ready", response_model=ApiEnvelope[SyntheticEnvironment])
+def mark_environment_ready(environment_id: str) -> ApiEnvelope[SyntheticEnvironment]:
+    env = get_environment(environment_id)
+    if not env:
+        raise HTTPException(
+            status_code=404,
+            detail={"message": f"Environment '{environment_id}' was not found."}
+        )
+
+    env.status = "ready"
+    update_environment(env)
+
+    return ApiEnvelope(
+        success=True,
+        data=env,
+        error=None
+    )
diff --git a/backend/app/core/store.py b/backend/app/core/store.py
index df6242f..73da563 100644
--- a/backend/app/core/store.py
+++ b/backend/app/core/store.py
@@ -94,11 +94,16 @@ def get_environment(environment_id: str) -> SyntheticEnvironment | None:
     return ENVIRONMENTS.get(environment_id)
 
 
+def update_environment(env: SyntheticEnvironment) -> SyntheticEnvironment:
+    env.updated_at = utc_now()
+    ENVIRONMENTS[env.environment_id] = env
+    return env
+
+
 def stop_environment(environment_id: str) -> SyntheticEnvironment:
     env = ENVIRONMENTS[environment_id]
     env.status = "stopped"
-    env.updated_at = utc_now()
-    return env
+    return update_environment(env)
 
 
 def submit_evaluation(payload: EvaluationSubmission) -> ReportSummary:
@@ -118,3 +123,21 @@ def submit_evaluation(payload: EvaluationSubmission) -> ReportSummary:
 
 def get_report(report_id: str) -> ReportSummary | None:
     return REPORTS.get(report_id)
+
+
+class Store:
+    get_environment = get_environment
+    update_environment = update_environment
+    create_environment = create_environment
+    stop_environment = stop_environment
+    register_agent = register_agent
+    get_agent = get_agent
+    create_test_run = create_test_run
+    get_test_run = get_test_run
+    cancel_test_run = cancel_test_run
+    get_events_for_run = get_events_for_run
+    submit_evaluation = submit_evaluation
+    get_report = get_report
+
+
+store = Store()
```

---

## 4. Verification & Live Endpoint Testing

### A. Live Server Lifecycle Verification
The full synthetic environment lifecycle was validated against the local Uvicorn development server:

1. **API Documentation**:
   - `GET /docs` → `200 OK`
   - `GET /openapi.json` → `200 OK`
2. **Environment Provisioning**:
   - `POST /api/v1/environments` → `201 Created`
   - Returns initial status `"provisioning"` and generated ID (e.g., `env-81333064`).
3. **Environment Retrieval**:
   - `GET /api/v1/environments/env-81333064` → `200 OK`
4. **Transition to Ready**:
   - `POST /api/v1/environments/env-81333064/ready` → `200 OK`
   - Confirms status transition to `"ready"`.
5. **Environment Teardown**:
   - `POST /api/v1/environments/env-81333064/stop` → `200 OK`
   - Confirms status transition to `"stopped"`.

### B. Automated Test Suite (Pytest)
- Ran: `python -m pytest`
- Result: **4 passed** in 0.72s (`test_api_contracts.py`, `test_health.py`).





### C. CRM Leads Schema and Routes (backend/app/schemas/crm.py, backend/app/api/routes/crm.py)
1. **Added CRM Lead Schemas (schemas/crm.py)**:
   - CRMLeadCreate: Defines lead creation fields (name with min_length=2, max_length=100, email, optional company, status with Literal values: new, contacted, qualified, closed).
   - CRMLeadResponse: Extends CRMLeadCreate with id, created_at, updated_at.

2. **Extended In-Memory Store (core/store.py)**:
   - Added CRM_LEADS state dictionary.
   - Added helper functions: create_crm_lead, get_crm_lead, list_crm_leads, update_crm_lead, delete_crm_lead.
   - Added corresponding methods to Store class.

3. **Added CRM Routes (backend/app/api/routes/crm.py)**:
   - POST /api/v1/leads (201) - Create lead
   - GET /api/v1/leads - List all leads
   - GET /api/v1/leads/{lead_id} - Get lead (404 if not found)
   - PUT /api/v1/leads/{lead_id} - Update lead (404 if not found)
   - DELETE /api/v1/leads/{lead_id} (204) - Delete lead (404 if not found)

4. **Registered CRM Router (backend/app/main.py)**:
   - Added import and app.include_router(crm_router, prefix=settings.api_prefix).

---

## 5. Fault Simulation & Resiliency Testing

### A. Objective
Allow agents under test to be exercised against network latency, rate limiting
(HTTP 429) and server failures (HTTP 500) using only the synthetic CRM surface.

### B. CRM Read Endpoints (`backend/app/api/routes/crm.py`)
1. **Added shared query parameters** (`simulated_latency_ms`, `inject_error`) to
   `GET /api/v1/leads` and `GET /api/v1/leads/{lead_id}`:
   - `simulated_latency_ms`: `0`-`60000`; injects a delay before responding.
   - `inject_error`: `400`-`599`; raises the requested HTTP error.
2. **Added `_apply_fault_injection` helper**:
   - Raises `HTTPException(inject_error)` first, matching the reference order.
   - Otherwise awaits `asyncio.sleep(simulated_latency_ms / 1000)`. A non-blocking
     sleep was chosen over `time.sleep` because the endpoints are `async` and a
     blocking call would stall the event loop for every concurrent request.
3. **Validation**: out-of-range codes (e.g. `inject_error=200`) are rejected with
   `422`, protecting against invalid `HTTPException` status codes.
4. **No state mutation**: injection occurs before store access, so faults are
   repeatable and never corrupt in-memory CRM state.

### C. Tests (`backend/tests/test_api_contracts.py`)
- Added `test_crm_fault_and_latency_injection` covering baseline reads, measurable
  latency, `429`/`500` injection on both endpoints, state recovery, and `422`
  rejection of out-of-range codes.

### D. Verification
- `python -m pytest` -> **5 passed** in 0.68s.
- `app.openapi()` confirms both parameters are documented on both read paths.
- **Live Uvicorn Server Verification** (`http://127.0.0.1:8000`):
  1. `POST /api/v1/leads` -> `201 Created`
  2. `GET /api/v1/leads/{lead_id}` -> `200 OK`
  3. `GET /api/v1/leads?inject_error=429` -> `429 Too Many Requests`

### E. Code Diff
```diff
--- a/backend/app/api/routes/crm.py
+++ b/backend/app/api/routes/crm.py
@@
-from fastapi import APIRouter, HTTPException
+import asyncio
+from typing import Annotated
+
+from fastapi import APIRouter, HTTPException, Query
@@
 router = APIRouter(tags=["crm"])
+
+SimulatedLatencyMs = Annotated[
+    int | None,
+    Query(ge=0, le=60_000, description="Inject a synthetic delay (in milliseconds) before responding."),
+]
+InjectError = Annotated[
+    int | None,
+    Query(ge=400, le=599, description="Simulate an HTTP error status (e.g. 429 rate limit, 500 server error)."),
+]
+
+
+async def _apply_fault_injection(
+    simulated_latency_ms: int | None,
+    inject_error: int | None,
+) -> None:
+    if inject_error is not None:
+        raise HTTPException(
+            status_code=inject_error,
+            detail={"message": f"Simulated fault triggered with error code {inject_error}"},
+        )
+    if simulated_latency_ms:
+        await asyncio.sleep(simulated_latency_ms / 1000.0)
@@
 @router.get("/leads", response_model=ApiEnvelope[list[CRMLeadResponse]])
-async def list_leads_endpoint() -> ApiEnvelope[list[CRMLeadResponse]]:
+async def list_leads_endpoint(
+    simulated_latency_ms: SimulatedLatencyMs = None,
+    inject_error: InjectError = None,
+) -> ApiEnvelope[list[CRMLeadResponse]]:
+    await _apply_fault_injection(simulated_latency_ms, inject_error)
     leads = list_crm_leads()
     return ApiEnvelope(success=True, data=leads)
@@
 @router.get("/leads/{lead_id}", response_model=ApiEnvelope[CRMLeadResponse])
-async def get_lead_endpoint(lead_id: str) -> ApiEnvelope[CRMLeadResponse]:
+async def get_lead_endpoint(
+    lead_id: str,
+    simulated_latency_ms: SimulatedLatencyMs = None,
+    inject_error: InjectError = None,
+) -> ApiEnvelope[CRMLeadResponse]:
+    await _apply_fault_injection(simulated_latency_ms, inject_error)
     lead = get_crm_lead(lead_id)
```

---

## 6. Protocol Adapters for Agent Communication (Phase 3)

### A. Objective
Normalize requests and responses between external AI agents (REST and
OpenAI/LangChain function calling) and the internal synthetic APIs through a
modular, registry-driven adapter layer.

### B. New Modules
1. `backend/app/core/adapters.py`
   - Unified models: `AgentToolRequest` (`call_id`, `tool_name`, `parameters`, `agent_id`) and `AgentToolResponse` (`call_id`, `success`, `data`, `error`, `execution_time_ms`).
   - `BaseProtocolAdapter` abstract base with `parse_request()` and `format_response()`.
   - `RESTProtocolAdapter` and `OpenAIFunctionAdapter` implementations.
   - `AdapterFactory` registry with `get_adapter(protocol_type)` defaulting to `rest`.
2. `backend/app/core/tools.py`
   - `TOOL_REGISTRY` mapping CRM tool names/aliases to store operations.
   - `execute_synthetic_tool()` plus `ToolNotFoundError` / `ToolExecutionError`.
3. `backend/app/api/routes/agent_execution.py`
   - `POST /api/v1/synthetic/agent/execute/{protocol}` dispatcher.

### C. Behavior
- `RESTProtocolAdapter` accepts `tool_name`/`tool`/`name` and `parameters`/`params`/`arguments`; returns the normalized response as a flat dict.
- `OpenAIFunctionAdapter` accepts `{"function": {"name", "arguments"}}` (arguments may be a dict or a JSON-encoded string) and emits an OpenAI tool message (`{"role": "tool", "tool_call_id", "content"}`) whose `content` is a JSON string of the normalized result.
- `AdapterFactory` registers `rest` (default), `openai`, `openai_function`, `function`, and `langchain`; unknown protocols raise `UnknownProtocolError`, mapped to HTTP `400`.
- The dispatcher parses via the adapter, executes the tool while timing it (`execution_time_ms`), and re-formats the result. All parse/execution exceptions are captured and normalized (`invalid_request`, `tool_not_found`, `tool_execution_error`, `execution_error`) so a raw `500` never reaches the agent.

### D. Registration
- `backend/app/main.py` includes the execution router under `settings.api_prefix`, exposing `/api/v1/synthetic/agent/execute/{protocol}`.

### E. Tests
- `backend/tests/test_protocol_adapters.py` (7 tests) covers adapter round trips, factory defaults/aliases, REST execution, OpenAI tool-message formatting, unknown tools, malformed payloads, and unknown protocols.

### F. Verification
- `python -m pytest` -> **12 passed**.

---

## 7. Agent Profiling, Tool-Call Tracing & Sensitive Data Redaction (Phase 3)

### A. Objective
Capture per-tool execution telemetry for agent runs while guaranteeing secrets
never enter persisted traces.

### B. New Schemas
- `backend/app/schemas/tracing.py`
  - `ToolCallTraceCreate`: `run_id`, `call_id`, `tool_name`, `parameters`, `success`, `result`, `error`, `execution_time_ms`.
  - `ToolCallTraceResponse`: extends `ToolCallTraceCreate` with `timestamp`.

### C. Sensitive Data Redaction
- `backend/app/core/redaction.py`
  - `redact_sensitive_data()` recursively processes dictionaries, lists/tuples and strings.
  - Dict keys matching normalized sensitive names (`password`, `token`, `api_key`, `secret`, `authorization`, `credit_card`, ...) have their values replaced with `"[REDACTED]"`.
  - Inline secrets scrubbed via regex: Bearer/Basic authorization tokens, `key=value` / `key: value` assignments, OpenAI `sk-...` keys, AWS access key IDs, and JWTs.

### D. Store Extensions
- `backend/app/core/store.py`
  - `TOOL_TRACES: dict[str, list[dict]]`.
  - `record_tool_trace(run_id, trace_data)` appends a trace stamped with a generated UTC timestamp.
  - `get_traces_for_run(run_id)` returns the recorded traces.
  - Both helpers are surfaced on the `Store` singleton.

### E. Execution Wrapper
- `backend/app/core/telemetry.py`
  - `execute_and_trace_tool(run_id, call_id, tool_name, parameters, executor=None)` is async; times with `time.perf_counter()`, supports sync or async executors, classifies exceptions (`tool_not_found`, `tool_execution_error`, `invalid_request`, `execution_error`), redacts parameters/results/errors, and persists via `record_tool_trace`.
  - Returns a `ToolExecutionOutcome` carrying the raw `data`/`error` for the agent plus the sanitized `trace`.

### F. API Integration
- `POST /api/v1/synthetic/agent/execute/{protocol}` accepts an optional `run_id` query parameter; when supplied (and the run exists) the execution is traced.
- `GET /api/v1/test-runs/{run_id}/traces` returns `ApiEnvelope[list[ToolCallTraceResponse]]` (`404` when no traces exist).

### G. Tests
- `backend/tests/test_tracing.py` (6 tests): recursive redaction, inline secret scrubbing, wrapper success/failure telemetry, end-to-end dispatcher -> traces, and missing-record handling.

### H. Verification
- `python -m pytest` -> **18 passed**.
- Manual check: an `api_key` parameter is stored as `"[REDACTED]"` in the trace with a UTC `timestamp`.

### I. Code Modifications (Git Diff)

```diff
diff --git a/backend/app/api/routes/agent_execution.py b/backend/app/api/routes/agent_execution.py
--- a/backend/app/api/routes/agent_execution.py
+++ b/backend/app/api/routes/agent_execution.py
@@ -4,10 +4,11 @@ import time
 from typing import Any
 from uuid import uuid4
 
-from fastapi import APIRouter, Body, HTTPException
+from fastapi import APIRouter, Body, HTTPException, Query
 
 from app.core.adapters import AdapterFactory, AgentToolResponse, UnknownProtocolError
-from app.core.tools import ToolExecutionError, ToolNotFoundError, execute_synthetic_tool
+from app.core.store import get_test_run
+from app.core.telemetry import execute_and_trace_tool
 
 router = APIRouter(tags=["synthetic-agent"])
@@ -28,7 +29,10 @@ async def execute_agent_tool_endpoint(
     protocol: str,
+    run_id: str | None = Query(default=None, description="Test run to attach tool-call telemetry to."),
     payload: dict[str, Any] | None = Body(default=None),
 ) -> dict[str, Any]:
+    if run_id is not None and get_test_run(run_id) is None:
+        raise HTTPException(status_code=404, detail={"message": f"Test run '{run_id}' was not found."})
+    ...
+    outcome = await execute_and_trace_tool(run_id, request.call_id, request.tool_name, request.parameters)
+    ...
diff --git a/backend/app/api/routes/test_runs.py b/backend/app/api/routes/test_runs.py
--- a/backend/app/api/routes/test_runs.py
+++ b/backend/app/api/routes/test_runs.py
@@ -48,3 +55,11 @@ async def get_test_run_events_endpoint(run_id: str) -> ApiEnvelope[list[Executio
+@router.get("/test-runs/{run_id}/traces", response_model=ApiEnvelope[list[ToolCallTraceResponse]])
+async def get_test_run_traces_endpoint(run_id: str) -> ApiEnvelope[list[ToolCallTraceResponse]]:
+    traces = get_traces_for_run(run_id)
+    if not traces:
+        raise HTTPException(status_code=404, detail={"message": f"No tool traces were found for run '{run_id}'."})
+    return ApiEnvelope(success=True, data=traces)
diff --git a/backend/app/core/store.py b/backend/app/core/store.py
--- a/backend/app/core/store.py
+++ b/backend/app/core/store.py
@@ -14,6 +14,7 @@
+TOOL_TRACES: dict[str, list[dict]] = {}
+
+def record_tool_trace(run_id: str, trace_data: dict) -> dict:
+    trace = {**trace_data, "run_id": run_id, "timestamp": utc_now().isoformat()}
+    TOOL_TRACES.setdefault(run_id, []).append(trace)
+    return trace
+
+def get_traces_for_run(run_id: str) -> list[dict]:
+    return TOOL_TRACES.get(run_id, [])
```

