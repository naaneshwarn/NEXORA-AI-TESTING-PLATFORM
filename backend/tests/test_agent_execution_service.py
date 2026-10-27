"""Tests for the agent-execution service layer (Work Package A).

Covers the service directly (protocol errors, run/agent validation, tracing,
events) — the HTTP status mapping for the same conditions is asserted through
the route below.
"""

from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient

from app.core.adapters import UnknownProtocolError
from app.core.store import (
    AGENTS,
    get_events_for_run,
    get_test_run,
    get_traces_for_run,
    register_agent,
)
from app.integrations.target_agents import TargetAgentNotFoundError
from app.main import app as main_app
from app.schemas.agent import AgentConfig
from app.schemas.test_run import RunCreateRequest
from app.services.agent_execution import (
    RunNotFoundError,
    call_id_hint,
    execute_agent_tool_call,
)

client = TestClient(main_app)


@pytest.fixture(autouse=True)
def _clean_agents():
    saved = dict(AGENTS)
    AGENTS.clear()
    yield
    AGENTS.clear()
    AGENTS.update(saved)


def _new_run() -> str:
    return create_run()


def create_run() -> str:
    from app.core.store import create_test_run

    return create_test_run(RunCreateRequest(suite_name="service-suite")).run_id


# -- service-level behaviour -------------------------------------------------


def test_unknown_protocol_raises() -> None:
    with pytest.raises(UnknownProtocolError):
        asyncio.run(execute_agent_tool_call("not-a-protocol", {}))


def test_unknown_run_raises_before_execution() -> None:
    with pytest.raises(RunNotFoundError):
        asyncio.run(
            execute_agent_tool_call(
                "rest",
                {"tool_name": "list_crm_leads", "parameters": {}},
                run_id="run-not-real",
            )
        )


def test_unknown_agent_raises() -> None:
    with pytest.raises(TargetAgentNotFoundError):
        asyncio.run(
            execute_agent_tool_call(
                "rest",
                {"tool_name": "list_crm_leads", "parameters": {}},
                agent_id="agent-ghost",
            )
        )


def test_malformed_payload_returns_in_band_error() -> None:
    result = asyncio.run(execute_agent_tool_call("rest", {"unexpected": True}))

    assert result["success"] is False
    assert result["error"]["code"] == "invalid_request"
    assert "tool_name" in result["error"]["message"]


def test_successful_call_executes_traces_and_records_event() -> None:
    run_id = _new_run()
    call_id = f"svc-{run_id}"

    result = asyncio.run(
        execute_agent_tool_call(
            "rest",
            {"call_id": call_id, "tool_name": "list_crm_leads", "parameters": {}},
            run_id=run_id,
        )
    )

    assert result["success"] is True
    assert result["call_id"] == call_id

    traces = get_traces_for_run(run_id)
    assert [t["call_id"] for t in traces] == [call_id]

    events = get_events_for_run(run_id)
    tool_events = [e for e in events if e.event_type == "tool_call"]
    assert len(tool_events) == 1
    assert tool_events[0].tool_calls[0].tool_name == "list_crm_leads"
    assert tool_events[0].tool_calls[0].status == "success"
    assert tool_events[0].sequence == len(events)


def test_event_payload_is_redacted() -> None:
    run_id = _new_run()

    asyncio.run(
        execute_agent_tool_call(
            "rest",
            {
                "call_id": "secret-call",
                "tool_name": "list_crm_leads",
                "parameters": {"password": "hunter2-secret"},
            },
            run_id=run_id,
        )
    )

    events = [e for e in get_events_for_run(run_id) if e.event_type == "tool_call"]
    assert events, "expected a tool_call event"
    assert "hunter2-secret" not in str(events[0].model_dump())


def test_failed_tool_call_records_failed_event() -> None:
    run_id = _new_run()

    result = asyncio.run(
        execute_agent_tool_call(
            "rest",
            {"call_id": "bad-tool", "tool_name": "not_a_tool", "parameters": {}},
            run_id=run_id,
        )
    )
    assert result["success"] is False

    events = [e for e in get_events_for_run(run_id) if e.event_type == "tool_call"]
    assert events[0].tool_calls[0].status == "failed"
    assert events[0].payload["success"] is False


def test_call_is_executed_through_named_store_agent() -> None:
    register_agent(AgentConfig(agent_id="agent-svc", name="Service Agent", role="observer"))

    result = asyncio.run(
        execute_agent_tool_call(
            "rest",
            {"tool_name": "list_crm_leads", "parameters": {}},
            agent_id="agent-svc",
        )
    )

    assert result["success"] is True


def test_openai_protocol_round_trip() -> None:
    result = asyncio.run(
        execute_agent_tool_call(
            "openai",
            {
                "call_id": "fn-1",
                "function": {
                    "name": "list_crm_leads",
                    "arguments": "{}",
                },
            },
        )
    )

    # OpenAI wire shape: role/tool_call_id with a JSON-encoded content body.
    assert result["role"] == "tool"
    assert result["tool_call_id"] == "fn-1"
    assert '"success": true' in result["content"]


def test_call_id_hint_falls_back_to_generated_id() -> None:
    generated = call_id_hint({})
    assert generated.startswith("call-")
    assert call_id_hint({"id": "explicit-id"}) == "explicit-id"
    assert call_id_hint({"tool_call_id": "tc-9"}) == "tc-9"


# -- HTTP status mapping -----------------------------------------------------


def test_route_maps_unknown_protocol_to_400() -> None:
    response = client.post("/api/v1/synthetic/agent/execute/unknown-proto", json={})
    assert response.status_code == 400
    assert "Unsupported protocol" in response.json()["error"]["message"]


def test_route_maps_unknown_run_to_404() -> None:
    response = client.post(
        "/api/v1/synthetic/agent/execute/rest?run_id=run-nope",
        json={"tool_name": "list_crm_leads", "parameters": {}},
    )
    assert response.status_code == 404
    assert "run-nope" in response.json()["error"]["message"]


def test_route_maps_unknown_agent_to_404() -> None:
    response = client.post(
        "/api/v1/synthetic/agent/execute/rest?agent_id=agent-ghost",
        json={"tool_name": "list_crm_leads", "parameters": {}},
    )
    assert response.status_code == 404
    assert "agent-ghost" in response.json()["error"]["message"]


def test_route_executes_through_named_agent() -> None:
    register_agent(AgentConfig(agent_id="agent-http", name="HTTP Agent", role="executor"))
    response = client.post(
        "/api/v1/synthetic/agent/execute/rest?agent_id=agent-http",
        json={"call_id": "http-1", "tool_name": "list_crm_leads", "parameters": {}},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["call_id"] == "http-1"


def test_route_without_agent_uses_default_mock() -> None:
    response = client.post(
        "/api/v1/synthetic/agent/execute/rest",
        json={"call_id": "default-1", "tool_name": "list_crm_leads", "parameters": {}},
    )

    assert response.status_code == 200
    assert response.json()["success"] is True


def test_run_still_exists_after_service_calls() -> None:
    # The service must not mutate run state — it only attaches telemetry.
    run_id = _new_run()
    asyncio.run(
        execute_agent_tool_call(
            "rest", {"tool_name": "list_crm_leads", "parameters": {}}, run_id=run_id
        )
    )
    assert get_test_run(run_id) is not None
