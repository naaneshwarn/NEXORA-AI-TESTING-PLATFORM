"""Additive schemas for automated workflow evaluation reports (Rahul / Work Package D).

These models are deliberately stored in a NEW module instead of the shared
``app/schemas/evaluation.py`` file so the Phase 2 ``ReportSummary`` contract
remains untouched.  The rich report is exposed through the additive
``GET /api/v1/test-runs/{run_id}/report`` endpoint; a ``ReportSummary``
projection is still written for every workflow run so the existing
``GET /api/v1/reports/{report_id}`` contract keeps working.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class CriterionScore(BaseModel):
    """Score of a single evaluation criterion (0-100) with its weight and rationale."""

    criterion: str = Field(..., min_length=1)
    weight: float = Field(..., ge=0.0, le=100.0)
    score: float = Field(..., ge=0.0, le=100.0)
    rationale: str = Field(..., min_length=1)


class Finding(BaseModel):
    """A specific, evidence-backed observation produced during evaluation."""

    severity: Literal["info", "warning", "critical"]
    code: str = Field(..., min_length=1)
    message: str = Field(..., min_length=1)
    evidence_ref: str | None = None


class ReportEvidence(BaseModel):
    """References to the raw evidence backing the score (never secret values)."""

    scenario_id: str
    agent_ids: list[str] = Field(default_factory=list)
    tool_call_ids: list[str] = Field(default_factory=list)
    event_ids: list[str] = Field(default_factory=list)


class WorkflowReport(BaseModel):
    """Full evaluation report produced by an automated workflow run."""

    report_id: str
    run_id: str
    scenario_id: str
    status: Literal["pass", "fail"] = "fail"
    score: float = Field(default=0.0, ge=0.0, le=100.0)
    pass_threshold: float = Field(..., ge=0.0, le=100.0)
    summary: str = Field(..., min_length=1)
    criteria: list[CriterionScore] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)
    evidence: ReportEvidence
    workflow_state: Literal["passed", "failed", "cancelled"] = "failed"
    duration_ms: float = Field(default=0.0, ge=0.0)
    generated_at: datetime | None = None
