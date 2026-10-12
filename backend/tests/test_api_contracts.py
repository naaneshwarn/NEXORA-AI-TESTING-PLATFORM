import time
from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


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
            "config": {"temperature": 0.2},
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["success"] is True
    assert payload["data"]["agent_id"] == agent_id

    lookup = client.get(f"/api/v1/agents/{agent_id}")
    assert lookup.status_code == 200
    assert lookup.json()["data"]["name"] == "planner-agent"

    invalid = client.post(
        "/api/v1/agents",
        json={"agent_id": "", "name": "bad", "role": "invalid-role"},
    )
    assert invalid.status_code == 422
    assert invalid.json()["success"] is False


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

    cancelled = client.post(f"/api/v1/test-runs/{run_id}/cancel")
    assert cancelled.status_code == 200
    assert cancelled.json()["data"]["state"] == "cancelled"

    events = client.get(f"/api/v1/test-runs/{run_id}/events")
    assert events.status_code == 200
    assert events.json()["data"][0]["run_id"] == run_id


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

    env_id = env_data["environment_id"]
    retrieved = client.get(f"/api/v1/environments/{env_id}")
    assert retrieved.status_code == 200
    assert retrieved.json()["data"]["label"] == "local-testing-db"

    client.post(f"/api/v1/environments/{env_id}/stop")
    stopped = client.get(f"/api/v1/environments/{env_id}")
    assert stopped.json()["data"]["status"] == "stopped"

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


def test_crm_fault_and_latency_injection() -> None:
    created = client.post(
        "/api/v1/leads",
        json={"name": "Resiliency Lead", "email": "resiliency@example.com", "status": "new"},
    )
    assert created.status_code == 201
    lead_id = created.json()["data"]["id"]

    # Healthy reads are unaffected when no fault parameters are supplied.
    baseline = client.get("/api/v1/leads")
    assert baseline.status_code == 200
    assert baseline.json()["success"] is True

    # Latency injection adds a measurable delay without altering the payload.
    started = time.perf_counter()
    delayed = client.get("/api/v1/leads", params={"simulated_latency_ms": 50})
    elapsed = time.perf_counter() - started
    assert delayed.status_code == 200
    assert delayed.json()["success"] is True
    assert elapsed >= 0.04

    # Rate limiting (429) and server failures (500) are simulated on both reads.
    for path in ("/api/v1/leads", f"/api/v1/leads/{lead_id}"):
        rate_limited = client.get(path, params={"inject_error": 429})
        assert rate_limited.status_code == 429
        assert rate_limited.json()["success"] is False
        assert rate_limited.json()["error"]["code"] == "http_429"

        failing = client.get(path, params={"inject_error": 500})
        assert failing.status_code == 500
        assert failing.json()["success"] is False
        assert failing.json()["error"]["code"] == "http_500"

    # Injected faults must not corrupt synthetic state.
    recovered = client.get(f"/api/v1/leads/{lead_id}")
    assert recovered.status_code == 200
    assert recovered.json()["data"]["id"] == lead_id

    # Codes outside the HTTP error range are rejected by request validation.
    invalid = client.get("/api/v1/leads", params={"inject_error": 200})
    assert invalid.status_code == 422
    assert invalid.json()["success"] is False
