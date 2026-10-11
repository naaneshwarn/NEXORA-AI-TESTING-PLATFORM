from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class ToolCallTrace(BaseModel):
    call_id: str = Field(..., min_length=1)
    tool_name: str = Field(..., min_length=1)
    status: Literal["started", "success", "failed"] = "started"
    payload: dict[str, Any] = Field(default_factory=dict)


class ExecutionEvent(BaseModel):
    event_id: str
    run_id: str
    event_type: Literal["created", "started", "heartbeat", "tool_call", "result", "error", "completed"]
    sequence: int = Field(ge=0)
    message: str
    payload: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime | None = None
    tool_calls: list[ToolCallTrace] = Field(default_factory=list)
