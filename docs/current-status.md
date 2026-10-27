# NEXORA AI Testing Platform — Current Status

**Last Updated:** October 28, 2026
**Active Branch:** `feature/integration-wpb-wpd`
**Upstream Base:** `25dab08` (*Publish NEXORA AI Testing Platform source code*)

---

## 1. Executive Summary

The NEXORA platform is **launch-ready for a demo/preview deployment**: all four
Phase 3 work packages are implemented, wired together and verified end-to-end,
backend and frontend run separately, and the whole surface is documented on
OpenAPI/Swagger.

**Verification totals (as of this update):**
- Backend: **260 passed, 3 skipped** (the 3 skips are Docker-gated live
  integration tests — no Docker daemon on this machine)
- Frontend: **34 passed** (Vitest), `tsc --noEmit` clean, production build OK

**What Phase 3 added (all four work packages merged):**

1. **WP-A (Naaneshwar) — target agents + API hardening**
   - `TargetAgent` ABC + `MockTargetAgent` + thread-safe
     `TargetAgentRegistry` (`backend/app/integrations/target_agents/`).
     Any agent registered via `POST /agents` is immediately executable —
     the registry resolves unknown ids to a mock built from the agent store.
   - Agent-execution **service layer** (`app/services/agent_execution.py`)
     extracted from the route (protocol parse → run/agent validation →
     target-agent execution → traced event → protocol format). Route is a thin
     HTTP mapping with a new optional `agent_id` query param (404 unknown).
   - **Real API-key authentication**: `NEXORA_API_KEYS` +
     `NEXORA_AUTH_MODE=auto|off|write|full`. Timing-safe comparison, standard
     error envelope, synthetic sentinels honoured in every mode, health/schema
     paths always open. Enforced in a pure-ASGI `AuthMiddleware` plus the
     shared `authenticate_token()` in the route dependency.
   - **Durable persistence**: the core store snapshots to
     `NEXORA_STATE_DIR/store.json` (default `backend/.state/`) after every
     mutation, with atomic writes and corruption-tolerant loading. A restarted
     server keeps its data.
   - **Middleware stack**: `ObservabilityMiddleware` (security headers +
     structured request log, probes excluded) → CORS → `AuthMiddleware` → app;
     all pure ASGI so SSE streaming passes through untouched.
   - Synthetic-API **self-description** at `GET /api/v1/synthetic` (WP-C).

2. **WP-B (Rajath) — synthetic environments**
   - Docker-backed provisioning for postgres/mysql/mongodb/redis/neo4j/docker
     with a full lifecycle (`provisioning → ready → stopped`, plus `reset`,
     `destroy`). Without a Docker daemon the API correctly reports
     `failed: "Docker Engine is unavailable"` (specified behaviour, not a bug).

3. **WP-C (Prajwal) — synthetic API & adapters**
   - Stateful synthetic CRM (`/api/v1/leads` CRUD), deterministic fault
     injection (`simulated_latency_ms`, `inject_error`), three protocol
     adapters (`rest`, `openai`, `langchain`), redacted tool-call tracing,
     and the new `app/integrations/synthetic_api/` package (faults, lead
     repository, capability descriptor router).

4. **WP-D (Rahul) — workflow, evaluation, reports**
   - Deterministic LangGraph-compatible engine, scenario registry, mock agent
     client with injectable seam, weighted evaluator with configurable pass
     threshold and critical-finding safety rule, orchestration service with
     cancellation/timeouts/idempotency, durable run-context store with startup
     recovery, and `GET /api/v1/workflow/readiness`.
   - The dashboard drives real runs end-to-end: create run → live SSE trace
     stream → evaluation report.

**Launch-hardening added in this pass (on top of the four WPs):**
- Real API-key auth (modes, timing-safe compare, sentinels) — §4
- Durable core-store persistence (atomic, corruption-tolerant) — §5
- Security headers + structured request logging — §4
- Service-layer extraction for agent execution — §2
- Target-agent abstraction with a registry and mock fallback — §2
- Synthetic-API capability descriptor (`GET /api/v1/synthetic`) — §3
- Frontend API-key support (`authHeaders()` across all fetch clients) — §6
- CI workflow (`backend pytest` + `frontend typecheck/test/build`),
  backend/frontend Dockerfiles, `docker-compose.yml` — §7

---

## 2. Service & Repository Status

| Component | Path | Technology | Status |
| :--- | :--- | :--- | :--- |
| **Backend API** | `backend/` | FastAPI + Python 3.12/3.13 | ✅ Canonical API (`:8000`). All `/api/v1` endpoints operational; auth, persistence, middleware, target agents, synthetic API, workflow engine live. 260 tests passing |
| **Frontend UI** | `apps/web/` | React + TypeScript + Vite | ✅ Dashboard (`:3000`) drives real runs: create run, live SSE trace viewer, environment lifecycle, agent registration, API-key support. 34 tests passing, build clean |
| **Legacy/Node API** | `apps/api/` | Node.js + Express | 🟡 Placeholder retained for compatibility; **not** the canonical backend |
| **Shared Lib** | `packages/shared/` | TypeScript | ✅ Shared types/utilities |
| **Docs** | `docs/` | Markdown | ✅ Architecture, API contract, this status file |
| **CI/CD** | `.github/workflows/ci.yml` | GitHub Actions | ✅ Backend pytest + frontend typecheck/test/build on push/PR |
| **Containers** | `backend/Dockerfile`, `apps/web/Dockerfile`, `docker-compose.yml` | Docker + nginx | ✅ Non-root images with health checks; `docker compose up --build` runs the stack |

---

## 3. API Surface (OpenAPI/Swagger at `/docs`)

All endpoints are versioned under `/api/v1` (except root `/health` and the
OpenAI-compatible `/v1/*` routes) and use the standard `ApiEnvelope`
packaging `{"success", "data", "error"}`.

| Domain | Route | Method | Notes |
| :--- | :--- | :--- | :--- |
| Health | `/api/v1/health`, `/health` | `GET` | Service health (open in every auth mode) |
| Agents | `/api/v1/agents` | `POST` | Register a target agent; `409` on duplicates |
| Agents | `/api/v1/agents/{agent_id}` | `GET` | Inspect a registered agent |
| Test Runs | `/api/v1/test-runs` | `POST` | Create + auto-execute registered scenarios (unknown scenarios stay `queued`) |
| Test Runs | `/api/v1/test-runs/{run_id}` | `GET` | Run status |
| Test Runs | `/api/v1/test-runs/{run_id}/cancel` | `POST` | Cancel an active run |
| Test Runs | `/api/v1/test-runs/{run_id}/execute` | `POST` | Execute a queued run (`404` unknown, `409` non-queued) |
| Test Runs | `/api/v1/test-runs/{run_id}/events` | `GET` | Execution timeline |
| Test Runs | `/api/v1/test-runs/{run_id}/traces` | `GET` | **Redacted** tool-call traces |
| Test Runs | `/api/v1/test-runs/{run_id}/report` | `GET` | Rich `WorkflowReport` (criteria, findings, threshold) |
| Test Runs | `/api/v1/test-runs/{run_id}/stream` | `GET` | **SSE** live trace stream (`tool_trace` + terminal `run_status`) |
| Environments | `/api/v1/environments` | `POST` | Provision a synthetic environment |
| Environments | `/api/v1/environments/{id}` | `GET` | Environment status |
| Environments | `/api/v1/environments/{id}/ready\|stop\|reset\|destroy` | `POST` | Lifecycle transitions |
| Evaluations | `/api/v1/evaluations` | `POST` | Submit an evaluation, generate a report |
| Reports | `/api/v1/reports/{report_id}` | `GET` | Fetch an evaluation report |
| CRM Leads | `/api/v1/leads` | `POST` | Create lead (`201`) |
| CRM Leads | `/api/v1/leads` | `GET` | List leads; fault injection via `simulated_latency_ms` / `inject_error` |
| CRM Leads | `/api/v1/leads/{lead_id}` | `GET`/`PUT`/`DELETE` | Read / full replace / delete (`404` when missing) |
| Synthetic Agent | `/api/v1/synthetic/agent/execute/{protocol}` | `POST` | Protocol dispatcher (`rest`, `openai`, `langchain`); optional `run_id` (tracing) and `agent_id` (target agent, `404` unknown) |
| Synthetic API | `/api/v1/synthetic` | `GET` | **Self-description**: protocols, tools, fault ranges, auth mode, redaction contract |
| Synthetic API | `/api/v1/synthetic/tools` | `GET` | Tool registry |
| Workflow | `/api/v1/workflow/readiness` | `GET` | Engine readiness + process metrics |
| OpenAI-compat | `/v1/models`, `/v1/health` | `GET` | OpenAI-compatible discovery/health |

---

## 4. Authentication (WP-A launch hardening)

Configuration (`backend/app/core/auth.py`, `app/core/middleware.py`):

- `NEXORA_API_KEYS` — comma-separated accepted keys (empty ⇒ auth off).
- `NEXORA_AUTH_MODE` — `auto` (default: `write` when keys exist, else `off`),
  `off`, `write` (mutations require a key; **reads stay open** so the
  dashboard, Swagger and SSE keep working), `full` (everything requires a key).
  An explicit `write`/`full` with no keys degrades to `off` with a startup
  warning instead of locking everyone out.
- Credentials accepted via `X-API-Key` or `Authorization: Bearer`
  (Bearer wins when both are present); comparison is **timing-safe**
  (`secrets.compare_digest` over every configured key).
- Synthetic sentinels honoured in every mode: `invalid-token-test` → 401,
  `forbidden-token-test` → 403.
- Always-open paths: `/health`, `/api/v1/health`, `/v1/health`, `/v1/models`,
  `/docs`, `/redoc`, `/openapi.json`.
- Enforcement is duplicated at the edge (`AuthMiddleware`, standard error
  envelope) and in the route dependency (`verify_optional_auth`) so a route
  behaves identically with or without the middleware.

**Known limitation:** the browser's `EventSource` cannot send headers, so the
SSE stream relies on reads staying open — `write` mode (effective whenever
keys are configured with `auto`) is the recommended production config. `full`
mode breaks dashboard streaming by design.

**Frontend:** `apps/web/src/api/auth.ts` resolves a key from `sessionStorage`
(`nexora_api_key`) or build-time `VITE_API_KEY` and spreads `X-API-Key` into
every mutating fetch. A token never appears in a URL.

---

## 5. Durable Persistence (WP-A launch hardening)

`backend/app/core/persistence.py` snapshots the whole core store
(`AGENTS`, `TEST_RUNS`, `ENVIRONMENTS`, `EVENTS`, `REPORTS`, `TOOL_TRACES`,
`WORKFLOW_REPORTS`, `CRM_LEADS`) to `NEXORA_STATE_DIR/store.json` (default
`backend/.state/`) after every mutation and rehydrates at startup.

- **Atomic**: temp-file + `os.replace`; a crash mid-write never corrupts the
  last good snapshot.
- **Corruption tolerant**: an unreadable/malformed snapshot is logged and
  skipped — the process starts empty instead of crashing. Invalid individual
  records are skipped without dropping the rest.
- **Opt-out, not opt-in**: enabled by default; `NEXORA_STATE_DIR=""` disables
  it. `tests/conftest.py` disables it at import time plus an autouse fixture
  so the suite stays hermetic.
- The workflow subsystem keeps its own durable run-context store
  (`WORKFLOW_STATE_DIR`) with startup recovery of interrupted runs.

---

## 6. Frontend Status

`apps/web/` is a four-tab dashboard (Runs, Agents, Environments, Workflow)
driving the live backend:

- **Runs**: create a test run (bound to the built-in deterministic scenario),
  live SSE trace stream (`useTestRunStream` + `TraceStreamViewer`), cancel,
  report view.
- **Agents**: register/list agents (registration makes them executable).
- **Environments**: create + lifecycle (`ready`/`stop`/`reset`/`destroy`).
- **Workflow**: readiness metrics from `/api/v1/workflow/readiness`.
- API-key aware via `authHeaders()`; error surfaces use the standard envelope.

**Verification:** 34 Vitest tests pass (4 files, incl. 4 new auth tests),
`npx tsc --noEmit` clean, `npm run build` succeeds (~165 kB JS / 52 kB gzip).

---

## 7. CI, Containers & Configuration

- **CI** (`.github/workflows/ci.yml`): backend job (pip install + pytest) and
  frontend job (npm install at workspace root + tsc + vitest + vite build).
- **Backend image** (`backend/Dockerfile`): `python:3.12-slim`, non-root,
  `/data/state` volume for persistence, health check on `/health`.
- **Frontend image** (`apps/web/Dockerfile`): node build stage → nginx serve
  stage with SPA fallback (`nginx.conf`).
- **Compose** (`docker-compose.yml`): backend `:8000` + web `:3000`, named
  volume for the store, optional `docker_provisioning` profile that mounts the
  Docker socket for live environment provisioning.
- **Configuration**: see `.env.example` — `NEXORA_API_KEYS`,
  `NEXORA_AUTH_MODE`, `NEXORA_STATE_DIR`, `CORS_ORIGINS`, `WORKFLOW_*`,
  `VITE_API_BASE_URL`, `VITE_API_KEY`.

---

## 8. Testing & Verification

### Backend (`cd backend && .venv/Scripts/python -m pytest -q`)
**260 passed, 3 skipped** (~6s). The 3 skips are Docker-gated live
integration tests (`pytest.mark.docker`) that auto-skip without a daemon.

New coverage added in this pass (79 tests across 6 files):
- `test_persistence.py` (16): round-trip of every collection, atomic writes,
  corruption/shape/BOM tolerance, invalid-record skipping, disable semantics,
  and an HTTP restart cycle proving data survives a "process restart".
- `test_auth_enforcement.py` (17): mode resolution, timing-safe key matching,
  401/403 envelopes, reads-open in write mode, sentinels in every mode,
  health/schema always open.
- `test_middleware.py` (9): security headers on success/404/422/preflight,
  request logging with probes excluded, error-envelope shape.
- `test_target_agents.py` (15): ABC contract, mock execution, tracing +
  redaction, registry semantics, store-agent resolution, unknown-id errors.
- `test_agent_execution_service.py` (18): service-level protocol/run/agent
  validation, event recording, redaction, plus HTTP status mapping.
- `test_synthetic_api.py` (13): capability descriptor, repository CRUD,
  fault-injection contract and validation.

### Frontend (`cd apps/web && npm run test`)
**34 passed** (4 files). Typecheck and production build clean.

### Live verification (this pass)
- Full endpoint smoke: env lifecycle, runs/reports/traces/events, CRM
  CRUD + 422/404, 3 protocol adapters, fault injection (429), auth sentinels
  (401/403), secret redaction, failure scenario (hallucination → score 60,
  fail), SSE (`tool_trace` + `run_status` frames).
- Dashboard driven end-to-end in a real browser with zero console errors.
- Swagger UI at `/docs` lists every route above.

---

## 9. Remaining Work (documented, not blockers)

1. **Real target-agent providers** — the `TargetAgent` ABC + registry +
   `agent_client` seam are ready; implement an OpenAI/Anthropic/etc. agent
   class and register it. Workflow execution currently runs the deterministic
   mock.
2. **Docker-backed environment provisioning** — code and SDK integration are
   complete; requires a host with a Docker daemon (or the compose
   `docker_provisioning` profile). Verified to fail gracefully without one.
3. **PostgreSQL/Redis store swap** — `core/persistence.py` is the seam for a
   real database; today it is a durable JSON snapshot.
4. **Browser-level SSE e2e test** — covered by backend contract tests and
   manual browser verification; an automated browser e2e remains.
5. **Deployment automation** — CI runs tests/builds; image publishing and
   environment-specific deploy pipelines are not yet wired.
6. **Additional adapters** — Anthropic tool-use and MCP tool-schema adapters
   alongside `rest`/`openai`/`langchain`.
