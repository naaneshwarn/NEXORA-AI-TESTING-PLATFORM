from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class ScenarioConfig(BaseModel):
    name: str = Field(..., min_length=1)
    description: str | None = None
    variables: dict[str, Any] = Field(default_factory=dict)


class RunCreateRequest(BaseModel):
    suite_name: str = Field(..., min_length=1)
    scenario: ScenarioConfig | None = None
    environment: str = "local"
    tags: list[str] = Field(default_factory=list)
    target_agents: list[str] = Field(default_factory=list)
    config: dict[str, Any] = Field(default_factory=dict)


class RunDetail(BaseModel):
    run_id: str
    suite_name: str
    environment: str
    state: Literal["queued", "running", "passed", "failed", "cancelled"] = "queued"
    target_agents: list[str] = Field(default_factory=list)
    created_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    message: str | None = None


class ExecutionStatus(BaseModel):
    run_id: str
    state: Literal["queued", "running", "passed", "failed", "cancelled"] = "queued"
    message: str | None = None
    updated_at: datetime | None = None
