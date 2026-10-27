"""Agent-execution service layer (Naaneshwar / Work Package A).

Extracted from the HTTP route so protocol parsing, target-agent resolution,
telemetry and event recording live in one testable place.  The route stays a
thin translation layer (HTTP status codes + envelope), and the same service
can be called from workflows, CLI tooling or future gRPC surfaces without
duplicating behaviour.

Execution flow:

    protocol → adapter (400 on unknown)
             → run validation (404 on unknown run)
             → payload parsing (in-band ``invalid_request`` envelope)
             → target-agent resolution (404 on unknown agent)
             → ``TargetAgent.execute_tool`` (traced + redacted)
             → tool-call execution event (when a run is attached)
             → protocol-formatted response
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from app.core.adapters import AdapterFactory, AgentToolResponse
from app.core.redaction import redact_sensitive_data
from app.core.store import get_events_for_run, get_test_run, record_execution_event
from app.integrations.target_agents import resolve_target_agent
from app.schemas.events import ExecutionEvent


class RunNotFoundError(LookupError):
    """Raised when tool-call telemetry is requested for an unknown run."""


def call_id_hint(payload: dict[str, Any]) -> str:
    """Best-effort call id for payloads that never declare one."""
    for key in ("call_id", "id", "tool_call_id"):
        value = payload.get(key)
        if value:
            return str(value)
    return f"call-{uuid4().hex[:8]}"


def _elapsed_ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 3)


def _record_tool_call_event(run_id: str, request: Any, response: AgentToolResponse) -> None:
    """Append a redacted ``tool_call`` event so the run timeline sees the call.

    Only redacted telemetry is exposed: the payload stored on the event is the
    same scrubbed parameter map that the trace endpoint serves.
    """
    record_execution_event(
        run_id,
        ExecutionEvent(
            event_id=f"event-{uuid4().hex[:8]}",
            run_id=run_id,
            event_type="tool_call",
            sequence=len(get_events_for_run(run_id)) + 1,
            message=f"Executing tool {request.tool_name}",
            timestamp=datetime.now(timezone.utc),
            tool_calls=[
                {
                    "call_id": request.call_id,
                    "tool_name": request.tool_name,
                    "status": "success" if response.success else "failed",
                    "payload": redact_sensitive_data(request.parameters),
                }
            ],
            payload={
                "call_id": request.call_id,
                "tool_name": request.tool_name,
                "success": response.success,
                "execution_time_ms": response.execution_time_ms,
            },
        ),
    )


async def execute_agent_tool_call(
    protocol: str,
    payload: dict[str, Any],
    *,
    run_id: str | None = None,
    agent_id: str | None = None,
) -> dict[str, Any]:
    """Parse, execute and re-format one agent tool call.

    Args:
        protocol: Wire protocol name resolved through :class:`AdapterFactory`.
        payload: Raw request body in that protocol's shape.
        run_id: Test run to attach telemetry to (validated, 404 when unknown).
        agent_id: Target agent to execute through; ``None`` uses the shared
            deterministic mock agent.

    Returns:
        The response serialized back into the protocol's wire shape.

    Raises:
        UnknownProtocolError: No adapter is registered for ``protocol``.
        RunNotFoundError: ``run_id`` does not identify a known test run.
        TargetAgentNotFoundError: ``agent_id`` is not registered anywhere.
    """
    adapter = AdapterFactory.get_adapter(protocol)

    if run_id is not None and get_test_run(run_id) is None:
        raise RunNotFoundError(f"Test run '{run_id}' was not found.")

    started = time.perf_counter()
    call_id = call_id_hint(payload)

    try:
        request = adapter.parse_request(payload)
    except Exception as exc:  # noqa: BLE001 - malformed calls are normalized, never raised
        response = AgentToolResponse(
            call_id=call_id,
            success=False,
            error={"code": "invalid_request", "message": str(exc)},
            execution_time_ms=_elapsed_ms(started),
        )
        return adapter.format_response(response)

    agent = resolve_target_agent(agent_id)
    response = await agent.execute_tool(request, run_id=run_id)

    if run_id:
        _record_tool_call_event(run_id, request, response)

    return adapter.format_response(response)
