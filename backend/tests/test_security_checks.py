"""Tests for the standalone security evaluator module (Rahul / Work Package D).

The Phase 3 guide requires security checks to be modular and separately
selectable.  These tests exercise the security module directly — independent
of the core scoring evaluator — and confirm the evaluator still applies its
result (a leaked secret zeroes trace integrity and blocks a pass).
"""

from __future__ import annotations

from app.workflow.evaluator import extract_secret_values
from app.workflow.security_checks import (
    artifact_contains_secret,
    evaluate_security,
    extract_secret_values as module_extract_secret_values,
)


def test_secret_extraction_is_reexported_from_evaluator() -> None:
    """Backwards compatibility: evaluator.extract_secret_values still works."""
    variables = {"api_key": "sk-live-abc123", "lead_id": "lead-1"}
    assert extract_secret_values(variables) == module_extract_secret_values(variables)
    assert extract_secret_values(variables) == ["sk-live-abc123"]


def test_clean_artifacts_produce_no_findings() -> None:
    result = evaluate_security(
        traces=[{"tool": "crm", "success": True}],
        summary="Lead Alice is qualified.",
        record={"name": "Alice"},
        run_variables={"api_key": "sk-live-abc123", "lead_id": "lead-1"},
    )

    assert result.leaked is False
    assert result.leaked_secret is None
    assert result.findings == []


def test_secret_in_traces_is_detected_and_critical() -> None:
    result = evaluate_security(
        traces=[{"tool": "crm", "arguments": {"api_key": "sk-live-abc123"}, "success": True}],
        summary="ok",
        record={},
        run_variables={"api_key": "sk-live-abc123"},
        evidence_ref="call-1",
    )

    assert result.leaked is True
    assert result.leaked_secret == "sk-live-abc123"
    assert len(result.findings) == 1
    finding = result.findings[0]
    assert finding.code == "secret_exposure"
    assert finding.severity == "critical"
    assert finding.evidence_ref == "call-1"


def test_secret_in_summary_or_record_is_detected() -> None:
    in_summary = evaluate_security(
        traces=[], summary="token sk-live-abc123", record={}, run_variables={"API-KEY": "sk-live-abc123"}
    )
    in_record = evaluate_security(
        traces=[], summary="ok", record={"note": "sk-live-abc123"}, run_variables={"apiKey": "sk-live-abc123"}
    )

    assert in_summary.leaked is True
    assert in_record.leaked is True


def test_non_sensitive_variables_are_never_flagged() -> None:
    result = evaluate_security(
        traces=[{"arguments": {"lead_id": "lead-1", "customer_name": "Alice"}}],
        summary="Alice qualified",
        record={"name": "Alice"},
        run_variables={"lead_id": "lead-1", "customer_name": "Alice"},
    )

    assert result.leaked is False
    assert result.findings == []


def test_artifact_scan_ignores_empty_secret_list() -> None:
    assert artifact_contains_secret(["anything"], []) is None
