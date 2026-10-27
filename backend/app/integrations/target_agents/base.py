"""Target-agent contract (Naaneshwar / Work Package A).

Every agent the platform can drive — the deterministic mock shipped today, or
a live provider adapter added later — implements :class:`TargetAgent`.  The
agent-execution service resolves an agent id to an implementation and calls
``execute_tool`` without knowing anything about the backend, so adding a real
provider is a new class plus a registry entry, never a change to route or
workflow code.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, Field

from app.core.adapters import AgentToolRequest, AgentToolResponse


class TargetAgentError(RuntimeError):
    """Base class for target-agent failures."""


class TargetAgentNotFoundError(TargetAgentError, LookupError):
    """Raised when no agent is registered for the requested id."""


class TargetAgentDescriptor(BaseModel):
    """Serializable description of a target agent (used by introspection APIs)."""

    agent_id: str
    name: str
    role: str = "executor"
    provider: str = "mock"
    status: str = "registered"
    capabilities: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class TargetAgent(ABC):
    """Protocol-agnostic executable agent.

    Implementations translate the unified :class:`AgentToolRequest` into their
    own transport (in-process registry today, HTTP/SDK later) and return a
    unified :class:`AgentToolResponse`.  Implementations are responsible for
    their own telemetry when they want it — the bundled mock routes through
    ``execute_and_trace_tool`` so traces and redaction behave exactly as they
    do for direct synthetic-tool calls.
    """

    provider: str = "custom"

    def __init__(
        self,
        agent_id: str,
        *,
        name: str | None = None,
        role: str = "executor",
        status: str = "registered",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        if not agent_id or not str(agent_id).strip():
            raise ValueError("TargetAgent requires a non-empty agent_id.")
        self.agent_id = str(agent_id).strip()
        self.name = name or self.agent_id
        self.role = role
        self.status = status
        self.metadata: dict[str, Any] = dict(metadata or {})

    @abstractmethod
    async def execute_tool(
        self, request: AgentToolRequest, *, run_id: str | None = None
    ) -> AgentToolResponse:
        """Execute one tool call, optionally attaching telemetry to ``run_id``."""

    async def healthcheck(self) -> bool:
        """Return whether the agent backend is currently reachable."""
        return True

    def describe(self) -> TargetAgentDescriptor:
        """Structured description of this agent for APIs and logs."""
        return TargetAgentDescriptor(
            agent_id=self.agent_id,
            name=self.name,
            role=self.role,
            provider=self.provider,
            status=self.status,
            capabilities=list(self.capabilities()),
            metadata=dict(self.metadata),
        )

    def capabilities(self) -> list[str]:
        """Feature flags advertising what this implementation supports."""
        return ["tool_execution"]

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<{type(self).__name__} agent_id={self.agent_id!r} provider={self.provider!r}>"
