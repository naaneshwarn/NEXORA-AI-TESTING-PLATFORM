"""Unit tests for the scenario registry, mock agent client, and evaluator.

Everything here is deterministic: synthetic CRM records only, no credentials,
no Docker, no network.  Each agent behavior (correct / hallucinated / error /
timeout) is exercised end to end through the telemetry wrapper so trace
redaction is verified at the same time.
"""

from __future__ import annotations

import asyncio

from app.core.store import create_crm_lead, get_traces_for_run
from app.workflow.agent_client import SyntheticToolAgentClient
from app.workflow.evaluator import (
    DEFAULT_PASS_THRESHOLD,
    evaluate_run,
    extract_secret_values,
    validate_pass_threshold,
)
from app.workflow.scenarios import (
    SEED_LEAD_EMAIL,
    ensure_seed_lead,
    get_scenario,
    is_registered_scenario,
    list_scenario_ids,
)

from app.workflow.evaluator import InvalidPassThreshold
import pytest


# --------------------------------------------------------------------------
# Scenario registry
# --------------------------------------------------------------------------


def test_registry_exposes_documented_scenarios() -> None:
    assert list_scenario_ids() == [
        "crm-read-customer-agent-failure",
        "crm-read-customer-hallucination",
        "crm-read-customer-summary",
    ]
    assert is_registered_scenario("crm-read-customer-summary")
    assert not is_registered_scenario("browser regression")
    assert get_scenario("nope") is None

    scenario = get_scenario("crm-read-customer-summary")
    assert scenario is not None
    assert scenario.tool_name == "get_crm_lead"
    assert scenario.summary_fields == ("name", "email", "status")


def test_seed_lead_is_deterministic_and_idempotent() -> None:
    first = ensure_seed_lead()
    second = ensure_seed_lead()

    assert first["id"] == second["id"]
    assert first["email"] == SEED_LEAD_EMAIL


# --------------------------------------------------------------------------
# Mock agent client behaviors
# --------------------------------------------------------------------------


def _run_turn(run_id: str, behavior: str, parameters: dict, timeout: float = 5.0):
    lead = ensure_seed_lead()
    client = SyntheticToolAgentClient()
    scenario = get_scenario("crm-read-customer-summary")
    return asyncio.run(
        client.run_turn(
            run_id=run_id,
            tool_name=scenario.tool_name,
            parameters=parameters,
            behavior=behavior,
            timeout_seconds=timeout,
            summary_fields=scenario.summary_fields,
        )
    )


def test_correct_behavior_summarizes_only_returned_fields_and_records_trace() -> None:
    lead = ensure_seed_lead()
    outcome = _run_turn("run-correct", "correct", {"lead_id": lead["id"], "api_key": "leak-me-not-123"})

    assert outcome.success is True
    assert lead["name"] in outcome.summary
    assert lead["email"] in outcome.summary
    assert lead["status"] in outcome.summary

    traces = get_traces_for_run("run-correct")
    assert len(traces) == 1
    trace = traces[0]
    assert trace["success"] is True
    assert trace["tool_name"] == "get_crm_lead"
    # The secret variable is redacted in persisted telemetry.
    assert trace["parameters"]["api_key"] == "[REDACTED]"
    assert "leak-me-not-123" not in str(trace)


def test_hallucinated_behavior_injects_forbidden_marker() -> None:
    lead = ensure_seed_lead()
    outcome = _run_turn("run-halluc", "hallucinated", {"lead_id": lead["id"]})

    assert outcome.success is True
    assert "platinum-vip" in outcome.summary
    assert lead["status"] in outcome.summary


def test_error_behavior_is_normalized_and_traced() -> None:
    outcome = _run_turn("run-error", "error", {"lead_id": "irrelevant"})

    assert outcome.success is False
    assert outcome.error is not None
    assert outcome.error["code"] == "tool_execution_error"
    assert "Simulated agent backend failure" in outcome.error["message"]

    traces = get_traces_for_run("run-error")
    assert len(traces) == 1
    assert traces[0]["success"] is False


def test_timeout_behavior_fails_fast_with_agent_timeout() -> None:
    outcome = _run_turn("run-timeout", "timeout", {"lead_id": "irrelevant"}, timeout=0.05)

    assert outcome.success is False
    assert outcome.error is not None
    assert outcome.error["code"] == "agent_timeout"


def test_unknown_lead_is_a_normalized_failure() -> None:
    outcome = _run_turn("run-missing-lead", "correct", {"lead_id": "lead-does-not-exist"})

    assert outcome.success is False
    assert outcome.error is not None
    assert outcome.error["code"] == "tool_execution_error"


# --------------------------------------------------------------------------
# Evaluator
# --------------------------------------------------------------------------


def test_perfect_run_scores_full_marks_and_passes() -> None:
    scenario = get_scenario("crm-read-customer-summary")
    lead = create_crm_lead({"name": "Eval Lead", "email": "eval@example.com", "status": "new"})
    outcome = _run_turn("run-eval-perfect", "correct", {"lead_id": lead["id"]})

    evaluation = evaluate_run(
        scenario,
        outcome,
        get_traces_for_run("run-eval-perfect"),
        threshold=DEFAULT_PASS_THRESHOLD,
        run_variables={"lead_id": lead["id"]},
    )

    assert evaluation.score == 100.0
    assert evaluation.status == "pass"
    assert evaluation.findings == []
    assert [criterion.criterion for criterion in evaluation.criteria] == [
        "task_completion",
        "factual_correctness",
        "trace_integrity",
    ]


def test_hallucinated_run_fails_with_specific_finding() -> None:
    scenario = get_scenario("crm-read-customer-hallucination")
    lead = ensure_seed_lead()
    outcome = _run_turn("run-eval-halluc", "hallucinated", {"lead_id": lead["id"]})

    evaluation = evaluate_run(
        scenario,
        outcome,
        get_traces_for_run("run-eval-halluc"),
        threshold=DEFAULT_PASS_THRESHOLD,
    )

    assert evaluation.status == "fail"
    assert evaluation.score < DEFAULT_PASS_THRESHOLD
    unsupported = [finding for finding in evaluation.findings if finding.code == "unsupported_fact"]
    assert len(unsupported) == 1
    assert "platinum-vip" in unsupported[0].message
    assert unsupported[0].severity == "critical"
    assert unsupported[0].evidence_ref == outcome.call_id


def test_failed_agent_run_scores_zero_task_completion() -> None:
    scenario = get_scenario("crm-read-customer-agent-failure")
    outcome = _run_turn("run-eval-error", "error", {"lead_id": "irrelevant"})

    evaluation = evaluate_run(
        scenario,
        outcome,
        get_traces_for_run("run-eval-error"),
        threshold=DEFAULT_PASS_THRESHOLD,
    )

    assert evaluation.status == "fail"
    task = next(c for c in evaluation.criteria if c.criterion == "task_completion")
    assert task.score == 0.0
    assert any(finding.code == "agent_execution_failed" for finding in evaluation.findings)


def test_missing_trace_is_flagged_as_incomplete_evidence() -> None:
    scenario = get_scenario("crm-read-customer-summary")
    lead = ensure_seed_lead()
    outcome = _run_turn("run-eval-no-trace", "correct", {"lead_id": lead["id"]})

    evaluation = evaluate_run(scenario, outcome, traces=[], threshold=DEFAULT_PASS_THRESHOLD)

    trace_criterion = next(c for c in evaluation.criteria if c.criterion == "trace_integrity")
    assert trace_criterion.score == 0.0
    assert any(finding.code == "missing_tool_trace" for finding in evaluation.findings)


def test_secret_leak_in_artifacts_is_critical() -> None:
    scenario = get_scenario("crm-read-customer-summary")
    lead = ensure_seed_lead()
    outcome = _run_turn("run-eval-leak", "correct", {"lead_id": lead["id"]})

    forged_traces = [{"success": True, "parameters": {"api_key": "raw-secret-value-999"}}]
    evaluation = evaluate_run(
        scenario,
        outcome,
        forged_traces,
        threshold=DEFAULT_PASS_THRESHOLD,
        run_variables={"api_key": "raw-secret-value-999"},
    )

    trace_criterion = next(c for c in evaluation.criteria if c.criterion == "trace_integrity")
    assert trace_criterion.score == 0.0
    assert any(finding.code == "secret_exposure" for finding in evaluation.findings)
    assert evaluation.status == "fail"


def test_pass_threshold_is_configurable_and_validated() -> None:
    scenario = get_scenario("crm-read-customer-summary")
    lead = ensure_seed_lead()
    outcome = _run_turn("run-eval-threshold", "correct", {"lead_id": lead["id"]})

    # A correct agent turn whose trace recorded failure scores 90/100 with no
    # critical findings, so only the threshold decides pass vs fail.
    partial_traces = [{"success": False, "tool_name": "get_crm_lead"}]

    strict = evaluate_run(scenario, outcome, partial_traces, threshold=95.0)
    relaxed = evaluate_run(scenario, outcome, partial_traces, threshold=85.0)

    assert strict.status == "fail"
    assert relaxed.status == "pass"
    assert strict.score == relaxed.score == 90.0

    assert validate_pass_threshold(70) == 70.0
    assert validate_pass_threshold("55.5") == 55.5
    with pytest.raises(InvalidPassThreshold):
        validate_pass_threshold(101)
    with pytest.raises(InvalidPassThreshold):
        validate_pass_threshold("not-a-number")


def test_critical_findings_block_pass_even_with_relaxed_threshold() -> None:
    """A hallucinated run has critical findings; no threshold may let it pass."""
    scenario = get_scenario("crm-read-customer-hallucination")
    lead = ensure_seed_lead()
    outcome = _run_turn("run-eval-blocking", "hallucinated", {"lead_id": lead["id"]})
    traces = get_traces_for_run("run-eval-blocking")

    relaxed = evaluate_run(scenario, outcome, traces, threshold=0.0)

    assert relaxed.score >= 0.0
    assert relaxed.status == "fail"
    assert "Critical findings block a passing result" in relaxed.summary


def test_evaluation_is_deterministic_for_fixed_inputs() -> None:
    scenario = get_scenario("crm-read-customer-hallucination")
    lead = ensure_seed_lead()
    outcome = _run_turn("run-eval-determinism", "hallucinated", {"lead_id": lead["id"]})
    traces = get_traces_for_run("run-eval-determinism")

    first = evaluate_run(scenario, outcome, traces, threshold=DEFAULT_PASS_THRESHOLD)
    second = evaluate_run(scenario, outcome, traces, threshold=DEFAULT_PASS_THRESHOLD)

    assert first.score == second.score
    assert first.summary == second.summary
    assert [f.model_dump() for f in first.findings] == [f.model_dump() for f in second.findings]


def test_extract_secret_values_matches_sensitively_named_variables() -> None:
    secrets = extract_secret_values(
        {"api_key": "s1", "API-SECRET": "s2", "Authorization": "s3", "lead_id": "not-a-secret", "count": 5}
    )
    assert secrets == ["s1", "s2", "s3"]
