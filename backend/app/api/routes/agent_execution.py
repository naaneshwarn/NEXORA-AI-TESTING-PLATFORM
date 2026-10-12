from __future__ import annotations

import time
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Body, HTTPException

from app.core.adapters import AdapterFactory, AgentToolResponse, UnknownProtocolError
from app.core.tools import ToolExecutionError, ToolNotFoundError, execute_synthetic_tool

router = APIRouter(tags=["synthetic-agent"])


def _elapsed_ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 3)


def _call_id_hint(payload: dict[str, Any]) -> str:
    for key in ("call_id", "id", "tool_call_id"):
        value = payload.get(key)
        if value:
            return str(value)
    return f"call-{uuid4().hex[:8]}"


def _error_code(exc: Exception) -> str:
    if isinstance(exc, ToolNotFoundError):
        return "tool_not_found"
    if isinstance(exc, ToolExecutionError):
        return "tool_execution_error"
    if isinstance(exc, (ValueError, KeyError)):
        return "invalid_request"
    return "execution_error"


@router.post("/synthetic/agent/execute/{protocol}")
async def execute_agent_tool_endpoint(
    protocol: str,
    payload: dict[str, Any] | None = Body(default=None),
) -> dict[str, Any]:
    """Parse, execute and re-format an agent tool call for the given protocol."""
    raw_payload = payload or {}

    try:
        adapter = AdapterFactory.get_adapter(protocol)
    except UnknownProtocolError as exc:
        raise HTTPException(status_code=400, detail={"message": str(exc)}) from exc

    started = time.perf_counter()
    call_id = _call_id_hint(raw_payload)

    try:
        request = adapter.parse_request(raw_payload)
        call_id = request.call_id
        data = execute_synthetic_tool(request.tool_name, request.parameters)
        response = AgentToolResponse(
            call_id=call_id,
            success=True,
            data=data,
            execution_time_ms=_elapsed_ms(started),
        )
    except Exception as exc:  # noqa: BLE001 - the dispatcher must never leak a raw 500
        response = AgentToolResponse(
            call_id=call_id,
            success=False,
            error={"code": _error_code(exc), "message": str(exc)},
            execution_time_ms=_elapsed_ms(started),
        )

    return adapter.format_response(response)
