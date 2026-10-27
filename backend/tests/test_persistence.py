"""Tests for the durable core-store snapshot (Work Package A).

Persistence is disabled for the whole suite by ``conftest.py``; these tests
opt back in with an explicit temporary directory and always restore the
disabled state afterwards.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.core import store
from app.core.config import settings
from app.core.persistence import SNAPSHOT_FILENAME, STATE_VERSION, persistence
from app.schemas.agent import AgentConfig
from app.schemas.environment import SyntheticEnvironment
from app.schemas.evaluation import EvaluationSubmission
from app.schemas.test_run import RunCreateRequest

_COLLECTIONS = (
    "AGENTS",
    "TEST_RUNS",
    "ENVIRONMENTS",
    "EVENTS",
    "REPORTS",
    "TOOL_TRACES",
    "WORKFLOW_REPORTS",
    "CRM_LEADS",
)


@pytest.fixture(autouse=True)
def isolated_store():
    """Snapshot and restore every store collection around each test."""
    saved = {name: dict(getattr(store, name)) for name in _COLLECTIONS}
    for name in _COLLECTIONS:
        getattr(store, name).clear()
    yield
    for name in _COLLECTIONS:
        collection = getattr(store, name)
        collection.clear()
        collection.update(saved[name])


@pytest.fixture
def enabled_persistence(tmp_path: Path):
    """Enable persistence into a temp dir; always restore the disabled state."""
    previous_state_dir = settings.state_dir
    settings.state_dir = str(tmp_path)
    persistence.configure(str(tmp_path))
    try:
        yield tmp_path / SNAPSHOT_FILENAME
    finally:
        persistence.disable()
        settings.state_dir = previous_state_dir


def _seed_state() -> None:
    """Populate every kind of store record so round-trips cover them all."""
    store.register_agent(
        AgentConfig(agent_id="agent-persist", name="Persisted Agent", role="executor")
    )
    store.create_crm_lead(
        {"name": "Persist Lead", "email": "persist@nexora.test", "status": "new"}
    )
    store.create_test_run(RunCreateRequest(suite_name="persist-suite"))
    store.record_tool_trace(
        "run-placeholder",
        {"call_id": "p-1", "tool_name": "list_crm_leads", "parameters": {"api_key": "[REDACTED]"}},
    )
    store.create_environment(
        SyntheticEnvironment(environment_id="env-persist", environment_type="postgres", label="p")
    )
    store.submit_evaluation(
        EvaluationSubmission(run_id="run-persist", score=88.0, summary="persisted score")
    )
    store.save_workflow_report(
        {
            "report_id": "wfreport-persist",
            "run_id": "run-persist",
            "score": 91.5,
            "generated_at": "2026-10-28T00:00:00+00:00",
        }
    )


def test_persistence_disabled_by_default() -> None:
    # conftest forces NEXORA_STATE_DIR="" for every test.
    assert settings.state_dir == ""
    assert persistence.enabled is False
    assert persistence.path is None
    assert persistence.save() is False
    assert persistence.load() is False


def test_configure_empty_string_disables(tmp_path: Path) -> None:
    assert persistence.configure(str(tmp_path)) is not None
    assert persistence.enabled is True
    assert persistence.configure("") is None
    assert persistence.configure(None) is None
    assert persistence.enabled is False


def test_relative_state_dir_resolves_under_backend(tmp_path: Path) -> None:
    path = persistence.configure("relative-state-dir")
    try:
        assert path is not None and path.is_absolute()
        assert path.name == SNAPSHOT_FILENAME
        assert str(path).endswith(str(Path("backend") / "relative-state-dir" / SNAPSHOT_FILENAME))
    finally:
        persistence.disable()


def test_save_then_load_round_trips_every_collection(enabled_persistence: Path) -> None:
    _seed_state()
    # A record created after seeding proves saves happen on later mutations too.
    store.create_crm_lead({"name": "Late Lead", "email": "late@nexora.test", "status": "new"})

    assert enabled_persistence.exists()
    snapshot = json.loads(enabled_persistence.read_text(encoding="utf-8"))
    assert snapshot["version"] == STATE_VERSION
    assert snapshot["saved_at"]
    assert set(snapshot) >= {
        "agents",
        "test_runs",
        "environments",
        "events",
        "reports",
        "tool_traces",
        "workflow_reports",
        "crm_leads",
    }
    # Atomic write: no temp file may survive a successful save.
    assert not enabled_persistence.with_name(enabled_persistence.name + ".tmp").exists()

    # Simulate a fresh process: wipe memory, then hydrate from disk.
    for name in _COLLECTIONS:
        getattr(store, name).clear()
    assert persistence.load() is True

    agent = store.get_agent("agent-persist")
    assert agent is not None
    assert agent.name == "Persisted Agent"
    assert agent.role == "executor"

    lead = next(
        (lead for lead in store.list_crm_leads() if lead["name"] == "Persist Lead"), None
    )
    assert lead is not None and lead["email"] == "persist@nexora.test"

    # Pydantic rehydrates datetime fields, not JSON strings.
    from datetime import datetime

    run = store.get_test_run(next(iter(snapshot["test_runs"])))  # id from our own snapshot
    assert run is not None
    assert run.suite_name == "persist-suite"
    assert isinstance(run.created_at, datetime)

    assert store.get_environment("env-persist") is not None
    assert store.get_traces_for_run("run-placeholder")[0]["call_id"] == "p-1"
    assert store.get_workflow_report("wfreport-persist")["score"] == 91.5
    reports = list(store.REPORTS.values())
    assert any(r.run_id == "run-persist" and r.score == 88.0 for r in reports)


def test_load_without_snapshot_returns_false(enabled_persistence: Path) -> None:
    assert enabled_persistence.exists() is False
    assert persistence.load() is False
    assert store.AGENTS == {}


def test_corrupt_snapshot_never_blocks_startup(enabled_persistence: Path) -> None:
    # Seed first (auto-saves a valid snapshot), then corrupt the file —
    # simulating on-disk damage between writes.
    store.create_crm_lead({"name": "Pre", "email": "pre@nexora.test", "status": "new"})
    enabled_persistence.write_text("{ this is not json", encoding="utf-8")

    # A failed load never raises and never clobbers live memory; a fresh
    # process (empty store at boot) therefore simply starts empty.
    assert persistence.load() is False
    assert len(store.CRM_LEADS) == 1
    assert store.AGENTS == {}


def test_snapshot_with_wrong_shape_is_rejected(enabled_persistence: Path) -> None:
    enabled_persistence.write_text("[1, 2, 3]", encoding="utf-8")
    assert persistence.load() is False


def test_invalid_records_are_skipped_not_fatal(enabled_persistence: Path) -> None:
    store.register_agent(
        AgentConfig(agent_id="agent-good", name="Good Agent", role="planner")
    )
    persistence.save()
    # Corrupt one record inside an otherwise valid snapshot.
    snapshot = json.loads(enabled_persistence.read_text(encoding="utf-8"))
    snapshot["agents"]["agent-broken"] = {"agent_id": "agent-broken"}  # missing required fields
    enabled_persistence.write_text(json.dumps(snapshot), encoding="utf-8")

    for name in _COLLECTIONS:
        getattr(store, name).clear()
    assert persistence.load() is True
    assert store.get_agent("agent-good") is not None
    assert store.get_agent("agent-broken") is None


def test_utf8_bom_snapshot_loads(enabled_persistence: Path) -> None:
    store.register_agent(AgentConfig(agent_id="agent-bom", name="BOM Agent", role="observer"))
    persistence.save()
    original = enabled_persistence.read_bytes()
    assert original
    enabled_persistence.write_bytes(b"\xef\xbb\xbf" + original)

    for name in _COLLECTIONS:
        getattr(store, name).clear()
    assert persistence.load() is True
    assert store.get_agent("agent-bom") is not None


def test_disabled_persistence_never_touches_disk(tmp_path: Path) -> None:
    persistence.disable()
    _seed_state()
    assert persistence.save() is False
    assert list(tmp_path.iterdir()) == []


def test_state_survives_http_restart_cycle(tmp_path: Path) -> None:
    """End-to-end: data written through the API is readable after a restart."""
    from fastapi.testclient import TestClient

    from app.main import app as main_app

    settings.state_dir = str(tmp_path)
    persistence.configure(str(tmp_path))
    try:
        client = TestClient(main_app)
        created = client.post(
            "/api/v1/leads",
            json={"name": "Restart Lead", "email": "restart@nexora.test", "status": "qualified"},
        )
        assert created.status_code == 201
        lead_id = created.json()["data"]["id"]

        # "Restart": wipe memory entirely, then rehydrate as a new process would.
        for name in _COLLECTIONS:
            getattr(store, name).clear()
        assert persistence.load() is True

        fetched = client.get(f"/api/v1/leads/{lead_id}")
        assert fetched.status_code == 200
        assert fetched.json()["data"]["email"] == "restart@nexora.test"
    finally:
        persistence.disable()
        settings.state_dir = ""
