# NEXORA AI Testing Platform — Changes & Inspection Log

## 1. Branch & Context
- **Branch**: `feature/synthetic-api`
- **Latest Commit**: `872a7d5` (*feat(tracing): verify live protocol execution dispatcher and redacted tool-call telemetry*)
- **Upstream Base**: `25dab08` (*Publish NEXORA AI Testing Platform source code*)
- **Date**: October 13, 2026
- **Focus**:
  1. Synthetic Environment lifecycle state transitions (`provisioning` → `ready` → `stopped`) and `/ready` endpoint.
  2. Stateful synthetic CRM Lead management API (`/api/v1/leads`).
  3. Deterministic fault simulation and latency injection on CRM read endpoints (`simulated_latency_ms`, `inject_error`).
  4. Protocol adapters for agent communication (`REST`, `OpenAI`, `LangChain`) via `/synthetic/agent/execute/{protocol}`.
  5. Agent profiling, tool-call telemetry with sensitive data redaction, and run trace retrieval (`/test-runs/{run_id}/traces`).
  6. Comprehensive automated test suite expansion (25 tests passing across 5 modules) and end-to-end integration verification.
  7. Execution event-system integration for profiled tool calls (`tool_call` events on `/test-runs/{run_id}/events`).
  8. Focused synthetic CRM contract coverage (`tests/test_crm.py`, 5 tests) for CRUD, validation, 404 envelopes, query boundaries, and repeated operations.

---

## 2. Comprehensive Summary of Changes

### A. Synthetic Environment Lifecycle & Store Persistence
- **Store Extensions (`backend/app/core/store.py`)**:
  - Added `update_environment(env)`: Sets `updated_at` to the current UTC timestamp (`utc_now()`) and updates `ENVIRONMENTS`.
  - Refactored `stop_environment(environment_id)`: Transitions status to `"stopped"` and delegates persistence to `update_environment`.
  - Exported `Store` class encapsulating all store operations alongside singleton instance `store = Store()`.
- **Environment Routes (`backend/app/api/routes/environments.py`)**:
  - Added `POST /api/v1/environments/{environment_id}/ready` endpoint.
  - Updates environment status from `"provisioning"` to `"ready"`, returning standard `ApiEnvelope[SyntheticEnvironment]`.
  - Enforces `404 Not Found` with standard error envelope when the target environment does not exist.

### B. Stateful Synthetic CRM Lead Management API
- **Schemas (`backend/app/schemas/crm.py`)**:
  - `CRMLeadCreate`: Field validations for `name` (`min_length=2, max_length=100`), `email`, optional `company`, and `status` (`"new" | "contacted" | "qualified" | "closed"`).
  - `CRMLeadResponse`: Extends `CRMLeadCreate` with `id`, `created_at`, and `updated_at`.
- **In-Memory Store Operations (`backend/app/core/store.py`)**:
  - Added `CRM_LEADS: dict[str, dict]` store.
  - Added CRUD helpers: `create_crm_lead`, `get_crm_lead`, `list_crm_leads`, `update_crm_lead`, `delete_crm_lead`.
  - Exposed all CRM helpers via the `Store` class.
- **CRM Router (`backend/app/api/routes/crm.py`)**:
  - `POST /api/v1/leads` (`201 Created`): Creates a new lead with generated UUID and UTC timestamps.
  - `GET /api/v1/leads` (`200 OK`): Lists all stored leads.
  - `GET /api/v1/leads/{lead_id}` (`200 OK`): Retrieves lead by ID; raises `404` if missing.
  - `PUT /api/v1/leads/{lead_id}` (`200 OK`): Updates lead fields and refreshes `updated_at`; raises `404` if missing.
  - `DELETE /api/v1/leads/{lead_id}` (`204 No Content`): Deletes lead; raises `404` if missing.
- **Main App Registration (`backend/app/main.py`)**:
  - Mounted CRM router under `settings.api_prefix` (`/api/v1`).

### C. Deterministic Fault Simulation & Latency Injection
- **Read Endpoint Fault Injection (`backend/app/api/routes/crm.py`)**:
  - Query parameters added to `GET /api/v1/leads` and `GET /api/v1/leads/{lead_id}`:
    - `simulated_latency_ms`: Annotated `Query(ge=0, le=60000)` injects delays before responding.
    - `inject_error`: Annotated `Query(ge=400, le=599)` simulates HTTP errors (e.g. `429`, `500`).
  - Added `_apply_fault_injection` helper:
    - Evaluates error injection first, raising `HTTPException(inject_error)`.
    - Otherwise awaits `asyncio.sleep(simulated_latency_ms / 1000.0)` asynchronously without blocking the event loop.
  - Out-of-range status codes (e.g. `200`) or invalid latency values fail with `422 Unprocessable Entity`.
  - Faults execute before store access, guaranteeing zero state mutation or data corruption.

### D. Multi-Protocol Adapter Layer & Tool Registry
- **Protocol Adapters (`backend/app/core/adapters.py`)**:
  - Unified data models: `AgentToolRequest` (`call_id`, `tool_name`, `parameters`, `agent_id`) and `AgentToolResponse` (`call_id`, `success`, `data`, `error`, `execution_time_ms`).
  - `BaseProtocolAdapter` abstract base class defining `parse_request()` and `format_response()`.
  - `RESTProtocolAdapter`: Parses flat REST/OpenAPI payloads (`tool_name`/`tool`/`name`, `parameters`/`params`/`arguments`); formats normalized dictionary responses.
  - `OpenAIFunctionAdapter`: Parses OpenAI function calling structures (`{"function": {"name", "arguments"}}` where arguments can be a dictionary or a JSON-encoded string); formats OpenAI tool messages (`{"role": "tool", "tool_call_id", "content"}`).
  - `AdapterFactory`: Registry mapping protocol identifiers (`rest`, `openai`, `openai_function`, `function`, `langchain`) to adapter instances; raises `UnknownProtocolError` for unregistered protocols.
- **Synthetic Tool Registry (`backend/app/core/tools.py`)**:
  - `TOOL_REGISTRY`: Maps tool names and aliases (`list_crm_leads`, `crm.list_leads`, `get_crm_lead`, `crm.get_lead`, `create_crm_lead`, `crm.create_lead`, `update_crm_lead`, `crm.update_lead`, `delete_crm_lead`, `crm.delete_lead`) to store operations.
  - `execute_synthetic_tool(tool_name, parameters)`: Dispatches tool calls and translates failures into `ToolNotFoundError` or `ToolExecutionError`.

### E. Protocol-Agnostic Agent Execution Dispatcher
- **Execution Route (`backend/app/api/routes/agent_execution.py`)**:
  - `POST /api/v1/synthetic/agent/execute/{protocol}`:
    - Resolves adapter via `AdapterFactory.get_adapter(protocol)`.
    - Normalizes incoming payload to `AgentToolRequest`.
    - Dispatches execution through `execute_and_trace_tool` with optional `run_id` telemetry attachment.
    - Serializes output back into protocol-specific wire format.
    - Normalizes parse errors, missing tools, and execution exceptions into structured error envelopes rather than raw `500` server crashes.
    - When `run_id` is supplied, validates the run exists (404 otherwise) and emits a `tool_call` `ExecutionEvent` (sequence = `get_events_for_run(run_id)` length + 1) carrying only the redacted parameter payload and a success/failed status.

### F. Agent Profiling, Tool-Call Telemetry & Sensitive Data Redaction
- **Schemas (`backend/app/schemas/tracing.py`)**:
  - `ToolCallTraceCreate`: `run_id`, `call_id`, `tool_name`, `parameters`, `success`, `result`, `error`, `execution_time_ms`.
  - `ToolCallTraceResponse`: Extends `ToolCallTraceCreate` with generated UTC `timestamp`.
- **Recursive Sensitive Data Redaction (`backend/app/core/redaction.py`)**:
  - `redact_sensitive_data()`: Recursively processes dicts, lists, and strings.
  - Dictionary keys matching sensitive tokens (`password`, `token`, `api_key`, `secret`, `authorization`, `credit_card`, `ssn`, `private_key`) are masked with `"[REDACTED]"`.
  - Inline regex scrubber detects and redacts Authorization header tokens (`Bearer ...`, `Basic ...`), inline assignments (`key=value`, `token: ...`), OpenAI secret keys (`sk-...`), AWS access keys (`AKIA...`), and JWT strings.
- **Trace & Event Storage (`backend/app/core/store.py`)**:
  - `TOOL_TRACES: dict[str, list[dict]]`: In-memory trace repository indexed by `run_id`.
  - Added helpers: `record_tool_trace(run_id, trace_data)` and `get_traces_for_run(run_id)`.
  - Added `record_execution_event(run_id, event)` alongside the existing `EVENTS` store and `get_events_for_run` so profiled executions are visible in the run event stream.
- **Instrumented Execution Wrapper (`backend/app/core/telemetry.py`)**:
  - `execute_and_trace_tool(run_id, call_id, tool_name, parameters, executor=None)`:
    - High-resolution timing via `time.perf_counter()`.
    - Supports synchronous and asynchronous tool executors.
    - Normalizes exceptions (`tool_not_found`, `tool_execution_error`, `invalid_request`, `execution_error`).
    - Applies `redact_sensitive_data()` to parameters, execution results, and error details prior to persisting.
    - Persists traces when `run_id` is provided; still times and formats execution when `run_id` is `None`.
- **Trace Retrieval Endpoint (`backend/app/api/routes/test_runs.py`)**:
  - `GET /api/v1/test-runs/{run_id}/traces`: Returns `ApiEnvelope[list[ToolCallTraceResponse]]`; raises `404 Not Found` if no traces exist for the run.

---

## 3. Key Code Modifications & Git Diff Highlights

### A. Environment Routes & Lifecycle Persistence
```diff
diff --git a/backend/app/api/routes/environments.py b/backend/app/api/routes/environments.py
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
+@router.post("/environments/{environment_id}/ready", response_model=ApiEnvelope[SyntheticEnvironment])
+def mark_environment_ready(environment_id: str) -> ApiEnvelope[SyntheticEnvironment]:
+    env = get_environment(environment_id)
+    if not env:
+        raise HTTPException(
+            status_code=404,
+            detail={"message": f"Environment '{environment_id}' was not found."}
+        )
+    env.status = "ready"
+    update_environment(env)
+    return ApiEnvelope(success=True, data=env, error=None)
```

### B. CRM Routes with Fault and Latency Injection
```diff
diff --git a/backend/app/api/routes/crm.py b/backend/app/api/routes/crm.py
--- a/backend/app/api/routes/crm.py
+++ b/backend/app/api/routes/crm.py
@@ -1,6 +1,28 @@
 from __future__ import annotations
+import asyncio
+from typing import Annotated
+from fastapi import APIRouter, HTTPException, Query
+from app.schemas.common import ApiEnvelope
+from app.schemas.crm import CRMLeadCreate, CRMLeadResponse
 
 router = APIRouter(tags=["crm"])
+
+SimulatedLatencyMs = Annotated[int | None, Query(ge=0, le=60_000, description="Inject a synthetic delay (in milliseconds).")]
+InjectError = Annotated[int | None, Query(ge=400, le=599, description="Simulate an HTTP error status.")]
+
+async def _apply_fault_injection(simulated_latency_ms: int | None, inject_error: int | None) -> None:
+    if inject_error is not None:
+        raise HTTPException(status_code=inject_error, detail={"message": f"Simulated fault triggered with error code {inject_error}"})
+    if simulated_latency_ms:
+        await asyncio.sleep(simulated_latency_ms / 1000.0)
+
+@router.get("/leads", response_model=ApiEnvelope[list[CRMLeadResponse]])
+async def list_leads_endpoint(
+    simulated_latency_ms: SimulatedLatencyMs = None,
+    inject_error: InjectError = None,
+) -> ApiEnvelope[list[CRMLeadResponse]]:
+    await _apply_fault_injection(simulated_latency_ms, inject_error)
+    leads = list_crm_leads()
+    return ApiEnvelope(success=True, data=leads)
```

### C. Protocol Dispatcher with Telemetry & Trace Retrieval
```diff
diff --git a/backend/app/api/routes/agent_execution.py b/backend/app/api/routes/agent_execution.py
--- a/backend/app/api/routes/agent_execution.py
+++ b/backend/app/api/routes/agent_execution.py
@@ -1,15 +1,40 @@
+from fastapi import APIRouter, Body, HTTPException, Query
+from app.core.adapters import AdapterFactory, AgentToolResponse, UnknownProtocolError
+from app.core.store import get_test_run
+from app.core.telemetry import execute_and_trace_tool
+
+router = APIRouter(tags=["synthetic-agent"])
+
+@router.post("/synthetic/agent/execute/{protocol}")
+async def execute_agent_tool_endpoint(
+    protocol: str,
+    run_id: str | None = Query(default=None, description="Test run to attach tool-call telemetry to."),
+    payload: dict[str, Any] | None = Body(default=None),
+) -> dict[str, Any]:
+    try:
+        adapter = AdapterFactory.get_adapter(protocol)
+    except UnknownProtocolError as exc:
+        raise HTTPException(status_code=400, detail={"message": str(exc)})
+    if run_id is not None and get_test_run(run_id) is None:
+        raise HTTPException(status_code=404, detail={"message": f"Test run '{run_id}' was not found."})
+    ...
+    outcome = await execute_and_trace_tool(run_id, request.call_id, request.tool_name, request.parameters)
+    response = AgentToolResponse(call_id=request.call_id, success=outcome.success, data=outcome.data, error=outcome.error, execution_time_ms=outcome.execution_time_ms)
+    return adapter.format_response(response)
+
diff --git a/backend/app/api/routes/test_runs.py b/backend/app/api/routes/test_runs.py
--- a/backend/app/api/routes/test_runs.py
+++ b/backend/app/api/routes/test_runs.py
@@ -57,3 +57,7 @@
+@router.get("/test-runs/{run_id}/traces", response_model=ApiEnvelope[list[ToolCallTraceResponse]])
+async def get_test_run_traces_endpoint(run_id: str) -> ApiEnvelope[list[ToolCallTraceResponse]]:
+    traces = get_traces_for_run(run_id)
+    if not traces:
+        raise HTTPException(status_code=404, detail={"message": f"No tool traces were found for run '{run_id}'."})
+    return ApiEnvelope(success=True, data=traces)
```

---

## 4. Automated Test Suite Verification

### Test Results Overview
- **Command**: `python -m pytest` (executed with `backend/.venv/Scripts/python.exe`)
- **Total Tests**: **25 passed** (0 failures, 0 errors, 1 benign deprecation warning)
- **Execution Time**: ~0.90s

### Detailed Test Module Breakdown
| Test Module | Tests | Status | Coverage Areas |
| :--- | :---: | :---: | :--- |
| `tests/test_api_contracts.py` | 4 | ✅ Passed | Agent registration & validation, Test run contracts & events, Synthetic environment readiness & evaluation, CRM fault simulation & latency injection |
| `tests/test_health.py` | 1 | ✅ Passed | Service health ping (`/health` and `/api/v1/health`) |
| `tests/test_protocol_adapters.py` | 7 | ✅ Passed | REST adapter round-trip, OpenAI function payload parsing & tool message formatting, `AdapterFactory` aliases & defaults, REST tool execution, OpenAI tool execution, error normalization on missing tools & invalid syntax, unknown protocol rejection |
| `tests/test_tracing.py` | 8 | ✅ Passed | Recursive dictionary/list secret masking, Inline secret token scrubbing, Instrumented tool execution telemetry, Execution failure capturing, Dispatcher end-to-end trace persistence, Missing trace 404 handling, `tool_call` execution event emission (success & failure) |
| `tests/test_crm.py` | 5 | ✅ Passed | CRM CRUD lifecycle & state changes, invalid payload rejection (422), structured 404 envelopes for missing leads, query-boundary validation for `inject_error` / `simulated_latency_ms`, repeated & concurrent operations |

> **Test isolation note:** as with the existing suites, the CRM module exercises the shared in-process in-memory store through a module-level `TestClient(app)`; assertions use generated unique IDs and are order-independent relative to other modules.

---

## 5. End-to-End Live Verification Cycles

All major user journeys and service interactions were verified against live FastAPI routes:

### Cycle 1: Synthetic Environment Lifecycle
1. `POST /api/v1/environments` with `{"environment_type": "postgres", "label": "crm-test-env"}` → `201 Created` (`status: "provisioning"`).
2. `GET /api/v1/environments/{env_id}` → `200 OK` (retrieves active environment record).
3. `POST /api/v1/environments/{env_id}/ready` → `200 OK` (transitions status to `"ready"`).
4. `POST /api/v1/environments/{env_id}/stop` → `200 OK` (transitions status to `"stopped"`).

### Cycle 2: Stateful Synthetic CRM Leads API
1. `POST /api/v1/leads` with `{"name": "Alice Smith", "email": "alice@example.com", "company": "Acme Inc", "status": "new"}` → `201 Created` (returns lead with generated UUID and UTC timestamps).
2. `GET /api/v1/leads/{lead_id}` → `200 OK` (returns lead data matching request).
3. `PUT /api/v1/leads/{lead_id}` with `{"name": "Alice Doe", "email": "alice@example.com", "status": "qualified"}` → `200 OK` (updates fields and refreshes `updated_at`).
4. `DELETE /api/v1/leads/{lead_id}` → `204 No Content` (removes record).
5. `GET /api/v1/leads/{lead_id}` → `404 Not Found` (verifies complete deletion).

### Cycle 3: Resiliency & Fault Injection Testing
1. `GET /api/v1/leads?simulated_latency_ms=10` → `200 OK` (adds delay while serving intact leads list).
2. `GET /api/v1/leads?inject_error=429` → `429 Too Many Requests` (simulates rate limiting without modifying state).
3. `GET /api/v1/leads/{lead_id}?inject_error=500` → `500 Internal Server Error` (simulates upstream service fault).
4. `GET /api/v1/leads?inject_error=200` → `422 Unprocessable Entity` (validates `inject_error` range `[400, 599]`).

### Cycle 4: Protocol Adapter Dispatcher
1. `POST /api/v1/synthetic/agent/execute/rest` with `{"tool": "create_crm_lead", "parameters": {...}}` → `200 OK` (executes tool and returns normalized flat response with `execution_time_ms`).
2. `POST /api/v1/synthetic/agent/execute/openai` with function call object → `200 OK` (returns formatted OpenAI tool message with `role: "tool"` and JSON string `content`).
3. `POST /api/v1/synthetic/agent/execute/grpc` → `400 Bad Request` (`"Unsupported protocol 'grpc'"`).

### Cycle 5: Telemetry, Profiling & Sensitive Data Redaction
1. `POST /api/v1/agents` with `{"agent_id": "agent-007", "name": "James", "role": "executor"}` → `201 Created`.
2. `POST /api/v1/test-runs` with `{"suite_name": "crm-audit", "target_agents": ["agent-007"]}` → `201 Created` (`run_id`).
3. Dispatched REST tool execution with sensitive parameter: `{"api_key": "super_secret_token_12345"}` and `?run_id={run_id}` → `200 OK`.
4. Dispatched OpenAI tool execution with `list_crm_leads` and `?run_id={run_id}` → `200 OK`.
5. `GET /api/v1/test-runs/{run_id}/traces` → `200 OK` (retrieves 2 recorded traces).
6. Trace inspection verifies `parameters.api_key` was securely stored as `"[REDACTED]"`.

---

## 6. Git Commit Log on `feature/synthetic-api`

| Commit | Message | Key Deliverables |
| :--- | :--- | :--- |
| `312f3b6` | `feat(backend): implement synthetic environment lifecycle and ready endpoint` | Synthetic environment store updates, `ready` transition route, 4 contract tests. |
| `e7e26ee` | `feat(crm): implement stateful synthetic CRM routes with fault and latency injection` | CRM schemas, store operations, CRUD routes, `simulated_latency_ms` and `inject_error` fault simulation, 5 passing tests. |
| `9a1d71a` | `feat(adapters): implement protocol adapter layer, tool registry, and agent execution dispatcher` | Unified models, `RESTProtocolAdapter`, `OpenAIFunctionAdapter`, `AdapterFactory`, `TOOL_REGISTRY`, `/synthetic/agent/execute/{protocol}` dispatcher, 12 passing tests. |
| `872a7d5` | `feat(tracing): verify live protocol execution dispatcher and redacted tool-call telemetry` | Redaction utility (`redact_sensitive_data`), execution tracing wrapper (`execute_and_trace_tool`), `TOOL_TRACES` storage, `/test-runs/{run_id}/traces` endpoint, 18 passing tests. |

---

## 7. Uncommitted Working-Tree Changes

Session-scoped changes (uncommitted; belong with Priority 1 & 2 work): wiring profiled tool executions into the existing event system and adding focused CRM contract coverage.

| File | Change |
| :--- | :--- |
| `backend/app/core/store.py` | Added `record_execution_event(run_id, event)` (appends to the existing `EVENTS` store) and exposed it on the `Store` class alongside `get_events_for_run`. |
| `backend/app/api/routes/agent_execution.py` | Validates `run_id` against `get_test_run` (404 envelope when unknown); after `execute_and_trace_tool`, emits a `tool_call` `ExecutionEvent` (sequence = current event count + 1) carrying only the redacted telemetry payload and a success/failed status. |
| `backend/tests/test_tracing.py` | Added `test_execution_dispatcher_writes_tool_call_event_for_run` and `test_execution_dispatcher_writes_failure_tool_call_event` (8 total in module). |
| `backend/tests/test_crm.py` | **New** module: 5 focused CRM contract tests (CRUD lifecycle, invalid payloads, 404 envelopes, query boundaries, repeated/concurrent operations). |

Result: **25 passed** (0 failures, 0 errors) in ~0.90s. Run with `backend/.venv/Scripts/python.exe -m pytest -v`. `docs/current-status.md` and this log were updated to match (uncommitted).