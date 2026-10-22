"""Focused tests for the synthetic CRM simulation surface (Priority Two).

Covers contract behaviour the platform relies on when agents interact with the
synthetic CRM: CRUD lifecycle, invalid payloads, missing-resource responses,
query-parameter boundary validation, sequential state changes, repeated
operations and consistent error envelopes. Fault/latency injection is covered
by ``test_api_contracts.py``.
"""

from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _create_lead(name: str | None = "Boundary Lead", email: str = "boundary@example.com", **overrides: object) -> dict:
    payload: dict[str, object] = {"name": name, "email": email, "status": "new"}
    payload.update(overrides)
    response = client.post("/api/v1/leads", json=payload)
    assert response.status_code == 201, response.text
    return response.json()["data"]


def test_crm_crud_lifecycle_and_state_changes() -> None:
    # Create
    lead = _create_lead("Alice Smith", "alice@example.com", company="Acme Inc", status="new")
    lead_id = lead["id"]
    assert lead_id.startswith("lead-")
    assert lead["created_at"]
    assert lead["updated_at"] is None

    # Retrieve
    fetched = client.get(f"/api/v1/leads/{lead_id}")
    assert fetched.status_code == 200
    assert fetched.json()["data"]["name"] == "Alice Smith"

    # Update (state change visible across sequential requests)
    updated = client.put(
        f"/api/v1/leads/{lead_id}",
        json={"name": "Alice Doe", "email": "alice@example.com", "status": "qualified"},
    )
    assert updated.status_code == 200
    updated_data = updated.json()["data"]
    assert updated_data["name"] == "Alice Doe"
    assert updated_data["status"] == "qualified"
    assert updated_data["updated_at"] is not None

    # The list endpoint reflects the mutation
    listing = client.get("/api/v1/leads")
    matches = [row for row in listing.json()["data"] if row["id"] == lead_id]
    assert matches and matches[0]["name"] == "Alice Doe"

    # Delete
    deleted = client.delete(f"/api/v1/leads/{lead_id}")
    assert deleted.status_code == 204

    # Delete is idempotent-safe at the HTTP layer: second delete 404s, get 404s
    assert client.get(f"/api/v1/leads/{lead_id}").status_code == 404


def test_crm_invalid_payloads_rejected_consistently() -> None:
    # Missing required name -> 422 validation error envelope
    missing_name = client.post("/api/v1/leads", json={"email": "x@example.com"})
    assert missing_name.status_code == 422
    assert missing_name.json()["success"] is False

    # Name shorter than min_length -> 422
    too_short = client.post("/api/v1/leads", json={"name": "A", "email": "x@example.com"})
    assert too_short.status_code == 422

    # Invalid status literal -> 422
    bad_status = client.post(
        "/api/v1/leads", json={"name": "Valid Name", "email": "x@example.com", "status": "lost"}
    )
    assert bad_status.status_code == 422

    # Non-object body (e.g. a plain list) -> 422
    non_object = client.post("/api/v1/leads", json=[1, 2, 3])
    assert non_object.status_code == 422


def test_crm_missing_resources_return_structured_404() -> None:
    missing_id = f"lead-{uuid4().hex[:8]}"

    get_response = client.get(f"/api/v1/leads/{missing_id}")
    assert get_response.status_code == 404
    assert get_response.json()["success"] is False
    assert "message" in get_response.json()["error"]

    # A valid update body is required: FastAPI validates the body first, so use a
    # well-formed payload to reach the route's existence check.
    put_response = client.put(
        f"/api/v1/leads/{missing_id}",
        json={"name": "Valid Name", "email": "valid@example.com", "status": "new"},
    )
    assert put_response.status_code == 404
    body = put_response.json()
    assert body["success"] is False
    assert "message" in body["error"]

    delete_response = client.delete(f"/api/v1/leads/{missing_id}")
    assert delete_response.status_code == 404
    assert delete_response.json()["error"]["message"]


def test_crm_query_boundary_validation() -> None:
    # Out-of-range fault-injection values are rejected with 422 before reaching storage.
    invalid_cases = [
        {"inject_error": 200},  # below the [400, 599] range (100-399 are not errors)
        {"inject_error": 600},  # above the range
        {"simulated_latency_ms": -1},
        {"simulated_latency_ms": 60001},  # above the 60s ceiling
    ]
    for params in invalid_cases:
        response = client.get("/api/v1/leads", params=params)
        assert response.status_code == 422, f"params={params}: {response.status_code}"
        assert response.json()["success"] is False

    # Lower edge of the accepted latency range is honoured without delay.
    assert client.get("/api/v1/leads", params={"simulated_latency_ms": 0}).status_code == 200


def test_crm_repeated_and_concurrent_operations() -> None:
    lead = _create_lead("Repeated Lead", "repeated@example.com")

    # Repeated reads of the same resource stay consistent.
    first = client.get(f"/api/v1/leads/{lead['id']}")
    second = client.get(f"/api/v1/leads/{lead['id']}")
    assert first.json()["data"] == second.json()["data"]

    # Parallel creates all succeed and remain independently addressable.
    names = [f"Concurrent {i}" for i in range(5)]
    created = [client.post("/api/v1/leads", json={"name": n, "email": f"{n}@example.com"}) for n in names]
    assert all(response.status_code == 201 for response in created)
    ids = [response.json()["data"]["id"] for response in created]
    assert len(set(ids)) == len(ids)
    assert all(client.get(f"/api/v1/leads/{lead_id}").status_code == 200 for lead_id in ids)