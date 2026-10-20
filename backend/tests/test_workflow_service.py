"""End-to-end unit tests for the workflow orchestration service.

Each test drives the full graph (validate -> environment -> scenario ->
agent -> evaluate -> report -> finalize) against the in-memory store.  No
credentials, Docker, network, or wall-clock-dependent assertions are used.
"""

from __future__ import annotations

import asyncio

from app.core.store import (
    AGENTS,
    create_environment,
    create_test_run,
    get_events_for_run,
    get_test_run,
    get_traces_for_run,
    get_workflow_report_for_run,
    update_environment,
)
from app.schemas.agent import AgentConfig
from app.schemas.environment import SyntheticEnvironment
from app.schemas.test_run import RunCreateRequest, ScenarioConfig
from app.workflow.service import (
    build_run_context,
    execute_workflow_run,
    register_run_context,
)


def _make_run(
    scenario_id: str,
    variables: dict | None = None,
    config: dict | None = None,
    agents: list[str] | None = None,
    suite: str = "workflow-suite",
) -> str:
    payload = RunCreateRequest(
        suite_name=suite,
        scenario=ScenarioConfig(name=scenario_id, variables=variables or {}),
        config=config or {},
        target_agents=agents or [],
    )
    run = create_test_run(payload)
    context = build_run_context(run.run_id, payload)
    assert context is not None
    register_run_context(context)
    return run.run_id


def _execute(run_id: str) -> dict:
    return asyncio.run(execute_workflow_run(run_id))


# --------------------------------------------------------------------------
# Success path
# --------------------------------------------------------------------------


def test_successful_run_reaches_passed_state_with_full_score_report() -> None:
    run_id = _make_run("crm-read-customer-summary")

    result = _execute(run_id)

    assert result["executed"] is True
    assert result["state"] == "passed"

    run = get_test_run(run_id)
    assert run.state == "passed"
    assert run.completed_at is not None

    report = get_workflow_report_for_run(run_id)
    assert report is not None
    assert report["status"] == "pass"
    assert report["score"] == 100.0
    assert report["pass_threshold"] == 70.0
    assert [criterion["criterion"] for criterion in report["criteria"]] == [
        "task_completion",
        "factual_correctness",
        "trace_integrity",
    ]
    assert report["evidence"]["tool_call_ids"]
    assert report["evidence"]["event_ids"]

    # The Phase 2 ReportSummary projection is stored alongside the rich report,
    # keyed by its own summary report ID.
    from app.core.store import REPORTS

    summary = REPORTS[result["summary_report_id"]]
    assert summary.run_id == run_id
    assert summary.score == 100.0
    assert summary.status == "generated"


def test_run_events_tell_the_whole_story_in_order() -> None:
    run_id = _make_run("crm-read-customer-summary")
    _execute(run_id)

    events = get_events_for_run(run_id)
    types = [event.event_type for event in events]

    assert types[0] == "created"
    assert "started" in types
    assert "tool_call" in types
    assert "result" in types
    assert types[-1] == "completed"
    # Sequence numbers are strictly increasing.
    assert [event.sequence for event in events] == list(range(1, len(events) + 1))


def test_seed_lead_is_used_when_no_lead_id_supplied() -> None:
    run_id = _make_run("crm-read-customer-summary")
    _execute(run_id)

    report = get_workflow_report_for_run(run_id)
    assert report["status"] == "pass"

    heartbeat = [e for e in get_events_for_run(run_id) if "seed lead" in e.message]
    assert len(heartbeat) == 1


# --------------------------------------------------------------------------
# Failure scenarios from the Phase 3 guide
# --------------------------------------------------------------------------


def test_hallucinating_agent_produces_failed_run_with_specific_finding() -> None:
    run_id = _make_run("crm-read-customer-hallucination")

    result = _execute(run_id)

    assert result["state"] == "failed"
    report = get_workflow_report_for_run(run_id)
    assert report["status"] == "fail"
    codes = [finding["code"] for finding in report["findings"]]
    assert "unsupported_fact" in codes
    assert report["workflow_state"] == "failed"


def test_agent_failure_produces_useful_failed_run_report() -> None:
    run_id = _make_run("crm-read-customer-agent-failure")

    result = _execute(run_id)

    assert result["state"] == "failed"
    report = get_workflow_report_for_run(run_id)
    assert report is not None, "failed runs must still produce a report where possible"
    codes = [finding["code"] for finding in report["findings"]]
    assert "agent_execution_failed" in codes
    task = next(c for c in report["criteria"] if c["criterion"] == "task_completion")
    assert task["score"] == 0.0


def test_agent_timeout_is_normalized_and_reported() -> None:
    # Register a timeout-behavior variant of the summary scenario, then pin a
    # tiny per-agent timeout so the hanging mock is cancelled immediately.
    from app.workflow.scenarios import SCENARIOS, ScenarioDefinition

    SCENARIOS["crm-read-customer-summary-timeout"] = ScenarioDefinition(
        scenario_id="crm-read-customer-summary-timeout",
        description="Timeout variant for tests.",
        goal="Normalize agent timeouts into failed runs.",
        tool_name="get_crm_lead",
        agent_behavior="timeout",
    )
    try:
        run_id = _make_run("crm-read-customer-summary-timeout", config={"agent_timeout_seconds": 0.05})
        result = _execute(run_id)
        assert result["state"] == "failed"
        report = get_workflow_report_for_run(run_id)
        messages = " ".join(finding["message"] for finding in report["findings"])
        assert "agent_timeout" in messages or "exceeded" in messages
    finally:
        SCENARIOS.pop("crm-read-customer-summary-timeout", None)


# --------------------------------------------------------------------------
# Environment readiness
# --------------------------------------------------------------------------


def test_unbound_environment_uses_local_mock() -> None:
    run_id = _make_run("crm-read-customer-summary")

    _execute(run_id)

    assert get_test_run(run_id).state == "passed"


def test_bound_environment_must_be_ready() -> None:
    env = create_environment(
        SyntheticEnvironment(environment_id="env-provisioning", environment_type="postgres", label="wf-db")
    )
    run_id = _make_run("crm-read-customer-summary", config={"environment_id": env.environment_id})

    result = _execute(run_id)

    assert result["state"] == "failed"
    run = get_test_run(run_id)
    assert "not 'ready'" in run.message
    error_events = [e for e in get_events_for_run(run_id) if e.event_type == "error"]
    assert error_events and error_events[0].payload.get("code") == "environment_not_ready"
    # No evaluation report is published when the workflow could not run the agent.
    assert get_workflow_report_for_run(run_id) is None


def test_ready_environment_allows_the_run() -> None:
    env = create_environment(
        SyntheticEnvironment(environment_id="env-ready", environment_type="postgres", label="wf-db-ready")
    )
    update_environment(_with_status(env, "ready"))
    run_id = _make_run("crm-read-customer-summary", config={"environment_id": env.environment_id})

    result = _execute(run_id)

    assert result["state"] == "passed"


def _with_status(env: SyntheticEnvironment, status: str) -> SyntheticEnvironment:
    env.status = status  # type: ignore[assignment]
    return env


def test_unknown_environment_id_fails_the_run() -> None:
    run_id = _make_run("crm-read-customer-summary", config={"environment_id": "env-missing"})

    result = _execute(run_id)

    assert result["state"] == "failed"
    assert "was not found" in get_test_run(run_id).message


# --------------------------------------------------------------------------
# Cancellation semantics
# --------------------------------------------------------------------------


def test_cancelled_run_is_never_executed_or_marked_successful() -> None:
    run_id = _make_run("crm-read-customer-summary")
    from app.core.store import cancel_test_run

    cancel_test_run(run_id)

    result = _execute(run_id)

    assert result["executed"] is False
    assert get_test_run(run_id).state == "cancelled"
    assert get_workflow_report_for_run(run_id) is None


def test_cancellation_during_execution_stops_before_a_passing_result() -> None:
    run_id = _make_run("crm-read-customer-summary")
    from app.core.store import cancel_test_run
    from app.workflow.agent_client import SyntheticToolAgentClient

    original = SyntheticToolAgentClient.run_turn

    async def cancel_mid_turn(self, *args, **kwargs):
        outcome = await original(self, *args, **kwargs)
        cancel_test_run(run_id)  # user cancels while the agent is working
        return outcome

    SyntheticToolAgentClient.run_turn = cancel_mid_turn  # type: ignore[method-assign]
    try:
        result = _execute(run_id)
    finally:
        SyntheticToolAgentClient.run_turn = original  # type: ignore[method-assign]

    run = get_test_run(run_id)
    assert run.state == "cancelled"
    assert result["state"] == "cancelled"
    # No report may claim success for a cancelled run.
    report = get_workflow_report_for_run(run_id)
    assert report is None or report["status"] != "pass"


# --------------------------------------------------------------------------
# Validation, idempotency, and configuration
# --------------------------------------------------------------------------


def test_invalid_pass_threshold_fails_the_run_with_a_clear_error() -> None:
    run_id = _make_run("crm-read-customer-summary", config={"pass_threshold": 400})

    result = _execute(run_id)

    assert result["state"] == "failed"
    assert "pass_threshold" in get_test_run(run_id).message
    assert get_workflow_report_for_run(run_id) is None


def test_invalid_agent_timeout_fails_the_run() -> None:
    run_id = _make_run("crm-read-customer-summary", config={"agent_timeout_seconds": "soon"})

    result = _execute(run_id)

    assert result["state"] == "failed"
    assert "agent_timeout_seconds" in get_test_run(run_id).message


def test_custom_pass_threshold_is_honored() -> None:
    run_id = _make_run(
        "crm-read-customer-hallucination",
        config={"pass_threshold": 25.0},
    )

    _execute(run_id)

    report = get_workflow_report_for_run(run_id)
    # Relaxed threshold, but critical findings still block the pass.
    assert report["pass_threshold"] == 25.0
    assert report["status"] == "fail"


def test_a_run_executes_at_most_once() -> None:
    run_id = _make_run("crm-read-customer-summary")

    first = _execute(run_id)
    second = _execute(run_id)

    assert first["executed"] is True
    assert second["executed"] is False
    assert second["reason"] == "run_is_passed"


def test_unknown_scenario_in_context_fails_with_available_scenarios_listed() -> None:
    run_id = _make_run("browser regression")

    result = _execute(run_id)

    assert result["state"] == "failed"
    message = get_test_run(run_id).message
    assert "not registered" in message
    assert "crm-read-customer-summary" in message


def test_unregistered_target_agent_is_reported_as_warning() -> None:
    AGENTS.pop("agent-ghost", None)
    run_id = _make_run("crm-read-customer-summary", agents=["agent-ghost"])

    _execute(run_id)

    report = get_workflow_report_for_run(run_id)
    warnings = [finding for finding in report["findings"] if finding["code"] == "agent_not_registered"]
    assert len(warnings) == 1
    assert warnings[0]["severity"] == "warning"
    # A warning does not block a pass.
    assert report["status"] == "pass"


def test_registered_target_agent_produces_no_warning() -> None:
    AGENTS["agent-real"] = AgentConfig(agent_id="agent-real", name="real", role="executor", status="active")
    try:
        run_id = _make_run("crm-read-customer-summary", agents=["agent-real"])

        _execute(run_id)

        report = get_workflow_report_for_run(run_id)
        assert not [f for f in report["findings"] if f["code"] == "agent_not_registered"]
        assert report["evidence"]["agent_ids"] == ["agent-real"]
    finally:
        AGENTS.pop("agent-real", None)


# --------------------------------------------------------------------------
# Security: secrets never reach reports or events
# --------------------------------------------------------------------------


def test_secret_variables_are_redacted_everywhere_end_to_end() -> None:
    run_id = _make_run(
        "crm-read-customer-summary",
        variables={"api_key": "super-secret-do-not-leak-42"},
    )

    _execute(run_id)

    serialized_traces = str(get_traces_for_run(run_id))
    serialized_events = str(get_events_for_run(run_id))
    serialized_report = str(get_workflow_report_for_run(run_id))
    serialized_run = str(get_test_run(run_id))

    for artifact in (serialized_traces, serialized_events, serialized_report, serialized_run):
        assert "super-secret-do-not-leak-42" not in artifact

    trace = get_traces_for_run(run_id)[0]
    assert trace["parameters"]["api_key"] == "[REDACTED]"
