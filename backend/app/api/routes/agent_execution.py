from __future__ import annotations

import time
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Body, HTTPException, Query

from app.core.adapters import AdapterFactory, AgentToolResponse, UnknownProtocolError
from app.core.store import get_test_run
from app.core.telemetry import execute_and_trace_tool

router = APIRouter(tags=["synthetic-agent"])


def _elapsed_ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 3)


def _call_id_hint(payload: dict[str, Any]) -> str:
    for key in ("call_id", "id", "tool_call_id"):
        value = payload.get(key)
        if value:
            return str(value)
    return f"call-{uuid4().hex[:8]}"


@router.post("/synthetic/agent/execute/{protocol}")
async def execute_agent_tool_endpoint(
    protocol: str,
    run_id: str | None = Query(default=None, description="Test run to attach tool-call telemetry to."),
    payload: dict[str, Any] | None = Body(default=None),
) -> dict[str, Any]:
    """Parse, execute and re-format an agent tool call for the given protocol.

    When ``run_id`` is supplied, a redacted telemetry record is persisted and can
    be retrieved from ``GET /test-runs/{run_id}/traces``.
    """
    raw_payload = payload or {}

    try:
        adapter = AdapterFactory.get_adapter(protocol)
    except UnknownProtocolError as exc:
        raise HTTPException(status_code=400, detail={"message": str(exc)}) from exc

    if run_id is not None and get_test_run(run_id) is None:
        raise HTTPException(status_code=404, detail={"message": f"Test run '{run_id}' was not found."})

    started = time.perf_counter()
    call_id = _call_id_hint(raw_payload)

    try:
        request = adapter.parse_request(raw_payload)
    except Exception as exc:  # noqa: BLE001 - malformed calls are normalized, never raised
        response = AgentToolResponse(
            call_id=call_id,
            success=False,
            error={"code": "invalid_request", "message": str(exc)},
            execution_time_ms=_elapsed_ms(started),
        )
        return adapter.format_response(response)

    outcome = await execute_and_trace_tool(run_id, request.call_id, request.tool_name, request.parameters)
    response = AgentToolResponse(
        call_id=request.call_id,
        success=outcome.success,
        data=outcome.data,
        error=outcome.error,
        execution_time_ms=outcome.execution_time_ms,
    )
    return adapter.format_response(response)
