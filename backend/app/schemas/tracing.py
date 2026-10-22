from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ToolCallTraceCreate(BaseModel):
    """Validated payload for a single recorded agent tool execution."""

    run_id: str = Field(..., min_length=1)
    call_id: str = Field(..., min_length=1)
    tool_name: str = Field(..., min_length=1)
    parameters: dict[str, Any] = Field(default_factory=dict)
    success: bool
    result: Any | None = None
    error: dict[str, Any] | None = None
    execution_time_ms: float = Field(..., ge=0)


class ToolCallTraceResponse(ToolCallTraceCreate):
    """A stored tool-call trace, annotated with its capture timestamp."""

    timestamp: datetime
