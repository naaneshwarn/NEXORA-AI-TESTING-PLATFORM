"""Contract tests for the SSE live trace streaming endpoint.

The stream terminates as soon as a run reaches a terminal state, so tests drive
a run to ``cancelled`` (optionally after recording a trace) and read the fully
buffered event stream.
"""

from fastapi.testclient import TestClient
import pytest
from sse_starlette.sse import AppStatus

from app.core.auth import FORBIDDEN_TOKEN
from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _reset_sse_app_status() -> None:
    """Reset sse-starlette's process-global exit ``Event`` between tests.

    The library creates ``AppStatus.should_exit_event`` on first use and it binds
    to that request's event loop; ``TestClient`` spins up a fresh loop per
    request, so leaving it set raises "bound to a different event loop" on the
    next streaming call.
    """
    AppStatus.should_exit_event = None
    AppStatus.should_exit = False
    yield
    AppStatus.should_exit_event = None


def _create_run(suite_name: str) -> str:
    response = client.post(
        "/api/v1/test-runs",
        json={"suite_name": suite_name, "environment": "local", "target_agents": []},
    )
    assert response.status_code == 201
    return response.json()["data"]["run_id"]


def _stream(run_id: str, headers: dict[str, str] | None = None) -> str:
    with client.stream("GET", f"/api/v1/test-runs/{run_id}/stream", headers=headers) as response:
        assert response.status_code == 200
        return "".join(response.iter_text())


def test_stream_unknown_run_returns_404() -> None:
    response = client.get("/api/v1/test-runs/run-does-not-exist/stream")

    assert response.status_code == 404
    assert "was not found" in response.text


def test_stream_emits_run_status_and_terminates_for_terminal_run() -> None:
    run_id = _create_run("stream terminal")
    client.post(f"/api/v1/test-runs/{run_id}/cancel")

    body = _stream(run_id)

    assert "event: run_status" in body
    assert '"state": "cancelled"' in body
    assert "event: tool_trace" not in body


def test_stream_emits_recorded_tool_traces_before_terminal_status() -> None:
    run_id = _create_run("stream traces")

    execution = client.post(
        f"/api/v1/synthetic/agent/execute/rest?run_id={run_id}",
        json={
            "call_id": "call-stream-1",
            "tool_name": "list_crm_leads",
            "parameters": {"api_key": "stream-secret-123"},
        },
    )
    assert execution.status_code == 200

    client.post(f"/api/v1/test-runs/{run_id}/cancel")

    body = _stream(run_id)

    # Each traced tool call is emitted exactly once, before the terminal status.
    assert body.count("event: tool_trace") == 1
    assert "call-stream-1" in body
    assert "event: run_status" in body
    assert body.index("event: tool_trace") < body.index("event: run_status")
    # Only the redacted telemetry is streamed, never the raw secret.
    assert "stream-secret-123" not in body
    assert "[REDACTED]" in body


def test_stream_rejects_denied_access_sentinels() -> None:
    run_id = _create_run("stream auth")

    response = client.get(
        f"/api/v1/test-runs/{run_id}/stream",
        headers={"Authorization": f"Bearer {FORBIDDEN_TOKEN}"},
    )

    assert response.status_code == 403
    assert "Access denied" in response.text
