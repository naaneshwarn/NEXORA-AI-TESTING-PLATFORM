# NEXORA AI Testing Platform — Full Project Work Report

**Document:** Complete record of all work completed to date
**Last Updated:** October 28, 2026
**Branch:** `feature/integration-wpb-wpd`
**Latest Commit:** `75be416` — *docs: add full project work report* (previous: `412eca5` — *Launch hardening*)
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
21. [Operational & Troubleshooting Notes](#21-operational--troubleshooting-notes)
22. [Example Request/Response Exchanges](#22-example-requestresponse-exchanges)

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

### Full commit history (all 41 commits, chronological)

| # | Hash | Date | Author | Message |
|---|---|---|---|---|
| 1 | `25dab08` | 2026-10-11 | naaneshwarn | Publish NEXORA AI Testing Platform source code |
| 2 | `312f3b6` | 2026-10-11 | PrajwalGayakwad99 | feat(backend): implement synthetic environment lifecycle and ready endpoint |
| 3 | `0bf53a4` | 2026-10-11 | S Prajwal rao gayakwad | end point are ready |
| 4 | `e7e26ee` | 2026-10-12 | PrajwalGayakwad99 | feat(crm): implement stateful synthetic CRM routes with fault and latency injection |
| 5 | `8e06b3a` | 2026-10-12 | S Prajwal rao gayakwad | Merge pull request #2 from naaneshwarn/feature/synthetic-api |
| 6 | `9a1d71a` | 2026-10-12 | PrajwalGayakwad99 | feat(adapters): implement protocol adapter layer, tool registry, and agent execution dispatcher |
| 7 | `872a7d5` | 2026-10-12 | PrajwalGayakwad99 | feat(tracing): verify live protocol execution dispatcher and redacted tool-call telemetry |
| 8 | `5b2b571` | 2026-10-13 | S Prajwal rao gayakwad | Merge pull request #3 from naaneshwarn/feature/synthetic-api |
| 9 | `507c6d2` | 2026-10-13 | PrajwalGayakwad99 | feat(crm): implement comprehensive CRM tests, protocol execution, and redacted tracing |
| 10 | `4c7e76b` | 2026-10-13 | S Prajwal rao gayakwad | Merge pull request #4 from naaneshwarn/feature/synthetic-api |
| 11 | `b812020` | 2026-10-13 | PrajwalGayakwad99 | feat(auth+stream): implement optional auth dependency, SSE live streaming, and comprehensive test suite |
| 12 | `2e9864a` | 2026-10-13 | S Prajwal rao gayakwad | Merge pull request #5 from naaneshwarn/feature/synthetic-api |
| 13 | `82646d0` | 2026-10-13 | S Prajwal rao gayakwad | Merge pull request #6 from naaneshwarn/chore/project-foundation |
| 14 | `773a182` | 2026-10-13 | PrajwalGayakwad99 | feat(dashboard): add real-time SSE trace viewer |
| 15 | `4703dbc` | 2026-10-14 | S Prajwal rao gayakwad | Merge pull request #7 from naaneshwarn/feature/synthetic-api |
| 16 | `1c97e3b` | 2026-10-14 | S Prajwal rao gayakwad | Merge pull request #8 from naaneshwarn/chore/project-foundation |
| 17 | `4535298` | 2026-10-20 | Rahul kumar | feat(workflow): add deterministic graph engine and rich report schemas |
| 18 | `484eeb4` | 2026-10-21 | Rahul kumar | feat(workflow): add scenario registry, mock agent client, and deterministic evaluator |
| 19 | `0fe30da` | 2026-10-21 | Rahul kumar | feat(workflow): add orchestrator service with cancellation, failures, and reporting |
| 20 | `c4dd376` | 2026-10-21 | Rahul kumar | feat(api): wire workflow execution and report endpoints into test-runs API |
| 21 | `b73e073` | 2026-10-21 | Rahul kumar | test(api): cover agent-failure and invalid-threshold paths end-to-end over HTTP |
| 22 | `e134d52` | 2026-10-21 | Rahul kumar | docs: document workflow execution and report contracts, WP-D status and changes |
| 23 | `15111b8` | 2026-10-21 | Rahul kumar | fix(workflow): audit fixes - env failure reports, explicit cleanup node, standalone security evaluator |
| 24 | `e146be5` | 2026-10-21 | Rahul kumar | fix(workflow): second audit round - injectable agent client, dedup, crash-report boundary, doc corrections |
| 25 | `6132565` | 2026-10-21 | Rahul kumar | feat(workflow): launch-hardening runtime (durable contexts, config, metrics, recovery) |
| 26 | `27aa705` | 2026-10-21 | Rahul kumar | feat(environments): Docker lifecycle + synthetic PostgreSQL provisioning (WP-B) |
| 27 | `c04424d` | 2026-10-21 | Rahul kumar | fix(environments): harden Docker provider from real-daemon verification (WP-B) |
| 28 | `7a0df53` | 2026-10-21 | Rahul kumar | merge(wp-b): Docker environment lifecycle + synthetic PostgreSQL provisioning |
| 29 | `2646b6d` | 2026-10-21 | Rahul kumar | merge(wp-d): LangGraph-style workflow, scenarios, security checks, evaluation, reports |
| 30 | `8b36798` | 2026-10-21 | Rahul kumar | Harden error handling + fix unreachable workflow report IDs |
| 31 | `f96f5e8` | 2026-10-21 | Rahul kumar | Fix dashboard create-run to bind CRM scenario for live streaming |
| 32 | `1f63578` | 2026-10-22 | naaneshwarn | feat: integrate FastAPI backend contracts |
| 33 | `95e98d5` | 2026-10-22 | naaneshwarn | Merge branch 'chore/project-foundation' into feature/naaneshwar-backend-integration |
| 34 | `1cacaee` | 2026-10-22 | naaneshwarn | Merge pull request #10 from naaneshwarn/feature/naaneshwar-backend-integration |
| 35 | `b460773` | 2026-10-22 | naaneshwarn | Merge branch 'chore/project-foundation' into feature/docker-environment |
| 36 | `10ecc0d` | 2026-10-22 | naaneshwarn | Merge pull request #9 from naaneshwarn/feature/docker-environment |
| 37 | `5564ed9` | 2026-10-27 | Rahul kumar | untracked files on chore/project-foundation: 10ecc0d (stash entry) |
| 38 | `8f28305` | 2026-10-27 | Rahul kumar | index on chore/project-foundation: 10ecc0d (stash entry) |
| 39 | `717dfe9` | 2026-10-27 | Rahul kumar | On chore/project-foundation: wip (stash entry) |
| 40 | `412eca5` | 2026-10-28 | Rahul kumar | Launch hardening: real API-key auth, durable persistence, target agents, synthetic API, CI/Docker |
| 41 | `75be416` | 2026-10-28 | Rahul kumar | docs: add full project work report (all work packages, tests, verification, infra) |

> Rows 37–39 are the single stash entry `stash@{0}` created on
> `chore/project-foundation` (2026-10-27) — it belongs to pre-Phase-3 work and
> is not part of the Phase 3 deliverable.

### Pull requests merged

| PR | Branch | Content |
|---|---|---|
| #2 | `feature/synthetic-api` | Synthetic environment lifecycle + ready endpoint, CRM routes |
| #3 | `feature/synthetic-api` | Protocol adapters, tool registry, dispatcher, tracing |
| #4 | `feature/synthetic-api` | CRM tests, protocol execution, redacted tracing |
| #5 | `feature/synthetic-api` | Optional auth dependency, SSE streaming, test suite |
| #6 | `chore/project-foundation` | Foundation merge into feature line |
| #7 | `feature/synthetic-api` | Dashboard SSE trace viewer |
| #8 | `chore/project-foundation` | Foundation merge |
| #9 | `feature/docker-environment` | WP-B: Docker environment lifecycle |
| #10 | `feature/naaneshwar-backend-integration` | WP-A: FastAPI backend contracts |

All branches are in sync with their remotes. No unpushed commits exist.
HEAD `75be416` == `origin/feature/integration-wpb-wpd`; working tree clean.

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

**Lifecycle stages in detail:**

| Action | Contract `status` | `metadata["lifecycle"]` | What happens |
|---|---|---|---|
| `POST /environments` | `provisioning` → `ready` | `created` → `seeding` | Validate engine → generate credentials (if absent) → provider `create` (loopback bind by default) → wait for readiness (real query, not just `pg_isready`) → seed deterministic data |
| *(provision failure)* | `failed` | — | `failure_reason` recorded; container cleaned up (partial-failure cleanup is idempotent) |
| `POST .../ready` | `ready` | — | Marks ready (used by workflow environment verification) |
| `POST .../reset` | stays `ready` | `resetting` → `ready` | Truncate + re-seed; fails safely when the container is gone |
| `POST .../stop` | `stopped` | — | Stops container, clears stale failure reasons |
| `POST .../destroy` | `cancelled` | `destroyed` | Removes container (idempotent for unknown IDs) and strips credentials |

**Failure honesty:** unsupported engine types fail before the provider is
touched; a missing Docker daemon yields `failed: "Docker Engine is unavailable"`
— the guide's specified behavior for non-Docker hosts.

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

### Complete schema reference (every Pydantic contract)

**`common.py`**
| Model | Fields |
|---|---|
| `ApiEnvelope[T]` (generic) | `success: bool = true`, `data: T \| null`, `error: dict \| null` |
| `ErrorDetail` | `code: str`, `message: str`, `details: dict = {}` |
| `ErrorEnvelope` | `success: false`, `error: ErrorDetail` |
| `HealthResponse` | `status: "ok"`, `service: "nexora"`, `environment: "development"`, `version: "0.1.0"` |

**`agent.py`**
| Model | Fields |
|---|---|
| `AgentConfig` | `agent_id* (min 1)`, `name* (min 1)`, `role: planner\|executor\|observer\|reporter`, `model?`, `provider?`, `endpoint?`, `status: registered\|active\|disabled = registered`, `config: dict = {}`, `created_at?` |
| `AgentRegistrationResponse` | `agent_id`, `status`, `created_at?` |

**`test_run.py`**
| Model | Fields |
|---|---|
| `ScenarioConfig` | `name* (min 1)`, `description?`, `variables: dict = {}` |
| `RunCreateRequest` | `suite_name* (min 1)`, `scenario?: ScenarioConfig`, `environment: str = "local"`, `tags: list = []`, `target_agents: list = []`, `config: dict = {}` |
| `RunDetail` | `run_id`, `suite_name`, `environment`, `state: queued\|running\|passed\|failed\|cancelled = queued`, `target_agents: list = []`, `created_at?`, `started_at?`, `completed_at?`, `message?` |
| `ExecutionStatus` | `run_id`, `state`, `message?` |

**`environment.py`**
| Model | Fields |
|---|---|
| `SyntheticEnvironmentRequest` | `environment_type: postgres\|mysql\|mongodb\|redis\|neo4j\|docker`, `label* (min 1)`, `config: dict = {}` |
| `SyntheticEnvironment` | `environment_id`, `environment_type`, `label`, `status: provisioning\|ready\|stopped\|failed\|cancelled = provisioning`, `endpoint?` (never contains credentials), `metadata: dict = {}` (fine stage in `metadata["lifecycle"]`, connection secrets in `metadata["connection"]`), `created_at?`, `updated_at?` |

**`evaluation.py`**
| Model | Fields |
|---|---|
| `EvaluationResult` | `run_id`, `score: 0–100 = 0`, `status: pass\|fail\|partial = partial`, `summary?`, `metrics: dict = {}` |
| `EvaluationSubmission` | `run_id*`, `agent_id?`, `score`, `status`, `summary* (min 1)`, `metrics`, `issues: list = []` |
| `ReportSummary` *(Phase 2, frozen)* | `report_id`, `run_id`, `score`, `status: generated\|partial\|failed = generated`, `summary`, `metrics`, `generated_at?` |

**`events.py`**
| Model | Fields |
|---|---|
| `ToolCallTrace` | `call_id*`, `tool_name*`, `status: started\|success\|failed = started`, `payload: dict = {}` |
| `ExecutionEvent` | `event_id`, `run_id`, `event_type: created\|started\|heartbeat\|tool_call\|result\|error\|completed`, `sequence: int ≥ 0`, `message`, `payload: dict = {}`, `timestamp?`, `tool_calls: list[ToolCallTrace] = []` |

**`tracing.py`**
| Model | Fields |
|---|---|
| `ToolCallTraceCreate` | `run_id*`, `call_id*`, `tool_name*`, `parameters: dict = {}`, `success: bool`, `result?: Any`, `error?: dict`, `execution_time_ms: float ≥ 0` |
| `ToolCallTraceResponse` | all of the above + `timestamp: datetime` |

**`crm.py`**
| Model | Fields |
|---|---|
| `CRMLeadCreate` | `name: 2–100 chars`, `email: str`, `company?`, `status: new\|contacted\|qualified\|closed = new` |
| `CRMLeadResponse` | extends create + `id`, `created_at`, `updated_at?` |

**`workflow_report.py`** (new module — Phase 2 `ReportSummary` untouched)
| Model | Fields |
|---|---|
| `CriterionScore` | `criterion*`, `weight: 0–100`, `score: 0–100`, `rationale* (min 1)` |
| `Finding` | `severity: info\|warning\|critical`, `code*`, `message*`, `evidence_ref?` |
| `ReportEvidence` | `scenario_id`, `agent_ids: list = []`, `tool_call_ids: list = []`, `event_ids: list = []` (never secret values) |
| `WorkflowReport` | `report_id`, `run_id`, `scenario_id`, `status: pass\|fail = fail`, `score: 0–100 = 0`, `pass_threshold: 0–100*`, `summary*`, `criteria: list[CriterionScore]`, `findings: list[Finding]`, `evidence: ReportEvidence`, `workflow_state: passed\|failed\|cancelled = failed`, `duration_ms ≥ 0 = 0`, `generated_at?` |

`*` = required. All other fields have defaults.

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

### Backend — full test list (268 tests, 24 modules)

All test IDs exactly as collected by `pytest --collect-only`.

**`test_agent_execution_service.py` (16)**
```
test_unknown_protocol_raises
test_unknown_run_raises_before_execution
test_unknown_agent_raises
test_malformed_payload_returns_in_band_error
test_successful_call_executes_traces_and_records_event
test_event_payload_is_redacted
test_failed_tool_call_records_failed_event
test_call_is_executed_through_named_store_agent
test_openai_protocol_round_trip
test_call_id_hint_falls_back_to_generated_id
test_route_maps_unknown_protocol_to_400
test_route_maps_unknown_run_to_404
test_route_maps_unknown_agent_to_404
test_route_executes_through_named_agent
test_route_without_agent_uses_default_mock
test_run_still_exists_after_service_calls
```

**`test_api_contracts.py` (4)**
```
test_agent_registration_and_validation
test_test_run_contract_and_events
test_environment_and_evaluation_contract
test_crm_fault_and_latency_injection
```

**`test_auth.py` (9)**
```
test_optional_auth_allows_anonymous_requests
test_optional_auth_accepts_api_key_header
test_optional_auth_accepts_bearer_token
test_optional_auth_prefers_bearer_token_over_api_key
test_optional_auth_simulates_unauthorized_access
test_optional_auth_simulates_forbidden_access
test_crm_route_allows_anonymous_requests
test_crm_route_simulates_unauthorized_access
test_execution_route_simulates_forbidden_access
```

**`test_auth_enforcement.py` (17)**
```
test_default_mode_is_off
test_auto_mode_enables_write_protection_with_keys
test_health_and_schema_paths_always_open
test_explicit_mode_without_keys_degrades_to_off
test_unknown_mode_falls_back_to_auto
test_anonymous_mutation_rejected_with_envelope
test_invalid_key_rejected
test_valid_api_key_accepted
test_second_configured_key_accepted
test_bearer_token_accepted
test_reads_open_in_write_mode
test_health_open_in_write_mode
test_forbidden_sentinel_still_403_on_mutation
test_full_mode_protects_reads
test_full_mode_keeps_health_open
test_sentinels_behave_in_every_mode
test_sentinels_still_work_with_auth_disabled
```

**`test_crm.py` (5)**
```
test_crm_crud_lifecycle_and_state_changes
test_crm_invalid_payloads_rejected_consistently
test_crm_missing_resources_return_structured_404
test_crm_query_boundary_validation
test_crm_repeated_and_concurrent_operations
```

**`test_docker_provider_sdk.py` (20)**
```
test_available_reflects_real_ping
test_lazy_client_import_reports_unavailable_when_sdk_missing
test_create_passes_configuration_to_sdk
test_create_labels_are_ownership_tags
test_create_binds_loopback_by_default
test_create_normalizes_sdk_failure
test_exec_without_stdin_returns_decoded_output
test_exec_with_stdin_uses_low_level_api_not_exec_run
test_exec_with_stdin_propagates_nonzero_exit
test_is_running_inspects_status
test_is_running_false_for_unknown_container
test_host_port_resolves_ephemeral_binding
test_wait_for_ready_returns_true_when_query_succeeds
test_wait_for_ready_issues_real_query_not_just_pg_isready
test_wait_for_ready_returns_false_when_query_fails
test_wait_for_ready_returns_false_when_not_running
test_stop_verifies_container_exited
test_remove_is_idempotent_for_unknown_container
test_remove_marks_container_removed
test_mocked_provider_never_asserts_real_containers
```

**`test_environment_docker_integration.py` (4) — Docker-gated, skipped without a daemon**
```
test_provision_seed_and_destroy_real_postgres
test_repeated_cleanup_is_safe_against_real_docker
test_default_binding_is_loopback_only
test_connection_info_dsn_shape
```

**`test_environment_service.py` (26)**
```
test_provision_success_reaches_ready_and_seeds
test_provision_uses_supplied_environment_id
test_provision_generates_credentials_when_absent
test_loopback_only_by_default_and_public_when_opted_in
test_provision_fails_honestly_when_docker_unavailable
test_provision_cleans_up_when_container_not_running
test_provision_cleans_up_when_seeding_fails
test_provision_normalizes_create_failure
test_unsupported_engine_fails_without_touching_provider
test_reset_truncates_and_reseeds
test_reset_without_container_fails_safely
test_stop_sets_contract_status_and_stops_container
test_stop_clears_stale_failure_reason
test_cleanup_after_success_removes_container
test_cleanup_after_partial_failure_is_safe
test_repeated_cleanup_is_idempotent
test_cleanup_strips_credentials
test_redact_connection_removes_secrets_only
test_generated_passwords_are_unique
test_password_never_in_endpoint
test_create_environment_preserves_contract
test_created_environment_never_exposes_credentials
test_environment_lifecycle_endpoints
test_missing_environment_returns_404
test_unsupported_engine_via_route_fails_but_returns_201
test_concurrent_provisions_are_independent
```

**`test_health.py` (1)**
```
test_health_endpoint
```

**`test_middleware.py` (9)**
```
test_security_headers_on_success
test_security_headers_on_not_found
test_security_headers_on_validation_error
test_security_headers_cover_cors_preflight
test_completed_requests_are_logged
test_failures_are_logged
test_health_probes_are_not_logged
test_error_envelope_shape_matches_handlers
test_all_declared_security_headers_exist
```

**`test_persistence.py` (11)**
```
test_persistence_disabled_by_default
test_configure_empty_string_disables
test_relative_state_dir_resolves_under_backend
test_save_then_load_round_trips_every_collection
test_load_without_snapshot_returns_false
test_corrupt_snapshot_never_blocks_startup
test_snapshot_with_wrong_shape_is_rejected
test_invalid_records_are_skipped_not_fatal
test_utf8_bom_snapshot_loads
test_disabled_persistence_never_touches_disk
test_state_survives_http_restart_cycle
```

**`test_protocol_adapters.py` (7)**
```
test_rest_adapter_round_trip
test_openai_adapter_parses_function_payload_and_formats_tool_message
test_adapter_factory_defaults_and_aliases
test_execute_rest_tool_round_trip
test_execute_openai_function_call_returns_tool_message
test_execute_normalizes_unknown_tool_and_parse_failures
test_execute_rejects_unknown_protocol
```

**`test_request_robustness.py` (5)**
```
test_non_json_body_returns_422_not_500
test_missing_content_type_returns_422_not_500
test_malformed_json_object_returns_422
test_validation_error_payload_is_json_serializable_and_echoes_safely
test_non_json_body_does_not_mutate_state
```

**`test_security_checks.py` (6)**
```
test_secret_extraction_is_reexported_from_evaluator
test_clean_artifacts_produce_no_findings
test_secret_in_traces_is_detected_and_critical
test_secret_in_summary_or_record_is_detected
test_non_sensitive_variables_are_never_flagged
test_artifact_scan_ignores_empty_secret_list
```

**`test_settings_env.py` (5)**
```
test_defaults_are_development_friendly
test_nexora_prefixed_env_vars_are_read
test_bare_env_var_names_still_work
test_prefixed_var_wins_over_bare
test_workflow_env_vars_map_from_field_names
```

**`test_streaming.py` (4)**
```
test_stream_unknown_run_returns_404
test_stream_emits_run_status_and_terminates_for_terminal_run
test_stream_emits_recorded_tool_traces_before_terminal_status
test_stream_rejects_denied_access_sentinels
```

**`test_synthetic_api.py` (13)**
```
test_descriptor_endpoint_reports_capabilities
test_descriptor_advertises_fault_ranges
test_descriptor_never_leaks_configured_keys
test_descriptor_reports_redaction_contract
test_tools_endpoint_matches_registry
test_router_is_reusable_standalone
test_repository_crud_round_trip
test_repository_delete_is_idempotent
test_fault_injection_raises_requested_status
test_fault_injection_sleeps_for_latency
test_fault_injection_noop_by_default
test_injected_fault_precedes_store_reads
test_fault_query_parameters_still_validated
```

**`test_target_agents.py` (13)**
```
test_target_agent_is_abstract
test_agent_requires_non_empty_id
test_mock_executes_registered_tool
test_mock_normalizes_unknown_tool
test_mock_records_trace_when_run_bound
test_mock_produces_no_trace_without_run
test_healthcheck_and_describe
test_registry_register_get_list_remove
test_registry_rejects_non_agents
test_registry_reregistration_replaces
test_resolve_default_returns_seeded_mock
test_resolve_registered_store_agent_builds_executable_mock
test_resolve_unknown_agent_raises
```

**`test_tracing.py` (8)**
```
test_redact_sensitive_data_masks_keys_recursively
test_redact_sensitive_data_scrubs_inline_secrets
test_execute_and_trace_tool_persists_redacted_telemetry
test_execute_and_trace_tool_captures_failures
test_execution_dispatcher_records_and_exposes_traces
test_traces_endpoints_handle_missing_records
test_execution_dispatcher_writes_tool_call_event_for_run
test_execution_dispatcher_writes_failure_tool_call_event
```

**`test_workflow_api.py` (16)**
```
test_registered_scenario_aut_executes_but_post_body_stays_queued
test_unknown_scenario_name_keeps_legacy_queued_behavior
test_scenario_less_run_stays_queued
test_manual_execute_endpoint_runs_once_then_conflicts
test_manual_execute_unknown_run_returns_404
test_manual_execute_without_registered_scenario_lists_options
test_manual_execute_is_deterministic_for_a_fresh_run
test_workflow_report_endpoint_returns_rich_report
test_workflow_report_endpoint_404s
test_phase2_summary_endpoint_serves_workflow_runs
test_workflow_report_id_is_retrievable_through_reports_route
test_reports_route_still_serves_phase2_summaries_and_404s_unknown
test_secret_variables_never_appear_in_http_responses
test_agent_failure_scenario_fails_with_diagnostic_report_over_http
test_invalid_pass_threshold_surfaces_clear_error_over_http
test_full_demo_flow_pass_and_fail
```

**`test_workflow_engine.py` (13)**
```
test_linear_graph_visits_nodes_in_declared_order
test_conditional_edges_route_on_state
test_node_exception_is_captured_and_finalize_still_runs
test_abort_check_cancels_before_next_node_and_runs_finalize_once
test_unknown_router_route_becomes_routing_error_and_finalizes
test_async_node_functions_are_awaited
test_graph_definition_errors_are_rejected_eagerly
test_state_helpers
test_cleanup_runs_exactly_once_on_the_success_path
test_cleanup_runs_exactly_once_on_the_failure_path
test_cleanup_runs_exactly_once_on_the_cancellation_path
test_cleanup_is_skipped_when_not_configured
test_cleanup_definition_errors_are_rejected_eagerly
```

**`test_workflow_evaluation.py` (16)**
```
test_registry_exposes_documented_scenarios
test_seed_lead_is_deterministic_and_idempotent
test_correct_behavior_summarizes_only_returned_fields_and_records_trace
test_hallucinated_behavior_injects_forbidden_marker
test_error_behavior_is_normalized_and_traced
test_timeout_behavior_fails_fast_with_agent_timeout
test_unknown_lead_is_a_normalized_failure
test_perfect_run_scores_full_marks_and_passes
test_hallucinated_run_fails_with_specific_finding
test_failed_agent_run_scores_zero_task_completion
test_missing_trace_is_flagged_as_incomplete_evidence
test_secret_leak_in_artifacts_is_critical
test_pass_threshold_is_configurable_and_validated
test_critical_findings_block_pass_even_with_relaxed_threshold
test_evaluation_is_deterministic_for_fixed_inputs
test_extract_secret_values_matches_sensitively_named_variables
```

**`test_workflow_runtime.py` (15)**
```
test_configure_logging_is_idempotent_and_namespaced
test_run_context_store_survives_reload
test_run_context_store_pop_removes_and_persists
test_run_context_store_is_atomic_and_recovers_from_corruption
test_run_context_store_tolerates_utf8_bom
test_run_context_store_ignores_unexpected_top_level_shape
test_register_and_get_run_context_round_trip
test_run_context_durable_fallback_after_cache_clear
test_concurrency_limiter_bounds_in_use
test_concurrency_limiter_unbounded_when_none
test_metrics_counters_increment_and_reset
test_executing_a_run_updates_metrics_and_releases_context
test_workflow_readiness_reports_store_and_metrics
test_recover_startup_runs_terminalizes_stuck_runs
test_recovery_is_idempotent
```

**`test_workflow_service.py` (25)**
```
test_successful_run_reaches_passed_state_with_full_score_report
test_run_events_tell_the_whole_story_in_order
test_seed_lead_is_used_when_no_lead_id_supplied
test_hallucinating_agent_produces_failed_run_with_specific_finding
test_agent_failure_produces_useful_failed_run_report
test_agent_timeout_is_normalized_and_reported
test_workflow_level_crash_publishes_a_failed_report
test_crash_before_scenario_resolution_stays_report_less
test_agent_client_is_injectable
test_unbound_environment_uses_local_mock
test_bound_environment_must_be_ready
test_ready_environment_allows_the_run
test_unknown_environment_id_fails_the_run
test_validation_errors_stay_report_less
test_cleanup_runs_on_both_success_and_failure_paths
test_cancelled_run_is_never_executed_or_marked_successful
test_cancellation_during_execution_stops_before_a_passing_result
test_invalid_pass_threshold_fails_the_run_with_a_clear_error
test_invalid_agent_timeout_fails_the_run
test_custom_pass_threshold_is_honored
test_a_run_executes_at_most_once
test_unknown_scenario_in_context_fails_with_available_scenarios_listed
test_unregistered_target_agent_is_reported_as_warning
test_registered_target_agent_produces_no_warning
test_secret_variables_are_redacted_everywhere_end_to_end
```

### Frontend — 34 tests across 4 files

| File | Tests | Coverage |
|---|---|---|
| `useTestRunStream.test.tsx` | 14 | SSE hook state machine |
| `TraceStreamViewer.test.tsx` | 12 | Live trace viewer rendering |
| `api/auth.test.ts` | 4 | API-key resolution |
| `api/testRuns.test.ts` | 4 | Run creation contract |

**`src/api/auth.test.ts` (4)**
```
authHeaders > returns no headers when no key is configured (default anonymous mode)
authHeaders > picks up a runtime key from sessionStorage
authHeaders > falls back to the build-time VITE_API_KEY
authHeaders > prefers the runtime key over the build-time key
```

**`src/api/testRuns.test.ts` (4)**
```
createTestRun > binds the deterministic CRM scenario so the backend schedules execution
createTestRun > lets a caller override the default scenario
createTestRun > unwraps the API envelope into the run detail
createTestRun > throws the API error message when the response signals failure
```

**`src/hooks/useTestRunStream.test.tsx` (14)**
```
is idle and opens no connection without a run id
starts in connecting and subscribes to the run stream
moves to connected only after the open event fires
appends a valid tool trace
records both successful and failed traces
updates run status and closes the stream on a terminal state
keeps a non-terminal status running
ignores malformed payloads without crashing
never duplicates a trace with the same identity
treats a transient drop as reconnecting and recovers on reopen
reports a fatal connection failure as an error
resets run state and reconnects when the run id changes
closes the stream when the run is cleared
closes the stream on unmount
```

**`src/components/TraceStreamViewer.test.tsx` (12)**
```
prompts the user when no run is selected and opens no stream
shows the connecting state before the stream opens
renders a received tool trace with call id and duration
updates the run status from a status event
seeds the current run status from the REST API
distinguishes successful and failed traces with accessible labels
does not crash on malformed event payloads
surfaces fatal connection errors
shows reconnection then recovery
reconnects to a new run when the run id changes
never renders sensitive parameter values
renders long tool names without losing content
```

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

### Redaction engine — exact rules (`app/core/redaction.py`)

Marker: **`[REDACTED]`**.

**Sensitive keys (25)** — a dict value under any of these keys is replaced
entirely. Keys are normalized first (`lower()` + strip every non-alphanumeric
character), so `api-key`, `apiKey`, `API_KEY`, and `api_key` all match:

```
password, passwd, pwd, token, access_token, refresh_token, id_token,
auth_token, api_key, apikey, api_secret, secret, secret_key, client_secret,
authorization, auth, credit_card, card_number, cvv, cvc, ssn, private_key,
session_id, cookie, set_cookie
```

**Inline string patterns (6 regexes)** — applied to every string encountered
(recursing through dicts, lists, and tuples):

| Pattern | Matches | Replacement |
|---|---|---|
| Bearer | `bearer <token>` | `bearer [REDACTED]` |
| Basic | `basic <credential>` | `basic [REDACTED]` |
| Assignment | `password=/token=/api_key=/secret=/cvv=...` (case-insensitive, `=` or `:`, never already-redacted, never `bearer`/`basic`) | value → `[REDACTED]` |
| OpenAI key | `sk-` + 16+ alphanumerics | `[REDACTED]` |
| AWS key | `AKIA`/`ASIA` + 16 uppercase alphanumerics | `[REDACTED]` |
| JWT | `eyJ...`.`...`.`...` (three base64url segments) | `[REDACTED]` |

Non-container, non-string scalars pass through unchanged. The same
`normalize_key` helper is reused by `workflow/security_checks.py` for
secret-leak detection, so key definitions can never drift between the two.

**Where redaction applies:** every tool-call trace before persistence,
`tool_call` event payloads, the agent-execution service responses, workflow
report evidence, and any telemetry dict passed through
`execute_and_trace_tool()`.

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

### Exact dependency versions (`backend/requirements.txt`)

| Package | Version | Why it's here |
|---|---|---|
| `fastapi` | `0.115.6` | HTTP framework, OpenAPI/Swagger generation |
| `uvicorn[standard]` | `0.32.1` | ASGI server |
| `pydantic` | `2.10.6` | Request/response schemas & validation |
| `pydantic-settings` | `2.6.1` | `.env` + environment configuration |
| `pytest` | `8.3.4` | Test runner |
| `httpx` | `0.28.1` | `TestClient` transport for tests |
| `starlette` | `0.41.3` | ASGI primitives (middleware, SSE responses) |
| `sse-starlette` | `2.1.3` | Server-Sent Events streaming |
| `docker` | `7.1.0` | WP-B Docker SDK — **imported lazily**; API and unit tests run fine without it (only live provisioning needs it) |

Deliberately **absent**: no LLM SDK, no LangGraph, no database driver, no
auth/identity library — the core platform is credential-free and
dependency-light.

`pytest.ini` (repo root):
```ini
[pytest]
pythonpath = backend
markers =
    docker: live Docker Engine integration tests (skipped automatically when Docker is unavailable)
```

Frontend toolchain: React 18, TypeScript, Vite, Vitest (plus `@nexora/shared`
workspace package).

### Backend variable reference

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

## 21. Operational & Troubleshooting Notes

### Known operational traps (found and handled during live testing)

| Symptom | Root cause | Resolution |
|---|---|---|
| New routes return 404 despite code changes | A **stale duplicate `uvicorn` process** is still bound to `:8000`, serving old code | Kill *all* uvicorn python processes before restarting; this masked new routes twice during verification |
| `NEXORA_API_KEYS` has no effect | pydantic-settings has **no env prefix**, so `NEXORA_*` names don't map to bare field names silently | Fixed with `AliasChoices("NEXORA_API_KEYS", "API_KEYS")` (etc.); bare names still work; `test_settings_env.py` guards the regression |
| Dashboard rows stuck on "Queued" after a run executes | No polling — the list only updated on manual Refresh | Non-terminal runs auto-poll every 2s in `App.tsx`; terminal states stop polling |
| `429`/`500` from environment provisioning on a dev laptop | No Docker daemon | Expected: `failed: "Docker Engine is unavailable"` (specified behavior) |
| SSE stream silent in `full` auth mode | `EventSource` cannot send headers | Use `write` mode (reads open); documented in README + this report |
| Persistence runs during tests | Snapshot writes to disk would slow and contaminate the suite | `conftest.py` disables it at import time **and** via an autouse fixture |
| Report ID unreachable via `/reports/{id}` | Workflow report IDs weren't stored as Phase 2 summaries | Fixed in `8b36798`: every workflow run writes a `ReportSummary` projection |

### Environment-specific notes (Windows / PowerShell)

- No `&&`, `head`, or `tail` in PowerShell — chain with `;` and
  `Select-Object -First/-Last`.
- Backend venv: `backend\.venv\Scripts\python.exe`; run tests with
  `cd backend; .\.venv\Scripts\python.exe -m pytest -q` (~7 s).
- Frontend: `cd apps\web; npx vitest run` (~4 s), `npx tsc --noEmit`,
  `npm run build`.
- One stale stash exists: `stash@{0}` on `chore/project-foundation`
  (2026-10-27) — pre-Phase-3 work, not part of this deliverable.

### Day-2 operational checks

```powershell
# Backend alive + OpenAPI current
Invoke-RestMethod http://127.0.0.1:8000/api/v1/health
Invoke-RestMethod http://127.0.0.1:8000/openapi.json | % { $_.paths.PSObject.Properties.Count }   # 28

# Capability descriptor (protocols, tools, auth mode, redaction contract)
Invoke-RestMethod http://127.0.0.1:8000/api/v1/synthetic

# Durable state landed on disk
Get-Content backend\.state\store.json -Raw | % { $_.Substring(0, 200) }

# Full suites before pushing
cd backend; .\.venv\Scripts\python.exe -m pytest -q     # 265 passed, 3 skipped
cd apps\web; npx tsc --noEmit; npm run test              # 34 passed
```

### Live-verification scripts

Reusable smoke scripts live outside the repo in the agent temp dir:
- `live_smoke.py` — 27-check API smoke (headers, OpenAPI, descriptor, faults,
  agents, workflow, report, traces, persistence)
- `live_auth_smoke.py` — 17-check auth enforcement with keys configured

Both run against a live uvicorn with `httpx`; keep them when re-verifying
after future changes.

---

## 22. Example Request/Response Exchanges

### 1. Register an agent, then execute a tool call

```http
POST /api/v1/agents
Content-Type: application/json

{"agent_id": "crm-agent", "name": "CRM Agent", "role": "executor"}
```
```json
{"success": true, "data": {"agent_id": "crm-agent", "status": "registered",
 "created_at": "2026-10-28T09:12:44Z"}}
```

```http
POST /api/v1/synthetic/agent/execute/rest?agent_id=crm-agent
Content-Type: application/json

{"tool_name": "get_crm_lead", "parameters": {"lead_id": "lead-1"}}
```
```json
{"success": true, "data": {"call_id": "call_...", "protocol": "rest",
 "result": {"id": "lead-1", "name": "Synthetic Seed Lead", ...},
 "execution_time_ms": 1.7}}
```

### 2. Create a run → live stream → report

```http
POST /api/v1/test-runs
Content-Type: application/json

{"suite_name": "crm-smoke",
 "scenario": {"name": "crm-read-customer-summary"}}
```
```json
{"success": true, "data": {"run_id": "run_...", "state": "queued",
 "suite_name": "crm-smoke", "environment": "local"}}
```
*(registered scenarios auto-execute in the background; the POST body still
reads `queued` for backward compatibility)*

```http
GET /api/v1/test-runs/{run_id}/stream      (Accept: text/event-stream)
```
```
event: tool_trace
data: {"call_id":"call_...","tool_name":"get_crm_lead","status":"success","duration_ms":1.4}

event: run_status
data: {"run_id":"run_...","state":"passed","completed_at":"2026-10-28T09:13:02Z"}
```

```http
GET /api/v1/test-runs/{run_id}/report
```
```json
{"success": true, "data": {
  "report_id": "report_...", "run_id": "run_...",
  "scenario_id": "crm-read-customer-summary",
  "status": "pass", "score": 100.0, "pass_threshold": 70.0,
  "criteria": [
    {"criterion": "task_completion",   "weight": 40, "score": 100,
     "rationale": "Agent completed the lookup and produced a summary."},
    {"criterion": "factual_correctness","weight": 40, "score": 100,
     "rationale": "All expected record fields present; no invented markers."},
    {"criterion": "trace_integrity",   "weight": 20, "score": 100,
     "rationale": "One successful redacted tool-call trace recorded."}
  ],
  "findings": [],
  "evidence": {"scenario_id": "crm-read-customer-summary",
               "tool_call_ids": ["call_..."], "event_ids": ["evt_..."]},
  "workflow_state": "passed", "duration_ms": 214.6
}}
```
*(The hallucination scenario instead returns `status: "fail"`, `score: 60`,
and a `critical` `unsupported_fact` finding whose `evidence_ref` cites the
invented `platinum-vip` marker.)*

### 3. Fault injection

```http
GET /api/v1/leads?inject_error=429
→ 429 {"success": false, "error": {"code": "injected_error",
       "message": "Simulated upstream error (429)."}}

GET /api/v1/leads?simulated_latency_ms=1500
→ 200 after ~1500 ms (non-blocking async sleep)

GET /api/v1/leads?inject_error=200
→ 422 (query validation rejects codes outside 400–599)
```

### 4. Auth enforcement (with `NEXORA_API_KEYS` configured)

```http
POST /api/v1/agents                       (no key)
→ 401 {"success": false, "error": {"code": "unauthorized",
       "message": "A valid API key is required."}}

POST /api/v1/agents                       (X-API-Key: wrong)
→ 401 same envelope

POST /api/v1/agents                       (X-API-Key: <valid>)
→ 201 created

GET /api/v1/agents/any                    (no key, write mode)
→ 200 (reads stay open so the dashboard + SSE keep working)

X-API-Key: invalid-token-test             → 401 (any mode)
X-API-Key: forbidden-token-test           → 403 (any mode)
```

### 5. Provision an environment

```http
POST /api/v1/environments
{"environment_type": "postgres", "label": "demo-db"}
```
```json
// with Docker:
{"success": true, "data": {"environment_id": "env_...", "status": "ready",
 "endpoint": "127.0.0.1:49153",
 "metadata": {"lifecycle": "ready",
              "connection": {"user": "nexora", "password": "[REDACTED]"}}}}

// without Docker (expected):
{"success": true, "data": {"environment_id": "env_...", "status": "failed",
 "metadata": {"failure_reason": "Docker Engine is unavailable"}}}
```

---

*End of report. Companion documents: `docs/current-status.md` (living status),
`docs/architecture.md` (module boundaries), `docs/api-contracts.md` (contracts),
`docs/work-package-d-summary.md` and `docs/work-package-b-summary.md` (per-WP detail).*
