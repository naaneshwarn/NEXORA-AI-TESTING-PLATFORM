# Work Package D — Complete Work Summary

**Owner:** Rahul (Workflows & Evaluation)
**Branch:** `feature/workflow-evaluation-reporting`
**Base:** `4703dbc` (*Merge pull request #7 — feature/synthetic-api*)
**Status:** ✅ Complete, all fixes applied, **109 tests passing**
**Last updated:** October 21, 2026

> This document is the single consolidated record of *everything* done for Work Package D
> (LangGraph workflow, scenarios, simulated-user/advisory checks, evaluation, scoring, and
> reporting) as required by the Phase 3 Implementation Guide. It covers the original build,
> the 10 verification checkpoints, the live demonstration, the professional audit, the
> follow-up fixes, test evidence, and the outstanding team-coordination items.

---

## 1. Scope delivered

Work Package D is the **workflow, evaluation, and reporting layer** of the NEXORA AI Testing
Platform. Delivered on one branch:

| Area | What was built |
| :--- | :--- |
| **Workflow engine** | Deterministic state machine with a LangGraph-compatible API (`add_node`, `add_conditional_edges`, `compile`, `invoke`), cancellation, failure capture, finalize-once, and **cleanup-once-before-finalize** guarantees. Zero new dependencies. |
| **Scenarios** | Three deterministic scenarios (`crm-read-customer-summary`, `crm-read-customer-hallucination`, `crm-read-customer-agent-failure`) with an idempotent synthetic seed CRM lead. Expected results live in the registry, never in the agent-visible prompt. |
| **Simulated agent client** | `SyntheticToolAgentClient` supporting `correct`, `hallucinated`, `error`, and `timeout` behaviours — the documented seam where a real `TargetAgent` provider plugs in. |
| **Security / advisory checks** | Standalone `security_checks.py` module that scans persisted artifacts for leaked secret variables and emits critical `secret_exposure` findings; advisory warnings (`agent_not_registered`, `empty_summary`, `missing_tool_trace`) never block a pass on their own. |
| **Evaluation & scoring** | Weighted criteria (task 40 / factual 40 / trace 20), configurable per-run `pass_threshold` (default 70.0, validated 0–100), hallucination detection via forbidden markers, and the safety rule **any critical finding blocks a pass regardless of score**. |
| **Orchestration service** | `validate → verify_environment → build_scenario → invoke_agent → evaluate → publish_report → cleanup → finalize`, with a run-context registry, idempotent execution (queued-state guard), and a 30 s total timeout. |
| **Reporting** | Rich `WorkflowReport` (criteria, findings, evidence, threshold, duration) via new `GET /api/v1/test-runs/{run_id}/report`, plus a `ReportSummary` projection so the Phase 2 `GET /api/v1/reports/{report_id}` endpoint keeps working unchanged. |
| **API surface (additive)** | `POST /api/v1/test-runs/{run_id}/execute` (404 unknown run, 409 non-queued or unregistered scenario) and background auto-execution of registered scenarios on `POST /api/v1/test-runs` (legacy `queued` response preserved). |

**Out of scope:** the separate *Aegis Quant* blueprint — not part of Work Package D.

---

## 2. Files added or changed

### New files
| File | Purpose |
| :--- | :--- |
| `backend/app/workflow/graph.py` | Workflow engine (nodes, edges, conditional routing, cancellation, error capture, cleanup + finalize guarantees). |
| `backend/app/workflow/scenarios.py` | Scenario registry + deterministic seed lead. |
| `backend/app/workflow/agent_client.py` | Mock agent client (`correct`/`hallucinated`/`error`/`timeout`). |
| `backend/app/workflow/evaluator.py` | Scoring, threshold validation, findings, pass/fail decision. |
| `backend/app/workflow/security_checks.py` | **Standalone security evaluator** (added during the audit fixes). |
| `backend/app/workflow/service.py` | Orchestration service and graph wiring. |
| `backend/app/schemas/workflow_report.py` | `WorkflowReport`, `CriterionScore`, `Finding`, `ReportEvidence` (additive new schema file). |
| `backend/tests/test_workflow_engine.py` | Engine tests, incl. cleanup guarantees. |
| `backend/tests/test_workflow_evaluation.py` | Evaluator/scoring tests. |
| `backend/tests/test_security_checks.py` | Security module tests (added during the audit fixes). |
| `backend/tests/test_workflow_service.py` | Orchestration tests. |
| `backend/tests/test_workflow_api.py` | HTTP-level tests. |

### Modified files (additive only)
| File | Change |
| :--- | :--- |
| `backend/app/core/store.py` | **Lead-owned file — additive-only, flagged for review**: `WORKFLOW_REPORTS`, `update_test_run_state`, `save_workflow_report`, `get_workflow_report`, `get_workflow_report_for_run`. |
| `backend/app/api/routes/test_runs.py` | Background auto-execution for registered scenarios; `POST .../execute`. |
| `backend/app/api/routes/evaluations.py` | `GET /api/v1/test-runs/{run_id}/report`. |
| `docs/api-contracts.md`, `docs/current-status.md`, `docs/changes.md` | Contract, status, and change-log documentation. |

**No existing file in `app/schemas/` was modified.** All shared-contract changes are additive
and live in new files.

---

## 3. Verification checkpoints (C1–C10 + audit)

Every step was verified before moving on:

| Checkpoint | What was verified |
| :--- | :--- |
| **C1** | Repository and guide reconnaissance; branch/scope confirmed; no shared schema edits required. |
| **C2** | Engine unit tests: node order, conditional edges, cancellation, failure capture, finalize-once, determinism. |
| **C3** | Evaluator tests: weighted scoring, threshold validation, hallucination detection, critical-finding safety rule. |
| **C4** | Scenario and mock-client tests: deterministic behaviours, seed lead idempotency. |
| **C5** | Service tests: environment checks, idempotency, invalid-config failures, timeouts, cancellation. |
| **C6** | API tests: auto-execution contract compatibility, execute (200/404/409), report (200/404), Phase 2 projection. |
| **C7** | Full suite green after each milestone (38 → 46 → 62 → 82 → 94 → 96 tests). |
| **C8** | **Live uvicorn demonstration** over real HTTP (see §4). |
| **C9** | Security review: secret redaction verified end to end; canary value never present in traces/reports/events. |
| **C10** | Commit hygiene: 6 clean milestone commits, working tree clean, nothing pushed. |
| **Audit** | Professional self-audit against the guide's acceptance criteria — found and fixed the 3 gaps in §5. |

---

## 4. Live HTTP demonstration (C8)

Server: `python -m uvicorn app.main:app` on `127.0.0.1:8000`, exercised with real HTTP requests:

1. Health check OK; demo agent registered; synthetic environment created.
2. Run bound to a `provisioning` environment **fails safely** with a clear message.
3. `POST /environments/{id}/ready` marks it ready.
4. A fresh run reaches **`passed`** with report **`score 100.00`, `status pass`**.
5. `crm-read-customer-hallucination` run **fails** with score **60.00** and a
   `critical/unsupported_fact` finding citing `platinum-vip`.
6. Secret canary supplied via `scenario.variables` is **absent** from traces (stored as `[REDACTED]`).
7. Unknown scenario `"browser regression"` keeps legacy **`queued`** behaviour.
8. Server logs: **no 500s, no tracebacks, no secret material**.

Re-verified after the audit fixes (see §5): environment-failure run produces `fail` / `0.0` /
`environment_not_ready` report; a `cleanup` event is observable before `finalize`; the secret
canary is never present in the report response.

---

## 5. Professional audit findings and fixes

A self-audit was run against the Phase 3 guide's acceptance criteria. Three genuine gaps were
found and **all were fixed** (final milestone commit):

### Gap 1 — Environment failure did not publish a report
- **Problem:** an environment failure set `state.error` and the engine routed straight to
  finalize, so the run failed with **no report** — contradicting the guide ("Environment/agent
  failure produces a useful failed-run report where possible") and the service's own docstring.
- **Fix:** `_publish_failure_report()` builds a zero-scored `WorkflowReport` with a **critical
  finding carrying the error code** (`environment_not_found` / `environment_not_ready`), full
  evidence, and a Phase 2 `ReportSummary` projection. Validation-stage errors (invalid
  `pass_threshold`, unknown scenario, missing context) intentionally stay report-less.
- **Evidence:** `test_bound_environment_must_be_ready`, `test_unknown_environment_id_fails_the_run`,
  `test_validation_errors_stay_report_less`, and the HTTP demo-flow assertion.

### Gap 2 — No explicit cleanup step
- **Problem:** the guide asks for cleanup to be handled *explicitly*; errors and cancellations
  routed straight to finalize.
- **Fix:** `WorkflowGraph.set_cleanup(name)` + reworked `CompiledWorkflow.invoke` guarantee the
  cleanup node runs **exactly once before finalize on all four exit paths** — normal completion,
  node failure, routing error, and cancellation. The service's `n_cleanup` node releases
  scenario-owned resources (an explicit, idempotent no-op that records what it inspected) and
  emits an auditable `heartbeat` event.
- **Evidence:** 5 new engine tests + a service test asserting exactly one cleanup event on both
  the success and failure paths.

### Gap 3 — Security check entangled with scoring
- **Problem:** secret-leak detection was embedded in the `trace_integrity` scoring block, mixing
  security logic with scoring logic.
- **Fix:** new `backend/app/workflow/security_checks.py` owns `extract_secret_values`,
  `artifact_contains_secret`, and `evaluate_security` (returning a `SecurityCheckResult`).
  `evaluate_run` calls it as a separate step and still applies its result to trace integrity, so
  behaviour is unchanged while the check is independently selectable and testable.
  `extract_secret_values` stays importable from `evaluator` for backward compatibility.
- **Evidence:** new `backend/tests/test_security_checks.py` (7 tests).

---

## 6. Test evidence

```
python -m pytest -q
109 passed, 5 warnings in ~1.3s
```

| Module | Tests | Covers |
| :--- | ---: | :--- |
| pre-existing baseline (7 modules) | 38 | Phase 2/3 platform contracts (unchanged) |
| `test_workflow_engine.py` | 13 | ordering, routing, cancellation, failure capture, cleanup-on-every-path, definition validation |
| `test_workflow_evaluation.py` | 16 | scoring, thresholds, hallucination, secret leak, critical-finding rule |
| `test_security_checks.py` | 7 | standalone security evaluator |
| `test_workflow_service.py` | 23 | environment, idempotency, config errors, reports, timeouts, cancellation, cleanup |
| `test_workflow_api.py` | 14 | execute/report endpoints, contract compatibility, secret canary, demo flow |
| **Total** | **109** | **71 Work Package D tests added** |

Guarantees: **no API keys, no Docker, no network** required; fully deterministic (no clocks or
randomness in assertions).

---

## 7. Commits

All commits are **local** on `feature/workflow-evaluation-reporting` and **have not been pushed**
(per the "do not push" instruction).

| Commit | Message | Tests after |
| :--- | :--- | ---: |
| `4535298` | feat(workflow): add deterministic graph engine and rich report schemas | 46 |
| `484eeb4` | feat(workflow): add scenario registry, mock agent client, and deterministic evaluator | 62 |
| `0fe30da` | feat(workflow): add orchestrator service with cancellation, failures, and reporting | 82 |
| `c4dd376` | feat(api): wire workflow execution and report endpoints into test-runs API | 94 |
| `b73e073` | test(api): cover agent-failure and invalid-threshold paths end-to-end over HTTP | 96 |
| `e134d52` | docs: document workflow execution and report contracts, WP-D status and changes | 96 |
| *(final milestone)* | fix(workflow): environment-failure reports, explicit cleanup node, standalone security evaluator | **109** |

---

## 8. Security posture

- **No secrets in artifacts:** scenario-variable secrets are redacted before storage; reports
  carry only `evidence_ref` ids; the standalone security evaluator fails any run whose persisted
  output leaks a secret.
- **Canary tests:** an HTTP test asserts the raw secret value never appears in report, traces,
  events, or run responses.
- **No credentials anywhere:** tests need no API keys; nothing is pushed; the diff was scanned
  for secret-like patterns (only intentional test canaries such as `sk-live-abc123` remain).
- **Shared contracts respected:** no existing `app/schemas/` file modified; `store.py` changes
  are additive-only and flagged for lead review.

---

## 9. Outstanding team-coordination items (not code defects)

1. **`store.py` review** — the file is lead-owned; the additive workflow helpers still need team
   sign-off.
2. **`TargetAgent` interface** — Naaneshwar's provider interface is not yet in the repo;
   `SyntheticToolAgentClient` is the documented integration seam, so no rework is expected.
3. **Report-field / scoring sign-off** — the team still needs to confirm the report fields and
   scoring weights (schemas were kept additive-only to avoid blocking anyone).
4. **WhatsApp reference image** — the image could not be read (no image input available), so any
   requirements it contains are unaddressed.

---

## 10. Suggested next steps (beyond WP-D scope)

- Swap the in-repo state machine for real LangGraph (`langgraph` is already pinned) — the API was
  deliberately kept compatible, so this is a drop-in change.
- Wire a live LLM agent provider behind `agent_client.py`.
- Extend the environment verification check to Rajath's Docker-backed provider once merged.
- Add browser-level end-to-end coverage for the workflow report UI.
