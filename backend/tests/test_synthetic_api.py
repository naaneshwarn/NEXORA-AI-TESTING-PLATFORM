"""Tests for the synthetic API package (Prajwal / Work Package C).

Covers the capability descriptor published at ``GET /api/v1/synthetic``, the
lead repository seam and the fault-injection contract both routes and tooling
share.
"""

from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.core.tools import TOOL_REGISTRY
from app.integrations.synthetic_api import (
    LeadRepository,
    apply_fault_injection,
    create_synthetic_api_router,
)
from app.integrations.synthetic_api.app import build_descriptor
from app.integrations.synthetic_api.faults import ERROR_CODE_RANGE, LATENCY_RANGE_MS
from app.main import app as main_app

client = TestClient(main_app)


# -- capability descriptor ----------------------------------------------------


def test_descriptor_endpoint_reports_capabilities() -> None:
    response = client.get("/api/v1/synthetic")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["name"] == "NEXORA Synthetic CRM API"
    assert data["version"]
    assert {"rest", "openai", "langchain"} <= set(data["protocols"])
    assert "list_crm_leads" in data["tools"]
    assert data["tools"] == sorted(data["tools"])
    assert data["endpoints"]["execute"].endswith("/synthetic/agent/execute/{protocol}")


def test_descriptor_advertises_fault_ranges() -> None:
    faults = {f.parameter: f for f in build_descriptor().fault_injection}

    assert faults["simulated_latency_ms"].minimum == LATENCY_RANGE_MS[0]
    assert faults["simulated_latency_ms"].maximum == LATENCY_RANGE_MS[1]
    assert faults["inject_error"].minimum == ERROR_CODE_RANGE[0]
    assert faults["inject_error"].maximum == ERROR_CODE_RANGE[1]


def test_descriptor_never_leaks_configured_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.config import settings

    previous = settings.api_keys
    try:
        settings.api_keys = "super-secret-key"
        descriptor = build_descriptor()
        assert descriptor.authentication.keys_configured is True
        assert descriptor.authentication.active_mode == "write"
        # Never the key material itself.
        assert "super-secret-key" not in descriptor.model_dump_json()
    finally:
        settings.api_keys = previous


def test_descriptor_reports_redaction_contract() -> None:
    redaction = build_descriptor().redaction

    assert redaction.enabled is True
    assert redaction.marker == "[REDACTED]"
    lowered = {key.lower() for key in redaction.sensitive_keys}
    assert {"password", "api_key", "secret", "authorization"} <= lowered


def test_tools_endpoint_matches_registry() -> None:
    response = client.get("/api/v1/synthetic/tools")

    assert response.status_code == 200
    assert response.json()["data"] == sorted(TOOL_REGISTRY)


def test_router_is_reusable_standalone() -> None:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient as StandaloneClient

    standalone = FastAPI()
    standalone.include_router(create_synthetic_api_router())

    response = StandaloneClient(standalone).get("/synthetic")
    assert response.status_code == 200
    assert response.json()["data"]["protocols"]


# -- lead repository ----------------------------------------------------------


def test_repository_crud_round_trip() -> None:
    repository = LeadRepository()

    created = repository.create(
        {"name": "Repo Lead", "email": "repo@nexora.test", "status": "new"}
    )
    try:
        assert repository.exists(created["id"]) is True
        assert repository.get(created["id"])["email"] == "repo@nexora.test"
        assert created in repository.list()

        updated = repository.update(created["id"], {"status": "qualified"})
        assert updated["status"] == "qualified"
        assert updated["updated_at"] is not None
    finally:
        repository.delete(created["id"])

    assert repository.exists(created["id"]) is False
    assert repository.get(created["id"]) is None


def test_repository_delete_is_idempotent() -> None:
    repository = LeadRepository()
    repository.delete("lead-never-existed")  # must not raise


# -- fault injection ----------------------------------------------------------


def test_fault_injection_raises_requested_status() -> None:
    with pytest.raises(HTTPException) as excinfo:
        asyncio.run(apply_fault_injection(None, 429))

    assert excinfo.value.status_code == 429
    assert "429" in str(excinfo.value.detail)


def test_fault_injection_sleeps_for_latency(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.integrations.synthetic_api import faults as faults_module

    slept: list[float] = []

    async def _fake_sleep(seconds: float) -> None:
        slept.append(seconds)

    monkeypatch.setattr(faults_module.asyncio, "sleep", _fake_sleep)
    asyncio.run(apply_fault_injection(1500, None))

    assert slept == [1.5]


def test_fault_injection_noop_by_default() -> None:
    # Must not raise, sleep or mutate anything when both knobs are unset.
    asyncio.run(apply_fault_injection(None, None))
    asyncio.run(apply_fault_injection(0, None))


def test_injected_fault_precedes_store_reads() -> None:
    """A fault must fire even when the target record does not exist."""
    with pytest.raises(HTTPException) as excinfo:
        asyncio.run(apply_fault_injection(None, 500))
    assert excinfo.value.status_code == 500


def test_fault_query_parameters_still_validated() -> None:
    response = client.get("/api/v1/leads?inject_error=999")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"

    response = client.get("/api/v1/leads?simulated_latency_ms=-1")
    assert response.status_code == 422
