# NEXORA AI Testing Platform — Changes & Inspection Log

## 1. Branch & Context
- **Branch**: `feature/synthetic-api`
- **Latest Commit**: `82646d0` (*Merge pull request #6 from naaneshwarn/chore/project-foundation*)
- **Upstream Base**: `25dab08` (*Publish NEXORA AI Testing Platform source code*)
- **Date**: October 13, 2026
- **Focus**:
  1. Synthetic Environment lifecycle state transitions (`provisioning` → `ready` → `stopped`) and `/ready` endpoint.
  2. Stateful synthetic CRM Lead management API (`/api/v1/leads`).
  3. Deterministic fault simulation and latency injection on CRM read endpoints (`simulated_latency_ms`, `inject_error`).
  4. Protocol adapters for agent communication (`REST`, `OpenAI`, `LangChain`) via `/synthetic/agent/execute/{protocol}`.
  5. Agent profiling, tool-call telemetry with sensitive data redaction, and run trace retrieval (`/test-runs/{run_id}/traces`).
  6. Comprehensive automated test suite expansion (38 tests passing across 7 modules) and end-to-end integration verification.
  7. Execution event-system integration for profiled tool calls (`tool_call` events on `/test-runs/{run_id}/events`).
  8. Focused synthetic CRM contract coverage (`tests/test_crm.py`, 5 tests) for CRUD, validation, 404 envelopes, query boundaries, and repeated operations.
  9. Optional authentication dependency (`backend/app/core/auth.py`) accepting `X-API-Key` / `Authorization: Bearer` with deterministic 401/403 simulation sentinels for denied-access testing, attached to the CRM and synthetic execution routers.
  10. Server-Sent Events (SSE) live trace streaming (`GET /api/v1/test-runs/{run_id}/stream`) emitting deduplicated `tool_trace` frames and a terminal `run_status` frame.
  11. Real-time dashboard integration: a reusable `useTestRunStream` React hook and `TraceStreamViewer` component consuming the SSE stream (with REST-based run status seeding and client-side redaction), plus a 26-test Vitest suite and production build verification.

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

### G. Optional Authentication Dependency
- **Auth Helper (`backend/app/core/auth.py`)**:
  - `api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)` and `bearer_scheme = HTTPBearer(auto_error=False)` allow credentials to be supplied optionally without FastAPI auto-rejecting anonymous callers.
  - `verify_optional_auth(api_key, bearer)`: Resolves the effective token with Bearer precedence, then returns `{"authenticated": bool(token), "token_prefix": token[:4] + "..."}` (or `None` when anonymous).
  - Deterministic denied-access sentinels: `INVALID_TOKEN = "invalid-token-test"` raises `401 Unauthorized`, and `FORBIDDEN_TOKEN = "forbidden-token-test"` raises `403 Forbidden`, each wrapped in the standard `{"message": ...}` detail envelope.
  - Designed to be attached via `Depends(verify_optional_auth)` / router `dependencies=[...]` on any synthetic surface; it never blocks anonymous traffic unless a sentinel is presented.
- **Route Integration (`backend/app/api/routes/crm.py`, `backend/app/api/routes/agent_execution.py`)**:
  - Every CRM route (`POST`/`GET`/`GET {id}`/`PUT`/`DELETE` on `/leads`) now declares `auth_info: dict = Depends(verify_optional_auth)` alongside its existing parameters.
  - `POST /synthetic/agent/execute/{protocol}` declares the same dependency, so both synthetic surfaces share identical optional-auth semantics.
  - Anonymous calls remain `200`/`201`/`204`, while `X-API-Key: invalid-token-test` and `Authorization: Bearer forbidden-token-test` are rejected with the standard `401` / `403` error envelopes before any handler logic runs.

### H. SSE Live Trace Streaming
- **Streaming Router (`backend/app/api/routes/streaming.py`)**:
  - `APIRouter(prefix="/test-runs", tags=["streaming"])` exposing `GET /{run_id}/stream` (mounted as `/api/v1/test-runs/{run_id}/stream`).
  - Validates the run via `get_test_run(run_id)` and raises the structured `404` envelope before opening a stream.
  - Returns `EventSourceResponse` (from `sse_starlette.sse`) wrapping an async `_event_stream` generator.
  - Polls `get_traces_for_run(run_id)` every `POLL_INTERVAL_SECONDS = 1.0` (non-blocking `asyncio.sleep`) and yields `"event": "tool_trace"` frames with `json.dumps(..., default=str)` payloads.
  - De-duplicates traces with a stable `call_id:timestamp` key tracked in an in-memory `sent` set (also used as the SSE `id`).
  - Treats `{"completed", "failed", "cancelled", "passed"}` as terminal: emits a final `"event": "run_status"` frame (`run_id`, `state`, `message`, `completed_at`) and closes the stream.
  - Observes `await request.is_disconnected()` each iteration for graceful client-disconnect cleanup.
  - Reuses the optional auth dependency (`Depends(verify_optional_auth)`), so streaming is anonymously reachable while the synthetic 401/403 sentinels still apply.
- **Application Registration (`backend/app/main.py`)**:
  - Mounted `streaming_router` under `settings.api_prefix` (`/api/v1`).
- **Dependencies (`backend/requirements.txt`)**:
  - Pinned `sse-starlette==2.1.3` and `starlette==0.41.3` (the newer `sse-starlette` 3.x pulls a Starlette that conflicts with `fastapi==0.115.6`).

### I. Real-Time SSE Trace Dashboard (Frontend)
- **Confirmed backend contract** (inspected before building the client):
  - Endpoint: `GET /api/v1/test-runs/{run_id}/stream` (`text/event-stream`; structured `404` envelope before the stream opens for unknown runs).
  - `tool_trace` frame: `id` = `"{call_id}:{timestamp}"`, `data` = the stored `ToolCallTraceResponse` JSON — `run_id`, `call_id`, `tool_name`, `parameters` (already redacted server-side), `success`, `result`, `error` (`{code, message}` or `null`), `execution_time_ms`, `timestamp` (ISO 8601).
  - `run_status` frame: `data` = `{run_id, state, message, completed_at}` where `state` ∈ `queued | running | passed | failed | cancelled`; the stream closes on `completed | failed | cancelled | passed`.
  - Because a `run_status` frame is only emitted on termination, the current state is seeded from `GET /api/v1/test-runs/{run_id}` on connect.
- **API client (`apps/web/src/api/testRuns.ts`)**: `API_BASE_URL` from `VITE_API_BASE_URL` (default `http://localhost:8000`), `testRunStreamUrl(runId)`, `createTestRun`, `getTestRun`, `cancelTestRun`. Unwraps the standard `ApiEnvelope` and surfaces the backend `error.message`.
- **Stream hook (`apps/web/src/hooks/useTestRunStream.ts`)**: connects an `EventSource` when `runId` is set, exposes `traces`, `runStatus`, `runStatusMessage`, `connectionStatus` (`idle | connecting | connected | reconnecting | disconnected | error`), and `error`. Resets run-specific state on run change, ignores malformed JSON, de-duplicates by the SSE `id` (falling back to `call_id:timestamp`), marks `connected` only on the `open` event, treats a transient drop as `reconnecting`, distinguishes fatal (`readyState === CLOSED`) failures, and closes the stream on terminal status or unmount.
- **Viewer (`apps/web/src/components/TraceStreamViewer.tsx`)**: renders the test run id, run status, connection status (text labels, not colour alone), a scrollable newest-first trace list (tool name, call id, duration, timestamp, success/failure, safe error detail, redacted parameters), plus loading/empty/error states. Seeds the current run status from REST and redacts parameter values defensively (`apps/web/src/utils/redaction.ts` mirrors the backend rules).
- **Dashboard integration (`apps/web/src/App.tsx`, `apps/web/src/index.css`)**: a "Live run monitoring" panel lets the user watch an existing run id or create one via `POST /api/v1/test-runs`, then renders `<TraceStreamViewer runId={…} />`. Changing the selected run reconnects the stream; the existing metrics/recent-runs UI is unchanged.
- **Auth note**: browser `EventSource` cannot send custom headers, so the stream is consumed anonymously (the route's optional auth allows this). No token is ever placed in the URL/query string.
- **Test tooling**: the frontend had no test framework, so Vitest 5 + `@testing-library/react` + `jsdom` were added to `apps/web` (`vitest.config.ts`, `src/test/setup.ts`, `src/test/mockEventSource.ts`) with a `test` script.

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

### D. Optional Authentication Dependency
```diff
diff --git a/backend/app/core/auth.py b/backend/app/core/auth.py
--- /dev/null
+++ b/backend/app/core/auth.py
@@ -0,0 +1,42 @@
+from __future__ import annotations
+
+from fastapi import HTTPException, Security, status
+from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer
+
+api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
+bearer_scheme = HTTPBearer(auto_error=False)
+
+INVALID_TOKEN = "invalid-token-test"
+FORBIDDEN_TOKEN = "forbidden-token-test"
+
+
+async def verify_optional_auth(
+    api_key: str | None = Security(api_key_header),
+    bearer: HTTPAuthorizationCredentials | None = Security(bearer_scheme),
+) -> dict:
+    token = bearer.credentials if bearer else api_key
+
+    if token == INVALID_TOKEN:
+        raise HTTPException(
+            status_code=status.HTTP_401_UNAUTHORIZED,
+            detail={"message": "Invalid authentication credentials provided."},
+        )
+
+    if token == FORBIDDEN_TOKEN:
+        raise HTTPException(
+            status_code=status.HTTP_403_FORBIDDEN,
+            detail={"message": "Access denied for this synthetic resource."},
+        )
+
+    return {
+        "authenticated": bool(token),
+        "token_prefix": token[:4] + "..." if token else None,
+    }
```

The dependency is then attached to the synthetic routers:
```diff
diff --git a/backend/app/api/routes/crm.py b/backend/app/api/routes/crm.py
--- a/backend/app/api/routes/crm.py
+++ b/backend/app/api/routes/crm.py
@@ -3,9 +3,10 @@
 import asyncio
 from typing import Annotated
 
-from fastapi import APIRouter, HTTPException, Query
+from fastapi import APIRouter, Depends, HTTPException, Query
 
+from app.core.auth import verify_optional_auth
 from app.core.store import (
@@ -68,6 +69,7 @@
 async def list_leads_endpoint(
     simulated_latency_ms: SimulatedLatencyMs = None,
     inject_error: InjectError = None,
+    auth_info: dict = Depends(verify_optional_auth),
 ) -> ApiEnvelope[list[CRMLeadResponse]]:
     await _apply_fault_injection(simulated_latency_ms, inject_error)
     leads = list_crm_leads()

diff --git a/backend/app/api/routes/agent_execution.py b/backend/app/api/routes/agent_execution.py
--- a/backend/app/api/routes/agent_execution.py
+++ b/backend/app/api/routes/agent_execution.py
@@ -30,6 +30,7 @@
 async def execute_agent_tool_endpoint(
     protocol: str,
     run_id: str | None = Query(default=None, description="Test run to attach tool-call telemetry to."),
     payload: dict[str, Any] | None = Body(default=None),
+    auth_info: dict = Depends(verify_optional_auth),
 ) -> dict[str, Any]:
```

### E. SSE Live Trace Streaming
```diff
diff --git a/backend/app/api/routes/streaming.py b/backend/app/api/routes/streaming.py
--- /dev/null
+++ b/backend/app/api/routes/streaming.py
@@ -0,0 +1,86 @@
+from __future__ import annotations
+
+import asyncio
+import json
+from collections.abc import AsyncIterator
+from typing import Any
+
+from fastapi import APIRouter, Depends, HTTPException, Request
+from sse_starlette.sse import EventSourceResponse
+
+from app.core.auth import verify_optional_auth
+from app.core.store import get_test_run, get_traces_for_run
+
+router = APIRouter(prefix="/test-runs", tags=["streaming"])
+
+TERMINAL_STATES: frozenset[str] = frozenset({"completed", "failed", "cancelled", "passed"})
+TRACE_EVENT = "tool_trace"
+STATUS_EVENT = "run_status"
+POLL_INTERVAL_SECONDS = 1.0
+
+
+def _trace_key(trace: dict[str, Any]) -> str:
+    return f"{trace.get('call_id')}:{trace.get('timestamp')}"
+
+
+async def _event_stream(request: Request, run_id: str) -> AsyncIterator[dict[str, Any]]:
+    sent: set[str] = set()
+
+    while True:
+        if await request.is_disconnected():
+            break
+
+        for trace in get_traces_for_run(run_id):
+            key = _trace_key(trace)
+            if key in sent:
+                continue
+            sent.add(key)
+            yield {"event": TRACE_EVENT, "id": key, "data": json.dumps(trace, default=str)}
+
+        run = get_test_run(run_id)
+        if run is None or run.state in TERMINAL_STATES:
+            yield {"event": STATUS_EVENT, "data": json.dumps(_status_payload(run), default=str)}
+            break
+
+        await asyncio.sleep(POLL_INTERVAL_SECONDS)
+
+
+@router.get("/{run_id}/stream")
+async def stream_test_run(
+    run_id: str,
+    request: Request,
+    auth_info: dict = Depends(verify_optional_auth),
+) -> EventSourceResponse:
+    if get_test_run(run_id) is None:
+        raise HTTPException(status_code=404, detail={"message": f"Test run '{run_id}' was not found."})
+    return EventSourceResponse(_event_stream(request, run_id))
+
diff --git a/backend/app/main.py b/backend/app/main.py
--- a/backend/app/main.py
+++ b/backend/app/main.py
@@ -40,6 +40,8 @@
 from app.api.routes.agent_execution import router as agent_execution_router
 from app.api.routes.crm import router as crm_router
+from app.api.routes.streaming import router as streaming_router
 
 app.include_router(crm_router, prefix=settings.api_prefix)
 app.include_router(agent_execution_router, prefix=settings.api_prefix)
+app.include_router(streaming_router, prefix=settings.api_prefix)
```

### F. Frontend SSE Trace Dashboard
```diff
diff --git a/apps/web/src/hooks/useTestRunStream.ts b/apps/web/src/hooks/useTestRunStream.ts
--- /dev/null
+++ b/apps/web/src/hooks/useTestRunStream.ts
@@
+export function useTestRunStream(runId: string | null): TestRunStreamState {
+  const [traces, setTraces] = useState<ToolTrace[]>([]);
+  const [connectionStatus, setConnectionStatus] = useState<StreamConnectionStatus>('idle');
+  const seenRef = useRef<Set<string>>(new Set());
+
+  useEffect(() => {
+    seenRef.current = new Set();
+    setTraces([]);
+    if (!runId) { setConnectionStatus('idle'); return; }
+
+    setConnectionStatus('connecting');
+    const source = new EventSource(testRunStreamUrl(runId));
+    let terminal = false;
+
+    const handleOpen = () => { setConnectionStatus('connected'); setError(null); };
+    const handleTrace = (event: Event) => {
+      const message = event as MessageEvent<string>;
+      const trace = parseToolTrace(message.data);
+      if (!trace) return;                       // ignore malformed frames
+      const identity = message.lastEventId || traceIdentity(trace);
+      if (seenRef.current.has(identity)) return; // de-duplicate
+      seenRef.current.add(identity);
+      setTraces((previous) => [...previous, trace]);
+    };
+    const handleStatus = (event: Event) => { /* set runStatus; close if terminal */ };
+    const handleError = () => { /* 'reconnecting' (transient) vs 'error' (readyState CLOSED) */ };
+
+    source.onopen = handleOpen;
+    source.onerror = handleError;
+    source.addEventListener('tool_trace', handleTrace);
+    source.addEventListener('run_status', handleStatus);
+    return () => { source.close(); };
+  }, [runId]);
+
+  return { traces, runStatus, runStatusMessage, connectionStatus, error };
+}
+
diff --git a/apps/web/src/api/testRuns.ts b/apps/web/src/api/testRuns.ts
--- /dev/null
+++ b/apps/web/src/api/testRuns.ts
@@
+export const API_BASE_URL =
+  String(import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000').replace(/\/+$/, '');
+
+export function testRunStreamUrl(runId: string): string {
+  return `${API_BASE_URL}/api/v1/test-runs/${encodeURIComponent(runId)}/stream`;
+}
+
+export async function createTestRun(input: CreateTestRunInput): Promise<TestRunDetail> { /* POST /api/v1/test-runs */ }
+export async function getTestRun(runId: string): Promise<TestRunDetail> { /* GET /api/v1/test-runs/{run_id} */ }

diff --git a/apps/web/src/components/TraceStreamViewer.tsx b/apps/web/src/components/TraceStreamViewer.tsx
--- /dev/null
+++ b/apps/web/src/components/TraceStreamViewer.tsx
@@
+export default function TraceStreamViewer({ runId, className }: TraceStreamViewerProps) {
+  const { traces, runStatus, runStatusMessage, connectionStatus, error } = useTestRunStream(runId);
+  const [seedStatus, setSeedStatus] = useState<string | null>(null);
+  // Seed the current state from REST; the stream event wins once it arrives.
+  useEffect(() => { /* getTestRun(runId) → setSeedStatus(run.state) */ }, [runId]);
+  const effectiveStatus = runStatus ?? seedStatus;
+  const newestFirst = useMemo(() => [...traces].reverse(), [traces]);
+  return (/* run/connection badges, error alert, empty states, trace list */);
+}

diff --git a/apps/web/src/App.tsx b/apps/web/src/App.tsx
--- a/apps/web/src/App.tsx
+++ b/apps/web/src/App.tsx
@@
+      <section className="panel live-panel">
+        <h2>Live run monitoring</h2>
+        <form onSubmit={handleWatch}>
+          <input value={runIdInput} onChange={…} placeholder="e.g. run_ab12cd34" />
+          <button type="submit">Watch run</button>
+          <button type="button" onClick={handleCreate}>Create test run</button>
+        </form>
+        <TraceStreamViewer runId={streamRunId} />
+      </section>
```

---

## 4. Automated Test Suite Verification

### Test Results Overview
- **Command**: `python -m pytest` (executed with `backend/.venv/Scripts/python.exe`)
- **Total Tests**: **38 passed** (0 failures, 0 errors, 1 benign deprecation warning)
- **Execution Time**: ~0.98s

### Detailed Test Module Breakdown
| Test Module | Tests | Status | Coverage Areas |
| :--- | :---: | :---: | :--- |
| `tests/test_api_contracts.py` | 4 | ✅ Passed | Agent registration & validation, Test run contracts & events, Synthetic environment readiness & evaluation, CRM fault simulation & latency injection |
| `tests/test_health.py` | 1 | ✅ Passed | Service health ping (`/health` and `/api/v1/health`) |
| `tests/test_protocol_adapters.py` | 7 | ✅ Passed | REST adapter round-trip, OpenAI function payload parsing & tool message formatting, `AdapterFactory` aliases & defaults, REST tool execution, OpenAI tool execution, error normalization on missing tools & invalid syntax, unknown protocol rejection |
| `tests/test_tracing.py` | 8 | ✅ Passed | Recursive dictionary/list secret masking, Inline secret token scrubbing, Instrumented tool execution telemetry, Execution failure capturing, Dispatcher end-to-end trace persistence, Missing trace 404 handling, `tool_call` execution event emission (success & failure) |
| `tests/test_crm.py` | 5 | ✅ Passed | CRM CRUD lifecycle & state changes, invalid payload rejection (422), structured 404 envelopes for missing leads, query-boundary validation for `inject_error` / `simulated_latency_ms`, repeated & concurrent operations |
| `tests/test_auth.py` | 9 | ✅ Passed | Anonymous request allowance, `X-API-Key` acceptance & prefix, `Authorization: Bearer` acceptance, Bearer-over-API-key precedence, simulated `401` (invalid sentinel), simulated `403` (forbidden sentinel), plus real-route integration checks (anonymous CRM `200`, CRM `401`, execution `403`) |
| `tests/test_streaming.py` | 4 | ✅ Passed | Unknown-run `404`, terminal-run `run_status` emission & stream close, deduplicated `tool_trace` frame ordering before `run_status` with redacted payloads, and auth-sentinel rejection on the stream route |

> **Test isolation note:** as with the existing suites, the CRM module exercises the shared in-process in-memory store through a module-level `TestClient(app)`; assertions use generated unique IDs and are order-independent relative to other modules. The auth module verifies the dependency both through its own isolated `FastAPI()` app and against the real `app.main` routers with the synthetic sentinels. The streaming module drives each run to a terminal `cancelled` state so the SSE body is fully buffered, and resets `sse_starlette`'s process-global exit `Event` between tests (a library/`TestClient` event-loop artefact).

### Frontend Test Suite (Vitest)
- **Command**: `npm test --workspace @nexora/web` (Vitest 5, `jsdom` environment, Testing Library, mocked `EventSource`).
- **Result**: **`26 passed`** across 2 files:
  - `src/hooks/useTestRunStream.test.tsx` (14): idle without a run id, `connecting` → `connected` on `open`, trace append, success/failure traces, non-terminal vs terminal `run_status` (stream close), malformed JSON tolerance, de-duplication by identity, transient drop → `reconnecting` → recovery, fatal error, run-id switch reset, cleared run, unmount cleanup.
  - `src/components/TraceStreamViewer.test.tsx` (12): no-run empty state, `connecting` state, trace rendering (tool name, call id, duration), run-status updates, success/failure labels, REST status seeding, malformed payload tolerance, fatal error alert, reconnect → recover, run-id switch, sensitive-value redaction (`password`/`api_key`/`Authorization`), long tool names.
- **Type check**: `npm run lint --workspace @nexora/web` (`tsc --noEmit`) → clean.
- **Build**: `npm run build --workspace @nexora/web` (`tsc --noEmit && vite build`) → success (21 modules, `index-*.js` 152.78 kB / 49.92 kB gzip).

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

### Cycle 6: Optional Authentication & Denied-Access Simulation
1. An isolated FastAPI route guarded by `Depends(verify_optional_auth)` with no credentials → `200 OK` (`{"authenticated": false, "token_prefix": null}`).
2. Same route with `X-API-Key: abcdef123456` → `200 OK` (`{"authenticated": true, "token_prefix": "abcd..."}`).
3. Same route with `Authorization: Bearer tok12345` → `200 OK` (`{"authenticated": true, "token_prefix": "tok1..."}`).
4. Same route with `X-API-Key: invalid-token-test` → `401 Unauthorized` (`"Invalid authentication credentials provided."`).
5. Same route with `Authorization: Bearer forbidden-token-test` → `403 Forbidden` (`"Access denied for this synthetic resource."`).
6. `GET /api/v1/leads` with no credentials → `200 OK` (CRM remains anonymously reachable).
7. `GET /api/v1/leads` with `X-API-Key: invalid-token-test` → `401 Unauthorized` (rejected before fault injection or store access).
8. `POST /api/v1/synthetic/agent/execute/rest` with `Authorization: Bearer forbidden-token-test` → `403 Forbidden`.

### Cycle 7: SSE Live Trace Streaming
1. `GET /api/v1/test-runs/run-does-not-exist/stream` → `404 Not Found` (structured envelope, no stream opened).
2. `POST /api/v1/test-runs` → `201 Created`; `POST /api/v1/test-runs/{run_id}/cancel` → `200 OK`.
3. `GET /api/v1/test-runs/{run_id}/stream` → `200 OK` (`text/event-stream`); stream yields a single `event: run_status` frame with `"state": "cancelled"`, then closes.
4. On a run with a recorded tool call: `POST /api/v1/synthetic/agent/execute/rest?run_id={run_id}` → `200 OK`; after cancellation the stream emits exactly one `event: tool_trace` frame (redacted payload) followed by `event: run_status`.
5. `GET /api/v1/test-runs/{run_id}/stream` with `Authorization: Bearer forbidden-token-test` → `403 Forbidden`.

---

## 6. Git Commit Log on `feature/synthetic-api`

| Commit | Message | Key Deliverables |
| :--- | :--- | :--- |
| `312f3b6` | `feat(backend): implement synthetic environment lifecycle and ready endpoint` | Synthetic environment store updates, `ready` transition route, 4 contract tests. |
| `e7e26ee` | `feat(crm): implement stateful synthetic CRM routes with fault and latency injection` | CRM schemas, store operations, CRUD routes, `simulated_latency_ms` and `inject_error` fault simulation, 5 passing tests. |
| `9a1d71a` | `feat(adapters): implement protocol adapter layer, tool registry, and agent execution dispatcher` | Unified models, `RESTProtocolAdapter`, `OpenAIFunctionAdapter`, `AdapterFactory`, `TOOL_REGISTRY`, `/synthetic/agent/execute/{protocol}` dispatcher, 12 passing tests. |
| `872a7d5` | `feat(tracing): verify live protocol execution dispatcher and redacted tool-call telemetry` | Redaction utility (`redact_sensitive_data`), execution tracing wrapper (`execute_and_trace_tool`), `TOOL_TRACES` storage, `/test-runs/{run_id}/traces` endpoint, 18 passing tests. |
| `507c6d2` | `feat(crm): implement comprehensive CRM tests, protocol execution, and redacted tracing` | Committed the event-system integration and focused CRM contract coverage; `tool_call` execution events, `tests/test_crm.py` (5 tests), 25 passing tests total. |

---

## 7. Uncommitted Working-Tree Changes

The optional authentication dependency and the SSE live trace streaming endpoint documented in sections G/H were committed as `b812020` (*feat(auth+stream): implement optional auth dependency, SSE live streaming, and comprehensive test suite*). The current uncommitted change set is the **real-time SSE dashboard integration**:

| File | Change |
| :--- | :--- |
| `apps/web/src/api/testRuns.ts` | **New** module: `API_BASE_URL` from `VITE_API_BASE_URL`, `testRunStreamUrl`, `createTestRun`, `getTestRun`, `cancelTestRun`, `ApiEnvelope` unwrapping. |
| `apps/web/src/hooks/useTestRunStream.ts` | **New** module: `EventSource` lifecycle hook exposing `traces`, `runStatus`, `runStatusMessage`, `connectionStatus`, `error`; malformed-frame tolerance, de-duplication, reconnect vs fatal handling, terminal close, run-switch reset. |
| `apps/web/src/components/TraceStreamViewer.tsx` | **New** component: run/connection status badges, newest-first trace list, safe error detail, redacted parameters, loading/empty/error states, REST status seeding. |
| `apps/web/src/utils/redaction.ts`, `apps/web/src/utils/format.ts` | **New** helpers: client-side mirror of the backend redaction rules and human-readable duration/timestamp formatting. |
| `apps/web/src/App.tsx`, `apps/web/src/index.css` | Added the "Live run monitoring" panel (watch an existing run id or create one) and viewer styling; existing metrics/recent-runs UI preserved. |
| `apps/web/src/hooks/useTestRunStream.test.tsx`, `apps/web/src/components/TraceStreamViewer.test.tsx` | **New** Vitest suites: 26 tests total. |
| `apps/web/src/test/setup.ts`, `apps/web/src/test/mockEventSource.ts`, `apps/web/vitest.config.ts` | **New** test infrastructure: Testing Library setup, `EventSource` mock, Vitest config (jsdom + shared-package source alias). |
| `apps/web/package.json`, `apps/web/tsconfig.json` | Added the `test`/`test:watch` scripts, Vitest/testing-library/jsdom dev dependencies, and the `vitest/globals` type. |
| `apps/web/.env.example` | **New** sample config documenting `VITE_API_BASE_URL`. |
| `apps/web/README.md` | **New** frontend documentation: SSE contract, configuration, run/test commands, limitations. |
| `package-lock.json` | Regenerated by installing the new frontend dev dependencies. |

Result: backend **38 passed**; frontend **26 passed**; `tsc --noEmit` and `vite build` both clean. Run the backend with `backend/.venv/Scripts/python.exe -m pytest -v` and the frontend with `npm test --workspace @nexora/web`. `docs/current-status.md` and this log were updated to match (uncommitted).

---

## 8. Work Package D — Workflow, Evaluation & Reporting (Rahul, `feature/workflow-evaluation-reporting`)

> This section is additive; sections 1–7 above describe the earlier `feature/synthetic-api` work and were not rewritten. Branch lineage: `feature/workflow-evaluation-reporting` was fast-forwarded onto `chore/project-foundation` (`4703dbc`, zero unique commits lost) before this work began; the 38-test baseline was green before the first and after the last commit.

### Focus
1. Deterministic, LangGraph-compatible workflow engine (zero new dependencies).
2. Scenario registry and deterministic mock agent client (correct / hallucinated / error / timeout).
3. Weighted evaluation (task 40 / factual 40 / trace 20) with configurable pass threshold and secret-leak detection.
4. Orchestration service with environment verification, cancellation, timeouts, idempotent execution, and report publishing.
5. Additive API surface: on-demand execution, rich workflow report retrieval, background auto-execution of registered scenarios.
6. 58 new deterministic tests (96 total), plus a live HTTP end-to-end demo.

### A. Deterministic Workflow Engine (`backend/app/workflow/graph.py`) — commit `4535298`
- In-repo state machine exposing the LangGraph API subset used by the platform: `add_node`, `add_edge`, `add_conditional_edges`, `compile()`, `invoke()`. Real LangGraph can replace it later without changing callers.
- Guarantees: cancellation propagation, failure capture into run state, finalize-once semantics (terminal state written exactly once), deterministic invoke order.
- Schemas (`backend/app/schemas/workflow_report.py`, additive): `CriterionScore`, `Finding` (severity/code/message/evidence_ref), `ReportEvidence`, `WorkflowReport`.
- Tests: `backend/tests/test_workflow_engine.py` (8).

### B. Scenarios, Mock Agent Client & Evaluator — commit `484eeb4`
- `backend/app/workflow/scenarios.py`: registry of `crm-read-customer-summary`, `crm-read-customer-hallucination` (platinum-vip unsupported marker), `crm-read-customer-agent-failure`; idempotent seed CRM lead.
- `backend/app/workflow/agent_client.py`: `SyntheticToolAgentClient` with deterministic behaviors (`correct`, `hallucinated`, `error`, `timeout`); telemetry-integrated tool-call recording.
- `backend/app/workflow/evaluator.py`: weights 40/40/20, `DEFAULT_PASS_THRESHOLD = 70.0`, `validate_pass_threshold` (0–100, numeric coercion, clear errors), secret-leak detection against scenario variables, and the safety rule **any critical finding blocks a pass regardless of score**.
- Tests: `backend/tests/test_workflow_evaluation.py` (16).

### C. Orchestration Service & Store Extensions — commit `0fe30da`
- `backend/app/workflow/service.py`: `WorkflowRunExecutor` pipeline validate → verify_environment → build_scenario → invoke_agent → evaluate → publish_report → finalize; `RUN_CONTEXTS` registry and `build_run_context`; `execute_workflow_run` is idempotent via a queued-state guard; `WORKFLOW_TOTAL_TIMEOUT_SECONDS = 30`.
- `backend/app/core/store.py` (**lead-owned file, additive-only** — flagged for team review): `WORKFLOW_REPORTS`, `update_test_run_state`, `save_workflow_report`, `get_workflow_report`, `get_workflow_report_for_run`.
- Tests: `backend/tests/test_workflow_service.py` (20).

### D. API Integration — commit `c4dd376`
- `backend/app/api/routes/test_runs.py`: `POST /api/v1/test-runs` schedules background auto-execution **only** for registered scenario ids (response body still `state: "queued"` per the Phase 2 contract; unknown/missing scenarios keep legacy queued behavior asserted by `test_api_contracts.py`); new `POST /api/v1/test-runs/{run_id}/execute` (`404` unknown run, `409` non-queued or unregistered scenario with the registered id list).
- `backend/app/api/routes/evaluations.py`: new `GET /api/v1/test-runs/{run_id}/report` returning `ApiEnvelope[WorkflowReport]` (`404` for unknown runs and runs without a report).
- Phase 2 compatibility: publishing a workflow run also writes a `ReportSummary` projection into the existing `REPORTS` store, so `GET /api/v1/reports/{report_id}` is untouched.
- Tests: `backend/tests/test_workflow_api.py` (14 at C6).

### E. End-to-End Coverage — commit `b73e073`
- Added HTTP-level coverage for the agent-failure scenario (failed state + diagnostic findings) and an invalid `pass_threshold` (failed state, clear message, no report published → `404`).
- Tests: `backend/tests/test_workflow_api.py` (14 total).

### F. Live HTTP Demonstration (checkpoint C8)
- Ran `python -m uvicorn app.main:app` and executed the Phase 3 guide's demo flow over real HTTP: health → agent/environment setup → not-ready environment fails safely → ready → passing run (`score 100.00`, `pass`) → hallucination run (`score 60.00`, `fail`, `critical/unsupported_fact` finding on `platinum-vip`) → secret canary absent from traces (`[REDACTED]`) → unknown scenario remains `queued`. Server logs: no 500s, no tracebacks, no secrets.

### G. Security Posture
- No secrets in code, traces, reports, or logs: scenario-variable secrets are redacted before storage; reports carry only `evidence_ref` ids; the evaluator fails any run whose output leaks a secret; an HTTP canary test asserts the raw value never appears in report/traces/events/run responses.
- Tests need no API keys, no Docker, no network (localhost demo excluded from the suite); all execution is deterministic.
- Shared contracts: `app/schemas/` existing files unchanged; all new schemas are in new files; `store.py` changes are additive-only.

### Test & Commit Summary
| Milestone | Commit | Tests after |
| :--- | :--- | :--- |
| Baseline (pre-existing) | `4703dbc` | 38 passed |
| Graph engine + report schemas | `4535298` | 46 passed |
| Scenarios, agent client, evaluator | `484eeb4` | 62 passed |
| Orchestration service + store helpers | `0fe30da` | 82 passed |
| API integration | `c4dd376` | 94 passed |
| E2E HTTP coverage | `b73e073` | **96 passed** |

All commits are local on `feature/workflow-evaluation-reporting` and have **not been pushed** (per instruction).