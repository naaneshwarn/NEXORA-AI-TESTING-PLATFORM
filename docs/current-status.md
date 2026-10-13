# NEXORA AI Testing Platform — Current Status

**Last Updated:** October 12, 2026  
**Active Branch:** `feature/synthetic-api`  
**Base Commit:** `312f3b6` (*feat(backend): implement synthetic environment lifecycle and ready endpoint*)  
**Upstream Base:** `25dab08` (*Publish NEXORA AI Testing Platform source code*)  

---

## 1. Executive Summary

The NEXORA platform foundation is fully functional in a local-development-first mode. All versioned core REST endpoints under `/api/v1` are active and backed by an in-memory store.

Key milestones achieved on the `feature/synthetic-api` branch:
1. **Synthetic Environment Lifecycle**: Enhanced state transitions (`provisioning` → `ready` → `stopped`), complete with the `/ready` transition endpoint, state persistence, and full test suite validation.
2. **Stateful Synthetic CRM API**: Added CRM Lead management endpoints (`/api/v1/leads`) backed by in-memory state storage with full CRUD capabilities, Pydantic schema validation, and standard `ApiEnvelope` packaging.
3. **Fault Simulation & Resiliency Testing**: Implemented deterministic fault injection (`simulated_latency_ms` and `inject_error` query parameters) on CRM read endpoints with non-blocking `asyncio.sleep`, strict Pydantic range validation (`422`), error code simulation (`429`, `500`), and zero state mutation guarantees.
4. **Protocol Adapter Layer (Phase 3)**: Added a modular adapter layer (`RESTProtocolAdapter`, `OpenAIFunctionAdapter`, `AdapterFactory`) with unified `AgentToolRequest` / `AgentToolResponse` models and a synthesis execution dispatcher at `/api/v1/synthetic/agent/execute/{protocol}`.
5. **Agent Profiling & Tool-Call Tracing (Phase 3)**: Added redacted tool-call telemetry (`ToolCallTraceCreate` / `ToolCallTraceResponse`), a recursive sensitive-data redaction utility, in-memory trace storage (`TOOL_TRACES`), and an async `execute_and_trace_tool` wrapper integrated into the execution dispatcher and exposed at `/api/v1/test-runs/{run_id}/traces`.

---

## 2. Service & Repository Status

| Component | Path | Technology | Current Status |
| :--- | :--- | :--- | :--- |
| **Backend API** | [backend/](file:///c:/NEXORA-AI-TESTING-PLATFORM/backend/) | FastAPI + Python 3.13 | ✅ Active, verified, health, synthetic env, CRM & fault injection routes functional |
| **Frontend UI** | [apps/web/](file:///c:/NEXORA-AI-TESTING-PLATFORM/apps/web/) | React + TypeScript + Vite | 🟡 Scaffold retained for dashboard & orchestration UI |
| **Legacy/Node API** | [apps/api/](file:///c:/NEXORA-AI-TESTING-PLATFORM/apps/api/) | Node.js + Express | 🟡 Placeholder service retained for compatibility |
| **Shared Lib** | [packages/shared/](file:///c:/NEXORA-AI-TESTING-PLATFORM/packages/shared/) | TypeScript | ✅ Common types and utilities retained |
| **Documentation** | [docs/](file:///c:/NEXORA-AI-TESTING-PLATFORM/docs/) | Markdown | ✅ Architecture, API contracts, changes log, and status fully documented |

---

## 3. API Endpoints & Contract Implementation Status

All endpoints are versioned under `/api/v1` (with the exception of root `/health`) using standard `ApiEnvelope` packaging:

| Domain | Route | Method | Status | Notes |
| :--- | :--- | :--- | :--- | :--- |
| **Health** | `/api/v1/health` | `GET` | ✅ Operational | Baseline status check |
| **Root Health**| `/health` | `GET` | ✅ Operational | Lightweight service ping |
| **Agents** | `/api/v1/agents` | `POST` | ✅ Operational | Agent registration; enforces 409 conflict |
| **Agents** | `/api/v1/agents/{agent_id}` | `GET` | ✅ Operational | Inspect registered agent configuration |
| **Environments**| `/api/v1/environments` | `POST` | ✅ Operational | Provisions synthetic env (`status: provisioning`) |
| **Environments**| `/api/v1/environments/{environment_id}` | `GET` | ✅ Operational | Fetches environment status and endpoint |
| **Environments**| `/api/v1/environments/{environment_id}/ready` | `POST` | ✅ Operational | Transitions status to `ready` |
| **Environments**| `/api/v1/environments/{environment_id}/stop` | `POST` | ✅ Operational | Transitions status to `stopped` |
| **Test Runs** | `/api/v1/test-runs` | `POST` | ✅ Operational | Queues scenario test run |
| **Test Runs** | `/api/v1/test-runs/{run_id}` | `GET` | ✅ Operational | Fetches execution state |
| **Test Runs** | `/api/v1/test-runs/{run_id}/cancel` | `POST` | ✅ Operational | Cancels active run |
| **Events** | `/api/v1/test-runs/{run_id}/events` | `GET` | ✅ Operational | Retrieves tool-call execution traces |
| **Evaluations** | `/api/v1/evaluations` | `POST` | ✅ Operational | Submits evaluation result and creates report |
| **Reports** | `/api/v1/reports/{report_id}` | `GET` | ✅ Operational | Retrieves final evaluation report |
| **CRM Leads** | `/api/v1/leads` | `POST` | ✅ Operational | Creates new CRM lead (`status: 201`, validates name/email/status) |
| **CRM Leads** | `/api/v1/leads` | `GET` | ✅ Operational | Lists all leads; supports `simulated_latency_ms` & `inject_error` |
| **CRM Leads** | `/api/v1/leads/{lead_id}` | `GET` | ✅ Operational | Retrieves specific lead (`404` if missing); supports fault injection |
| **CRM Leads** | `/api/v1/leads/{lead_id}` | `PUT` | ✅ Operational | Updates existing lead fields (`404` if not found) |
| **CRM Leads** | `/api/v1/leads/{lead_id}` | `DELETE` | ✅ Operational | Deletes CRM lead by ID (`status: 204`, `404` if not found) |
| **Synthetic Agent** | `/api/v1/synthetic/agent/execute/{protocol}` | `POST` | ✅ Operational | Protocol-agnostic tool dispatcher (`rest`, `openai`, `langchain`); normalizes request/response and records `execution_time_ms` |
| **Traces** | `/api/v1/test-runs/{run_id}/traces` | `GET` | ✅ Operational | Returns redacted tool-call telemetry (`ToolCallTraceResponse`) for a run |

---

## 4. Synthetic API, Resiliency & Protocol Adapter Architecture

- **Schema**: [`backend/app/schemas/crm.py`](file:///c:/NEXORA-AI-TESTING-PLATFORM/backend/app/schemas/crm.py)
  - `CRMLeadCreate`: Defines lead fields with validation (`name` with `min_length=2, max_length=100`, `email`, optional `company`, and `status` in `{"new", "contacted", "qualified", "closed"}`).
  - `CRMLeadResponse`: Extends `CRMLeadCreate` with `id`, `created_at`, and `updated_at`.
- **In-Memory Store**: [`backend/app/core/store.py`](file:///c:/NEXORA-AI-TESTING-PLATFORM/backend/app/core/store.py)
  - State dictionary `CRM_LEADS: dict[str, dict]`.
  - CRUD helper functions: `create_crm_lead`, `get_crm_lead`, `list_crm_leads`, `update_crm_lead`, `delete_crm_lead`.
  - Exposed via the singleton `Store` instance `store`.
- **Fault Injection & Latency Simulation**: [`backend/app/api/routes/crm.py`](file:///c:/NEXORA-AI-TESTING-PLATFORM/backend/app/api/routes/crm.py)
  - `SimulatedLatencyMs`: `Query(ge=0, le=60000)` introduces non-blocking delays via `asyncio.sleep` to prevent blocking the async event loop.
  - `InjectError`: `Query(ge=400, le=599)` simulates HTTP status codes (e.g., `429` rate limiting, `500` server errors).
  - Out-of-range status codes (e.g., `200`) or invalid latencies are automatically rejected with `422 Unprocessable Entity`.
  - Faults are evaluated prior to data retrieval, guaranteeing zero corruption of synthetic state.
- **Router Registration**: [`backend/app/main.py`](file:///c:/NEXORA-AI-TESTING-PLATFORM/backend/app/main.py)
  - Router registered with prefix `settings.api_prefix` (`/api/v1`).
- **Protocol Adapter Layer**: [`backend/app/core/adapters.py`](file:///c:/NEXORA-AI-TESTING-PLATFORM/backend/app/core/adapters.py)
  - Unified models `AgentToolRequest` (`call_id`, `tool_name`, `parameters`, `agent_id`) and `AgentToolResponse` (`call_id`, `success`, `data`, `error`, `execution_time_ms`).
  - `BaseProtocolAdapter` abstract base defining `parse_request()` and `format_response()`.
  - `RESTProtocolAdapter`: parses flat REST/OpenAPI payloads and returns the normalized response dict.
  - `OpenAIFunctionAdapter`: parses `{"function": {"name", "arguments"}}` (arguments as a dict or JSON string) and emits OpenAI tool messages (`{"role": "tool", "tool_call_id", "content"}`).
  - `AdapterFactory.get_adapter(protocol_type)` resolves `rest` (default), `openai`, `openai_function`, `function`, `langchain`; unknown protocols raise `UnknownProtocolError` → `400`.
- **Synthetic Tool Registry**: [`backend/app/core/tools.py`](file:///c:/NEXORA-AI-TESTING-PLATFORM/backend/app/core/tools.py)
  - Maps tool names and aliases (`list_crm_leads`, `crm.get_lead`, ...) to CRM store operations; raises `ToolNotFoundError` / `ToolExecutionError`.
- **Execution Dispatcher**: [`backend/app/api/routes/agent_execution.py`](file:///c:/NEXORA-AI-TESTING-PLATFORM/backend/app/api/routes/agent_execution.py)
  - `POST /synthetic/agent/execute/{protocol}` parses via the adapter, executes the tool while timing it, and re-formats the result into the protocol-specific shape; exceptions are captured and normalized (never a raw `500`).
  - Accepts an optional `run_id` query parameter; when supplied, execution flows through `execute_and_trace_tool` so redacted telemetry is persisted.
- **Tool-Call Telemetry**: [`backend/app/core/telemetry.py`](file:///c:/NEXORA-AI-TESTING-PLATFORM/backend/app/core/telemetry.py)
  - `execute_and_trace_tool(run_id, call_id, tool_name, parameters, executor=None)` measures high-resolution timing (`time.perf_counter`), classifies failures, and persists redacted traces.
  - Returns a `ToolExecutionOutcome` carrying the raw result for the agent plus the sanitized `ToolCallTraceResponse`.
- **Sensitive Data Redaction**: [`backend/app/core/redaction.py`](file:///c:/NEXORA-AI-TESTING-PLATFORM/backend/app/core/redaction.py)
  - `redact_sensitive_data()` recursively masks sensitive keys (`password`, `token`, `api_key`, `secret`, `authorization`, `credit_card`, ...) and scrubs inline Bearer/Basic tokens, `key=value` assignments, `sk-` keys, AWS key IDs, and JWTs.
- **Trace Storage**: [`backend/app/schemas/tracing.py`](file:///c:/NEXORA-AI-TESTING-PLATFORM/backend/app/schemas/tracing.py) + [`backend/app/core/store.py`](file:///c:/NEXORA-AI-TESTING-PLATFORM/backend/app/core/store.py)
  - `ToolCallTraceCreate` / `ToolCallTraceResponse` models; `TOOL_TRACES` indexed by run with `record_tool_trace()` and `get_traces_for_run()`.

---

## 5. Testing & Verification Status

### Automated Pytest Suite
- **Command**: `python -m pytest` (using `backend/.venv`)
- **Result**: **`18 passed`**
  - `tests/test_api_contracts.py` (4 passed):
    - `test_agent_registration_and_validation`
    - `test_test_run_contract_and_events`
    - `test_environment_and_evaluation_contract`
    - `test_crm_fault_and_latency_injection` (validates baseline reads, latency delay, 429/500 simulation, state preservation, 422 range checking)
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
  - `tests/test_tracing.py` (6 passed):
    - `test_redact_sensitive_data_masks_keys_recursively`
    - `test_redact_sensitive_data_scrubs_inline_secrets`
    - `test_execute_and_trace_tool_persists_redacted_telemetry`
    - `test_execute_and_trace_tool_captures_failures`
    - `test_execution_dispatcher_records_and_exposes_traces`
    - `test_traces_endpoints_handle_missing_records`

### Live Verification Cycles

#### A. Synthetic Environment Lifecycle
Verified end-to-end HTTP request cycle:
1. `POST /api/v1/environments` → `201 Created` (`status: provisioning`)
2. `GET /api/v1/environments/{environment_id}` → `200 OK`
3. `POST /api/v1/environments/{environment_id}/ready` → `200 OK` (`status: ready`)
4. `POST /api/v1/environments/{environment_id}/stop` → `200 OK` (`status: stopped`)

#### B. Synthetic CRM Leads Lifecycle
Verified end-to-end HTTP request cycle:
1. `POST /api/v1/leads` → `201 Created` (returns initialized lead with ID and UTC timestamp)
2. `GET /api/v1/leads` → `200 OK` (returns array of lead objects)
3. `GET /api/v1/leads/{lead_id}` → `200 OK` (retrieves created lead)
4. `PUT /api/v1/leads/{lead_id}` → `200 OK` (updates fields and assigns `updated_at` timestamp)
5. `DELETE /api/v1/leads/{lead_id}` → `204 No Content`
6. `GET /api/v1/leads/{lead_id}` → `404 Not Found` (confirms deletion)

#### C. Fault Simulation & Resiliency Verification
Verified query parameter behavior on `/api/v1/leads` and `/api/v1/leads/{lead_id}`:
1. `GET /api/v1/leads?simulated_latency_ms=50` → `200 OK` (measurable ≥50ms delay, intact payload)
2. `GET /api/v1/leads?inject_error=429` → `429 Too Many Requests` (`error.code: http_429`)
3. `GET /api/v1/leads/{lead_id}?inject_error=500` → `500 Internal Server Error` (`error.code: http_500`)
4. `GET /api/v1/leads/{lead_id}` → `200 OK` (confirms state preserved after fault injection)
5. `GET /api/v1/leads?inject_error=200` → `422 Unprocessable Entity` (non-error status code rejected)

#### D. Protocol Adapter Execution
Verified through the adapter test suite:
1. `POST /api/v1/synthetic/agent/execute/rest` with `create_crm_lead` → `200 OK` (normalized `data.id` returned, `execution_time_ms` recorded)
2. `POST /api/v1/synthetic/agent/execute/openai` with a `list_crm_leads` function call → OpenAI tool message (`role: tool`, `tool_call_id`, JSON `content`)
3. Unknown tool → normalized failure (`error.code: tool_not_found`)
4. Malformed REST payload → normalized failure (`error.code: invalid_request`)
5. Unknown protocol (`grpc`) → `400 Bad Request` with standard error envelope

#### E. Tool-Call Tracing & Redaction
Verified through the tracing test suite:
1. `POST /api/v1/synthetic/agent/execute/rest?run_id={run_id}` with an `api_key` parameter → `200 OK`, execution succeeds
2. `GET /api/v1/test-runs/{run_id}/traces` → `200 OK`; the stored trace shows `parameters.api_key == "[REDACTED]"` with a UTC `timestamp`
3. Unknown tool → normalized failure (`error.code: tool_not_found`) persisted with redacted parameters
4. `run_id` referencing a missing run → `404 Not Found`
5. `GET /api/v1/test-runs/{run_id}/traces` before any execution → `404 Not Found`

---

## 6. Team Next Steps & Upcoming Work

- **Prajwal (Simulation & Profiling)**:
  - ~~Implement protocol adapters and simulation behavior for target agents.~~ ✅ Protocol adapter layer (`REST`, OpenAI/LangChain) with execution dispatcher delivered.
  - ~~Expand execution event generator to stream dynamic `ToolCallTrace` data during test runs.~~ ✅ Tool-call tracing with sensitive-data redaction delivered (`/test-runs/{run_id}/traces`).
  - Add streaming/SSE transport for live trace emission and additional protocol adapters (e.g. gRPC, MCP) on top of `AdapterFactory`.
- **Rajath (Provisioning & Infrastructure)**:
  - Connect Docker Engine container lifecycle management for real PostgreSQL, MySQL, and MongoDB synthetic environments.
- **Naaneshwar (Integrations & Service Layer)**:
  - Transition backend store from in-memory dictionary to persistent storage (e.g., PostgreSQL / Redis) as modules evolve.
- **Rahul (Workflows & Evaluation)**:
  - Connect LangGraph orchestrator and automated test scoring evaluation flows.
