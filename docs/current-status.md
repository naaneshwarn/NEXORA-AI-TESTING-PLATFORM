# NEXORA AI Testing Platform — Current Status

**Last Updated:** October 13, 2026  
**Active Branch:** `feature/synthetic-api`  
**Latest Commit:** `82646d0` (*Merge pull request #6 from naaneshwarn/chore/project-foundation*)\
**Upstream Base:** `25dab08` (*Publish NEXORA AI Testing Platform source code*)  

---

## 1. Executive Summary

The NEXORA platform backend foundation is fully operational in local-development mode. All versioned core REST endpoints under `/api/v1` are live, validated against strict Pydantic schemas, and backed by a centralized in-memory store.

Key milestones delivered on `feature/synthetic-api`:
1. **Synthetic Environment Lifecycle**: State transitions (`provisioning` → `ready` → `stopped`), with the dedicated `/ready` transition endpoint, state persistence, and full test suite validation.
2. **Stateful Synthetic CRM API**: Complete CRM Lead management endpoints (`/api/v1/leads`) backed by in-memory state storage with CRUD capabilities, Pydantic validation, and standard `ApiEnvelope` packaging.
3. **Fault Simulation & Resiliency Testing**: Deterministic fault injection (`simulated_latency_ms` and `inject_error` query parameters) on CRM read endpoints with non-blocking `asyncio.sleep`, strict Pydantic range validation (`422`), error code simulation (`429`, `500`), and zero state mutation guarantees.
4. **Protocol Adapter Layer (Phase 3)**: Modular adapter layer (`RESTProtocolAdapter`, `OpenAIFunctionAdapter`, `AdapterFactory`) with unified `AgentToolRequest` / `AgentToolResponse` models, synthetic tool registry (`TOOL_REGISTRY`), and a synthesis execution dispatcher at `/api/v1/synthetic/agent/execute/{protocol}`.
5. **Agent Profiling & Tool-Call Tracing (Phase 3)**: Redacted tool-call telemetry (`ToolCallTraceCreate` / `ToolCallTraceResponse`), a recursive sensitive-data redaction engine scrubbing dictionary keys and inline token patterns, in-memory trace storage (`TOOL_TRACES`), and an async `execute_and_trace_tool` execution wrapper exposed at `/api/v1/test-runs/{run_id}/traces`. Integration with the event system records execution events for test run tracking.
6. **Automated Verification**: Complete 38-test automated pytest suite passing across 7 modules (`test_api_contracts.py`, `test_health.py`, `test_protocol_adapters.py`, `test_tracing.py`, `test_crm.py`, `test_auth.py`, `test_streaming.py`), plus full live HTTP lifecycle verification.
7. **Optional Authentication Dependency**: `backend/app/core/auth.py` inspects `X-API-Key` / `Authorization: Bearer` headers without forcing credentials on anonymous callers, exposes deterministic `invalid-token-test` (401) / `forbidden-token-test` (403) sentinels for denied-access testing, and is attached to the CRM, synthetic agent-execution, and streaming routers.
8. **SSE Live Trace Streaming (Phase 3)**: `GET /api/v1/test-runs/{run_id}/stream` streams deduplicated `tool_trace` frames and a terminal `run_status` frame over `EventSourceResponse`, with 404 validation, client-disconnect handling, and a 1s non-blocking poll loop.

---

## 2. Service & Repository Status

| Component | Path | Technology | Current Status |
| :--- | :--- | :--- | :--- |
| **Backend API** | [backend/](file:///c:/NEXORA-AI-TESTING-PLATFORM/backend/) | FastAPI + Python 3.13 | ✅ Active, verified, 38 passing tests; synthetic environments, stateful CRM, fault injection, protocol adapters (`rest`, `openai`, `langchain`), redacted tracing, execution-event integration, optional auth dependency, and SSE live trace streaming operational |
| **Frontend UI** | [apps/web/](file:///c:/NEXORA-AI-TESTING-PLATFORM/apps/web/) | React + TypeScript + Vite | ✅ Dashboard scaffold extended with a real-time SSE trace viewer (`useTestRunStream` + `TraceStreamViewer`), 26 Vitest tests, and REST run selection; production build verified |
| **Legacy/Node API** | [apps/api/](file:///c:/NEXORA-AI-TESTING-PLATFORM/apps/api/) | Node.js + Express | 🟡 Placeholder service retained for backward compatibility |
| **Shared Lib** | [packages/shared/](file:///c:/NEXORA-AI-TESTING-PLATFORM/packages/shared/) | TypeScript | ✅ Common types and utilities retained |
| **Documentation** | [docs/](file:///c:/NEXORA-AI-TESTING-PLATFORM/docs/) | Markdown | ✅ Architecture, API contracts, changes log, and current status fully updated |

---

## 3. API Endpoints & Contract Implementation Status

All endpoints are versioned under `/api/v1` (except the root `/health` ping) using standard `ApiEnvelope` packaging:

| Domain | Route | Method | Status | Notes |
| :--- | :--- | :--- | :--- | :--- |
| **Health** | `/api/v1/health` | `GET` | ✅ Operational | Baseline status and service health check |
| **Root Health**| `/health` | `GET` | ✅ Operational | Lightweight service ping |
| **Agents** | `/api/v1/agents` | `POST` | ✅ Operational | Registers agent configuration; enforces `409 Conflict` on duplicates |
| **Agents** | `/api/v1/agents/{agent_id}` | `GET` | ✅ Operational | Inspects registered agent details |
| **Environments**| `/api/v1/environments` | `POST` | ✅ Operational | Provisions synthetic environment (`status: provisioning`) |
| **Environments**| `/api/v1/environments/{environment_id}` | `GET` | ✅ Operational | Fetches environment status and endpoint |
| **Environments**| `/api/v1/environments/{environment_id}/ready` | `POST` | ✅ Operational | Transitions status from `provisioning` to `ready` |
| **Environments**| `/api/v1/environments/{environment_id}/stop` | `POST` | ✅ Operational | Transitions status to `stopped` |
| **Test Runs** | `/api/v1/test-runs` | `POST` | ✅ Operational | Queues scenario test run |
| **Test Runs** | `/api/v1/test-runs/{run_id}` | `GET` | ✅ Operational | Fetches execution state |
| **Test Runs** | `/api/v1/test-runs/{run_id}/cancel` | `POST` | ✅ Operational | Cancels active run |
| **Events** | `/api/v1/test-runs/{run_id}/events` | `GET` | ✅ Operational | Retrieves tool-call execution events |
| **Traces** | `/api/v1/test-runs/{run_id}/traces` | `GET` | ✅ Operational | Retrieves redacted tool-call execution traces (`ToolCallTraceResponse`) |
| **Streaming** | `/api/v1/test-runs/{run_id}/stream` | `GET` | ✅ Operational | Server-Sent Events stream of `tool_trace` frames plus a terminal `run_status` frame (`EventSourceResponse`); `404` for unknown runs |
| **Evaluations** | `/api/v1/evaluations` | `POST` | ✅ Operational | Submits evaluation result and generates report |
| **Reports** | `/api/v1/reports/{report_id}` | `GET` | ✅ Operational | Retrieves final evaluation report |
| **CRM Leads** | `/api/v1/leads` | `POST` | ✅ Operational | Creates new CRM lead (`status: 201`, validates name/email/status) |
| **CRM Leads** | `/api/v1/leads` | `GET` | ✅ Operational | Lists all leads; supports `simulated_latency_ms` & `inject_error` |
| **CRM Leads** | `/api/v1/leads/{lead_id}` | `GET` | ✅ Operational | Retrieves specific lead (`404` if missing); supports fault injection |
| **CRM Leads** | `/api/v1/leads/{lead_id}` | `PUT` | ✅ Operational | Updates existing lead fields (`404` if missing) |
| **CRM Leads** | `/api/v1/leads/{lead_id}` | `DELETE` | ✅ Operational | Deletes CRM lead by ID (`status: 204`, `404` if missing) |
| **Synthetic Agent** | `/api/v1/synthetic/agent/execute/{protocol}` | `POST` | ✅ Operational | Protocol-agnostic tool dispatcher (`rest`, `openai`, `langchain`); normalizes requests/responses and attaches traces when `run_id` is supplied |

---

## 4. Synthetic Architecture & Implementation Details

- **CRM Schemas**: [`backend/app/schemas/crm.py`](file:///c:/NEXORA-AI-TESTING-PLATFORM/backend/app/schemas/crm.py)
  - `CRMLeadCreate`: Field validation for `name` (`min_length=2, max_length=100`), `email`, optional `company`, and `status` (`new`, `contacted`, `qualified`, `closed`).
  - `CRMLeadResponse`: Extends `CRMLeadCreate` with `id`, `created_at`, and `updated_at`.
- **In-Memory Store**: [`backend/app/core/store.py`](file:///c:/NEXORA-AI-TESTING-PLATFORM/backend/app/core/store.py)
  - State dictionaries: `ENVIRONMENTS`, `AGENTS`, `TEST_RUNS`, `EVENTS`, `CRM_LEADS`, `TOOL_TRACES`, `REPORTS`.
  - Full CRUD operations with timestamp tracking, `get_events_for_run` / `record_execution_event` helpers, and singleton instance `store = Store()`.
- **Fault Simulation & Resiliency**: [`backend/app/api/routes/crm.py`](file:///c:/NEXORA-AI-TESTING-PLATFORM/backend/app/api/routes/crm.py)
  - `SimulatedLatencyMs`: `Query(ge=0, le=60000)` non-blocking delay via `asyncio.sleep`.
  - `InjectError`: `Query(ge=400, le=599)` simulates HTTP status codes (e.g., `429`, `500`).
  - Strict range validation rejecting out-of-range values with `422 Unprocessable Entity`.
  - Faults are evaluated before store operations, guaranteeing zero data corruption.
- **Protocol Adapter Layer**: [`backend/app/core/adapters.py`](file:///c:/NEXORA-AI-TESTING-PLATFORM/backend/app/core/adapters.py)
  - Unified models `AgentToolRequest` and `AgentToolResponse`.
  - `BaseProtocolAdapter` contract implemented by `RESTProtocolAdapter` and `OpenAIFunctionAdapter`.
  - `AdapterFactory` dynamically resolves adapters with support for aliases (`openai_function`, `function`, `langchain`).
- **Synthetic Tool Registry**: [`backend/app/core/tools.py`](file:///c:/NEXORA-AI-TESTING-PLATFORM/backend/app/core/tools.py)
  - Maps tool names and dotted aliases (`list_crm_leads`, `crm.list_leads`, etc.) to store operations.
- **Execution Dispatcher**: [`backend/app/api/routes/agent_execution.py`](file:///c:/NEXORA-AI-TESTING-PLATFORM/backend/app/api/routes/agent_execution.py)
  - `POST /api/v1/synthetic/agent/execute/{protocol}` parses via adapter, executes tool, captures timing, attaches telemetry to test runs, and emits a redacted `tool_call` execution event when `run_id` is supplied.
- **Sensitive Data Redaction**: [`backend/app/core/redaction.py`](file:///c:/NEXORA-AI-TESTING-PLATFORM/backend/app/core/redaction.py)
  - `redact_sensitive_data()` recursively scrubs sensitive dictionary keys (`password`, `token`, `api_key`, `secret`, `authorization`, etc.) and inline regex patterns (Bearer tokens, AWS keys, JWTs, OpenAI keys).
- **Tool-Call Telemetry**: [`backend/app/core/telemetry.py`](file:///c:/NEXORA-AI-TESTING-PLATFORM/backend/app/core/telemetry.py)
  - `execute_and_trace_tool()` times execution via `time.perf_counter()`, applies redaction, and records traces into `TOOL_TRACES`.
- **Optional Authentication**: [`backend/app/core/auth.py`](file:///c:/NEXORA-AI-TESTING-PLATFORM/backend/app/core/auth.py)
  - `verify_optional_auth()` is a reusable FastAPI dependency backed by `APIKeyHeader(name="X-API-Key", auto_error=False)` and `HTTPBearer(auto_error=False)`, so anonymous callers are never rejected.
  - Accepts either credential (Bearer takes precedence) and reports `{"authenticated": bool, "token_prefix": …}`.
  - Deterministic denied-access sentinels: `invalid-token-test` → `401 Unauthorized`, `forbidden-token-test` → `403 Forbidden`, both using the standard `{"message": ...}` error envelope.
  - Attached via `Depends(verify_optional_auth)` to all `/api/v1/leads` endpoints ([`crm.py`](file:///c:/NEXORA-AI-TESTING-PLATFORM/backend/app/api/routes/crm.py)), to `POST /api/v1/synthetic/agent/execute/{protocol}` ([`agent_execution.py`](file:///c:/NEXORA-AI-TESTING-PLATFORM/backend/app/api/routes/agent_execution.py)), and to the SSE stream route; sentinels are rejected before any handler logic runs.
- **SSE Live Trace Streaming**: [`backend/app/api/routes/streaming.py`](file:///c:/NEXORA-AI-TESTING-PLATFORM/backend/app/api/routes/streaming.py)
  - `GET /api/v1/test-runs/{run_id}/stream` returns an `EventSourceResponse`; unknown runs get a structured `404` before the stream opens.
  - Polls `get_traces_for_run(run_id)` every 1s and emits `tool_trace` frames, de-duplicated by a stable `call_id:timestamp` key (also the SSE `id`).
  - Emits a terminal `run_status` frame (`run_id`, `state`, `message`, `completed_at`) and closes on `completed` / `failed` / `cancelled` / `passed`, or when `request.is_disconnected()`.

---

## 5. Testing & Verification Status

### Automated Pytest Suite
- **Command**: `python -m pytest` (using `backend/.venv/Scripts/python.exe`)
- **Result**: **`38 passed`** in 0.98s
  - `tests/test_api_contracts.py` (4 passed):
    - `test_agent_registration_and_validation`
    - `test_test_run_contract_and_events`
    - `test_environment_and_evaluation_contract`
    - `test_crm_fault_and_latency_injection`
  - `tests/test_health.py` (1 passed):
    - `test_health_endpoint`
  - `tests/test_protocol_adapters.py` (7 passed):
    - `test_rest_adapter_round_trip`
    - `test_openai_adapter_parses_function_payload_and_formats_tool_message`
    - `test_adapter_factory_defaults_and_aliases`
    - `test_execute_rest_tool_round_trip`
    - `test_execute_openai_function_call_returns_tool_message`
    - `test_execute_normalizes_unknown_tool_and_parse_failures`
    - `test_execute_rejects_unknown_protocol`
  - `tests/test_tracing.py` (8 passed):
    - `test_redact_sensitive_data_masks_keys_recursively`
    - `test_redact_sensitive_data_scrubs_inline_secrets`
    - `test_execute_and_trace_tool_persists_redacted_telemetry`
    - `test_execute_and_trace_tool_captures_failures`
    - `test_execution_dispatcher_records_and_exposes_traces`
    - `test_traces_endpoints_handle_missing_records`
    - `test_execution_dispatcher_writes_tool_call_event_for_run`
    - `test_execution_dispatcher_writes_failure_tool_call_event`
  - `tests/test_crm.py` (5 passed):
    - `test_crm_crud_lifecycle_and_state_changes`
    - `test_crm_invalid_payloads_rejected_consistently`
    - `test_crm_missing_resources_return_structured_404`
    - `test_crm_query_boundary_validation`
    - `test_crm_repeated_and_concurrent_operations`
  - `tests/test_auth.py` (9 passed):
    - `test_optional_auth_allows_anonymous_requests`
    - `test_optional_auth_accepts_api_key_header`
    - `test_optional_auth_accepts_bearer_token`
    - `test_optional_auth_prefers_bearer_token_over_api_key`
    - `test_optional_auth_simulates_unauthorized_access`
    - `test_optional_auth_simulates_forbidden_access`
    - `test_crm_route_allows_anonymous_requests`
    - `test_crm_route_simulates_unauthorized_access`
    - `test_execution_route_simulates_forbidden_access`
  - `tests/test_streaming.py` (4 passed):
    - `test_stream_unknown_run_returns_404`
    - `test_stream_emits_run_status_and_terminates_for_terminal_run`
    - `test_stream_emits_recorded_tool_traces_before_terminal_status`
    - `test_stream_rejects_denied_access_sentinels`

### Frontend Vitest Suite (`apps/web`)
- **Command**: `npm test --workspace @nexora/web` (Vitest 5 + jsdom + Testing Library)
- **Result**: **`26 passed`** (2 files)
  - `src/hooks/useTestRunStream.test.tsx` (14 passed): idle without a run, connecting → connected transition, trace append, success/failure traces, non-terminal vs terminal `run_status` (stream close), malformed payload tolerance, de-duplication, transient → reconnecting → recovery, fatal error, run-id switch reset, cleared run, unmount cleanup.
  - `src/components/TraceStreamViewer.test.tsx` (12 passed): no-run empty state, connecting state, trace rendering (name/call id/duration), run-status updates, success/failure labels, REST status seeding, malformed payload tolerance, fatal error alert, reconnect → recover, run-id switch, sensitive-value redaction, long tool names.
- **Type check**: `npm run lint --workspace @nexora/web` (`tsc --noEmit`) passes.
- **Build**: `npm run build --workspace @nexora/web` (`tsc --noEmit && vite build`) succeeds (21 modules; `dist/assets/index-*.js` ~152.8 kB / 49.9 kB gzip).
- **Limitation**: the viewer is verified with a mocked `EventSource` (jsdom has no SSE); the browser-to-backend path is covered indirectly by the backend `tests/test_streaming.py` SSE contract tests.

### Live Verification Cycles
1. **Synthetic Environment Lifecycle**: Verified `POST /environments` (`provisioning`) → `POST /environments/{id}/ready` (`ready`) → `POST /environments/{id}/stop` (`stopped`).
2. **Synthetic CRM Leads Lifecycle**: Verified `POST /leads` (201) → `GET /leads/{id}` (200) → `PUT /leads/{id}` (200) → `DELETE /leads/{id}` (204) → `GET /leads/{id}` (404).
3. **Fault Simulation & Resiliency**: Verified `GET /leads?simulated_latency_ms=10` (200 delay), `GET /leads?inject_error=429` (429 status), `GET /leads?inject_error=200` (422 validation failure).
4. **Protocol Adapter Execution**: Verified `POST /synthetic/agent/execute/rest` and `POST /synthetic/agent/execute/openai` with function payloads.
5. **Tool-Call Tracing & Secret Redaction**: Verified `POST /synthetic/agent/execute/rest?run_id={run_id}` with secret parameter `api_key`; confirmed `GET /test-runs/{run_id}/traces` returns `api_key == "[REDACTED]"` with UTC timestamp, and `GET /test-runs/{run_id}/events` returns the linked `tool_call` event with the redacted payload.
6. **Optional Authentication**: Verified anonymous (`authenticated: false`), `X-API-Key` and `Bearer` acceptance with token prefixes, Bearer precedence over the API key, and simulated `401` / `403` denied-access responses via the synthetic sentinels — both on an isolated probe route and on the real `/api/v1/leads` and `/api/v1/synthetic/agent/execute/{protocol}` routers.
7. **SSE Live Trace Streaming**: Verified `GET /test-runs/{run_id}/stream` returns `404` for unknown runs, streams exactly one deduplicated `tool_trace` frame (redacted payload) followed by a terminal `run_status` frame with `"state": "cancelled"` for a cancelled run, and rejects the forbidden sentinel with `403`.

---

## 6. Team Next Steps & Upcoming Work

- **Prajwal (Simulation & Profiling)**:
  - ✅ Protocol adapter layer (`REST`, OpenAI/LangChain) with execution dispatcher delivered.
  - ✅ Tool-call tracing with sensitive-data redaction delivered (`/test-runs/{run_id}/traces`).
  - ✅ Execution-event integration for profiled tool calls and focused CRM contract coverage delivered (`tests/test_crm.py`, 5 tests).
  - ✅ SSE live trace streaming delivered (`GET /api/v1/test-runs/{run_id}/stream`; 4 tests in `tests/test_streaming.py`).
  - ✅ SSE stream wired into the dashboard client: `useTestRunStream` hook + `TraceStreamViewer` component, run selection/creation via the REST client, 26 Vitest tests.
  - Next: Add additional adapters (Anthropic tool use, MCP tool schema execution) and add a browser-level end-to-end check for the live stream.
- **Rajath (Provisioning & Infrastructure)**:
  - Connect Docker Engine container lifecycle management for real PostgreSQL, MySQL, and MongoDB synthetic environments.
- **Naaneshwar (Integrations & Service Layer)**:
  - ✅ Optional authentication dependency delivered (`backend/app/core/auth.py`): accepts `X-API-Key` / `Authorization: Bearer`, supports simulated 401/403 denial, 9 contract tests (`tests/test_auth.py`; 34 tests total).
  - ✅ Dependency attached to all `/api/v1/leads` routes and `POST /api/v1/synthetic/agent/execute/{protocol}` via `Depends(verify_optional_auth)`; anonymous traffic still flows, sentinels return 401/403.
  - Next: Extend the dependency to the remaining routers (agents, test runs, environments) and enforce real API keys instead of the synthetic sentinels.
  - Transition backend store from in-memory dictionary to persistent storage (PostgreSQL / Redis).
- **Rahul (Workflows & Evaluation)**:
  - Connect LangGraph orchestrator and automated test scoring evaluation flows.