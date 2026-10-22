from __future__ import annotations

import copy
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

_SENSITIVE_KEYS = {
    "api_key",
    "apikey",
    "token",
    "access_token",
    "refresh_token",
    "secret",
    "client_secret",
    "password",
    "auth",
    "authorization",
    "credentials",
    "private_key",
}


def sanitize_config(config: dict[str, Any]) -> dict[str, Any]:
    """Recursively redacts sensitive credential keys from configuration dictionaries."""
    sanitized: dict[str, Any] = {}
    for key, value in config.items():
        lower_key = key.lower().replace("-", "_")
        if any(sensitive in lower_key for sensitive in _SENSITIVE_KEYS):
            sanitized[key] = "***REDACTED***"
        elif isinstance(value, dict):
            sanitized[key] = sanitize_config(value)
        elif isinstance(value, list):
            sanitized[key] = [
                sanitize_config(item) if isinstance(item, dict) else item
                for item in value
            ]
        else:
            sanitized[key] = value
    return sanitized


class AgentConfig(BaseModel):
    agent_id: str | None = Field(default=None, description="Unique agent identifier; auto-assigned if omitted")
    name: str = Field(..., min_length=1, description="Human-readable name of the agent")
    role: Literal["planner", "executor", "observer", "reporter"] = Field(..., description="Functional role of the agent")
    model: str | None = Field(default=None, description="Underlying model identifier (e.g. gpt-4o-mini)")
    provider: str | None = Field(default=None, description="Provider identifier (e.g. openai, anthropic, mock)")
    endpoint: str | None = Field(default=None, description="Optional target endpoint URL")
    status: Literal["registered", "active", "disabled"] = Field(default="registered", description="Current lifecycle state")
    config: dict[str, Any] = Field(default_factory=dict, description="Arbitrary configuration parameters")
    created_at: datetime | None = Field(default=None, description="UTC registration timestamp")

    def sanitized(self) -> AgentConfig:
        """Returns a copy of the agent configuration with private credentials redacted."""
        copy_obj = self.model_copy(deep=True)
        copy_obj.config = sanitize_config(copy_obj.config)
        return copy_obj


class AgentRegistrationResponse(BaseModel):
    agent_id: str
    status: Literal["registered", "active", "disabled"]
    created_at: datetime | None = None

