"""Tests for the target-agent contract, mock implementation and registry (WP-A)."""

from __future__ import annotations

import asyncio

import pytest

from app.core.adapters import AgentToolRequest, AgentToolResponse
from app.core.store import AGENTS, get_traces_for_run, register_agent
from app.integrations.target_agents import (
    DEFAULT_AGENT_ID,
    MockTargetAgent,
    TargetAgent,
    TargetAgentNotFoundError,
    TargetAgentRegistry,
    resolve_target_agent,
)
from app.schemas.agent import AgentConfig
from app.schemas.test_run import RunCreateRequest


@pytest.fixture(autouse=True)
def _clean_agents():
    saved = dict(AGENTS)
    AGENTS.clear()
    yield
    AGENTS.clear()
    AGENTS.update(saved)


def test_target_agent_is_abstract() -> None:
    with pytest.raises(TypeError):
        TargetAgent("agent-abstract")  # type: ignore[abstract]


def test_agent_requires_non_empty_id() -> None:
    with pytest.raises(ValueError):
        MockTargetAgent("")


def test_mock_executes_registered_tool() -> None:
    agent = MockTargetAgent("agent-unit")
    response = asyncio.run(
        agent.execute_tool(
            AgentToolRequest(call_id="c-1", tool_name="list_crm_leads", parameters={})
        )
    )

    assert isinstance(response, AgentToolResponse)
    assert response.call_id == "c-1"
    assert response.success is True
    assert isinstance(response.data, list)
    assert response.execution_time_ms >= 0


def test_mock_normalizes_unknown_tool() -> None:
    agent = MockTargetAgent("agent-unit")
    response = asyncio.run(
        agent.execute_tool(
            AgentToolRequest(call_id="c-2", tool_name="definitely_not_a_tool", parameters={})
        )
    )

    assert response.success is False
    assert response.error is not None
    assert response.error["code"] == "tool_not_found"


def test_mock_records_trace_when_run_bound() -> None:
    run = register_run()
    agent = MockTargetAgent("agent-unit")
    asyncio.run(
        agent.execute_tool(
            AgentToolRequest(
                call_id="c-traced",
                tool_name="list_crm_leads",
                parameters={"api_key": "super-secret-value"},
            ),
            run_id=run,
        )
    )

    traces = get_traces_for_run(run)
    assert len(traces) == 1
    assert traces[0]["call_id"] == "c-traced"
    # Redaction applies to mock-executed calls exactly as to direct calls.
    assert "super-secret-value" not in str(traces[0])


def test_mock_produces_no_trace_without_run() -> None:
    agent = MockTargetAgent("agent-unit")
    asyncio.run(
        agent.execute_tool(
            AgentToolRequest(call_id="c-free", tool_name="list_crm_leads", parameters={})
        )
    )
    assert get_traces_for_run("run-unbound") == []


def test_healthcheck_and_describe() -> None:
    agent = MockTargetAgent("agent-unit", name="Unit Agent", role="planner")
    assert asyncio.run(agent.healthcheck()) is True

    descriptor = agent.describe()
    assert descriptor.agent_id == "agent-unit"
    assert descriptor.name == "Unit Agent"
    assert descriptor.role == "planner"
    assert descriptor.provider == "mock"
    assert "tool_execution" in descriptor.capabilities
    assert descriptor.model_dump()["agent_id"] == "agent-unit"


def test_registry_register_get_list_remove() -> None:
    registry = TargetAgentRegistry()
    agent = registry.register(MockTargetAgent("r-1"))
    assert registry.get("r-1") is agent
    assert [a.agent_id for a in registry.list()] == ["r-1"]
    assert registry.descriptors()[0].agent_id == "r-1"

    assert registry.remove("r-1") is True
    assert registry.remove("r-1") is False
    assert registry.get("r-1") is None


def test_registry_rejects_non_agents() -> None:
    registry = TargetAgentRegistry()
    with pytest.raises(TypeError):
        registry.register(object())  # type: ignore[arg-type]


def test_registry_reregistration_replaces() -> None:
    registry = TargetAgentRegistry()
    first = registry.register(MockTargetAgent("r-dup", name="First"))
    second = registry.register(MockTargetAgent("r-dup", name="Second"))
    assert registry.get("r-dup") is second
    assert registry.get("r-dup") is not first


def test_resolve_default_returns_seeded_mock() -> None:
    default = resolve_target_agent(None)
    assert isinstance(default, MockTargetAgent)
    assert default.agent_id == DEFAULT_AGENT_ID
    # Blank ids also fall back to the default agent.
    assert resolve_target_agent("   ").agent_id == DEFAULT_AGENT_ID


def test_resolve_registered_store_agent_builds_executable_mock() -> None:
    register_agent(
        AgentConfig(agent_id="agent-store-1", name="Store Agent", role="reporter", provider="acme")
    )

    resolved = resolve_target_agent("agent-store-1")

    assert isinstance(resolved, MockTargetAgent)
    assert resolved.agent_id == "agent-store-1"
    assert resolved.name == "Store Agent"
    assert resolved.role == "reporter"
    assert resolved.describe().metadata["source"] == "agent-store"
    # It must actually execute.
    response = asyncio.run(
        resolved.execute_tool(
            AgentToolRequest(call_id="c-store", tool_name="list_crm_leads", parameters={})
        )
    )
    assert response.success is True


def test_resolve_unknown_agent_raises() -> None:
    with pytest.raises(TargetAgentNotFoundError) as excinfo:
        resolve_target_agent("agent-never-registered")
    assert "agent-never-registered" in str(excinfo.value)


def register_run() -> str:
    from app.core.store import create_test_run

    return create_test_run(RunCreateRequest(suite_name="target-agent-suite")).run_id
