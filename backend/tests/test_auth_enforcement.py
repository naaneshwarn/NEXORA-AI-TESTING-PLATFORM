"""Contract tests for real API-key enforcement (Work Package A).

The default configuration (no ``NEXORA_API_KEYS``) must keep behaving exactly
like the original optional-auth platform: anonymous traffic flows and only the
synthetic sentinels deny.  Configuring keys flips the process into write mode
(mutating requests require a valid key) or, explicitly, full mode (every
request does) — health and schema endpoints stay open in both.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.auth import (
    configured_api_keys,
    requires_auth,
    resolve_auth_mode,
)
from app.core.config import settings
from app.main import app as main_app

client = TestClient(main_app)

VALID_KEY = "launch-key-001"
SECOND_KEY = "launch-key-002"

LEAD_BODY = {"name": "Auth Lead", "email": "auth.enforcement@nexora.test"}


@pytest.fixture
def api_keys_enabled():
    """Configure two API keys in auto mode, restoring defaults afterwards."""
    previous_keys = settings.api_keys
    previous_mode = settings.auth_mode
    settings.api_keys = f"  {VALID_KEY} , {SECOND_KEY} ,, "
    settings.auth_mode = "auto"
    try:
        yield VALID_KEY
    finally:
        settings.api_keys = previous_keys
        settings.auth_mode = previous_mode


@pytest.fixture
def full_mode():
    previous_keys = settings.api_keys
    previous_mode = settings.auth_mode
    settings.api_keys = VALID_KEY
    settings.auth_mode = "full"
    try:
        yield VALID_KEY
    finally:
        settings.api_keys = previous_keys
        settings.auth_mode = previous_mode


def _delete_quietly(lead_id: str) -> None:
    client.delete(f"/api/v1/leads/{lead_id}", headers={"X-API-Key": VALID_KEY})


# -- mode resolution ---------------------------------------------------------


def test_default_mode_is_off() -> None:
    assert configured_api_keys() == frozenset()
    assert resolve_auth_mode() == "off"
    assert requires_auth("POST", "/api/v1/leads") is False


def test_auto_mode_enables_write_protection_with_keys(api_keys_enabled) -> None:
    assert configured_api_keys() == frozenset({VALID_KEY, SECOND_KEY})
    assert resolve_auth_mode() == "write"
    assert requires_auth("POST", "/api/v1/leads") is True
    assert requires_auth("DELETE", "/api/v1/leads/x") is True
    # Reads stay open so the dashboard, Swagger and SSE keep working.
    assert requires_auth("GET", "/api/v1/leads") is False


def test_health_and_schema_paths_always_open(api_keys_enabled) -> None:
    for path in ("/api/v1/health", "/health", "/docs", "/openapi.json", "/v1/models"):
        assert requires_auth("GET", path) is False
        assert requires_auth("POST", path) is False


def test_explicit_mode_without_keys_degrades_to_off() -> None:
    previous = settings.auth_mode
    try:
        settings.auth_mode = "full"
        assert resolve_auth_mode() == "off"  # nothing to validate against
    finally:
        settings.auth_mode = previous


def test_unknown_mode_falls_back_to_auto(api_keys_enabled) -> None:
    previous = settings.auth_mode
    try:
        settings.auth_mode = "banana"
        assert resolve_auth_mode() == "write"  # auto + keys configured
    finally:
        settings.auth_mode = previous


# -- HTTP enforcement --------------------------------------------------------


def test_anonymous_mutation_rejected_with_envelope(api_keys_enabled) -> None:
    response = client.post("/api/v1/leads", json=LEAD_BODY)

    assert response.status_code == 401
    body = response.json()
    assert body["success"] is False
    assert body["error"]["code"] == "http_401"
    assert "API key" in body["error"]["message"]


def test_invalid_key_rejected(api_keys_enabled) -> None:
    response = client.post(
        "/api/v1/leads", json=LEAD_BODY, headers={"X-API-Key": "wrong-key"}
    )

    assert response.status_code == 401
    assert response.json()["error"]["message"] == "Invalid authentication credentials provided."


def test_valid_api_key_accepted(api_keys_enabled) -> None:
    response = client.post(
        "/api/v1/leads", json=LEAD_BODY, headers={"X-API-Key": VALID_KEY}
    )

    assert response.status_code == 201
    _delete_quietly(response.json()["data"]["id"])


def test_second_configured_key_accepted(api_keys_enabled) -> None:
    response = client.post(
        "/api/v1/leads", json=LEAD_BODY, headers={"X-API-Key": SECOND_KEY}
    )

    assert response.status_code == 201
    _delete_quietly(response.json()["data"]["id"])


def test_bearer_token_accepted(api_keys_enabled) -> None:
    response = client.post(
        "/api/v1/leads",
        json=LEAD_BODY,
        headers={"Authorization": f"Bearer {SECOND_KEY}"},
    )

    assert response.status_code == 201
    _delete_quietly(response.json()["data"]["id"])


def test_reads_open_in_write_mode(api_keys_enabled) -> None:
    response = client.get("/api/v1/leads")

    assert response.status_code == 200


def test_health_open_in_write_mode(api_keys_enabled) -> None:
    assert client.get("/api/v1/health").status_code == 200
    assert client.get("/health").status_code == 200


def test_forbidden_sentinel_still_403_on_mutation(api_keys_enabled) -> None:
    response = client.post(
        "/api/v1/leads",
        json=LEAD_BODY,
        headers={"X-API-Key": "forbidden-token-test"},
    )

    assert response.status_code == 403
    assert "Access denied" in response.json()["error"]["message"]


def test_full_mode_protects_reads(full_mode) -> None:
    anonymous = client.get("/api/v1/leads")
    assert anonymous.status_code == 401

    authorized = client.get("/api/v1/leads", headers={"X-API-Key": VALID_KEY})
    assert authorized.status_code == 200


def test_full_mode_keeps_health_open(full_mode) -> None:
    assert client.get("/api/v1/health").status_code == 200
    assert client.get("/api/v1/workflow/readiness").status_code == 401


def test_sentinels_behave_in_every_mode(api_keys_enabled) -> None:
    invalid = client.get("/api/v1/leads", headers={"X-API-Key": "invalid-token-test"})
    assert invalid.status_code == 401
    assert "Invalid authentication credentials" in invalid.json()["error"]["message"]


def test_sentinels_still_work_with_auth_disabled() -> None:
    # Default suite configuration: no keys, sentinel-only behaviour unchanged.
    assert resolve_auth_mode() == "off"
    invalid = client.get("/api/v1/leads", headers={"X-API-Key": "invalid-token-test"})
    assert invalid.status_code == 401
    forbidden = client.get("/api/v1/leads", headers={"X-API-Key": "forbidden-token-test"})
    assert forbidden.status_code == 403
    assert client.get("/api/v1/leads").status_code == 200
