"""Workflow runtime services (Rahul / Work Package D).

Launch-grade operational layer for the workflow subsystem.  Everything here is
scoped to Work Package D and additive: no shared schemas or lead-owned store
functions are modified.

Provides:
- :func:`get_logger` — a namespaced structured logger for the workflow package.
- :class:`RunContextStore` — durable, restart-surviving persistence of run
  contexts (the volatile in-memory registry was a demo-only weakness).
- :class:`ConcurrencyLimiter` — a bounded semaphore so bulk run creation cannot
  exhaust the process.
- :class:`WorkflowMetrics` — counters for runs started/finished/failed/etc.,
  exposed for readiness checks.
- :func:`recover_interrupted_runs` — on startup, terminalize runs left in a
  non-terminal state by a previous process crash so they never dangle forever.

The module deliberately uses only the standard library.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

_LOGGER_NAME = "nexora.workflow"
_ROOT_NAME = "nexora"

# --- structured logging ----------------------------------------------------


def configure_logging(level: str = "INFO") -> None:
    """Ensure the ``nexora`` logger tree is configured at most once.

    Safe to call from application startup and from tests repeatedly.  Uses a
    plain stream handler and a compact, greppable format; no secrets are ever
    logged by the workflow subsystem (see the redaction note in service.py).
    """
    root = logging.getLogger(_ROOT_NAME)
    if not root.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(
            logging.Formatter(
                fmt="%(asctime)s %(levelname)s %(name)s %(message)s",
                datefmt="%Y-%m-%dT%H:%M:%S%z",
            )
        )
        root.addHandler(handler)
        root.propagate = False
    try:
        root.setLevel(getattr(logging, level.upper(), logging.INFO))
    except (AttributeError, TypeError):
        root.setLevel(logging.INFO)


def get_logger(suffix: str | None = None) -> logging.Logger:
    """Return a workflow-namespaced logger (``nexora.workflow[.suffix]``)."""
    return logging.getLogger(f"{_LOGGER_NAME}.{suffix}" if suffix else _LOGGER_NAME)


# --- durable run-context persistence --------------------------------------


@dataclass
class RunContextRecord:
    """JSON-serializable run context (mirrors service.RunContext)."""

    run_id: str
    scenario_id: str
    variables: dict[str, Any] = field(default_factory=dict)
    agent_ids: list[str] = field(default_factory=list)
    environment_id: str | None = None
    pass_threshold: float = 70.0
    agent_timeout_seconds: float = 10.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RunContextRecord":
        return cls(
            run_id=str(data["run_id"]),
            scenario_id=str(data["scenario_id"]),
            variables=dict(data.get("variables") or {}),
            agent_ids=list(data.get("agent_ids") or []),
            environment_id=data.get("environment_id"),
            pass_threshold=float(data.get("pass_threshold", 70.0)),
            agent_timeout_seconds=float(data.get("agent_timeout_seconds", 10.0)),
        )


class RunContextStore:
    """Durable run-context registry backed by a JSON file.

    Writes are atomic (temp file + ``os.replace``) so a crash mid-write can
    never corrupt the snapshot.  A process lock serializes mutations inside one
    interpreter; cross-process safety is provided by the atomic replace, which
    is sufficient for the single-instance deployment this platform targets.
    """

    def __init__(self, path: str | os.PathLike[str]) -> None:
        self._path = Path(path)
        self._lock = threading.RLock()
        self._records: dict[str, RunContextRecord] = {}
        self._load()

    @property
    def path(self) -> Path:
        return self._path

    def _load(self) -> None:
        try:
            if not self._path.exists():
                return
            # ``utf-8-sig`` transparently strips a UTF-8 BOM if an external
            # editor or a Windows shell wrote the snapshot; plain UTF-8 files
            # are read identically.  A launch snapshot on disk must survive
            # being touched by operator tooling.
            text = self._path.read_text(encoding="utf-8-sig")
            raw = json.loads(text)
            items = raw.get("contexts", []) if isinstance(raw, dict) else []
            for item in items:
                record = RunContextRecord.from_dict(item)
                self._records[record.run_id] = record
        except (OSError, ValueError, KeyError, TypeError):
            # A corrupt snapshot must never prevent the platform from starting;
            # we log and start from an empty registry.
            get_logger("runtime").warning(
                "run-context snapshot unreadable; starting empty", extra={"path": str(self._path)}
            )
            self._records = {}

    def _flush_locked(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"contexts": [r.to_dict() for r in self._records.values()]}
        tmp = self._path.with_suffix(self._path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        os.replace(tmp, self._path)

    def put(self, record: RunContextRecord) -> None:
        with self._lock:
            self._records[record.run_id] = record
            self._flush_locked()

    def get(self, run_id: str) -> RunContextRecord | None:
        with self._lock:
            return self._records.get(run_id)

    def pop(self, run_id: str) -> RunContextRecord | None:
        with self._lock:
            record = self._records.pop(run_id, None)
            if record is not None:
                self._flush_locked()
            return record

    def all(self) -> list[RunContextRecord]:
        with self._lock:
            return list(self._records.values())

    def __len__(self) -> int:
        with self._lock:
            return len(self._records)


# --- concurrency limiter ---------------------------------------------------


class ConcurrencyLimiter:
    """A re-entrant-safe async semaphore wrapper with observable depth.

    Bound the number of workflow runs executing at once so a burst of run
    creations degrades gracefully instead of exhausting the event loop / store.
    ``limit=None`` means unbounded (useful for tests that want no contention).
    """

    def __init__(self, limit: int | None) -> None:
        self._limit = limit
        self._in_use = 0
        self._lock = threading.Lock()
        import asyncio

        self._sem = asyncio.Semaphore(limit) if limit and limit > 0 else None

    @property
    def limit(self) -> int | None:
        return self._limit

    @property
    def in_use(self) -> int:
        with self._lock:
            return self._in_use

    class _Guard:
        def __init__(self, limiter: "ConcurrencyLimiter") -> None:
            self._limiter = limiter
            self._acquired = False

        async def __aenter__(self) -> None:
            if self._limiter._sem is not None:
                await self._limiter._sem.acquire()
            with self._limiter._lock:
                self._limiter._in_use += 1
            self._acquired = True

        async def __aexit__(self, *exc: object) -> None:
            with self._limiter._lock:
                self._limiter._in_use = max(self._limiter._in_use - 1, 0)
            if self._acquired and self._limiter._sem is not None:
                self._limiter._sem.release()

    def slot(self) -> "ConcurrencyLimiter._Guard":
        return ConcurrencyLimiter._Guard(self)


# --- metrics ---------------------------------------------------------------


@dataclass
class WorkflowMetrics:
    """Process-lifetime counters for workflow execution (readiness/observability)."""

    started: int = 0
    finished: int = 0
    passed: int = 0
    failed: int = 0
    cancelled: int = 0
    rejected: int = 0  # not executed because the run was not queued / not found
    recovered: int = 0  # runs terminalized by startup recovery

    def snapshot(self) -> dict[str, int]:
        return asdict(self)


# --- module singletons -----------------------------------------------------


def resolve_state_path(state_dir: str) -> Path:
    """Resolve the run-context snapshot path from a (possibly relative) dir."""
    base = Path(state_dir)
    if not base.is_absolute():
        base = Path(__file__).resolve().parents[2] / base
    return base / "run_contexts.json"


_limiter: ConcurrencyLimiter | None = None
_metrics = WorkflowMetrics()
_metrics_lock = threading.Lock()


def get_limiter() -> ConcurrencyLimiter:
    global _limiter
    if _limiter is None:
        from app.core.config import settings

        _limiter = ConcurrencyLimiter(settings.workflow_max_concurrent_runs)
    return _limiter


def reset_limiter(limit: int | None) -> None:
    """Test/reconfiguration hook: replace the process limiter."""
    global _limiter
    _limiter = ConcurrencyLimiter(limit)


def get_metrics() -> WorkflowMetrics:
    return _metrics


def incr(field_name: str, amount: int = 1) -> None:
    """Increment a metrics counter by name (thread-safe, unknown names ignored)."""
    with _metrics_lock:
        if hasattr(_metrics, field_name):
            setattr(_metrics, field_name, getattr(_metrics, field_name) + amount)


def reset_metrics() -> None:
    global _metrics
    with _metrics_lock:
        _metrics = WorkflowMetrics()


# --- startup recovery ------------------------------------------------------


def recover_interrupted_runs(*, get_runs, is_terminal, update_state) -> int:
    """Terminalize runs left non-terminal by a previous crash.

    Called on application startup.  ``get_runs`` returns all run records,
    ``is_terminal(state)`` classifies a state, and ``update_state(run_id,
    message)`` performs the failure transition.  Returns the number of runs
    recovered.  Runs stuck in ``queued``/``running`` from a dead process would
    otherwise be un-executable (their context may be gone) or dangle forever.
    """
    recovered = 0
    for run in get_runs():
        state = getattr(run, "state", None)
        run_id = getattr(run, "run_id", None)
        if run_id is None or state is None or is_terminal(state):
            continue
        if state in {"queued", "running"}:
            update_state(run_id, "Interrupted by a process restart; failed safely on startup.")
            recovered += 1
    if recovered:
        incr("recovered", recovered)
        get_logger("runtime").warning("recovered %d interrupted workflow run(s)", recovered)
    return recovered
