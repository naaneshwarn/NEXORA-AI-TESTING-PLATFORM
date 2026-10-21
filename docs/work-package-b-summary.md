# Work Package B — Docker Environment Lifecycle & Synthetic Database Provisioning

**Owner:** Rajath
**Branch:** `feature/docker-environment`
**Base:** `chore/project-foundation` (this repo has no `main`; the foundation branch is the Phase 2 baseline)
**Status:** Implemented, unit-tested (Docker-free), integration test present and skip-safe.
**Scope rule followed:** this work packages is *standalone* — it does not depend on or modify any other owner's Phase 3 features.

---

## 1. Problem / goal

Phase 2 exposed environment routes as a **placeholder**: `POST /api/v1/environments`
fabricated an endpoint (`{type}://localhost:{uuid}`) and never provisioned
anything. Work Package B replaces that placeholder with a real lifecycle service
that:

- provisions a disposable synthetic database (PostgreSQL first, per the guide),
- seeds it with deterministic synthetic data,
- exposes safe connection metadata,
- supports reset and idempotent cleanup,
- and **never claims a container is running unless it has been verified**.

The Phase 2 HTTP contract is preserved exactly.

---

## 2. What was built

### New module: `backend/app/integrations/environment/`

| File | Responsibility |
| --- | --- |
| `docker_provider.py` | Real Docker Engine provider on the Python Docker SDK. Creates/starts/inspects/stops/removes containers, resolves the bound host port, runs commands inside the container, and polls `pg_isready`. Owns the ownership labels and the loopback-only port policy. |
| `database_seed.py` | Deterministic synthetic PostgreSQL schema + dataset (`nexora.leads`, 3 fixed rows). Renders idempotent DDL/DML as SQL text. No real customer records; emails use the reserved `.test` TLD. |
| `manager.py` | `EnvironmentManager` — the service layer behind the routes. Orchestrates provision → ready → reset → stop → destroy, maps lifecycle onto the shared schema, redacts credentials, and guarantees partial-failure cleanup. |
| `__init__.py` | Public surface. |

### Rewritten route layer: `backend/app/api/routes/environments.py`

Thin HTTP layer over the manager; **no business logic in routes**.

| Method | Path | Behaviour | Change |
| --- | --- | --- | --- |
| POST | `/api/v1/environments` | `201`, `status: provisioning` immediately; real provisioning runs in the background | contract preserved |
| GET | `/api/v1/environments/{id}` | `200`/`404`, credentials redacted | contract preserved |
| POST | `/api/v1/environments/{id}/stop` | `200`/`404`, genuinely stops the container and verifies | contract preserved |
| POST | `/api/v1/environments/{id}/ready` | `200`/`404` | compatibility endpoint (see §5) |
| POST | `/api/v1/environments/{id}/reset` | `200`/`404`, truncate + reseed | **additive** |
| POST | `/api/v1/environments/{id}/destroy` | `200`/`404`, idempotent cleanup | **additive** |

### Tests

| File | What it covers |
| --- | --- |
| `backend/tests/test_environment_service.py` | 26 Docker-free tests of the real manager against a fake provider: happy path, Docker-unavailable failure, container-not-running failure, seed failure, create failure, unsupported engine, reset, stop, cleanup after success and partial failure, repeated cleanup idempotency, credential redaction, and route-level contract/404/lifecycle. |
| `backend/tests/test_environment_docker_integration.py` | Optional live-Docker integration tests. **Skip cleanly** when Docker is unavailable (`pytest.mark.docker`), so the default run stays green everywhere. |

---

## 3. Design decisions (and why)

1. **Background provisioning, synchronous contract.**
   The existing contract test asserts `POST /environments` returns `201 + status: provisioning`
   synchronously. Real Docker work is therefore scheduled via FastAPI
   `BackgroundTasks`; the response is contract-identical while the container is
   created out of band and the record later becomes `ready` or `failed`.

2. **Seeding via `exec_run(psql …)` instead of a host DB driver.**
   The backend declares no PostgreSQL client dependency (`psycopg`/`psycopg2`
   are absent), and the guide forbids exposing database ports broadly. Seeding
   from *inside* the container with `psql` needs no host driver and keeps the
   exposure minimal.

3. **Loopback-only ports by default.**
   The default host binding is `127.0.0.1` on an ephemeral port. A caller must
   explicitly pass `config.expose_publicly: true` to bind `0.0.0.0`.

4. **Ownership labels + filter-on-owned-resource cleanup.**
   Every container carries `nexora.owner=nexora-testing-platform`,
   `nexora.environment_id`, and `nexora.engine`. Cleanup only ever removes the
   container id recorded on that specific environment, so it can never touch a
   resource the platform does not own.

5. **Verify, never assume.**
   `DockerProvider.is_running` inspects the container; `stop` reloads and checks
   the reported status before reporting success. `provision` refuses to mark an
   environment `ready` unless the container is running *and* `pg_isready` passes.

6. **No secret leakage.**
   Credentials live only under `metadata["connection"]`. The route layer applies
   `redact_connection()` before serialization, replacing `password` and `dsn`
   with `[REDACTED]`. `cleanup_environment` removes the connection block entirely.
   Nothing in the module logs a password.

7. **No host filesystem mounts.**
   Containers use only their own anonymous volume, removed with the container
   (`remove(v=True)`).

8. **`store.py` was not modified.**
   The existing `create_environment` / `get_environment` / `update_environment`
   functions already persist the whole `SyntheticEnvironment` object including
   `metadata`, so no shared-file change was needed.

---

## 4. Lifecycle state mapping (contract note)

The shared `SyntheticEnvironment.status` is a `Literal` of
`provisioning | ready | stopped | failed | cancelled`. It has **no**
`reset`/`destroyed` members. Per the repository rule (“do not modify shared
schemas independently”), this work does **not** edit the schema. Instead:

- `status` always stays within the existing literal, and
- the finer lifecycle stage is carried in `metadata["lifecycle"]`:

  `created | provisioning | seeding | ready | resetting | failed | stopped | destroyed`

**Coordination item (not a change):** if the team wants `reset`/`destroyed` as
first-class statuses, that is a shared-schema change requiring team approval and
should be raised as a separate PR. Until then, `metadata["lifecycle"]` is the
source of truth for the fine-grained stage.

---

## 5. Compatibility notes for other owners

- **Run execution (Rahul/WP-D)** binds to an environment and requires
  `status == "ready"`. Real provisioning now reaches `ready` on its own when
  Docker is present. The additive `POST /environments/{id}/ready` endpoint is
  retained so a test/operator can force readiness **deterministically without
  Docker** — important because unit test suites must not require Docker.
- **Synthetic API (Prajwal)** can read `metadata["connection"]` (host, port,
  database, username) and `metadata["seed"]` (schema, row count) without any
  schema change.
- **Adapter (Naaneshwar):** unaffected; no shared interface touched.

---

## 6. How to run the tests

From the repository root:

```bash
# All backend tests — no Docker, no API keys, deterministic
python -m pytest backend -q
```

Expected result on a machine without Docker (verified): **65 passed, 3 skipped**.
The 3 skips are the live-Docker integration tests.

With Docker running, to exercise the real provider:

```bash
pip install -r backend/requirements.txt   # includes docker==7.1.0
python -m pytest backend/tests/test_environment_docker_integration.py -v
```

`docker version` must succeed first. The first run pulls `postgres:16-alpine`.

---

## 7. New dependencies & configuration

- **New dependency:** `docker==7.1.0` (additive, `backend/requirements.txt`).
  Imported lazily, so the API and all unit tests run without it.
- **New pytest marker:** `docker` (registered in root `pytest.ini`) for the
  skip-safe integration tests.
- **New environment variables:** none required. Optional request-level config
  keys (all defaulted and bounded): `image`, `internal_port`, `network`,
  `nano_cpus`, `mem_limit`, `database`, `username`, `password`,
  `expose_publicly`, `env`.

---

## 8. Known limitations

- **PostgreSQL only.** Other `environment_type` values return a `failed`
  environment with an honest “not supported yet” message rather than pretending.
- **In-memory store.** Environments live in the existing process-local store,
  consistent with the rest of Phase 2/3; durable persistence is out of scope.
- **Live integration tests are opt-in.** They require Docker and network access
  to pull the image, so they skip by default. This is intentional and matches the
  guide's testing rule.
- **No container health `HEALTHCHECK` reliance.** Readiness is verified with
  `pg_isready` polling inside the container, not by trusting Docker health alone.
