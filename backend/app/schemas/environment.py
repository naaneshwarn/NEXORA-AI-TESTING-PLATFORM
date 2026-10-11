from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class SyntheticEnvironmentRequest(BaseModel):
    environment_type: Literal["postgres", "mysql", "mongodb", "redis", "neo4j", "docker"]
    label: str = Field(..., min_length=1)
    config: dict[str, Any] = Field(default_factory=dict)


class SyntheticEnvironment(BaseModel):
    environment_id: str
    environment_type: Literal["postgres", "mysql", "mongodb", "redis", "neo4j", "docker"]
    label: str
    status: Literal["provisioning", "ready", "stopped", "failed", "cancelled"] = "provisioning"
    endpoint: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None
