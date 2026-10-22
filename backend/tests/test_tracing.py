import asyncio
import json
from uuid import uuid4

from fastapi.testclient import TestClient

from app.core.redaction import REDACTED, redact_sensitive_data
from app.core.store import get_traces_for_run
from app.core.telemetry import execute_and_trace_tool
from app.main import app

client = TestClient(app)


def test_redact_sensitive_data_masks_keys_recursively() -> None:
    payload = {
        "username": "ada",
        "password": "hunter2",
        "apiKey": "not-a-real-key",
        "nested": {
            "Access-Token": "abc123",
            "items": [{"secret": "top-secret"}, {"card_number": "4111111111111111"}],
        },
        "notes": "the password is safe here",
    }

    redacted = redact_sensitive_data(payload)

    assert redacted["username"] == "ada"
    assert redacted["password"] == REDACTED
    assert redacted["apiKey"] == REDACTED
    assert redacted["nested"]["Access-Token"] == REDACTED
    assert redacted["nested"]["items"][0]["secret"] == REDACTED
    assert redacted["nested"]["items"][1]["card_number"] == REDACTED
    # A bare word is not treated as an inline secret.
    assert redacted["notes"] == "the password is safe here"


def test_redact_sensitive_data_scrubs_inline_secrets() -> None:
    assert "sk-abcdefghijklmnop1234" not in redact_sensitive_data("sk-abcdefghijklmnop1234")
    assert redact_sensitive_data("Bearer abc.def.ghi") == "Bearer [REDACTED]"
    assert "deadbeef" not in redact_sensitive_data("token=deadbeef&page=1")
    assert "[REDACTED]" in redact_sensitive_data("Authorization: Basic dXNlcjpwYXNz")


def test_execute_and_trace_tool_persists_redacted_telemetry() -> None:
    run_id = f"run-{uuid4().hex[:8]}"

    outcome = asyncio.run(
        execute_and_trace_tool(
            run_id,
            "call-trace-1",
            "create_crm_lead",
            {"name": "Trace Lead", "email": "trace@example.com", "password": "p@ssw0rd"},
        )
    )

    assert outcome.success is True
    assert outcome.error is None
    assert outcome.data["id"].startswith("lead-")
    assert outcome.execution_time_ms >= 0
    assert outcome.trace is not None
    assert outcome.trace.parameters["password"] == REDACTED
    assert outcome.trace.parameters["name"] == "Trace Lead"
    assert outcome.trace.timestamp is not None

    stored = get_traces_for_run(run_id)
    assert len(stored) == 1
    assert stored[0]["tool_name"] == "create_crm_lead"
    assert stored[0]["parameters"]["password"] == REDACTED
    assert stored[0]["timestamp"]


def test_execute_and_trace_tool_captures_failures() -> None:
    run_id = f"run-{uuid4().hex[:8]}"

    outcome = asyncio.run(
        execute_and_trace_tool(run_id, "call-trace-2", "does_not_exist", {"token": "abc"})
    )

    assert outcome.success is False
    assert outcome.error is not None
    assert outcome.error["code"] == "tool_not_found"

    stored = get_traces_for_run(run_id)
    assert len(stored) == 1
    assert stored[0]["success"] is False
    assert stored[0]["parameters"]["token"] == REDACTED


def test_execution_dispatcher_records_and_exposes_traces() -> None:
    run = client.post(
        "/api/v1/test-runs",
        json={"suite_name": "trace run", "environment": "local", "target_agents": []},
    )
    run_id = run.json()["data"]["run_id"]

    execution = client.post(
        f"/api/v1/synthetic/agent/execute/rest?run_id={run_id}",
        json={
            "call_id": "call-integration",
            "tool_name": "create_crm_lead",
            "parameters": {"name": "Integration Lead", "email": "integration@example.com", "password": "s3cret"},
        },
    )
    assert execution.status_code == 200
    assert execution.json()["success"] is True

    traces = client.get(f"/api/v1/test-runs/{run_id}/traces")
    assert traces.status_code == 200
    data = traces.json()["data"]
    assert len(data) == 1
    assert data[0]["call_id"] == "call-integration"
    assert data[0]["parameters"]["password"] == REDACTED
    assert "s3cret" not in json.dumps(data[0])


def test_traces_endpoints_handle_missing_records() -> None:
    unknown_run = client.post(
        "/api/v1/synthetic/agent/execute/rest?run_id=run-unknown",
        json={"call_id": "call-x", "tool_name": "list_crm_leads"},
    )
    assert unknown_run.status_code == 404

    run = client.post(
        "/api/v1/test-runs",
        json={"suite_name": "empty trace run", "environment": "local", "target_agents": []},
    )
    run_id = run.json()["data"]["run_id"]
    assert client.get(f"/api/v1/test-runs/{run_id}/traces").status_code == 404


def test_execution_dispatcher_writes_tool_call_event_for_run() -> None:
    """Profiled executions produce both a trace and a tool_call execution event."""
    run = client.post(
        "/api/v1/test-runs",
        json={"suite_name": "event trace run", "environment": "local", "target_agents": []},
    )
    run_id = run.json()["data"]["run_id"]

    execution = client.post(
        f"/api/v1/synthetic/agent/execute/rest?run_id={run_id}",
        json={
            "call_id": "call-event-1",
            "tool_name": "list_crm_leads",
            "parameters": {"api_key": "event-secret-123"},
        },
    )
    assert execution.status_code == 200
    assert execution.json()["success"] is True

    events = client.get(f"/api/v1/test-runs/{run_id}/events")
    assert events.status_code == 200
    data = events.json()["data"]

    tool_events = [event for event in data if event["event_type"] == "tool_call"]
    assert len(tool_events) == 1
    assert tool_events[0]["tool_calls"][0]["tool_name"] == "list_crm_leads"
    assert tool_events[0]["tool_calls"][0]["status"] == "success"
    # The event payload reuses the redacted telemetry, never the raw secret.
    assert tool_events[0]["tool_calls"][0]["payload"]["api_key"] == REDACTED
    assert "event-secret-123" not in events.text


def test_execution_dispatcher_writes_failure_tool_call_event() -> None:
    """Failed executions still produce an event carrying safe error metadata."""
    run = client.post(
        "/api/v1/test-runs",
        json={"suite_name": "failure event run", "environment": "local", "target_agents": []},
    )
    run_id = run.json()["data"]["run_id"]

    execution = client.post(
        f"/api/v1/synthetic/agent/execute/openai?run_id={run_id}",
        json={
            "id": "call-fail-1",
            "type": "function",
            "function": {"name": "missing_tool_xyz", "arguments": {}},
        },
    )
    assert execution.status_code == 200
    assert execution.json()["role"] == "tool"

    events = client.get(f"/api/v1/test-runs/{run_id}/events")
    tool_events = [event for event in events.json()["data"] if event["event_type"] == "tool_call"]
    assert len(tool_events) == 1
    assert tool_events[0]["tool_calls"][0]["status"] == "failed"
    assert tool_events[0]["payload"]["success"] is False
