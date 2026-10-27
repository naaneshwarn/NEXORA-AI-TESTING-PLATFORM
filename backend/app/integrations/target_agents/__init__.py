"""Target-agent registry and resolution (Naaneshwar / Work Package A).

Resolution order for :func:`resolve_target_agent`:

1. an explicitly registered implementation (live providers register here),
2. a :class:`~app.integrations.target_agents.mock.MockTargetAgent` built for
   any agent registered through ``POST /api/v1/agents`` — registering an agent
   is enough to make it executable, with no backend to deploy,
3. otherwise :class:`TargetAgentNotFoundError` (surfaced as HTTP 404).

``resolve_target_agent(None)`` returns the shared default mock used when a
tool call carries no ``agent_id``.
"""

from __future__ import annotations

import threading

from app.integrations.target_agents.base import (
    TargetAgent,
    TargetAgentDescriptor,
    TargetAgentError,
    TargetAgentNotFoundError,
)
from app.integrations.target_agents.mock import MockTargetAgent

__all__ = [
    "TargetAgent",
    "TargetAgentDescriptor",
    "TargetAgentError",
    "TargetAgentNotFoundError",
    "MockTargetAgent",
    "TargetAgentRegistry",
    "target_agents",
    "resolve_target_agent",
]


class TargetAgentRegistry:
    """Thread-safe registry of executable target agents."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._agents: dict[str, TargetAgent] = {}

    def register(self, agent: TargetAgent) -> TargetAgent:
        if not isinstance(agent, TargetAgent):
            raise TypeError("Only TargetAgent instances can be registered.")
        with self._lock:
            self._agents[agent.agent_id] = agent
        return agent

    def get(self, agent_id: str) -> TargetAgent | None:
        with self._lock:
            return self._agents.get(agent_id)

    def remove(self, agent_id: str) -> bool:
        with self._lock:
            return self._agents.pop(agent_id, None) is not None

    def clear(self) -> None:
        with self._lock:
            self._agents.clear()

    def list(self) -> list[TargetAgent]:
        with self._lock:
            return list(self._agents.values())

    def descriptors(self) -> list[TargetAgentDescriptor]:
        return [agent.describe() for agent in self.list()]

    def resolve(self, agent_id: str) -> TargetAgent:
        """Return a registered agent or build a mock from the agent store."""
        with self._lock:
            registered = self._agents.get(agent_id)
        if registered is not None:
            return registered

        # Fall back to agents registered via the REST contract: they become
        # executable immediately through the deterministic mock backend.
        from app.core.store import get_agent  # local import: store layering

        stored = get_agent(agent_id)
        if stored is not None:
            return MockTargetAgent(
                stored.agent_id,
                name=stored.name,
                role=stored.role,
                status=stored.status,
                metadata={
                    "provider": stored.provider,
                    "model": stored.model,
                    "endpoint": stored.endpoint,
                    "source": "agent-store",
                },
            )

        raise TargetAgentNotFoundError(
            f"Target agent '{agent_id}' is not registered. "
            "Register it via POST /api/v1/agents or the target-agent registry."
        )


# Process-wide registry, pre-seeded with the default mock agent.
target_agents = TargetAgentRegistry()
DEFAULT_AGENT_ID = "mock-agent"
target_agents.register(MockTargetAgent(DEFAULT_AGENT_ID))


def resolve_target_agent(agent_id: str | None = None) -> TargetAgent:
    """Resolve ``agent_id`` to an executable agent (default mock when None)."""
    if agent_id is None or not str(agent_id).strip():
        default = target_agents.get(DEFAULT_AGENT_ID)
        if default is not None:
            return default
        return MockTargetAgent(DEFAULT_AGENT_ID)  # pragma: no cover - registry is seeded
    return target_agents.resolve(str(agent_id).strip())
