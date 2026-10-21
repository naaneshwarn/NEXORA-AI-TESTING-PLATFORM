"""Tests for the workflow runtime/launch layer (Rahul / Work Package D).

Covers the operational surface added for launch: durable run-context
persistence, concurrency limiting, metrics, readiness reporting, structured
logging, and startup recovery of interrupted runs.  Deterministic, no network,
no credentials, no Docker.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

from app.core.store import (
    TEST_RUNS,
    create_test_run,
    get_test_run,
    update_test_run_state,
)
from app.schemas.test_run import RunCreateRequest, ScenarioConfig
from app.workflow import runtime
from app.workflow.service import (
    RunContext,
    build_run_context,
    get_run_context,
    recover_startup_runs,
    register_run_context,
    release_run_context,
    workflow_readiness,
)


def _payload(scenario: str = "crm-read-customer-summary") -> RunCreateRequest:
    return RunCreateRequest(
        suite_name="runtime-suite",
        scenario=ScenarioConfig(name=scenario, variables={}),
        config={},
        target_agents=[],
    )


# --- structured logging ----------------------------------------------------


def test_configure_logging_is_idempotent_and_namespaced() -> None:
    runtime.configure_logging("DEBUG")
    runtime.configure_logging("DEBUG")  # must not add duplicate handlers
    root = logging.getLogger("nexora")
    assert len(root.handlers) == 1
    assert root.level == logging.DEBUG
    logger = runtime.get_logger("service")
    assert logger.name == "nexora.workflow.service"
    assert logging.getLogger("nexora.workflow").name == "nexora.workflow"


# --- durable run-context persistence --------------------------------------


def test_run_context_store_survives_reload(tmp_path: Path) -> None:
    path = tmp_path / "run_contexts.json"
    store = runtime.RunContextStore(path)
    record = runtime.RunContextRecord(
        run_id="run-1", scenario_id="crm-read-customer-summary", pass_threshold=80.0
    )
    store.put(record)

    # A brand-new instance (simulating a process restart) sees the record.
    reloaded = runtime.RunContextStore(path)
    got = reloaded.get("run-1")
    assert got is not None
    assert got.scenario_id == "crm-read-customer-summary"
    assert got.pass_threshold == 80.0


def test_run_context_store_pop_removes_and_persists(tmp_path: Path) -> None:
    path = tmp_path / "run_contexts.json"
    store = runtime.RunContextStore(path)
    store.put(runtime.RunContextRecord(run_id="run-x", scenario_id="s"))
    removed = store.pop("run-x")
    assert removed is not None and removed.run_id == "run-x"
    assert runtime.RunContextStore(path).get("run-x") is None


def test_run_context_store_is_atomic_and_recovers_from_corruption(tmp_path: Path) -> None:
    path = tmp_path / "run_contexts.json"
    path.write_text("{ this is not valid json", encoding="utf-8")
    # Unreadable snapshot must not raise; it starts empty.
    store = runtime.RunContextStore(path)
    assert len(store) == 0
    store.put(runtime.RunContextRecord(run_id="run-y", scenario_id="s"))
    assert json.loads(path.read_text(encoding="utf-8"))["contexts"][0]["run_id"] == "run-y"


def test_run_context_store_tolerates_utf8_bom(tmp_path: Path) -> None:
    """A snapshot written by a Windows shell carries a BOM; it must still load."""
    path = tmp_path / "run_contexts.json"
    payload = {"contexts": [{"run_id": "run-bom", "scenario_id": "s"}]}
    path.write_bytes(b"\xef\xbb\xbf" + json.dumps(payload).encode("utf-8"))
    store = runtime.RunContextStore(path)
    got = store.get("run-bom")
    assert got is not None and got.scenario_id == "s"


def test_run_context_store_ignores_unexpected_top_level_shape(tmp_path: Path) -> None:
    path = tmp_path / "run_contexts.json"
    path.write_text(json.dumps(["not", "a", "dict"]), encoding="utf-8")
    store = runtime.RunContextStore(path)
    assert len(store) == 0


def test_register_and_get_run_context_round_trip() -> None:
    payload = _payload()
    run = create_test_run(payload)
    context = build_run_context(run.run_id, payload)
    assert context is not None
    register_run_context(context)
    try:
        fetched = get_run_context(run.run_id)
        assert fetched is not None
        assert fetched.scenario_id == "crm-read-customer-summary"
    finally:
        release_run_context(run.run_id)
    assert get_run_context(run.run_id) is None


def test_run_context_durable_fallback_after_cache_clear() -> None:
    """A context registered then evicted from the cache is still recoverable."""
    from app.workflow import service

    payload = _payload()
    run = create_test_run(payload)
    context = build_run_context(run.run_id, payload)
    assert context is not None
    register_run_context(context)
    service.RUN_CONTEXTS.clear()  # simulate cache loss, durable store intact
    fetched = get_run_context(run.run_id)
    assert fetched is not None and fetched.run_id == run.run_id
    release_run_context(run.run_id)


# --- concurrency limiter ---------------------------------------------------


def test_concurrency_limiter_bounds_in_use() -> None:
    limiter = runtime.ConcurrencyLimiter(1)
    seen: list[int] = []

    async def worker() -> None:
        async with limiter.slot():
            seen.append(limiter.in_use)

    async def main() -> None:
        await asyncio.gather(worker(), worker(), worker())

    asyncio.run(main())
    # Never more than one slot in use at a time.
    assert max(seen) == 1
    assert limiter.in_use == 0


def test_concurrency_limiter_unbounded_when_none() -> None:
    limiter = runtime.ConcurrencyLimiter(None)
    seen: list[int] = []

    async def worker() -> None:
        async with limiter.slot():
            seen.append(limiter.in_use)

    async def main() -> None:
        await asyncio.gather(worker(), worker())

    asyncio.run(main())
    assert limiter.limit is None
    assert limiter.in_use == 0


# --- metrics ---------------------------------------------------------------


def test_metrics_counters_increment_and_reset() -> None:
    runtime.reset_metrics()
    runtime.incr("started")
    runtime.incr("started")
    runtime.incr("passed")
    snap = runtime.get_metrics().snapshot()
    assert snap["started"] == 2 and snap["passed"] == 1
    runtime.incr("does_not_exist")  # unknown name is ignored, no crash
    assert "does_not_exist" not in runtime.get_metrics().snapshot()
    runtime.reset_metrics()
    assert runtime.get_metrics().snapshot()["started"] == 0


def test_executing_a_run_updates_metrics_and_releases_context() -> None:
    import asyncio as _asyncio

    from app.workflow.service import execute_workflow_run

    runtime.reset_metrics()
    payload = _payload()
    run = create_test_run(payload)
    context = build_run_context(run.run_id, payload)
    assert context is not None
    register_run_context(context)

    result = _asyncio.run(execute_workflow_run(run.run_id))
    assert result["state"] == "passed"
    snap = runtime.get_metrics().snapshot()
    assert snap["started"] == 1 and snap["finished"] == 1 and snap["passed"] == 1
    # Terminal runs release their context.
    assert get_run_context(run.run_id) is None


# --- readiness -------------------------------------------------------------


def test_workflow_readiness_reports_store_and_metrics() -> None:
    runtime.reset_metrics()
    runtime.incr("started")
    ready = workflow_readiness()
    assert ready["ready"] is True
    assert ready["state_store_path"]
    assert ready["metrics"]["started"] == 1


# --- startup recovery ------------------------------------------------------


def test_recover_startup_runs_terminalizes_stuck_runs() -> None:
    payload = _payload()
    running = create_test_run(payload)
    queued = create_test_run(payload)
    done = create_test_run(payload)

    update_test_run_state(running.run_id, "running", "in flight")
    update_test_run_state(done.run_id, "passed", "already done", mark_completed=True)

    recovered = recover_startup_runs()
    assert recovered >= 2
    assert get_test_run(running.run_id).state == "failed"
    assert get_test_run(queued.run_id).state == "failed"
    # Terminal runs are untouched.
    assert get_test_run(done.run_id).state == "passed"
    # The failed runs carry an explanatory message.
    assert "restart" in (get_test_run(running.run_id).message or "").lower()


def test_recovery_is_idempotent() -> None:
    payload = _payload()
    run = create_test_run(payload)
    update_test_run_state(run.run_id, "running", "in flight")
    first = recover_startup_runs()
    second = recover_startup_runs()
    assert first >= 1
    assert second == 0  # nothing left non-terminal
