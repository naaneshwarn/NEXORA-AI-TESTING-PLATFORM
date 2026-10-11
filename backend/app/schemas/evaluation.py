from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class EvaluationResult(BaseModel):
    run_id: str
    score: float = Field(default=0.0, ge=0.0, le=100.0)
    status: Literal["pass", "fail", "partial"] = "partial"
    summary: str | None = None
    metrics: dict[str, float] = Field(default_factory=dict)


class EvaluationSubmission(BaseModel):
    run_id: str = Field(..., min_length=1)
    agent_id: str | None = None
    score: float = Field(default=0.0, ge=0.0, le=100.0)
    status: Literal["pass", "fail", "partial"] = "partial"
    summary: str = Field(..., min_length=1)
    metrics: dict[str, float] = Field(default_factory=dict)
    issues: list[str] = Field(default_factory=list)


class ReportSummary(BaseModel):
    report_id: str
    run_id: str
    score: float = Field(default=0.0, ge=0.0, le=100.0)
    status: Literal["generated", "partial", "failed"] = "generated"
    summary: str
    metrics: dict[str, float] = Field(default_factory=dict)
    generated_at: datetime | None = None
