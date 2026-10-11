from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class AgentConfig(BaseModel):
    agent_id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    role: Literal["planner", "executor", "observer", "reporter"]
    model: str | None = None
    provider: str | None = None
    endpoint: str | None = None
    status: Literal["registered", "active", "disabled"] = "registered"
    config: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None


class AgentRegistrationResponse(BaseModel):
    agent_id: str
    status: Literal["registered", "active", "disabled"]
    created_at: datetime | None = None
