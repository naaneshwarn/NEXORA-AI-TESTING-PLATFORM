"""Deterministic run evaluation and scoring (Rahul / Work Package D).

``evaluate_run`` is a pure function of its inputs: the scenario definition,
the normalized agent outcome, the persisted tool-call traces, and the pass
threshold.  No wall-clock, randomness, or LLM calls are involved, so fixed
inputs always produce the same score, criteria, and findings.

Scoring (weights sum to 100):
- task_completion (40): did the agent complete a lookup and produce a summary?
- factual_correctness (40): does the summary contain every expected record
  field value and none of the scenario's forbidden (invented) markers?
- trace_integrity (20): was a successful, redacted tool-call trace recorded —
  and do the persisted artifacts contain no secret values from run variables?

The pass threshold is configurable per run (0-100) and defaults to
:data:`DEFAULT_PASS_THRESHOLD`; the chosen value is always embedded in the
report so a score is never unexplained.  Any critical finding (unsupported
fact, missing expected fact, failed agent turn, secret exposure) blocks a
passing result regardless of the numeric score.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Iterable

from app.core.redaction import SENSITIVE_KEYS
from app.schemas.workflow_report import CriterionScore, Finding
from app.workflow.agent_client import AgentTurnOutcome
from app.workflow.scenarios import ScenarioDefinition

DEFAULT_PASS_THRESHOLD = 70.0
MIN_PASS_THRESHOLD = 0.0
MAX_PASS_THRESHOLD = 100.0

CRITERION_WEIGHTS: dict[str, float] = {
    "task_completion": 40.0,
    "factual_correctness": 40.0,
    "trace_integrity": 20.0,
}

_NORMALIZED_SENSITIVE_KEYS = frozenset(re.sub(r"[^a-z0-9]", "", key.lower()) for key in SENSITIVE_KEYS)


class InvalidPassThreshold(ValueError):
    """Raised when a run requests a pass threshold outside 0-100."""


def validate_pass_threshold(value: Any) -> float:
    """Coerce and validate a configured pass threshold."""
    try:
        threshold = float(value)
    except (TypeError, ValueError) as exc:
        raise InvalidPassThreshold(f"pass_threshold must be a number between {MIN_PASS_THRESHOLD} and {MAX_PASS_THRESHOLD}.") from exc
    if not (MIN_PASS_THRESHOLD <= threshold <= MAX_PASS_THRESHOLD):
        raise InvalidPassThreshold(f"pass_threshold must be between {MIN_PASS_THRESHOLD} and {MAX_PASS_THRESHOLD}.")
    return threshold


@dataclass(slots=True)
class EvaluationOutcome:
    """Result of evaluating one run."""

    score: float
    status: str  # "pass" or "fail"
    criteria: list[CriterionScore]
    findings: list[Finding]
    summary: str


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().casefold()


def extract_secret_values(variables: dict[str, Any]) -> list[str]:
    """Collect values of sensitive scenario variables for leak detection."""
    secrets: list[str] = []
    for key, value in variables.items():
        normalized_key = re.sub(r"[^a-z0-9]", "", str(key).lower())
        if normalized_key in _NORMALIZED_SENSITIVE_KEYS and isinstance(value, str) and value:
            secrets.append(value)
    return secrets


def _artifact_contains_secret(artifacts: Iterable[Any], secrets: list[str]) -> str | None:
    """Return the first secret found in the serialized artifacts, if any."""
    if not secrets:
        return None
    serialized = json.dumps(list(artifacts), default=str, sort_keys=True)
    for secret in secrets:
        if secret in serialized:
            return secret
    return None


def evaluate_run(
    scenario: ScenarioDefinition,
    outcome: AgentTurnOutcome,
    traces: list[dict[str, Any]],
    threshold: float,
    run_variables: dict[str, Any] | None = None,
    agent_ids: list[str] | None = None,
) -> EvaluationOutcome:
    """Score a completed agent turn against the scenario's expected outcome."""
    findings: list[Finding] = []
    criteria: list[CriterionScore] = []

    # --- task completion -------------------------------------------------
    if outcome.success and outcome.summary and outcome.summary.strip():
        task_score = 100.0
        task_rationale = f"Agent completed tool '{outcome.tool_name}' and produced a summary."
    elif outcome.success:
        task_score = 50.0
        task_rationale = f"Tool '{outcome.tool_name}' succeeded but no summary was produced."
        findings.append(
            Finding(
                severity="warning",
                code="empty_summary",
                message="Agent completed the tool call but returned an empty summary.",
                evidence_ref=outcome.call_id,
            )
        )
    else:
        task_score = 0.0
        error_message = (outcome.error or {}).get("message", "Unknown agent failure.")
        task_rationale = f"Agent turn failed: {error_message}"
        findings.append(
            Finding(
                severity="critical",
                code="agent_execution_failed",
                message=error_message,
                evidence_ref=outcome.call_id,
            )
        )
    criteria.append(
        CriterionScore(
            criterion="task_completion",
            weight=CRITERION_WEIGHTS["task_completion"],
            score=task_score,
            rationale=task_rationale,
        )
    )

    # --- factual correctness --------------------------------------------
    summary = outcome.summary or ""
    normalized_summary = _normalize(summary)
    required_values = [str(value) for value in _expected_values(scenario, outcome)]
    missing = [value for value in required_values if _normalize(value) not in normalized_summary]
    present_markers = [marker for marker in scenario.forbidden_markers if _normalize(marker) in normalized_summary]

    if not outcome.success:
        factual_score = 0.0
        factual_rationale = "Not evaluated: the agent turn failed."
    elif missing or present_markers:
        matched = len(required_values) - len(missing)
        factual_score = 0.0 if present_markers else round(100.0 * matched / max(len(required_values), 1), 2)
        factual_rationale = (
            f"Matched {matched}/{len(required_values)} expected values; "
            f"{len(missing)} missing, {len(present_markers)} unsupported markers."
        )
    else:
        factual_score = 100.0
        factual_rationale = f"All {len(required_values)} expected values are present with no unsupported facts."

    for value in missing:
        findings.append(
            Finding(
                severity="critical",
                code="missing_expected_fact",
                message=f"Summary omits expected record value '{value}'.",
                evidence_ref=outcome.call_id,
            )
        )
    for marker in present_markers:
        findings.append(
            Finding(
                severity="critical",
                code="unsupported_fact",
                message=f"Summary contains unsupported fact '{marker}' that is absent from the source record.",
                evidence_ref=outcome.call_id,
            )
        )
    criteria.append(
        CriterionScore(
            criterion="factual_correctness",
            weight=CRITERION_WEIGHTS["factual_correctness"],
            score=factual_score,
            rationale=factual_rationale,
        )
    )

    # --- trace integrity -------------------------------------------------
    successful_traces = [trace for trace in traces if trace.get("success")]
    run_variables = run_variables or {}
    secrets = extract_secret_values(run_variables)
    leaked_secret = _artifact_contains_secret(
        [traces, summary, outcome.record], secrets
    )

    if leaked_secret is not None:
        trace_score = 0.0
        trace_rationale = "A secret scenario variable leaked into persisted run artifacts."
        findings.append(
            Finding(
                severity="critical",
                code="secret_exposure",
                message="A secret value from the run variables appeared in traces or reports.",
                evidence_ref=outcome.call_id,
            )
        )
    elif successful_traces:
        trace_score = 100.0
        trace_rationale = f"{len(successful_traces)} redacted tool-call trace(s) recorded."
    elif traces:
        trace_score = 50.0
        trace_rationale = "Tool-call traces exist but none recorded success."
    else:
        trace_score = 0.0
        trace_rationale = "No tool-call trace was recorded for this run."
        findings.append(
            Finding(
                severity="warning",
                code="missing_tool_trace",
                message="No tool-call trace was recorded; evidence is incomplete.",
                evidence_ref=outcome.call_id,
            )
        )
    criteria.append(
        CriterionScore(
            criterion="trace_integrity",
            weight=CRITERION_WEIGHTS["trace_integrity"],
            score=trace_score,
            rationale=trace_rationale,
        )
    )

    # --- weighted total --------------------------------------------------
    score = round(sum(criterion.weight * criterion.score / 100.0 for criterion in criteria), 2)
    # A run with any critical finding can never pass, regardless of its score:
    # security and correctness violations are blocking conditions.
    has_critical = any(finding.severity == "critical" for finding in findings)
    status = "fail" if (score < threshold or has_critical) else "pass"
    summary_text = (
        f"Scenario '{scenario.scenario_id}' scored {score:.2f} against threshold {threshold:.2f} "
        f"-> {status.upper()} (task={task_score:.0f}, factual={factual_score:.0f}, trace={trace_score:.0f})."
    )
    if has_critical and score >= threshold:
        summary_text += " Critical findings block a passing result despite the score."

    return EvaluationOutcome(
        score=score,
        status=status,
        criteria=criteria,
        findings=findings,
        summary=summary_text,
    )


def _expected_values(scenario: ScenarioDefinition, outcome: AgentTurnOutcome) -> list[str]:
    """Record values the summary must reflect, derived from the actual record."""
    record = outcome.record or {}
    return [str(record[field]) for field in scenario.summary_fields if field in record]
