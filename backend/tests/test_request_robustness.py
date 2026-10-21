"""Malformed-request robustness tests (adversarial input hardening).

These pin the fix for a real defect found by driving the live API with
non-JSON bodies: a ``text/plain`` (or missing ``Content-Type``) POST raised a
``RequestValidationError`` whose ``errors()`` echoed the raw request ``bytes``
in the ``input`` field.  ``JSONResponse`` cannot serialize ``bytes``, so the
422 handler itself raised ``TypeError`` and the caller received a misleading
``500``.  The handler now sanitizes the error payload, so every route returns a
well-formed ``422`` envelope for an unparseable body.

Every assertion here is Docker-free and uses the in-process TestClient.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


_ENDPOINTS = [
    "/api/v1/leads",
    "/api/v1/agents",
    "/api/v1/test-runs",
    "/api/v1/environments",
]


def test_non_json_body_returns_422_not_500() -> None:
    """A text/plain body must be a clean 422 for every POST route."""
    for path in _ENDPOINTS:
        response = client.post(path, content=b"not json at all", headers={"Content-Type": "text/plain"})
        assert response.status_code == 422, f"{path} -> {response.status_code}"
        payload = response.json()
        assert payload["success"] is False
        assert payload["error"]["code"] == "validation_error"


def test_missing_content_type_returns_422_not_500() -> None:
    """No Content-Type header must also be a clean 422, not a 500."""
    for path in _ENDPOINTS:
        response = client.post(path, content=b"raw-bytes-body")
        assert response.status_code == 422, f"{path} -> {response.status_code}"
        assert response.json()["error"]["code"] == "validation_error"


def test_malformed_json_object_returns_422() -> None:
    """Syntactically broken JSON with the right content-type -> 422."""
    response = client.post(
        "/api/v1/leads",
        content=b"{bad json",
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_validation_error_payload_is_json_serializable_and_echoes_safely() -> None:
    """The echoed ``input`` for a bytes body is a safe string, never raw bytes."""
    response = client.post("/api/v1/leads", content=b"hello", headers={"Content-Type": "text/plain"})
    body = response.json()
    errors = body["error"]["details"]["errors"]
    assert errors, "expected at least one validation error"
    # Serializing must not raise and the raw input echo must be a JSON type.
    for err in errors:
        if "input" in err:
            assert not isinstance(err["input"], (bytes, bytearray))


def test_non_json_body_does_not_mutate_state() -> None:
    """A rejected body creates nothing: the lead list is unchanged."""
    before = client.get("/api/v1/leads").json()["data"]
    client.post("/api/v1/leads", content=b"junk", headers={"Content-Type": "text/plain"})
    after = client.get("/api/v1/leads").json()["data"]
    assert len(after) == len(before)
