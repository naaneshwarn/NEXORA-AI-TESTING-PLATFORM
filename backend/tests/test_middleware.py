"""Tests for the platform middleware: security headers + request logging."""

from __future__ import annotations

import logging

import pytest
from fastapi.testclient import TestClient

from app.core.middleware import SECURITY_HEADERS
from app.main import app as main_app

client = TestClient(main_app)


@pytest.fixture
def http_log_records():
    """Capture records emitted by the request logger (``nexora.http``)."""
    records: list[str] = []

    class _Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:  # noqa: D102
            records.append(record.getMessage())

    logger = logging.getLogger("nexora.http")
    handler = _Capture()
    previous_level = logger.level
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    try:
        yield records
    finally:
        logger.removeHandler(handler)
        logger.setLevel(previous_level)


def test_security_headers_on_success() -> None:
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers["cross-origin-opener-policy"] == "same-origin"
    assert response.headers["cross-origin-resource-policy"] == "same-origin"
    assert "geolocation=()" in response.headers["permissions-policy"]


def test_security_headers_on_not_found() -> None:
    response = client.get("/api/v1/does-not-exist")

    assert response.status_code == 404
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"


def test_security_headers_on_validation_error() -> None:
    response = client.post("/api/v1/leads", json={"name": "x"})

    assert response.status_code == 422
    assert response.headers["x-content-type-options"] == "nosniff"
    # The error envelope must still be intact with the headers applied.
    assert response.json()["error"]["code"] == "validation_error"


def test_security_headers_cover_cors_preflight() -> None:
    response = client.options(
        "/api/v1/leads",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type,x-api-key",
        },
    )

    assert response.status_code in (200, 204)
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
    # Observability middleware is outermost, so preflights get headers too.
    assert response.headers["x-content-type-options"] == "nosniff"


def test_completed_requests_are_logged(http_log_records) -> None:
    response = client.get("/api/v1/leads")

    assert response.status_code == 200
    assert any("GET /api/v1/leads -> 200" in line for line in http_log_records)
    assert any("ms" in line for line in http_log_records)


def test_failures_are_logged(http_log_records) -> None:
    response = client.get("/api/v1/leads/lead-missing-xyz")

    assert response.status_code == 404
    assert any("GET /api/v1/leads/lead-missing-xyz -> 404" in line for line in http_log_records)


def test_health_probes_are_not_logged(http_log_records) -> None:
    # The dashboard polls readiness every 5s — these must stay out of the log.
    assert client.get("/health").status_code == 200
    assert client.get("/api/v1/health").status_code == 200
    assert client.get("/api/v1/workflow/readiness").status_code == 200

    assert http_log_records == []


def test_error_envelope_shape_matches_handlers() -> None:
    response = client.get("/api/v1/leads/definitely-missing")

    assert response.status_code == 404
    body = response.json()
    assert body["success"] is False
    assert set(body["error"]) == {"code", "message", "details"}
    assert body["error"]["code"] == "http_404"


def test_all_declared_security_headers_exist() -> None:
    response = client.get("/api/v1/health")

    for name, value in SECURITY_HEADERS:
        assert response.headers[name.decode()] == value.decode()
