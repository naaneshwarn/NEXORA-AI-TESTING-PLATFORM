"""Deterministic in-process target agent (default WP-A implementation).

The mock executes tool calls through the synthetic tool registry via the
existing telemetry wrapper, so every call is timed, redacted and — when a
``run_id`` is supplied — persisted as a tool-call trace.  It is credential
free and fully deterministic, which makes it the reference implementation for
contract tests and the fallback for agents registered without a live backend.
"""

from __future__ import annotations

from app.core.adapters import AgentToolRequest, AgentToolResponse
from app.core.telemetry import execute_and_trace_tool
from app.integrations.target_agents.base import TargetAgent


class MockTargetAgent(TargetAgent):
    """Executes tool calls against the synthetic tool registry."""

    provider = "mock"

    def __init__(self, agent_id: str, **kwargs: object) -> None:
        kwargs.setdefault("name", "Deterministic Mock Agent")
        super().__init__(agent_id, **kwargs)  # type: ignore[arg-type]

    async def execute_tool(
        self, request: AgentToolRequest, *, run_id: str | None = None
    ) -> AgentToolResponse:
        outcome = await execute_and_trace_tool(
            run_id,
            request.call_id,
            request.tool_name,
            request.parameters,
        )
        return AgentToolResponse(
            call_id=outcome.call_id,
            success=outcome.success,
            data=outcome.data,
            error=outcome.error,
            execution_time_ms=outcome.execution_time_ms,
        )

    def capabilities(self) -> list[str]:
        return ["tool_execution", "tracing", "redaction", "deterministic"]
