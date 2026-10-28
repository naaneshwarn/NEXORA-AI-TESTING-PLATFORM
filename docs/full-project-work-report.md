# NEXORA AI Testing Platform — Full Project Work Report

**Document:** Complete record of all work completed to date
**Last Updated:** October 28, 2026
**Branch:** `feature/integration-wpb-wpd`
**Latest Commit:** `412eca5` — *Launch hardening: real API-key auth, durable persistence, target agents, synthetic API, CI/Docker*
**Remote:** https://github.com/naaneshwarn/NEXORA-AI-TESTING-PLATFORM

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Verification Totals](#2-verification-totals)
3. [Repository History](#3-repository-history)
4. [Architecture & Module Boundaries](#4-architecture--module-boundaries)
5. [Work Package A — Backend & Target Agents (Naaneshwar)](#5-work-package-a--backend--target-agents-naaneshwar)
6. [Work Package B — Docker Environments (Rajath)](#6-work-package-b--docker-environments-rajath)
7. [Work Package C — Synthetic API & Adapters (Prajwal)](#7-work-package-c--synthetic-api--adapters-prajwal)
8. [Work Package D — Workflow, Evaluation & Reports (Rahul)](#8-work-package-d--workflow-evaluation--reports-rahul)
9. [Cross-Cutting: Launch Hardening](#9-cross-cutting-launch-hardening)
10. [Complete API Surface](#10-complete-api-surface)
11. [Frontend (Dashboard)](#11-frontend-dashboard)
12. [Testing & Test Inventory](#12-testing--test-inventory)
13. [Live Verification History](#13-live-verification-history)
14. [Security Posture](#14-security-posture)
15. [Infrastructure: CI, Docker, Compose](#15-infrastructure-ci-docker-compose)
16. [Configuration Reference](#16-configuration-reference)
17. [How to Run](#17-how-to-run)
18. [File Inventory](#18-file-inventory)
19. [Known Limitations](#19-known-limitations)
20. [Remaining Work](#20-remaining-work)

---

## 1. Executive Summary

NEXORA is an AI-powered testing platform for autonomous agents. It orchestrates
multi-step test workflows, provisions synthetic environments, drives target
agents through multiple wire protocols, injects deterministic faults, and
produces evaluation reports — all against a fully synthetic, credential-free
surface that never touches real infrastructure or requires LLM API keys.

**All four Phase 3 work packages (A–D) are implemented, integrated, and
verified end-to-end.** The backend and frontend run separately, the complete
API is documented on OpenAPI/Swagger, state survives restarts, authentication
can be enforced with API keys, and the dashboard drives real workflow runs
with live streaming.

### What the platform does today

1. **Register a target agent** → it becomes immediately executable (no agent runtime to deploy).
2. **Create a test run** bound to a deterministic scenario → the workflow engine executes it in the background.
3. **Watch live** over Server-Sent Events as tool calls execute (redacted, timed).
4. **Read the evaluation report** — weighted score, per-criterion rationale, evidence-backed findings, pass/fail against a configurable threshold.
5. **Test resilience** by injecting deterministic faults (latency, HTTP errors) into the synthetic external surface.
6. **Provision synthetic databases** (postgres/mysql/mongodb/redis/neo4j/docker) through a full lifecycle — with correct graceful failure when no Docker daemon exists.

### Design principles honored

- **Deterministic** — no wall-clock, randomness, network, or LLM calls in scoring; fixed inputs always produce identical outputs.
- **Credential-free** — everything runs against the synthetic CRM/tool registry; no external API keys needed.
- **Contract-stable** — Phase 2 schemas were never edited; additive changes only.
- **Secrets never leak** — recursive redaction applied to every telemetry artifact before persistence.
- **Zero new runtime dependencies** — the workflow engine is a hand-built LangGraph-compatible state machine; real LangGraph can slot in later without API changes.

---

## 2. Verification Totals

| Suite | Result | Notes |
|---|---|---|
| **Backend pytest** | **268 collected → 265 passed, 3 skipped** | 3 skips are Docker-gated live integration tests (auto-skip without a daemon) |
| **Frontend Vitest** | **34 passed** (4 files) | Includes 4 new API-key auth tests |
| **Frontend typecheck** | `tsc --noEmit` clean | Zero errors |
| **Frontend build** | `vite build` OK | ~165 kB JS / 52 kB gzip |
| **Live API smoke** | **27/27 checks passed** | Headers, OpenAPI, descriptor, faults, agents, workflow, report, traces, persistence |
| **Live auth smoke** | **17/17 checks passed** | With keys configured: 401/403 enforcement, reads open, sentinels, descriptor |
| **Browser E2E** | Passed, zero console errors | Run created via UI auto-polled Queued → Passed |

Backend suite runtime: ~7s. Frontend suite runtime: ~4s.

---

## 3. Repository History

### Branch topology

| Branch | Purpose | Status |
|---|---|---|
| `chore/project-foundation` | Initial scaffold (web + Node API + shared) | Merged (base) |
| `feature/synthetic-api` | Phase 2/3: CRM, faults, adapters, tracing, auth, SSE | Merged |
| `feature/naaneshwar-backend-integration` | FastAPI backend contracts | Merged (PR #10) |
| `feature/docker-environment` | WP-B: Docker environment lifecycle | Merged (PR #9) |
| `feature/workflow-evaluation-reporting` | WP-D: workflow, evaluation, reports | Merged |
| `feature/integration-wpb-wpd` | **Current:** all WPs merged + launch hardening | **HEAD `412eca5`** |

### Key commits (chronological)

```
412eca5 Launch hardening: real API-key auth, durable persistence, target agents, synthetic API, CI/Docker
f96f5e8 Fix dashboard create-run to bind CRM scenario for live streaming
8b36798 Harden error handling + fix unreachable workflow report IDs
2646b6d merge(wp-d): LangGraph-style workflow, scenarios, security checks, evaluation, reports
7a0df53 merge(wp-b): Docker environment lifecycle + synthetic PostgreSQL provisioning
6132565 feat(workflow): launch-hardening runtime (durable contexts, config, metrics, recovery)
e146be5 fix(workflow): second audit round - injectable agent client, dedup, crash-report boundary
15111b8 fix(workflow): audit fixes - env failure reports, explicit cleanup node, standalone security evaluator
0fe30da feat(workflow): add orchestrator service with cancellation, failures, and reporting
484eeb4 feat(workflow): add scenario registry, mock agent client, and deterministic evaluator
4535298 feat(workflow): add deterministic graph engine and rich report schemas
c04424d fix(environments): harden Docker provider from real-daemon verification (WP-B)
27aa705 feat(environments): Docker lifecycle + synthetic PostgreSQL provisioning (WP-B)
773a182 feat(dashboard): add real-time SSE trace viewer
b812020 feat(auth+stream): implement optional auth dependency, SSE live streaming, test suite
1f63578 feat: integrate FastAPI backend contracts
```

All branches are in sync with their remotes. No unpushed commits exist.

---

## 4. Architecture & Module Boundaries

NEXORA is a **modular monolith** with clear seams reserved for future
multi-service extraction.

```
NEXORA-AI-TESTING-PLATFORM/
├── backend/                     # Python FastAPI — CANONICAL API (:8000)
│   ├── app/
│   │   ├── api/routes/          # Thin HTTP layer (status codes + envelopes)
│   │   ├── core/                # Config, auth, middleware, store, adapters,
│   │   │                        #   telemetry, redaction, tools, errors, persistence
│   │   ├── integrations/
│   │   │   ├── target_agents/   # WP-A: TargetAgent ABC, mock, registry
│   │   │   ├── environment/     # WP-B: Docker provider, manager, seeding
│   │   │   └── synthetic_api/   # WP-C: faults, repository, descriptor
│   │   ├── schemas/             # Pydantic contracts (Phase 2 frozen, additive only)
│   │   ├── services/            # Business logic (agent execution)
│   │   └── workflow/            # WP-D: graph, scenarios, agent client,
│   │                            #   evaluator, security checks, runtime, service
│   ├── tests/                   # 268 pytest tests across 24 modules
│   └── requirements.txt
├── apps/web/                    # React + TypeScript + Vite dashboard (:3000)
├── apps/api/                    # Node/Express placeholder (legacy, retained)
├── packages/shared/             # Shared TypeScript utilities
├── docs/                        # Architecture, contracts, status reports
├── .github/workflows/ci.yml     # CI: backend pytest + frontend build
├── backend/Dockerfile           # Non-root backend image
├── apps/web/Dockerfile          # Node build → nginx serve
├── apps/web/nginx.conf          # SPA fallback + security headers
└── docker-compose.yml           # Full stack + docker_provisioning profile
```

### Layering rule

```
HTTP routes  →  services  →  integrations / workflow  →  core (store, tools)
     ↑              ↑                    ↑
  status codes   business logic    external-system adapters
  + envelopes
```

Routes never contain business logic; services never import FastAPI; the store
is the single source of truth shared by every module.

### Team ownership (per the Architecture & Ownership Guide)

| Member | Ownership |
|---|---|
| **Naaneshwar** | API route design, service layer, target-agent adapters, external integration boundaries, auth |
| **Rajath** | Synthetic environment provisioning, Docker lifecycle, infrastructure |
| **Prajwal** | Protocol adapters, synthetic API surface, tool-call tracing, fault injection |
| **Rahul** | Workflow orchestration, evaluation engine, reporting, dashboard |

---

## 5. Work Package A — Backend & Target Agents (Naaneshwar)

### 5.1 Target-Agent Abstraction (`app/integrations/target_agents/`)

**The problem solved:** agents needed a pluggable execution backend so a live
LLM provider could replace the deterministic mock without touching route or
workflow code.

- **`base.py`** — `TargetAgent` abstract base class defining the contract:
  - `async execute_tool(request: AgentToolRequest, *, run_id: str | None) -> AgentToolResponse`
  - `async healthcheck() -> bool`
  - `describe() -> TargetAgentDescriptor` (serializable introspection)
  - `capabilities() -> list[str]`
  - Error hierarchy: `TargetAgentError` → `TargetAgentNotFoundError`
- **`mock.py`** — `MockTargetAgent`: the reference implementation. Executes tool
  calls through the synthetic tool registry via `execute_and_trace_tool`, so
  every call is timed, redacted, and (when bound to a run) persisted as a trace.
  Capabilities: `tool_execution`, `tracing`, `redaction`, `deterministic`.
- **`__init__.py`** — `TargetAgentRegistry` (thread-safe, RLock-guarded) with
  `register/get/remove/clear/list/descriptors/resolve`, plus the process-wide
  `target_agents` singleton pre-seeded with `mock-agent`.

**Resolution order** (`resolve_target_agent`):
1. An explicitly registered implementation (where live providers will register).
2. A `MockTargetAgent` built from any agent registered via `POST /agents` —
   registration alone makes an agent executable.
3. `TargetAgentNotFoundError` → surfaced as HTTP 404.

`resolve_target_agent(None)` returns the shared default mock.

### 5.2 Agent-Execution Service (`app/services/agent_execution.py`)

Extracted from the HTTP route so the flow is testable and reusable by
workflows/CLI/gRPC without duplication.

```
protocol → adapter (400 on unknown)
         → run validation (404 on unknown run)
         → payload parsing (in-band invalid_request envelope)
         → target-agent resolution (404 on unknown agent)
         → TargetAgent.execute_tool (traced + redacted)
         → tool_call execution event (when run attached)
         → protocol-formatted response
```

Public API: `execute_agent_tool_call(protocol, payload, *, run_id, agent_id)`,
`RunNotFoundError`, `call_id_hint()`. The route
(`/api/v1/synthetic/agent/execute/{protocol}`) is now a thin HTTP mapping with
an optional `agent_id` query parameter (404 unknown agent).

### 5.3 Real API-Key Authentication (`app/core/auth.py`)

Replaced the optional-auth-only model with enforceable, mode-driven auth.

| Element | Detail |
|---|---|
| `configured_api_keys()` | Parses `NEXORA_API_KEYS` (comma-separated); blank entries ignored |
| `resolve_auth_mode()` | `auto` → `write` when keys exist, else `off`; explicit `write`/`full` without keys degrades to `off` |
| `requires_auth(method, path)` | Mode + method + path rules; health/schema paths always open |
| `authenticate_token(token, enforce=)` | Validates credential; raises 401/403 with standard envelope |
| `_token_is_valid()` | **Timing-safe**: `secrets.compare_digest` over every configured key, result accumulated so timing never reveals which key matched |
| `extract_token_from_headers()` | Accepts raw ASGI bytes mappings and Starlette Headers |
| `verify_optional_auth` | FastAPI dependency applying identical method/path rules |

**Accepted credentials:** `X-API-Key: <key>` or `Authorization: Bearer <key>`
(Bearer wins when both present).

**Synthetic sentinels** (honored in *every* mode, so denial handling is testable
without an identity provider):
- `invalid-token-test` → **401 Unauthorized**
- `forbidden-token-test` → **403 Forbidden**

**Always-open paths:** `/health`, `/api/v1/health`, `/v1/health`, `/v1/models`,
`/docs`, `/redoc`, `/openapi.json` — so container probes and API explorers keep
working in every mode.

### 5.4 Durable Core-Store Persistence (`app/core/persistence.py`)

Made the previously in-memory store survive process restarts.

- **What persists:** `AGENTS`, `TEST_RUNS`, `ENVIRONMENTS`, `EVENTS`, `REPORTS`,
  `TOOL_TRACES`, `WORKFLOW_REPORTS`, `CRM_LEADS` — the entire core state.
- **Where:** `NEXORA_STATE_DIR/store.json` (default `backend/.state/`).
- **Atomic writes:** temp file + `os.replace` — a crash mid-write can never
  corrupt the last good snapshot.
- **Corruption tolerant:** unreadable/malformed snapshot is logged and skipped;
  the process starts empty instead of crashing. Invalid individual records are
  skipped without dropping the rest.
- **Opt-out, not opt-in:** enabled by default; `NEXORA_STATE_DIR=""` disables.
  `tests/conftest.py` disables it at import time **and** via an autouse fixture
  so the suite stays hermetic.
- **Hook-based:** every mutator in `app/core/store.py` ends with
  `persistence.save()` (lock-guarded no-op when disabled).
- **Hydration:** `_hydrate_store` stages into local containers first so a
  mid-way failure cannot leave the store half-cleared; Pydantic rehydrates
  datetime fields (not JSON strings); UTF-8 BOM tolerated.

### 5.5 Middleware Stack (`app/core/middleware.py`)

Both are **pure ASGI** (not `BaseHTTPMiddleware`) so SSE streaming passes
through untouched.

Registration order (last added = outermost):

```
ObservabilityMiddleware   security headers + nexora.http request log
  └─ CORSMiddleware       answers preflight OPTIONS before auth
       └─ AuthMiddleware  edge-level API-key enforcement
            └─ application
```

- **`ObservabilityMiddleware`** — applies `SECURITY_HEADERS` to every response
  (including error responses, CORS preflights, and middleware-generated 401s)
  and logs `METHOD path -> status (X ms) client=ip:port`. Health/readiness
  probes are excluded from the log (they poll constantly). 5xx logged at WARNING.
- **`AuthMiddleware`** — rejects unauthenticated protected requests at the edge
  using the same error envelope as the app's exception handlers, so clients
  cannot tell whether a 401 came from middleware or a route dependency.

### 5.6 Environment Variables (pydantic-settings)

`Settings` gained `api_keys`, `auth_mode`, `state_dir` with **`NEXORA_*`
aliases** (a live-testing catch: pydantic-settings has no env prefix, so
`NEXORA_API_KEYS` silently did not map to `api_keys`). Fixed with
`AliasChoices("NEXORA_API_KEYS", "API_KEYS")` etc., keeping bare names working
as fallback. Regression-tested in `test_settings_env.py`.

---

## 6. Work Package B — Docker Environments (Rajath)

### 6.1 Environment Manager (`app/integrations/environment/manager.py`, 380 lines)

The service layer behind the environment routes. Owns the full lifecycle:

```
provision → ready → (reset) → stop → destroy
```

**Shared-schema rule honored:** the Phase 2 `SyntheticEnvironment.status`
literal (`provisioning | ready | stopped | failed | cancelled`) was **not**
edited. The finer stage (`created`/`seeding`/`resetting`/`destroyed`) is
carried in `metadata["lifecycle"]`, so intent is visible without a contract
change.

**Provider-agnostic:** depends on a `DatabaseProvider` protocol, so the real
`DockerProvider` and a deterministic mock are interchangeable — this is what
lets unit tests run with **no Docker**.

**Credential safety:** never places a password in `endpoint` or any
response-only field. Connection secrets live under `metadata["connection"]`;
`redact_connection()` produces the safe view used by routes and logs.

### 6.2 Docker Provider (`docker_provider.py`, 350 lines)

- Lazy SDK import — the API and unit tests run fine without the `docker` package;
  it is only required for live provisioning.
- `DockerUnavailableError` → environments correctly report
  `failed: "Docker Engine is unavailable"` when no daemon exists (**specified
  behavior, not a bug**).
- `ContainerSpec`/`ConnectionInfo` value objects; `DEFAULT_IMAGE`,
  `DEFAULT_INTERNAL_PORT` constants.

### 6.3 Database Seeding (`database_seed.py`, 135 lines)

Deterministic seed data applied after provisioning so environments are usable
immediately (e.g., synthetic PostgreSQL tables/rows).

### 6.4 Lifecycle Routes (`app/api/routes/environments.py`)

`POST /environments` (provision), `GET /environments/{id}` (status),
`POST .../ready`, `.../stop`, `.../reset`, `.../destroy`.

---

## 7. Work Package C — Synthetic API & Adapters (Prajwal)

### 7.1 Protocol Adapters (`app/core/adapters.py`, 137 lines)

Unified `AgentToolRequest`/`AgentToolResponse` models and a
`BaseProtocolAdapter` contract.

| Protocol | Wire shape |
|---|---|
| `rest` | `{call_id, tool_name, parameters}` → same shape back |
| `openai` (+ aliases `openai_function`, `function`) | OpenAI function-call shape; `function.name`/`function.arguments` (JSON-string tolerated); response is `role: tool`, `tool_call_id`, JSON-encoded `content` |
| `langchain` | LangChain tool-call shape |

`AdapterFactory.get_adapter()` resolves with alias support and raises
`UnknownProtocolError` listing supported protocols. `supported_protocols()`
backs the capability descriptor.

**Payload normalization:** `_coerce_parameters` accepts an already-decoded
object, a blank value, or a JSON-encoded object string (the shape OpenAI
function calling returns).

### 7.2 Synthetic API Package (`app/integrations/synthetic_api/`)

New package consolidating the emulated external surface:

- **`faults.py`** — the fault-injection query contract shared by read endpoints:
  - `SimulatedLatencyMs = Query(ge=0, le=60000)` — non-blocking `asyncio.sleep`
  - `InjectError = Query(ge=400, le=599)` — deterministic HTTP error
  - `apply_fault_injection()` — raises *immediately* on error (evaluated
    **before** any store operation, so an injected failure can never corrupt
    synthetic data); latency uses non-blocking sleep so the event loop stays free
  - `LATENCY_RANGE_MS`, `ERROR_CODE_RANGE` constants mirror the query constraints
- **`repository.py`** — `LeadRepository` seam over the store (CRUD + `exists` +
  `clear`); routes and tool handlers go through it instead of touching the store
  directly, giving one place for future paging/filtering/observability.
- **`schemas.py`** — descriptor models: `FaultInjectionSpec`,
  `AuthenticationSpec`, `RedactionSpec`, `SyntheticAPIDescriptor`.
- **`app.py`** — router publishing machine-readable self-description at
  `GET /api/v1/synthetic` (protocols, tools, fault ranges, live auth mode,
  redaction contract) and `GET /api/v1/synthetic/tools`. Composed live from
  process state so it can never drift; **never leaks configured key material**.

### 7.3 Synthetic CRM API (`app/api/routes/crm.py`)

Full CRUD on `/api/v1/leads`, refactored onto the repository + fault modules:

| Method | Path | Notes |
|---|---|---|
| `POST` | `/leads` | 201; validates name/email/status |
| `GET` | `/leads` | List; supports `simulated_latency_ms` & `inject_error` |
| `GET` | `/leads/{id}` | 404 if missing; fault injection supported |
| `PUT` | `/leads/{id}` | Full replace; 404 if missing |
| `DELETE` | `/leads/{id}` | 204; 404 if missing |

### 7.4 Tool Registry (`app/core/tools.py`)

10 registered tool names (5 operations + dotted aliases):

```
list_crm_leads,  crm.list_leads
get_crm_lead,    crm.get_lead
create_crm_lead, crm.create_lead
update_crm_lead, crm.update_lead
delete_crm_lead, crm.delete_lead
```

Unknown tool → `ToolNotFoundError` → normalized `tool_not_found` error;
execution failure → `ToolExecutionError`.

### 7.5 Tracing & Redaction

- **`app/core/telemetry.py`** — `execute_and_trace_tool()` times execution via
  `time.perf_counter()`, applies redaction, records traces into `TOOL_TRACES`.
  `classify_tool_error()` maps exceptions to normalized error dicts.
- **`app/core/redaction.py`** — `redact_sensitive_data()` recursively scrubs:
  - Sensitive dictionary keys (`password`, `passwd`, `pwd`, `token`,
    `access_token`, `refresh_token`, `id_token`, `auth_token`, `api_key`,
    `apikey`, `api_secret`, `secret`, `secret_key`, `client_secret`,
    `authorization`, `auth`, `credit_card`, `card_number`, `cvv`, `cvc`, `ssn`,
    `private_key`, `session_id`, `cookie`, `set_cookie`) — key names normalized
    to lowercase alphanumerics so `api-key`/`apiKey`/`API_KEY` all match.
  - Inline regex patterns: Bearer tokens, Basic auth, assignment-style secrets,
    OpenAI keys (`sk-...`), AWS keys (`AKIA`/`ASIA...`), JWTs.
  - Marker: `[REDACTED]`.

---

## 8. Work Package D — Workflow, Evaluation & Reports (Rahul)

### 8.1 Deterministic Graph Engine (`app/workflow/graph.py`, 200 lines)

A hand-built **LangGraph-compatible** state machine: `add_node` /
`add_conditional_edges` / `compile` / `invoke`. Supports cancellation, failure
capture, and finalize-once guarantees. **Zero new dependencies** — real
LangGraph can slot in later without API changes (pin `langgraph` in
`requirements.txt` first, a deliberate current choice).

An explicit **`cleanup` node runs exactly once before finalize on every exit
path** (success, node failure, routing error, cancellation).

### 8.2 Scenario Registry (`app/workflow/scenarios.py`)

Immutable `ScenarioDefinition` records declaring goal, tool, summary fields,
agent behavior, and forbidden markers. **Expected results live in the scenario
— never in the agent-visible prompt** (per the Phase 3 guide).

Three built-in deterministic scenarios:

| Scenario ID | Behavior | Expected outcome |
|---|---|---|
| `crm-read-customer-summary` | `correct` | **Pass** (score 100) |
| `crm-read-customer-hallucination` | `hallucinated` | **Fail** (score 60; critical `unsupported_fact` finding citing `platinum-vip`) |
| `crm-read-customer-agent-failure` | `error` | **Fail** (useful failed-run report) |

`ensure_seed_lead()` idempotently creates/reuses a deterministic demo lead
(`seed.lead@nexora.test`).

### 8.3 Mock Agent Client (`app/workflow/agent_client.py`, 129 lines)

`SyntheticToolAgentClient` with behaviors `correct` / `hallucinated` / `error` /
`timeout`, executing through `execute_and_trace_tool` so every turn is timed,
redacted, and traced. The **`agent_client` constructor argument on
`WorkflowRunExecutor` is the ready-made integration seam** for Naaneshwar's
`TargetAgent` — no service changes needed when a live provider lands.

### 8.4 Deterministic Evaluator (`app/workflow/evaluator.py`, 218 lines)

`evaluate_run` is a **pure function** of (scenario, agent outcome, traces,
threshold) — no clocks, randomness, or LLM calls. Fixed inputs always produce
the same score, criteria, and findings.

**Weighted scoring (sums to 100):**

| Criterion | Weight | Question answered |
|---|---|---|
| `task_completion` | 40 | Did the agent complete a lookup and produce a summary? |
| `factual_correctness` | 40 | Does the summary contain every expected field value and none of the forbidden (invented) markers? |
| `trace_integrity` | 20 | Was a successful, redacted tool-call trace recorded? |

**Safety rule:** any **critical** finding (unsupported fact, missing expected
fact, failed agent turn, secret exposure) blocks a passing result **regardless
of numeric score**. Threshold configurable per run (0–100, default 70) and
always embedded in the report so a score is never unexplained.
`validate_pass_threshold()` raises `InvalidPassThreshold` outside range.

### 8.5 Security Checks (`app/workflow/security_checks.py`, 78 lines)

**Modular** secret-leak detection, independently selectable:
1. Collect secret values from sensitive-named run variables (reuses the
   redaction engine's normalizer so the two never drift).
2. Scan every persisted artifact (traces, summary, raw record) for them.
3. Emit a critical `secret_exposure` finding when one leaks.

`evaluate_run` applies the result to the trace-integrity criterion, so a leaked
secret zeroes trace integrity and blocks a pass — but detection logic lives here
and can be extended/replaced independently.

### 8.6 Rich Report Schemas (`app/schemas/workflow_report.py`)

Deliberately a **new module** so the Phase 2 `ReportSummary` contract stays
untouched:

- `CriterionScore` — criterion, weight, score, rationale
- `Finding` — severity (`info`/`warning`/`critical`), code, message, evidence_ref
- `ReportEvidence` — scenario_id, agent_ids, tool_call_ids, event_ids (**never secret values**)
- `WorkflowReport` — report_id, run_id, scenario_id, status, score,
  pass_threshold, summary, criteria, findings, evidence, workflow_state, duration_ms, generated_at

A `ReportSummary` projection is still written for every workflow run so the
existing `GET /api/v1/reports/{report_id}` contract keeps working.

### 8.7 Orchestration Service (`app/workflow/service.py`, 725 lines)

Flow: **validate → verify environment → build scenario → invoke agent →
evaluate → publish report → finalize.** Includes a run-context registry,
idempotent execution (queued-state guard), 30s total timeout, cancellation,
and **startup recovery** of interrupted runs. Environment failures publish a
useful failed-run report (guide acceptance criterion).

### 8.8 Runtime Layer (`app/workflow/runtime.py`, 239 lines)

Launch-hardening runtime:
- **Structured logging** (`nexora` logger tree, configured at most once)
- **Durable run-context store** surviving restarts (atomic JSON snapshot,
  BOM/corruption tolerant) under `WORKFLOW_STATE_DIR`
- **Settings-driven config** (`WORKFLOW_*` env vars)
- **Concurrency limiter**, **process metrics**, **startup recovery**
  (terminalizes stuck runs, idempotent), context release on terminal states
- Backs `GET /api/v1/workflow/readiness`

### 8.9 Report Schema Highlights

Reports include per-criterion rationale, evidence references (never secrets),
the chosen threshold, and duration — so every score is explainable and
auditable.

---

## 9. Cross-Cutting: Launch Hardening

Added on top of the four work packages to reach production-grade readiness:

| Area | Delivered |
|---|---|
| **Authentication** | Real API-key enforcement with modes, timing-safe compare, sentinels, always-open health/schema paths |
| **Persistence** | Durable, atomic, corruption-tolerant snapshot of the entire core store |
| **Middleware** | Security headers + structured request logging + edge auth, all pure-ASGI (SSE-safe) |
| **Service layer** | Agent execution extracted from routes for reuse and testability |
| **Target agents** | ABC + registry + mock fallback; registered agents instantly executable |
| **Synthetic API** | Machine-readable self-description (`GET /api/v1/synthetic`) |
| **Frontend auth** | `authHeaders()` across all fetch clients (sessionStorage or `VITE_API_KEY`); token never in URLs |
| **Frontend UX** | Auto-polling of non-terminal runs (Queued → Passed without manual refresh) |
| **Infra** | CI workflow, non-root Dockerfiles, nginx SPA config, docker-compose with provisioning profile |
| **Docs** | README rewritten for Phase 3; `docs/current-status.md` refreshed; `.env.example` + `.gitignore` updated |

---

## 10. Complete API Surface

All endpoints versioned under `/api/v1` (except root `/health` and
OpenAI-compatible `/v1/*`). Every response uses the standard envelope
`{"success": bool, "data": ..., "error": {...}}`.

| Domain | Method | Path | Notes |
|---|---|---|---|
| Health | `GET` | `/api/v1/health` | Service health (open in every mode) |
| Health | `GET` | `/health` | Lightweight root ping |
| Agents | `POST` | `/api/v1/agents` | Register target agent; 409 on duplicates |
| Agents | `GET` | `/api/v1/agents/{agent_id}` | Inspect registered agent |
| Test Runs | `POST` | `/api/v1/test-runs` | Create + auto-execute registered scenarios (unknown stay `queued`) |
| Test Runs | `GET` | `/api/v1/test-runs/{run_id}` | Run status |
| Test Runs | `POST` | `/api/v1/test-runs/{run_id}/cancel` | Cancel active run |
| Test Runs | `POST` | `/api/v1/test-runs/{run_id}/execute` | Execute queued run (404 unknown, 409 non-queued) |
| Test Runs | `GET` | `/api/v1/test-runs/{run_id}/events` | Execution timeline |
| Test Runs | `GET` | `/api/v1/test-runs/{run_id}/traces` | **Redacted** tool-call traces |
| Test Runs | `GET` | `/api/v1/test-runs/{run_id}/report` | Rich `WorkflowReport` |
| Test Runs | `GET` | `/api/v1/test-runs/{run_id}/stream` | **SSE** live trace stream |
| Environments | `POST` | `/api/v1/environments` | Provision environment |
| Environments | `GET` | `/api/v1/environments/{id}` | Environment status |
| Environments | `POST` | `/api/v1/environments/{id}/ready` | → ready |
| Environments | `POST` | `/api/v1/environments/{id}/stop` | → stopped |
| Environments | `POST` | `/api/v1/environments/{id}/reset` | Reset data |
| Environments | `POST` | `/api/v1/environments/{id}/destroy` | Destroy |
| Evaluations | `POST` | `/api/v1/evaluations` | Submit evaluation, generate report |
| Reports | `GET` | `/api/v1/reports/{report_id}` | Fetch report summary |
| CRM Leads | `POST` | `/api/v1/leads` | Create lead (201) |
| CRM Leads | `GET` | `/api/v1/leads` | List; fault injection supported |
| CRM Leads | `GET` | `/api/v1/leads/{lead_id}` | Read; fault injection supported |
| CRM Leads | `PUT` | `/api/v1/leads/{lead_id}` | Full replace |
| CRM Leads | `DELETE` | `/api/v1/leads/{lead_id}` | Delete (204) |
| Synthetic Agent | `POST` | `/api/v1/synthetic/agent/execute/{protocol}` | Protocol dispatcher; optional `run_id` (tracing), `agent_id` (target agent) |
| Synthetic API | `GET` | `/api/v1/synthetic` | Self-description: protocols, tools, fault ranges, auth mode, redaction |
| Synthetic API | `GET` | `/api/v1/synthetic/tools` | Tool registry |
| Workflow | `GET` | `/api/v1/workflow/readiness` | Engine readiness + metrics |
| OpenAI-compat | `GET` | `/v1/models` | Model discovery |
| OpenAI-compat | `GET` | `/v1/health` | OpenAI-style health |
| Docs | `GET` | `/docs`, `/redoc`, `/openapi.json` | Swagger UI, ReDoc, schema |

**SSE frame types:** `tool_trace` (deduplicated by `call_id:timestamp`) and a
terminal `run_status` frame (`run_id`, `state`, `message`, `completed_at`).
Stream closes on `completed`/`failed`/`cancelled`/`passed` or client
disconnect. Unknown runs get a structured 404 before the stream opens.

**Fault-injection example:**
```
GET /api/v1/leads?simulated_latency_ms=1500   # non-blocking delay
GET /api/v1/leads?inject_error=429            # deterministic rate limit
```

---

## 11. Frontend (Dashboard)

`apps/web/` — React 18 + TypeScript + Vite, four-tab dashboard.

### Tabs

| Tab | Capabilities |
|---|---|
| **Overview** | Workflow metrics cards (started/passed/failed/rate/cancelled/pending), system status (Python API, Node API, workflow engine + state path) |
| **Workflows (WP-D)** | Scenario picker (3 scenarios), create+execute run, run list with **auto-polling** (Queued → Passed/Failed without manual refresh), per-row Refresh/Watch/Cancel |
| **Environments (WP-B)** | Provision (type + label), lifecycle buttons, activity log, polls until settled |
| **Monitoring** | Watch arbitrary run by ID, live SSE trace stream |

### Key modules

| File | Lines | Purpose |
|---|---|---|
| `src/App.tsx` | 607 | Dashboard shell, state, all handlers, run auto-polling |
| `src/index.css` | 463 | Full design system (dark theme, panels, tables, status pills, trace tones) |
| `src/components/TraceStreamViewer.tsx` | 212 | Live trace rendering (name, call id, duration, success/failure, redaction) |
| `src/hooks/useTestRunStream.ts` | 212 | SSE hook: connect/reconnect/transient recovery, dedup, terminal handling |
| `src/api/auth.ts` | 38 | **API-key resolution**: `sessionStorage.nexora_api_key` → `VITE_API_KEY` → anonymous |
| `src/api/testRuns.ts` | 95 | Run CRUD + stream URL; binds default scenario so runs actually execute |
| `src/api/environments.ts` | 69 | Environment lifecycle via `lifecycleAction()` helper |
| `src/api/agents.ts` | 55 | Agent registration/fetch |
| `src/api/workflow.ts` | 40 | Readiness fetch |
| `src/utils/redaction.ts` | 72 | Client-side redaction mirroring the backend |
| `src/utils/format.ts` | 20 | Formatting helpers |

### Frontend behaviors worth noting

- **Scenario binding:** `createTestRun` always binds a registered scenario
  (default `crm-read-customer-summary`); a scenario-less run would stay
  `queued` forever with a silent stream.
- **Auth:** `authHeaders()` spreads `X-API-Key` into every mutating fetch.
  **No token ever appears in a URL.** SSE relies on read-open write mode
  because `EventSource` cannot send headers.
- **Auto-polling (added during launch hardening):** non-terminal runs are
  polled every 2s so the list reflects backend progress without a manual
  Refresh click. Terminal states stop the polling.
- **Environment polling:** provisions then polls until status settles.

---

## 12. Testing & Test Inventory

### Backend — 268 tests across 24 modules (265 pass, 3 Docker-gated skips)

| Module | Tests | Coverage focus |
|---|---|---|
| `test_workflow_service.py` | 25 | Environment verification (incl. failed-run reports), scenario build, idempotent execution, run-context registry, invalid configs, report publishing, timeouts, crash/timeout report boundary, cancellation, cleanup events, injectable agent client |
| `test_environment_service.py` | 26 | Lifecycle state machine, metadata stages, credential redaction |
| `test_docker_provider_sdk.py` | 20 | SDK integration, lazy import, unavailable-daemon handling |
| `test_workflow_evaluation.py` | 16 | Weighted scoring, threshold config/validation, hallucination detection, secret-leak detection, critical-finding safety rule, determinism |
| `test_workflow_api.py` | 16 | Auto-execution contract, manual execute (200/404/409), report endpoints, ReportSummary projection, secret canary absence, agent-failure & invalid-threshold HTTP paths, full pass+fail demo |
| `test_auth_enforcement.py` | 17 | Mode resolution, timing-safe matching, 401/403 envelopes, reads-open in write mode, sentinels in every mode, health/schema open |
| `test_agent_execution_service.py` | 16 | Protocol/run/agent validation, event recording, redaction, HTTP status mapping |
| `test_workflow_runtime.py` | 15 | Structured logging, durable run-context store (reload/atomic/pop/BOM/corruption/shape), concurrency limiter, metrics, readiness, startup recovery |
| `test_target_agents.py` | 13 | ABC contract, mock execution, tracing+redaction, registry semantics, store-agent resolution, unknown-id errors |
| `test_synthetic_api.py` | 13 | Capability descriptor, repository CRUD, fault-injection contract & validation |
| `test_workflow_engine.py` | 13 | Node order, conditional edges, cancellation, failure capture, finalize-once, cleanup-exactly-once, determinism |
| `test_persistence.py` | 11 | Round-trip of every collection, atomic writes, corruption/shape/BOM tolerance, invalid-record skipping, disable semantics, HTTP restart cycle |
| `test_auth.py` | 9 | Optional-auth dependency, sentinels, Bearer precedence |
| `test_middleware.py` | 9 | Security headers (success/404/422/preflight), request logging with probes excluded, error-envelope shape |
| `test_tracing.py` | 8 | Tool-call trace capture, redaction |
| `test_protocol_adapters.py` | 7 | REST/OpenAI/LangChain adapters, alias resolution, payload normalization |
| `test_security_checks.py` | 6 | Standalone secret-leak detection, key extraction, severity |
| `test_crm.py` | 5 | CRM CRUD contracts, validation |
| `test_request_robustness.py` | 5 | Malformed payloads, edge cases |
| `test_api_contracts.py` | 4 | Envelope contracts |
| `test_streaming.py` | 4 | SSE 404, dedup, terminal frame, forbidden sentinel |
| `test_environment_docker_integration.py` | 4 | **Docker-gated live tests** (skip without daemon) |
| `test_settings_env.py` | 5 | `NEXORA_*` env-var aliases, defaults, precedence |
| `test_health.py` | 1 | Health endpoint |

### Frontend — 34 tests across 4 files

| File | Tests | Coverage |
|---|---|---|
| `useTestRunStream.test.tsx` | 14 | Idle/connecting/connected, trace append, success/failure, terminal close, malformed payload, dedup, transient→reconnect→recovery, fatal error, run-id switch, unmount cleanup |
| `TraceStreamViewer.test.tsx` | 12 | Empty state, connecting, trace rendering, run-status updates, labels, REST seeding, malformed payload, fatal error, reconnect, run-id switch, redaction, long names |
| `api/auth.test.ts` | 4 | Anonymous default, sessionStorage key, `VITE_API_KEY` fallback, precedence |
| `api/testRuns.test.ts` | 4 | Create-run request shape, scenario binding, auth header, error unwrapping |

### Testing philosophy

- **Hermetic:** `conftest.py` disables store persistence at import time plus an
  autouse fixture; Docker-gated tests auto-skip; no network, no API keys.
- **Contract-style:** routes tested through the real `TestClient(app)`.
- **Deterministic:** evaluator and scenarios are pure functions.
- **Two audit rounds** on WP-D found and fixed 7 real defects (false doc claim,
  hardcoded agent client, duplicated normalization, unhandled crash boundary,
  missing env-failure reports, missing cleanup node, entangled security logic).

---

## 13. Live Verification History

Every item below was verified over real HTTP against a running uvicorn, or in a
real browser:

1. **Environment lifecycle** — `POST /environments` (provisioning) → `/ready`
   → `/stop`; correct `failed: "Docker Engine is unavailable"` without a daemon.
2. **CRM lifecycle** — POST (201) → GET (200) → PUT (200) → DELETE (204) → GET (404).
3. **Fault simulation** — `simulated_latency_ms=10` (delayed 200),
   `inject_error=429` (429), `inject_error=200` (422 validation).
4. **Protocol adapters** — `execute/rest` and `execute/openai` with function payloads.
5. **Tracing + redaction** — secret `api_key` parameter → traces show
   `[REDACTED]` with UTC timestamp; linked `tool_call` event carries redacted payload.
6. **Auth (sentinels)** — anonymous, `X-API-Key`, Bearer, Bearer precedence, 401/403 sentinels.
7. **SSE streaming** — 404 unknown run, one deduplicated `tool_trace` frame,
   terminal `run_status` (`cancelled`), 403 forbidden sentinel.
8. **WP-D full demo** — health → agent registration → environment → run bound to
   `provisioning` env fails safely → `/ready` → passing run reaches `passed`
   (score 100) → hallucination run fails (score 60, critical finding citing
   `platinum-vip`) → secret canary absent from traces → unknown scenario stays `queued`.
9. **WP-D launch verification** — readiness endpoint, restart recovery (durable
   context reloaded; UTF-8 BOM reader bug found & fixed), env-config wiring
   (`WORKFLOW_DEFAULT_PASS_THRESHOLD=95` honored in persisted report), 5-run
   burst all terminal under concurrency limit.
10. **Launch-hardening smoke (27/27)** — security headers, OpenAPI 28 paths,
    descriptor (5 protocols, 10 tools, auth=off), 429 + 311ms latency
    injection, agent register→execute, unknown-agent 404, sentinels, full run →
    score-100 report with 3 criteria, traces, `store.json` on disk.
11. **Live auth enforcement (17/17)** — with `NEXORA_API_KEYS` set: anonymous
    GET open, anonymous POST 401 (standard envelope), wrong key 401, valid
    `X-API-Key` 201, valid Bearer 201, sentinels 401/403, health/docs/models
    open, descriptor reports `write` mode **without leaking the key**,
    authorized DELETE 204.
12. **Browser E2E** — dashboard loaded (zero console errors), run created via
    the UI auto-polled **Queued → Passed** (score 100) with no manual refresh;
    hallucination scenario verified to fail.

**Live-testing catches fixed during verification:**
- Stale duplicate `uvicorn` process masked new routes (killed both).
- `NEXORA_*` env vars silently did not map (pydantic-settings has no prefix) →
  `AliasChoices` + regression tests.
- Dashboard rows stuck on "Queued" → added auto-polling for non-terminal runs.

---

## 14. Security Posture

| Control | Implementation |
|---|---|
| **API-key auth** | Timing-safe comparison (`secrets.compare_digest` over every key, accumulated so timing never reveals a match); modes `auto/off/write/full` |
| **Credential transport** | `X-API-Key` or `Authorization: Bearer`; token never in URLs |
| **Secret redaction** | Recursive key-based + regex-based scrubbing applied to every telemetry artifact before persistence; marker `[REDACTED]` |
| **Secret-leak detection** | Standalone `security_checks` module; a leak zeroes trace integrity and blocks a pass regardless of score |
| **Security headers** | `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, COOP `same-origin`, CORP `same-origin`, `Permissions-Policy` (geolocation/mic/camera denied) — on every response incl. errors and preflights |
| **Structured logging** | `nexora.http` request log with health/readiness probes excluded; no secrets logged |
| **Error envelopes** | Consistent `{success:false, error:{code,message,details}}`; 422 sanitizes non-JSON-serializable echoed input (prevents a misleading 500) |
| **SSE-safe middleware** | Pure-ASGI (never `BaseHTTPMiddleware`) so streaming is never buffered |
| **Container hardening** | Non-root user, health checks, minimal slim images |
| **Credential isolation (env)** | Connection secrets under `metadata["connection"]`; `redact_connection()` for routes/logs; never in `endpoint` |
| **Fault injection safety** | Evaluated before any store operation — an injected failure cannot corrupt synthetic data |
| **Dependency hygiene** | Docker SDK imported lazily (optional); zero LLM/network dependencies for core operation |

---

## 15. Infrastructure: CI, Docker, Compose

### CI (`.github/workflows/ci.yml`)

Runs on push/PR to `main`, `master`, `feature/**`:

- **Backend job** — Python 3.12, pip cache, `pip install -r requirements.txt`,
  `python -m pytest -q` (conftest disables persistence; Docker tests auto-skip).
- **Frontend job** — Node 20, workspace-root `npm install` (so `@nexora/shared`
  resolves), `npx tsc --noEmit`, `npm run test`, `npm run build`.

### Backend image (`backend/Dockerfile`)

- `python:3.12-slim`; `PYTHONDONTWRITEBYTECODE=1`, `PYTHONUNBUFFERED=1`
- Deps installed first (cached layer); `backend/app` copied to `/app/app` so
  `app.main:app` resolves
- `NEXORA_STATE_DIR=/data/state` volume for persistence across restarts
- Runs as `nobody`; `EXPOSE 8000`; health check on `/health`
- `CMD uvicorn app.main:app --host 0.0.0.0 --port 8000`

### Frontend image (`apps/web/Dockerfile`)

- **Stage 1 (node:20-slim):** workspace-root install, build `@nexora/shared`
  then `@nexora/web`; accepts `VITE_API_BASE_URL`/`VITE_API_KEY` build args
- **Stage 2 (nginx:1.27-alpine):** serves `dist/` with SPA fallback
- `nginx.conf`: `try_files ... /index.html` for deep links, immutable caching
  for hashed assets, `no-cache` for `index.html`, gzip, baseline security headers
- `EXPOSE 80`; health check via `wget`

### Compose (`docker-compose.yml`)

```bash
docker compose up --build                                  # backend :8000, web :3000
docker compose --profile docker_provisioning up --build    # + Docker socket for live envs
```

- **backend** — named volume `backend-state:/data/state`, passes
  `NEXORA_API_KEYS`/`NEXORA_AUTH_MODE`/`CORS_ORIGINS` from host env
- **web** — build args for API base URL/key; depends_on backend
- **backend-docker** (profile `docker_provisioning`) — additionally mounts
  `/var/run/docker.sock` for real container provisioning
- Note: the dashboard calls the API from the **browser**, so
  `VITE_API_BASE_URL` is baked at build time pointing at the published backend port

---

## 16. Configuration Reference

Backend reads `.env` via pydantic-settings (copy `.env.example` → `.env`).

| Variable | Default | Purpose |
|---|---|---|
| `APP_NAME` | `NEXORA` | Application name |
| `APP_ENV` | `development` | Environment label |
| `API_PREFIX` | `/api/v1` | Versioned route prefix |
| `PORT` | `8000` | Backend port |
| `LOG_LEVEL` | `INFO` | Log level |
| `CORS_ORIGINS` | `http://localhost:3000,http://localhost:5173` | Allowed browser origins |
| `NEXORA_API_KEYS` | *(empty)* | Comma-separated accepted API keys (auth off when empty) |
| `NEXORA_AUTH_MODE` | `auto` | `auto` / `off` / `write` / `full` |
| `NEXORA_STATE_DIR` | `.state` | Durable store snapshot dir (empty = disabled) |
| `WORKFLOW_TOTAL_TIMEOUT_SECONDS` | `30` | Whole-run timeout |
| `WORKFLOW_AGENT_TIMEOUT_SECONDS` | `10` | Per-turn agent timeout |
| `WORKFLOW_DEFAULT_PASS_THRESHOLD` | `70` | Score required to pass |
| `WORKFLOW_MAX_CONCURRENT_RUNS` | `4` | Workflow concurrency limit |
| `WORKFLOW_STATE_DIR` | `.workflow_state` | Durable run-context snapshots |
| `VITE_API_BASE_URL` | `http://localhost:8000` | Dashboard → API base URL |
| `VITE_API_KEY` | *(empty)* | Build-time dashboard API key |

**Auth mode semantics:**

| Mode | Behavior |
|---|---|
| `auto` | `write` when keys exist, else `off` (default) |
| `off` | Never enforce (sentinels still simulate 401/403) |
| `write` | Mutations (`POST/PUT/PATCH/DELETE`) require a valid key; **reads stay open** |
| `full` | Every request under the API prefix requires a valid key |

> **Important:** `full` mode breaks the dashboard's SSE stream (EventSource
> cannot send headers). `write` mode is the recommended production setting.

---

## 17. How to Run

### Backend (FastAPI — :8000)

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\activate          # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

- Swagger UI: http://127.0.0.1:8000/docs
- Health: http://127.0.0.1:8000/api/v1/health
- Descriptor: http://127.0.0.1:8000/api/v1/synthetic

### Frontend (React + Vite — :3000)

```powershell
# Second terminal, from repo root
npm install
npm run dev
```

Open http://localhost:3000. Override API location with `apps/web/.env.local`:
`VITE_API_BASE_URL=http://localhost:8000`

### Tests

```powershell
cd backend
.\.venv\Scripts\python -m pytest -q      # 265 pass, 3 skip

cd apps\web
npm run test                              # 34 pass
npx tsc --noEmit                          # clean
```

### Docker (one command)

```powershell
docker compose up --build
```

### Enable authentication (optional)

```powershell
$env:NEXORA_API_KEYS = "my-secret-key"
$env:NEXORA_AUTH_MODE = "auto"
uvicorn app.main:app --port 8000
```

Dashboard can pick up the key via browser console:
```js
sessionStorage.setItem('nexora_api_key', 'my-secret-key')
```

### 60-second demo

1. Backend up, frontend up
2. http://localhost:3000 → **Workflows (WP-D)**
3. Scenario *CRM read customer summary (pass)* → **Create & execute run**
4. Row goes **Queued → Passed** (score 100)
5. Try *CRM hallucination* → **fails** (score 60, critical finding)
6. Click **Watch** for the live SSE trace stream
7. Explore any endpoint at http://127.0.0.1:8000/docs → **Try it out**

---

## 18. File Inventory

### Backend (`backend/app/`) — ~5,400 lines across 57 modules

**Core (`app/core/`)**

| File | Lines | Purpose |
|---|---|---|
| `store.py` | 210 | Shared in-memory store + persistence hooks (single source of truth) |
| `persistence.py` | 205 | Durable JSON snapshot (atomic, corruption-tolerant) |
| `auth.py` | 170 | API-key modes, timing-safe compare, sentinels |
| `adapters.py` | 137 | Protocol adapters + factory |
| `middleware.py` | 131 | Observability + Auth ASGI middleware |
| `errors.py` | 72 | Standard error envelope + handlers (422 sanitization) |
| `telemetry.py` | 83 | Timed, redacted tool execution + trace recording |
| `redaction.py` | 81 | Recursive secret scrubbing (keys + regex) |
| `tools.py` | 68 | Synthetic tool registry (10 names) |
| `config.py` | 57 | Settings incl. `NEXORA_*` aliases |

**Integrations**

| File | Lines | Purpose |
|---|---|---|
| `environment/manager.py` | 380 | Environment lifecycle service (WP-B) |
| `environment/docker_provider.py` | 350 | Docker SDK provider (WP-B) |
| `environment/database_seed.py` | 135 | Deterministic seeding (WP-B) |
| `target_agents/__init__.py` | 93 | Registry + resolution (WP-A) |
| `target_agents/base.py` | 76 | `TargetAgent` ABC + descriptor (WP-A) |
| `target_agents/mock.py` | 35 | Deterministic mock agent (WP-A) |
| `synthetic_api/app.py` | 90 | Self-description router (WP-C) |
| `synthetic_api/faults.py` | 50 | Fault-injection contract (WP-C) |
| `synthetic_api/repository.py` | 36 | Lead repository seam (WP-C) |
| `synthetic_api/schemas.py` | 35 | Descriptor models (WP-C) |

**Workflow (`app/workflow/`)**

| File | Lines | Purpose |
|---|---|---|
| `service.py` | 725 | Orchestration: validate→verify→build→invoke→evaluate→publish→finalize (WP-D) |
| `runtime.py` | 239 | Logging, durable contexts, limiter, metrics, recovery (WP-D) |
| `evaluator.py` | 218 | Weighted deterministic scoring (WP-D) |
| `graph.py` | 200 | LangGraph-compatible state machine (WP-D) |
| `agent_client.py` | 129 | Mock agent client with injectable seam (WP-D) |
| `security_checks.py` | 78 | Modular secret-leak detection (WP-D) |
| `scenarios.py` | 75 | Deterministic scenario registry (WP-D) |

**Services & Routes**

| File | Lines | Purpose |
|---|---|---|
| `services/agent_execution.py` | 107 | Agent-execution service layer (WP-A) |
| `api/routes/environments.py` | 124 | Environment routes (WP-B) |
| `api/routes/test_runs.py` | 102 | Test-run routes + auto-execution (WP-D) |
| `api/routes/streaming.py` | 65 | SSE live trace stream |
| `api/routes/crm.py` | 61 | CRM CRUD + fault injection (WP-C) |
| `api/routes/evaluations.py` | 50 | Evaluation submission |
| `api/routes/agent_execution.py` | 38 | Protocol dispatcher route (thin) |
| `main.py` | 118 | App assembly, middleware stack, lifespan |

**Schemas** — `agent.py` (18), `common.py` (20), `crm.py` (12),
`environment.py` (17), `evaluation.py` (26), `events.py` (18),
`test_run.py` (30), `tracing.py` (17), `workflow_report.py` (45)

### Frontend (`apps/web/src/`) — ~2,360 lines

Covered in §11. Highlights: `App.tsx` (607), `index.css` (463),
`TraceStreamViewer.tsx` (212), `useTestRunStream.ts` (212).

### Tests

- Backend: 24 modules, 268 tests (see §12)
- Frontend: 4 modules, 34 tests

---

## 19. Known Limitations

Documented, deliberate, and not bugs:

1. **Docker provisioning reports failure on non-Docker hosts** — by design per
   the guide; the API correctly returns `failed: "Docker Engine is unavailable"`.
2. **`full` auth mode breaks dashboard SSE** — `EventSource` cannot send
   headers; `write` mode (read-open) is the recommended production config.
3. **In-memory store with JSON snapshot** — durable across restarts but not a
   real database; `core/persistence.py` is the swap point for PostgreSQL/Redis.
4. **Deterministic mock agents** — no live LLM calls; the `TargetAgent`/`agent_client`
   seams are ready for real providers.
5. **Hand-built workflow engine** — LangGraph-compatible API but zero
   dependencies; real LangGraph can slot in after pinning `langgraph`.
6. **SSE verified via backend contract tests + manual browser run** — no
   automated browser-level SSE e2e yet (jsdom has no SSE; hook tests use a mock
   `EventSource`).
7. **`apps/api` (Node) is legacy** — retained for compatibility; the FastAPI
   backend is canonical.

---

## 20. Remaining Work

Ordered by impact; none are blockers for a demo/preview deployment:

| # | Item | Seam / notes |
|---|---|---|
| 1 | **Real target-agent providers** | Implement a provider class (OpenAI/Anthropic/etc.) against the `TargetAgent` ABC + `agent_client` interface and register it. Workflow execution currently runs the deterministic mock. |
| 2 | **Docker-backed environments in production** | Code + SDK integration complete; needs a Docker host or the compose `docker_provisioning` profile. Verified to fail gracefully without one. |
| 3 | **PostgreSQL / Redis persistence swap** | `core/persistence.py` is the seam; replace the JSON snapshot with a real database backend. |
| 4 | **Browser-level SSE e2e test** | Covered by backend contract tests + manual verification; automate with a real browser runner. |
| 5 | **Deployment automation** | CI runs tests/builds; wire image publishing (GHCR) and environment-specific deploy pipelines. |
| 6 | **Additional protocol adapters** | Anthropic tool-use and MCP tool-schema adapters alongside `rest`/`openai`/`langchain`. |
| 7 | **Optional: real LangGraph** | Pin `langgraph` in `backend/requirements.txt` and swap the in-repo state machine (deliberate zero-dependency choice today). |

---

*End of report. Companion documents: `docs/current-status.md` (living status),
`docs/architecture.md` (module boundaries), `docs/api-contracts.md` (contracts),
`docs/work-package-d-summary.md` and `docs/work-package-b-summary.md` (per-WP detail).*
