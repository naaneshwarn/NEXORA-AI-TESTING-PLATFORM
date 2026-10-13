from __future__ import annotations

import inspect
import time
from dataclasses import dataclass
from typing import Any, Callable

from app.core.redaction import redact_sensitive_data
from app.core.store import record_tool_trace
from app.core.tools import ToolExecutionError, ToolNotFoundError, execute_synthetic_tool
from app.schemas.tracing import ToolCallTraceCreate, ToolCallTraceResponse

ToolExecutor = Callable[[str, dict[str, Any]], Any]


@dataclass(slots=True)
class ToolExecutionOutcome:
    """Result of an instrumented tool execution."""

    call_id: str
    tool_name: str
    success: bool
    data: Any | None
    error: dict[str, Any] | None
    execution_time_ms: float
    trace: ToolCallTraceResponse | None = None


def classify_tool_error(exc: Exception) -> dict[str, Any]:
    """Map an exception raised by a synthetic tool to a normalized error dict."""
    if isinstance(exc, ToolNotFoundError):
        code = "tool_not_found"
    elif isinstance(exc, ToolExecutionError):
        code = "tool_execution_error"
    elif isinstance(exc, (ValueError, KeyError)):
        code = "invalid_request"
    else:
        code = "execution_error"
    return {"code": code, "message": str(exc)}


async def execute_and_trace_tool(
    run_id: str | None,
    call_id: str,
    tool_name: str,
    parameters: dict[str, Any] | None = None,
    executor: ToolExecutor | None = None,
) -> ToolExecutionOutcome:
    """Execute a synthetic tool, measure it, and persist redacted telemetry.

    Timing uses :func:`time.perf_counter` for high resolution. When ``run_id``
    is provided the sanitized record is stored via ``record_tool_trace`` and the
    resulting trace is attached to the outcome; when it is ``None`` execution is
    still timed but no telemetry is persisted. ``executor`` may be supplied to
    override the default synthetic tool registry (useful for tests).
    """
    params = dict(parameters or {})
    runner = executor or execute_synthetic_tool

    started = time.perf_counter()
    data: Any | None = None
    error: dict[str, Any] | None = None
    try:
        result = runner(tool_name, params)
        if inspect.isawaitable(result):
            result = await result
        data = result
    except Exception as exc:  # noqa: BLE001 - telemetry must capture every failure mode
        error = classify_tool_error(exc)
    execution_time_ms = round((time.perf_counter() - started) * 1000, 3)

    trace: ToolCallTraceResponse | None = None
    if run_id is not None:
        record = record_tool_trace(
            run_id,
            ToolCallTraceCreate(
                run_id=run_id,
                call_id=call_id,
                tool_name=tool_name,
                parameters=redact_sensitive_data(params),
                success=error is None,
                result=redact_sensitive_data(data),
                error=redact_sensitive_data(error) if error else None,
                execution_time_ms=execution_time_ms,
            ).model_dump(),
        )
        trace = ToolCallTraceResponse(**record)

    return ToolExecutionOutcome(
        call_id=call_id,
        tool_name=tool_name,
        success=error is None,
        data=data,
        error=error,
        execution_time_ms=execution_time_ms,
        trace=trace,
    )
