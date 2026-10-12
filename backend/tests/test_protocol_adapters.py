import json

from fastapi.testclient import TestClient

from app.core.adapters import (
    AdapterFactory,
    AgentToolRequest,
    AgentToolResponse,
    OpenAIFunctionAdapter,
    RESTProtocolAdapter,
    UnknownProtocolError,
)
from app.main import app

client = TestClient(app)


def test_rest_adapter_round_trip() -> None:
    adapter = RESTProtocolAdapter()

    request = adapter.parse_request(
        {
            "call_id": "call-rest-1",
            "tool_name": "list_crm_leads",
            "parameters": {"limit": 5},
            "agent_id": "agent-analyst",
        }
    )
    assert isinstance(request, AgentToolRequest)
    assert request.call_id == "call-rest-1"
    assert request.tool_name == "list_crm_leads"
    assert request.parameters == {"limit": 5}
    assert request.agent_id == "agent-analyst"

    formatted = adapter.format_response(
        AgentToolResponse(call_id="call-rest-1", success=True, data=[], execution_time_ms=1.25)
    )
    assert formatted == {
        "call_id": "call-rest-1",
        "success": True,
        "data": [],
        "error": None,
        "execution_time_ms": 1.25,
    }


def test_openai_adapter_parses_function_payload_and_formats_tool_message() -> None:
    adapter = OpenAIFunctionAdapter()

    request = adapter.parse_request(
        {
            "id": "call_oai_1",
            "type": "function",
            "function": {"name": "get_crm_lead", "arguments": json.dumps({"lead_id": "lead-1"})},
            "agent_id": "agent-langchain",
        }
    )
    assert request.call_id == "call_oai_1"
    assert request.tool_name == "get_crm_lead"
    assert request.parameters == {"lead_id": "lead-1"}
    assert request.agent_id == "agent-langchain"

    message = adapter.format_response(
        AgentToolResponse(
            call_id="call_oai_1",
            success=False,
            error={"code": "tool_not_found", "message": "nope"},
            execution_time_ms=2.0,
        )
    )
    assert message["role"] == "tool"
    assert message["tool_call_id"] == "call_oai_1"
    content = json.loads(message["content"])
    assert content["success"] is False
    assert content["error"]["code"] == "tool_not_found"
    assert content["execution_time_ms"] == 2.0


def test_adapter_factory_defaults_and_aliases() -> None:
    assert isinstance(AdapterFactory.get_adapter(None), RESTProtocolAdapter)
    assert isinstance(AdapterFactory.get_adapter(""), RESTProtocolAdapter)
    assert isinstance(AdapterFactory.get_adapter("openai"), OpenAIFunctionAdapter)
    assert isinstance(AdapterFactory.get_adapter("langchain"), OpenAIFunctionAdapter)

    try:
        AdapterFactory.get_adapter("grpc")
    except UnknownProtocolError as exc:
        assert "Unsupported protocol" in str(exc)
    else:  # pragma: no cover - guards against a silent regression
        raise AssertionError("Expected UnknownProtocolError for an unregistered protocol.")


def test_execute_rest_tool_round_trip() -> None:
    created = client.post(
        "/api/v1/synthetic/agent/execute/rest",
        json={
            "call_id": "call-create",
            "tool_name": "create_crm_lead",
            "parameters": {"name": "Adapter Lead", "email": "adapter@example.com", "status": "new"},
        },
    )
    assert created.status_code == 200
    body = created.json()
    assert body["success"] is True
    assert body["execution_time_ms"] >= 0
    lead_id = body["data"]["id"]

    fetched = client.post(
        "/api/v1/synthetic/agent/execute/rest",
        json={"call_id": "call-get", "tool_name": "get_crm_lead", "parameters": {"lead_id": lead_id}},
    )
    assert fetched.status_code == 200
    assert fetched.json()["success"] is True
    assert fetched.json()["data"]["id"] == lead_id


def test_execute_openai_function_call_returns_tool_message() -> None:
    response = client.post(
        "/api/v1/synthetic/agent/execute/openai",
        json={
            "id": "call_oai_list",
            "type": "function",
            "function": {"name": "list_crm_leads", "arguments": {}},
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["role"] == "tool"
    assert body["tool_call_id"] == "call_oai_list"
    parsed = json.loads(body["content"])
    assert parsed["success"] is True
    assert isinstance(parsed["data"], list)


def test_execute_normalizes_unknown_tool_and_parse_failures() -> None:
    unknown_tool = client.post(
        "/api/v1/synthetic/agent/execute/rest",
        json={"call_id": "call-unknown", "tool_name": "does_not_exist", "parameters": {}},
    )
    assert unknown_tool.status_code == 200
    assert unknown_tool.json()["success"] is False
    assert unknown_tool.json()["error"]["code"] == "tool_not_found"

    malformed = client.post(
        "/api/v1/synthetic/agent/execute/rest",
        json={"call_id": "call-malformed", "parameters": {}},
    )
    assert malformed.status_code == 200
    assert malformed.json()["success"] is False
    assert malformed.json()["error"]["code"] == "invalid_request"


def test_execute_rejects_unknown_protocol() -> None:
    response = client.post(
        "/api/v1/synthetic/agent/execute/grpc",
        json={"call_id": "call-grpc", "tool_name": "list_crm_leads"},
    )
    assert response.status_code == 400
    assert response.json()["success"] is False
    assert "Unsupported protocol" in response.json()["error"]["message"]
