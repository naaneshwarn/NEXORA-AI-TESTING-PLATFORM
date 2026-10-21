# [Work Package B] Docker environment lifecycle & synthetic PostgreSQL provisioning

> **Status: DRAFT — not yet filed.** Local only; open once the push is approved.
> **Target branch:** `feature/docker-environment` → `chore/project-foundation`
> (this repository has no `main`; `chore/project-foundation` is the Phase 2 baseline.)
> **Owner:** Rajath — Docker environment lifecycle, synthetic database provisioning and cleanup.

---

## Problem

The Phase 2 environment routes were a placeholder: `POST /api/v1/environments`
fabricated a fake endpoint (`{type}://localhost:{uuid4().hex[:4]}`) and never
provisioned anything. There was no lifecycle, no seeding, no cleanup, and no safe
connection metadata.

## Implementation summary

Replaced the placeholder with a real, provider-neutral environment service behind
the existing routes:

- **`EnvironmentManager`** orchestrates `provision → ready → reset → stop → destroy`,
  maps lifecycle onto the existing shared schema, redacts credentials, and cleans up
  partial failures.
- **`DockerProvider`** talks to the Docker Engine via the Python SDK: create, start,
  inspect (verify running before claiming ready), `pg_isready` polling, in-container
  `psql` seeding, genuine `stop` with verification, and ownership-filtered removal.
- **`database_seed.py`** produces a deterministic synthetic PostgreSQL schema and
  dataset (no real records).
- Routes stay thin; no business logic. The Phase 2 contract is preserved exactly.
  Two additive lifecycle endpoints (`reset`, `destroy`) were added.

Safety properties (per the Phase 3 guide):
- loopback-only port binding by default (`expose_publicly` to opt out);
- no broad host filesystem mounts (anonymous volume removed with the container);
- every container labelled `nexora.owner=nexora-testing-platform` and cleanup only
  ever removes the container recorded on that environment;
- credentials never leave `metadata["connection"]` unredacted, and are stripped on
  cleanup; nothing logs a password;
- never claim a container is running unless inspected and verified.

## Files changed

| File | Owner | Change |
| --- | --- | --- |
| `backend/app/integrations/environment/docker_provider.py` | Rajath | **new** — Docker provider |
| `backend/app/integrations/environment/database_seed.py` | Rajath | **new** — deterministic seed |
| `backend/app/integrations/environment/manager.py` | Rajath | **new** — lifecycle service |
| `backend/app/integrations/environment/__init__.py` | Rajath | **new** — public surface |
| `backend/app/integrations/__init__.py` | Rajath | **new** — package marker |
| `backend/app/api/routes/environments.py` | Rajath | rewired to the service; contract preserved; additive reset/destroy |
| `backend/tests/test_environment_service.py` | Rajath | **new** — 25 Docker-free tests |
| `backend/tests/test_environment_docker_integration.py` | Rajath | **new** — skip-safe live-Docker tests |
| `backend/requirements.txt` | Rajath | additive `docker==7.1.0` (lazily imported) |
| `pytest.ini` | Rajath | registers `docker` marker (skip-safe integration tests) |
| `docs/work-package-b-summary.md` | Rajath | **new** — full design record |

No shared schema (`app/schemas/`) or lead-owned store (`app/core/store.py`) was modified.

## How to run tests & actual result

```bash
python -m pytest backend -q
```

**Actual result (verified on this machine, Docker daemon NOT running):**

```
65 passed, 3 skipped
```

- 38 = pre-existing Phase 2 baseline (unchanged, still passing).
- 26 = new Docker-free environment-service tests.
- 1 = new pure unit check (DSN shape).
- 3 skipped = live Docker integration tests (`pytest.mark.docker`), skipped
  cleanly because Docker Desktop was not running.

With Docker running:

```bash
pip install -r backend/requirements.txt
python -m pytest backend/tests/test_environment_docker_integration.py -v
```

## New dependencies & environment variables

- **New dependency:** `docker==7.1.0` (additive). Imported lazily inside
  `DockerProvider`, so the API and every unit test run without it.
- **New environment variables:** none required.
- **New pytest marker:** `docker`.

## Contract changes & notes for other owners

- **Phase 2 contract preserved.** `POST/GET/…/stop` behaviour is unchanged
  (verified by the existing `test_api_contracts.py::test_environment_and_evaluation_contract`).
- **Additive endpoints:** `POST /environments/{id}/reset` and
  `POST /environments/{id}/destroy`. Non-breaking; no existing consumer affected.
- **Lifecycle-state coordination item (no change made):** the shared
  `SyntheticEnvironment.status` literal is
  `provisioning | ready | stopped | failed | cancelled` — it has no `reset`/`destroyed`.
  We did **not** edit the shared schema; the fine-grained stage is exposed in
  `metadata["lifecycle"]` (`created|provisioning|seeding|ready|resetting|failed|stopped|destroyed`).
  Promoting `reset`/`destroyed` to first-class statuses would be a shared-schema
  change and should be raised separately for team approval.
- **For Rahul (workflow):** run execution requires `status == "ready"`. Real
  provisioning reaches `ready` on its own when Docker is present; the retained
  `POST /environments/{id}/ready` endpoint lets tests force readiness without Docker.
- **For Prajwal (synthetic API):** read `metadata["connection"]` and
  `metadata["seed"]`; no schema change needed.

## Known limitations

- PostgreSQL only (other engine types fail honestly as “not supported yet”).
- In-memory environment store (consistent with Phase 2/3 scope).
- Live integration tests are opt-in (require Docker + image pull) and skip by default.
