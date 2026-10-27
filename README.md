# NEXORA AI Testing Platform

NEXORA is an AI-powered testing platform for autonomous agents: it orchestrates
multi-step test workflows, provisions synthetic environments, drives target
agents through multiple wire protocols, injects deterministic faults, and
produces evaluation reports — all against a fully synthetic, credential-free
surface.

**Phase 3 status:** all four work packages (A–D) are implemented and tested —
260 backend tests and 34 frontend tests pass, the API is fully documented on
OpenAPI/Swagger, and the dashboard runs against the live backend.

---

## Quick start

### 1. Backend (FastAPI, port 8000)

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate        # Windows — use `source .venv/bin/activate` on macOS/Linux
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

- Swagger UI: <http://127.0.0.1:8000/docs>
- ReDoc: <http://127.0.0.1:8000/redoc>
- Health: <http://127.0.0.1:8000/api/v1/health>

### 2. Frontend (React + Vite, port 3000)

In a second terminal, from the repository root:

```bash
npm install
npm run dev          # builds @nexora/shared then serves apps/web
```

Open <http://localhost:3000>. The dashboard talks to `http://localhost:8000`
by default; override with `VITE_API_BASE_URL` (see `.env.example`).

### 3. Tests

```bash
# Backend (260 tests; 3 Docker-gated tests skip when no daemon is present)
cd backend && .venv\Scripts\python -m pytest -q

# Frontend (34 tests + typecheck)
cd apps/web && npm run test && npx tsc --noEmit
```

### 4. Everything in Docker

```bash
docker compose up --build
# Backend  : http://localhost:8000/docs
# Dashboard: http://localhost:3000
```

---

## How it works

### The testing loop

1. **Register an agent** — `POST /api/v1/agents` records a target agent
   (planner/executor/observer/reporter). Any registered agent is immediately
   executable through the deterministic mock backend — no agent runtime to
   deploy.
2. **Create a test run** — `POST /api/v1/test-runs` with a scenario binding
   (e.g. the built-in `crm-read-customer-summary`) schedules workflow
   execution in the background.
3. **Watch it live** — `GET /api/v1/test-runs/{id}/stream` streams
   Server-Sent Events (`created`, `started`, `tool_call`, `result`,
   `completed`) that the dashboard renders as a live trace.
4. **Inspect the evidence** — `GET /api/v1/test-runs/{id}/traces` returns
   redacted tool-call traces; `/events` returns the full timeline;
   `/report` returns the evaluation report with score, criteria and findings.
5. **Evaluate** — the workflow evaluator scores determinism, correctness,
   fault resilience and redaction against a configurable pass threshold
   (`WORKFLOW_DEFAULT_PASS_THRESHOLD`, default 70).

### What the agents are tested against

A **synthetic CRM API** (`/api/v1/leads` — full CRUD) stands in for a real
external service. It is deterministic, in-memory and durable across restarts.
Fault-injection query parameters exercise agent resiliency:

```
GET /api/v1/leads?simulated_latency_ms=1500   # non-blocking synthetic delay
GET /api/v1/leads?inject_error=429            # deterministic rate-limit response
```

Agents call this surface through three wire protocols via
`POST /api/v1/synthetic/agent/execute/{protocol}`:

| Protocol  | Wire shape                                            |
|-----------|-------------------------------------------------------|
| `rest`    | `{call_id, tool_name, parameters}` → same shape back  |
| `openai`  | OpenAI function-call shape (`function.name/arguments`)|
| `langchain` | LangChain tool-call shape                           |

`GET /api/v1/synthetic` publishes a machine-readable self-description of the
whole surface: protocols, tool registry, fault ranges, auth mode and the
redaction contract.

### Synthetic environments (WP-B)

`POST /api/v1/environments` provisions postgres/mysql/mongodb/redis/neo4j/docker
environments with a full lifecycle: `provisioning → ready → stopped`, plus
`reset` and `destroy`. On a machine without a Docker daemon the API correctly
reports `failed: "Docker Engine is unavailable"` — this is the specified
behaviour, not a bug. Run the backend on a Docker host (or start the
`docker_provisioning` profile in `docker-compose.yml`) for live containers.

### Durability

All platform state (agents, runs, environments, leads, traces, reports)
snapshots to `NEXORA_STATE_DIR/store.json` (default `backend/.state/`) after
every mutation and rehydrates at startup — a restarted server keeps its data.
Writes are atomic (temp file + rename) and a corrupt snapshot never blocks
startup. Set `NEXORA_STATE_DIR=""` to disable.

---

## Authentication

Authentication is **off by default** so local development needs no setup.
Configure `NEXORA_API_KEYS` (comma-separated) to turn it on:

| `NEXORA_AUTH_MODE` | Behaviour                                                                 |
|--------------------|---------------------------------------------------------------------------|
| `auto` (default)   | `write` when keys exist, otherwise `off`                                  |
| `off`              | never enforce (synthetic sentinels still simulate 401/403)                |
| `write`            | mutations (`POST/PUT/PATCH/DELETE`) require a valid key; **reads open**   |
| `full`             | every request under the API prefix requires a valid key                   |

```bash
export NEXORA_API_KEYS="my-secret-key"
export NEXORA_AUTH_MODE=auto
```

```bash
# Mutation without a key → 401 (standard error envelope)
curl -X POST http://localhost:8000/api/v1/leads \
  -H "Content-Type: application/json" \
  -d '{"name":"Ada","email":"ada@nexora.test"}'

# With a key → 201
curl -X POST http://localhost:8000/api/v1/leads \
  -H "Content-Type: application/json" -H "X-API-Key: my-secret-key" \
  -d '{"name":"Ada","email":"ada@nexora.test"}'
```

Accepted credentials: `X-API-Key: <key>` or `Authorization: Bearer <key>`
(comparison is timing-safe). Health and schema endpoints (`/health`,
`/docs`, `/openapi.json`, `/v1/models`) stay open in every mode so probes and
API explorers keep working.

**Testing denial without an identity provider** — two sentinel values are
honoured in every mode: `invalid-token-test` → 401, `forbidden-token-test` → 403.

**Dashboard note:** the browser's `EventSource` cannot send headers, so the SSE
trace stream relies on reads staying open — `write` mode (the effective mode
when keys are configured with `auto`) is the recommended production setting.
`full` mode protects reads but breaks dashboard streaming. The dashboard picks
up a key from `sessionStorage` (`nexora_api_key`) or the build-time
`VITE_API_KEY`; a token never appears in a URL.

---

## API surface (OpenAPI)

Every endpoint below is documented interactively at `/docs`:

| Method | Path | Purpose |
|--------|------|---------|
| GET    | `/api/v1/health` | Service health |
| POST   | `/api/v1/agents` | Register a target agent |
| GET    | `/api/v1/agents/{agent_id}` | Fetch a registered agent |
| POST   | `/api/v1/test-runs` | Create + schedule a workflow run |
| GET    | `/api/v1/test-runs/{run_id}` | Run status |
| POST   | `/api/v1/test-runs/{run_id}/cancel` | Cancel a run |
| POST   | `/api/v1/test-runs/{run_id}/execute` | Drive an agent turn directly |
| GET    | `/api/v1/test-runs/{run_id}/events` | Execution timeline |
| GET    | `/api/v1/test-runs/{run_id}/traces` | Redacted tool-call traces |
| GET    | `/api/v1/test-runs/{run_id}/report` | Evaluation report |
| GET    | `/api/v1/test-runs/{run_id}/stream` | **SSE** live trace stream |
| POST   | `/api/v1/environments` | Provision a synthetic environment |
| GET    | `/api/v1/environments/{id}` | Environment status |
| POST   | `/api/v1/environments/{id}/ready\|stop\|reset\|destroy` | Lifecycle |
| POST   | `/api/v1/evaluations` | Submit an evaluation |
| GET    | `/api/v1/reports/{report_id}` | Fetch a report |
| GET    | `/api/v1/leads` (± fault params) | List CRM leads (fault injection) |
| POST   | `/api/v1/leads` | Create a lead |
| GET/PUT/DELETE | `/api/v1/leads/{lead_id}` | Read / replace / delete a lead |
| POST   | `/api/v1/synthetic/agent/execute/{protocol}` | Execute an agent tool call |
| GET    | `/api/v1/synthetic` | Synthetic-surface self-description |
| GET    | `/api/v1/synthetic/tools` | Tool registry |
| GET    | `/api/v1/workflow/readiness` | Workflow engine readiness + metrics |
| GET    | `/v1/models`, `/v1/health` | OpenAI-compatible endpoints |

All responses use the standard envelope `{"success": bool, "data": ..., "error": ...}`;
errors carry `{code, message, details}`.

---

## Repository layout

- `backend/` — **Python FastAPI application** (canonical API, port 8000)
  - `app/api/routes/` — HTTP layer (thin: status codes + envelopes)
  - `app/services/` — business logic (agent execution)
  - `app/core/` — config, auth, middleware, store + persistence, adapters,
    telemetry, redaction, tools
  - `app/integrations/` — `target_agents/` (WP-A), `environment/` (WP-B),
    `synthetic_api/` (WP-C)
  - `app/workflow/` — orchestration, evaluation, reporting (WP-D)
  - `tests/` — 260 pytest tests
- `apps/web/` — React + TypeScript dashboard (Vite, port 3000)
- `apps/api/` — legacy Node/Express placeholder, retained for compatibility
  (not the canonical backend)
- `packages/shared/` — shared TypeScript utilities
- `docs/` — architecture and status documentation
- `.github/workflows/ci.yml` — CI: backend pytest + frontend typecheck/test/build

---

## Configuration

Copy `.env.example` to `.env` (backend reads it via pydantic-settings). Key
variables:

| Variable | Default | Purpose |
|----------|---------|---------|
| `NEXORA_API_KEYS` | *(empty)* | Comma-separated accepted API keys |
| `NEXORA_AUTH_MODE` | `auto` | `auto` / `off` / `write` / `full` |
| `NEXORA_STATE_DIR` | `.state` | Durable store snapshot dir (empty = off) |
| `CORS_ORIGINS` | `localhost:3000,5173` | Allowed browser origins |
| `WORKFLOW_TOTAL_TIMEOUT_SECONDS` | `30` | Whole-run timeout |
| `WORKFLOW_AGENT_TIMEOUT_SECONDS` | `10` | Per-turn agent timeout |
| `WORKFLOW_DEFAULT_PASS_THRESHOLD` | `70` | Score required to pass |
| `WORKFLOW_MAX_CONCURRENT_RUNS` | `4` | Workflow concurrency limit |
| `VITE_API_BASE_URL` | `http://localhost:8000` | Dashboard → API base URL |
| `VITE_API_KEY` | *(empty)* | Build-time dashboard API key |

---

## Security posture

- Timing-safe API-key comparison; secrets never logged (redaction of
  `password`, `api_key`, `token`, `authorization`, `secret`, … in all telemetry)
- Security headers on every response (`X-Content-Type-Options`,
  `X-Frame-Options`, `Referrer-Policy`, COOP/CORP, `Permissions-Policy`)
- Structured request logging with health/readiness probes excluded
- Pure-ASGI middleware so SSE streaming is never buffered
- Container images run as non-root with health checks
- Fault injection is deterministic and side-effect free (evaluated before any
  store operation, so an injected failure can never corrupt synthetic data)

---

## What remains to implement

The platform is fully functional end-to-end today; the items below are the
planned next steps that require infrastructure beyond this machine or live
third-party credentials:

1. **Real target agents** — the `TargetAgent` ABC and registry are the seam:
   implement a provider class (OpenAI/Anthropic/etc. via the existing
   `agent_client` interface) and register it. Workflow execution currently runs
   the deterministic mock.
2. **Docker-backed environments** — code is complete and SDK-integrated;
   requires a host with a Docker daemon (or the compose
   `docker_provisioning` profile).
3. **PostgreSQL / Redis persistence swap** — the store's snapshot layer
   (`core/persistence.py`) is the seam for a real database backend; today it
   is a durable JSON snapshot.
4. **Browser-level SSE e2e test** — the SSE stream is covered by backend tests
   and driven manually in the dashboard; an automated browser e2e remains.
5. **CI hardening** — the GitHub Actions workflow runs tests and builds;
   container image publishing and deployment automation are not yet wired.

See `docs/current-status.md` for the detailed per-work-package status.
