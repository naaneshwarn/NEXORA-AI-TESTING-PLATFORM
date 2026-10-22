from typing import Generator
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.core.store import reset_store
from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_store() -> Generator[None, None, None]:
    """Ensure in-memory store is reset between each test execution."""
    reset_store()
    yield
    reset_store()


def test_agent_registration_and_validation() -> None:
    agent_id = f"agent-{uuid4().hex[:8]}"
    response = client.post(
        "/api/v1/agents",
        json={
            "agent_id": agent_id,
            "name": "planner-agent",
            "role": "planner",
            "model": "gpt-4o-mini",
            "provider": "mock",
            "status": "registered",
            "config": {"temperature": 0.2, "api_key": "sk-secret123456", "token": "bearer-token"},
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["success"] is True
    assert payload["data"]["agent_id"] == agent_id
    # Ensure sensitive credentials are redacted in response
    assert payload["data"]["config"]["api_key"] == "***REDACTED***"
    assert payload["data"]["config"]["token"] == "***REDACTED***"
    assert payload["data"]["config"]["temperature"] == 0.2

    # Lookup agent by ID
    lookup = client.get(f"/api/v1/agents/{agent_id}")
    assert lookup.status_code == 200
    assert lookup.json()["data"]["name"] == "planner-agent"
    assert lookup.json()["data"]["config"]["api_key"] == "***REDACTED***"

    # Auto-generate agent ID when not provided
    auto_gen_res = client.post(
        "/api/v1/agents",
        json={"name": "auto-agent", "role": "executor"},
    )
    assert auto_gen_res.status_code == 201
    auto_id = auto_gen_res.json()["data"]["agent_id"]
    assert auto_id.startswith("agent-")

    # List registered agents
    all_agents = client.get("/api/v1/agents")
    assert all_agents.status_code == 200
    assert len(all_agents.json()["data"]) >= 2

    # Duplicate agent registration should return 409 Conflict
    duplicate = client.post(
        "/api/v1/agents",
        json={"agent_id": agent_id, "name": "duplicate-agent", "role": "reporter"},
    )
    assert duplicate.status_code == 409
    dup_body = duplicate.json()
    assert dup_body["success"] is False
    assert dup_body["error"]["code"] == "conflict"

    # Missing agent lookup should return 404 Not Found
    missing = client.get("/api/v1/agents/agent-non-existent")
    assert missing.status_code == 404
    missing_body = missing.json()
    assert missing_body["success"] is False
    assert missing_body["error"]["code"] == "not_found"

    # Invalid input should return 422 Unprocessable Entity
    invalid = client.post(
        "/api/v1/agents",
        json={"agent_id": "", "name": "bad", "role": "invalid-role"},
    )
    assert invalid.status_code == 422
    assert invalid.json()["success"] is False
    assert invalid.json()["error"]["code"] == "validation_error"


def test_test_run_contract_and_events() -> None:
    agent_id = f"agent-{uuid4().hex[:8]}"
    client.post(
        "/api/v1/agents",
        json={
            "agent_id": agent_id,
            "name": "executor-agent",
            "role": "executor",
            "model": "mock-model",
            "provider": "mock",
            "status": "active",
            "config": {"timeout": 30},
        },
    )

    run_payload = {
        "suite_name": "checkout smoke",
        "scenario": {"name": "browser regression", "variables": {"region": "eu-west-1"}},
        "environment": "local",
        "target_agents": [agent_id],
        "tags": ["smoke", "checkout"],
        "config": {"parallel": False, "timeout_seconds": 120},
    }

    run = client.post("/api/v1/test-runs", json=run_payload)
    assert run.status_code == 201
    run_data = run.json()["data"]
    assert run_data["suite_name"] == "checkout smoke"
    assert run_data["state"] == "queued"

    run_id = run_data["run_id"]
    status = client.get(f"/api/v1/test-runs/{run_id}")
    assert status.status_code == 200
    assert status.json()["data"]["run_id"] == run_id

    # List test runs
    runs_list = client.get("/api/v1/test-runs")
    assert runs_list.status_code == 200
    assert len(runs_list.json()["data"]) >= 1

    # Cancellation
    cancelled = client.post(f"/api/v1/test-runs/{run_id}/cancel")
    assert cancelled.status_code == 200
    assert cancelled.json()["data"]["state"] == "cancelled"

    # Attempting to cancel an already cancelled run should return 400 Bad Request
    already_cancelled = client.post(f"/api/v1/test-runs/{run_id}/cancel")
    assert already_cancelled.status_code == 400
    assert already_cancelled.json()["error"]["code"] == "invalid_state_transition"

    # Event retrieval
    events = client.get(f"/api/v1/test-runs/{run_id}/events")
    assert events.status_code == 200
    assert len(events.json()["data"]) >= 2
    assert events.json()["data"][0]["run_id"] == run_id

    # Event retrieval for unknown run
    missing_events = client.get("/api/v1/test-runs/run-unknown-999/events")
    assert missing_events.status_code == 404
    assert missing_events.json()["error"]["code"] == "not_found"

    # Reject run when referenced agent does not exist (and allow_mock is not True)
    bad_ref_run = client.post(
        "/api/v1/test-runs",
        json={
            "suite_name": "invalid target",
            "target_agents": ["agent-does-not-exist"],
        },
    )
    assert bad_ref_run.status_code == 404
    assert "agent-does-not-exist" in bad_ref_run.json()["error"]["message"]


def test_environment_and_evaluation_contract() -> None:
    environment = client.post(
        "/api/v1/environments",
        json={
            "environment_type": "postgres",
            "label": "local-testing-db",
            "config": {"database": "nexora_dev", "port": 5432},
        },
    )
    assert environment.status_code == 201
    env_data = environment.json()["data"]
    assert env_data["environment_type"] == "postgres"
    assert env_data["status"] == "provisioning"
    # Ensure no fabricated container URL is returned before Docker engine confirmation
    assert env_data["endpoint"] is None

    env_id = env_data["environment_id"]
    retrieved = client.get(f"/api/v1/environments/{env_id}")
    assert retrieved.status_code == 200
    assert retrieved.json()["data"]["label"] == "local-testing-db"

    # List environments
    all_envs = client.get("/api/v1/environments")
    assert all_envs.status_code == 200
    assert len(all_envs.json()["data"]) >= 1

    # Stop environment (safe and idempotent)
    client.post(f"/api/v1/environments/{env_id}/stop")
    stopped = client.get(f"/api/v1/environments/{env_id}")
    assert stopped.json()["data"]["status"] == "stopped"

    # Stopping again should succeed idempotently
    idempotent_stop = client.post(f"/api/v1/environments/{env_id}/stop")
    assert idempotent_stop.status_code == 200
    assert idempotent_stop.json()["data"]["status"] == "stopped"

    # Evaluation on valid test run
    run = client.post(
        "/api/v1/test-runs",
        json={
            "suite_name": "reporting workflow",
            "environment": "local",
            "target_agents": ["agent-reporting"],
            "config": {"allow_mock": True},
        },
    )
    run_id = run.json()["data"]["run_id"]

    submission = client.post(
        "/api/v1/evaluations",
        json={
            "run_id": run_id,
            "agent_id": "agent-reporting",
            "score": 92.5,
            "status": "pass",
            "summary": "The workflow passed the smoke validation requirements.",
            "metrics": {"coverage": 0.92, "latency_ms": 245.0},
            "issues": [],
        },
    )
    assert submission.status_code == 201
    report_id = submission.json()["data"]["report_id"]
    report = client.get(f"/api/v1/reports/{report_id}")
    assert report.status_code == 200
    assert report.json()["data"]["score"] == 92.5

    # Report lookup by run_id
    run_report = client.get(f"/api/v1/reports/runs/{run_id}")
    assert run_report.status_code == 200
    assert run_report.json()["data"]["report_id"] == report_id

    # Evaluation submission on unknown run_id should return 404
    bad_submission = client.post(
        "/api/v1/evaluations",
        json={
            "run_id": "run-does-not-exist",
            "score": 50.0,
            "summary": "invalid run evaluation",
        },
    )
    assert bad_submission.status_code == 404
    assert bad_submission.json()["error"]["code"] == "not_found"

    # Lookup missing report should return 404
    missing_report = client.get("/api/v1/reports/report-non-existent")
    assert missing_report.status_code == 404
    assert missing_report.json()["error"]["code"] == "not_found"


def test_cors_preflight_headers() -> None:
    response = client.options(
        "/api/v1/health",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://localhost:5173"

