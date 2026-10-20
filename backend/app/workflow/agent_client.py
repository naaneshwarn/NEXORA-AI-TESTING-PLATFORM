"""Deterministic mock agent client (Rahul / Work Package D).

Provides the narrow interface the workflow service uses to drive a target
agent turn.  The default implementation executes the synthetic tool registry
through the existing telemetry wrapper (``execute_and_trace_tool``), so every
turn is timed, redacted, and persisted as a tool-call trace under the run ID.

Behaviors are deterministic and credential-free:
- ``correct``: summarizes only fields returned by the tool.
- ``hallucinated``: performs the lookup but injects an unsupported fact.
- ``error``: the mock backend raises a normalized execution failure.
- ``timeout``: the mock backend hangs; the client enforces its timeout and
  normalizes the result to ``agent_timeout``.

A future provider adapter (Naaneshwar's TargetAgent interface) can replace
this client without changing the workflow service.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Protocol
from uuid import uuid4

from app.core.telemetry import execute_and_trace_tool
from app.core.tools import ToolExecutionError
from app.workflow.scenarios import AgentBehavior


class AgentTurnError(RuntimeError):
    """Raised when an agent client cannot complete a turn."""


@dataclass(slots=True)
class AgentTurnOutcome:
    """Normalized result of one agent turn."""

    call_id: str
    tool_name: str
    success: bool
    summary: str | None
    record: dict[str, Any] | None
    error: dict[str, Any] | None
    execution_time_ms: float


class WorkflowAgentClient(Protocol):
    """Minimal contract for anything that can execute an agent turn."""

    async def run_turn(
        self,
        run_id: str,
        tool_name: str,
        parameters: dict[str, Any],
        behavior: AgentBehavior,
        timeout_seconds: float,
    ) -> AgentTurnOutcome: ...


def _summary_from_record(record: dict[str, Any], fields: tuple[str, ...]) -> str:
    parts = [f"{field}: {record[field]}" for field in fields if field in record]
    return "Summary — " + "; ".join(parts) + "."


def _build_executor(behavior: AgentBehavior):
    """Return the tool executor implementing the requested mock behavior."""
    from app.core.tools import execute_synthetic_tool

    if behavior in ("correct", "hallucinated"):
        return execute_synthetic_tool

    if behavior == "error":

        def failing_executor(tool_name: str, parameters: dict[str, Any]) -> Any:
            raise ToolExecutionError("Simulated agent backend failure (deterministic mock fault).")

        return failing_executor

    if behavior == "timeout":

        async def hanging_executor(tool_name: str, parameters: dict[str, Any]) -> Any:
            await asyncio.sleep(3600)
            return {}

        return hanging_executor

    raise AgentTurnError(f"Unknown agent behavior '{behavior}'.")


class SyntheticToolAgentClient:
    """Mock-first agent client backed by the synthetic tool registry."""

    async def run_turn(
        self,
        run_id: str,
        tool_name: str,
        parameters: dict[str, Any],
        behavior: AgentBehavior,
        timeout_seconds: float,
        summary_fields: tuple[str, ...] = ("name", "email", "status"),
        forbidden_markers: tuple[str, ...] = (),
    ) -> AgentTurnOutcome:
        call_id = f"wf-call-{uuid4().hex[:8]}"
        executor = _build_executor(behavior)

        try:
            outcome = await asyncio.wait_for(
                execute_and_trace_tool(
                    run_id,
                    call_id,
                    tool_name,
                    parameters,
                    executor=executor,
                ),
                timeout=timeout_seconds,
            )
        except TimeoutError:
            return AgentTurnOutcome(
                call_id=call_id,
                tool_name=tool_name,
                success=False,
                summary=None,
                record=None,
                error={
                    "code": "agent_timeout",
                    "message": f"Agent turn exceeded the {timeout_seconds:.3f}s workflow timeout.",
                },
                execution_time_ms=timeout_seconds * 1000.0,
            )

        if not outcome.success or not isinstance(outcome.data, dict):
            return AgentTurnOutcome(
                call_id=call_id,
                tool_name=tool_name,
                success=False,
                summary=None,
                record=None,
                error=outcome.error or {"code": "agent_error", "message": "Agent returned no record."},
                execution_time_ms=outcome.execution_time_ms,
            )

        summary = _summary_from_record(outcome.data, summary_fields)
        if behavior == "hallucinated":
            marker = forbidden_markers[0] if forbidden_markers else "platinum-vip"
            summary += f" Account tier: {marker}."

        return AgentTurnOutcome(
            call_id=call_id,
            tool_name=tool_name,
            success=True,
            summary=summary,
            record=outcome.data,
            error=None,
            execution_time_ms=outcome.execution_time_ms,
        )
