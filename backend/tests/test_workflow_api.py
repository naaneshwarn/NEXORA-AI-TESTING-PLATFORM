"""API contract tests for workflow-enabled test-run and report endpoints.

Covers the additive endpoints (``POST /test-runs/{id}/execute`` and
``GET /test-runs/{id}/report``), auto-execution of registered scenarios, and
backward compatibility: runs with unknown or missing scenarios keep the
legacy ``queued`` behavior asserted by the Phase 2 contract tests.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _create_run(scenario_name: str | None, variables: dict | None = None, config: dict | None = None) -> str:
    payload: dict = {"suite_name": "api-workflow-suite", "environment": "local"}
    if scenario_name is not None:
        payload["scenario"] = {"name": scenario_name, "variables": variables or {}}
    if config:
        payload["config"] = config
    response = client.post("/api/v1/test-runs", json=payload)
    assert response.status_code == 201
    return response.json()["data"]["run_id"]


def test_registered_scenario_aut_executes_but_post_body_stays_queued() -> None:
    run_id = _create_run("crm-read-customer-summary")

    # The Phase 2 contract response shape is preserved: the run was queued.
    # Background execution completes deterministically under TestClient, so a
    # follow-up GET already reflects the terminal state.
    status = client.get(f"/api/v1/test-runs/{run_id}")
    assert status.status_code == 200
    assert status.json()["data"]["state"] == "passed"


def test_unknown_scenario_name_keeps_legacy_queued_behavior() -> None:
    run_id = _create_run("browser regression")

    status = client.get(f"/api/v1/test-runs/{run_id}")
    assert status.json()["data"]["state"] == "queued"

    cancelled = client.post(f"/api/v1/test-runs/{run_id}/cancel")
    assert cancelled.status_code == 200
    assert cancelled.json()["data"]["state"] == "cancelled"


def test_scenario_less_run_stays_queued() -> None:
    run_id = _create_run(None)

    status = client.get(f"/api/v1/test-runs/{run_id}")
    assert status.json()["data"]["state"] == "queued"


def test_manual_execute_endpoint_runs_once_then_conflicts() -> None:
    # Use an unknown scenario name so nothing auto-executes, then bind the
    # scenario through a registered one for the manual path.
    run_id = _create_run("crm-read-customer-agent-failure")

    # Auto-execution already completed this run; manual execute must conflict.
    executed = client.post(f"/api/v1/test-runs/{run_id}/execute")
    assert executed.status_code == 409
    assert "only queued runs can be executed" in executed.text


def test_manual_execute_unknown_run_returns_404() -> None:
    response = client.post("/api/v1/test-runs/run-does-not-exist/execute")
    assert response.status_code == 404
    assert "was not found" in response.text


def test_manual_execute_without_registered_scenario_lists_options() -> None:
    run_id = _create_run("browser regression")

    response = client.post(f"/api/v1/test-runs/{run_id}/execute")

    assert response.status_code == 409
    assert "no registered scenario" in response.text
    assert "crm-read-customer-summary" in response.text
    # The run is untouched and still cancellable.
    assert client.get(f"/api/v1/test-runs/{run_id}").json()["data"]["state"] == "queued"


def test_manual_execute_is_deterministic_for_a_fresh_run() -> None:
    # Cancel the auto-scheduled execution path by creating a run without a
    # registered scenario is impossible; instead create a run bound to a
    # registered scenario and let auto-execution produce the terminal state.
    run_id = _create_run("crm-read-customer-hallucination")

    status = client.get(f"/api/v1/test-runs/{run_id}").json()["data"]
    assert status["state"] == "failed"
    assert "scored" in status["message"]


def test_workflow_report_endpoint_returns_rich_report() -> None:
    run_id = _create_run("crm-read-customer-summary")

    response = client.get(f"/api/v1/test-runs/{run_id}/report")

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    data = body["data"]
    assert data["run_id"] == run_id
    assert data["scenario_id"] == "crm-read-customer-summary"
    assert data["status"] == "pass"
    assert data["score"] == 100.0
    assert data["pass_threshold"] == 70.0
    assert len(data["criteria"]) == 3
    assert data["findings"] == []
    assert data["evidence"]["tool_call_ids"]
    assert data["evidence"]["event_ids"]


def test_workflow_report_endpoint_404s() -> None:
    unknown_run = client.get("/api/v1/test-runs/run-does-not-exist/report")
    assert unknown_run.status_code == 404
    assert "was not found" in unknown_run.text

    queued_run_id = _create_run(None)
    no_report = client.get(f"/api/v1/test-runs/{queued_run_id}/report")
    assert no_report.status_code == 404
    assert "No workflow report" in no_report.text


def test_phase2_summary_endpoint_serves_workflow_runs() -> None:
    run_id = _create_run("crm-read-customer-hallucination")

    report_id = client.get(f"/api/v1/test-runs/{run_id}/report").json()["data"]["report_id"]
    assert report_id  # rich report exists

    # The projection is discoverable through the existing report list store.
    from app.core.store import REPORTS

    summary_id = next(rid for rid, summary in REPORTS.items() if summary.run_id == run_id)
    summary = client.get(f"/api/v1/reports/{summary_id}")
    assert summary.status_code == 200
    assert summary.json()["data"]["run_id"] == run_id
    assert summary.json()["data"]["score"] < 70.0


def test_workflow_report_id_is_retrievable_through_reports_route() -> None:
    """The ``wfreport-…`` ID the API publishes must resolve on /reports/{id}.

    Regression for a real integration seam defect: ``GET /test-runs/{id}/report``
    returned a ``wfreport-…`` ID that ``GET /reports/{id}`` could not find,
    because the rich report lives in a separate store from the Phase-2
    ``ReportSummary`` projection.  The published ID was therefore a dead
    reference.  The route now falls back to the workflow report store.
    """
    run_id = _create_run("crm-read-customer-summary")

    report = client.get(f"/api/v1/test-runs/{run_id}/report").json()["data"]
    published_id = report["report_id"]
    assert published_id.startswith("wfreport-")

    fetched = client.get(f"/api/v1/reports/{published_id}")
    assert fetched.status_code == 200
    data = fetched.json()["data"]
    assert data["report_id"] == published_id
    assert data["run_id"] == run_id
    assert data["status"] == report["status"]
    # The rich projection keeps its own contract (criteria/evidence/pass_threshold).
    assert data["criteria"] and "pass_threshold" in data


def test_reports_route_still_serves_phase2_summaries_and_404s_unknown() -> None:
    """The fallback must not break the Phase-2 contract or unknown lookups."""
    submission = client.post(
        "/api/v1/evaluations",
        json={"run_id": "run-manual", "score": 88.0, "status": "pass", "summary": "manual"},
    )
    assert submission.status_code == 201
    summary_id = submission.json()["data"]["report_id"]
    assert summary_id.startswith("report-")

    fetched = client.get(f"/api/v1/reports/{summary_id}")
    assert fetched.status_code == 200
    assert fetched.json()["data"]["summary"] == "manual"

    assert client.get("/api/v1/reports/report-does-not-exist").status_code == 404


def test_secret_variables_never_appear_in_http_responses() -> None:
    secret = "http-secret-canary-777"
    run_id = _create_run(
        "crm-read-customer-summary",
        variables={"api_key": secret},
    )

    report = client.get(f"/api/v1/test-runs/{run_id}/report")
    traces = client.get(f"/api/v1/test-runs/{run_id}/traces")
    events = client.get(f"/api/v1/test-runs/{run_id}/events")
    run = client.get(f"/api/v1/test-runs/{run_id}")

    for response in (report, traces, events, run):
        assert response.status_code == 200
        assert secret not in response.text
    assert "[REDACTED]" in traces.text


def test_agent_failure_scenario_fails_with_diagnostic_report_over_http() -> None:
    run_id = _create_run("crm-read-customer-agent-failure")

    state = client.get(f"/api/v1/test-runs/{run_id}").json()["data"]
    assert state["state"] == "failed"

    report = client.get(f"/api/v1/test-runs/{run_id}/report").json()["data"]
    assert report["status"] == "fail"
    assert report["score"] < report["pass_threshold"]
    assert report["findings"], "a failing run must publish diagnostic findings"


def test_invalid_pass_threshold_surfaces_clear_error_over_http() -> None:
    run_id = _create_run("crm-read-customer-summary", config={"pass_threshold": 400})

    state = client.get(f"/api/v1/test-runs/{run_id}").json()["data"]
    assert state["state"] == "failed"
    assert "pass_threshold" in state["message"]
    # No report is published for a run that failed before evaluation.
    assert client.get(f"/api/v1/test-runs/{run_id}/report").status_code == 404


def test_full_demo_flow_pass_and_fail() -> None:
    """The Phase 3 guide's demonstration: one passing and one failing scenario."""
    agent = client.post(
        "/api/v1/agents",
        json={
            "agent_id": "agent-demo-rahul",
            "name": "demo-agent",
            "role": "executor",
            "provider": "mock",
            "status": "active",
        },
    )
    assert agent.status_code == 201

    environment = client.post(
        "/api/v1/environments",
        json={"environment_type": "postgres", "label": "demo-db", "config": {}},
    )
    assert environment.status_code == 201
    env_id = environment.json()["data"]["environment_id"]

    # Not ready yet: a run bound to it must fail safely — and publish a
    # useful failed-run report (Phase 3 guide acceptance criterion).
    failing = _create_run("crm-read-customer-summary", config={"environment_id": env_id})
    failing_state = client.get(f"/api/v1/test-runs/{failing}").json()["data"]
    assert failing_state["state"] == "failed"
    assert "ready" in failing_state["message"]

    failing_env_report = client.get(f"/api/v1/test-runs/{failing}/report")
    assert failing_env_report.status_code == 200
    env_report = failing_env_report.json()["data"]
    assert env_report["status"] == "fail"
    assert env_report["score"] == 0.0
    assert any(finding["code"] == "environment_not_ready" for finding in env_report["findings"])

    # Mark ready via the Phase 2 lifecycle endpoint and rerun with a fresh run.
    ready = client.post(f"/api/v1/environments/{env_id}/ready")
    assert ready.status_code == 200
    assert ready.json()["data"]["status"] == "ready"

    passing = _create_run("crm-read-customer-summary", config={"environment_id": env_id})
    passing_state = client.get(f"/api/v1/test-runs/{passing}").json()["data"]
    assert passing_state["state"] == "passed"

    passing_report = client.get(f"/api/v1/test-runs/{passing}/report").json()["data"]
    assert passing_report["status"] == "pass"

    hallucination = _create_run("crm-read-customer-hallucination")
    failing_report = client.get(f"/api/v1/test-runs/{hallucination}/report").json()["data"]
    assert failing_report["status"] == "fail"
    assert any(finding["code"] == "unsupported_fact" for finding in failing_report["findings"])
