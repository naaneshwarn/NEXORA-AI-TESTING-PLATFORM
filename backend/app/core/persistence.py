"""Durable JSON snapshot for the core store (WP-A launch hardening).

The platform's core state (agents, test runs, environments, events, traces,
reports, CRM leads) lives in ``app.core.store`` as in-process dictionaries so
every module shares one source of truth.  This module makes that state survive
process restarts by snapshotting it to ``NEXORA_STATE_DIR/store.json`` after
every mutation and re-hydrating it at startup.

Design notes:

* **Opt-out, not opt-in** — persistence is enabled by default (``.state/``
  under the backend directory) so a restarted server keeps its data.  Setting
  ``NEXORA_STATE_DIR=""`` disables it entirely (the test suite does exactly
  that in ``conftest.py`` so tests stay hermetic).
* **Atomic writes** — snapshots are written to a temp file and moved into
  place with :func:`os.replace`, so a crash mid-write can never corrupt the
  last good snapshot.
* **Corruption tolerant** — an unreadable or structurally invalid snapshot is
  logged and skipped; the process starts empty instead of crashing.
* **Thread safe** — every entry point takes a re-entrant lock because store
  mutations arrive from the threadpool, background tasks and the event loop.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from datetime import date, datetime
from pathlib import Path
from typing import Any

from app.core.config import settings

_logger = logging.getLogger("nexora.persistence")

STATE_VERSION = 1
SNAPSHOT_FILENAME = "store.json"

# ``backend/`` — resolved from this file so relative state dirs behave the same
# regardless of the process working directory.
_BACKEND_ROOT = Path(__file__).resolve().parents[2]


def _json_default(value: Any) -> Any:
    """JSON encoder fallback for values the Pydantic layer did not flatten."""
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, (set, frozenset, tuple)):
        return list(value)
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


class StorePersistence:
    """Snapshot coordinator for the shared in-memory store."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._path: Path | None = None

    # -- configuration ----------------------------------------------------
    @property
    def enabled(self) -> bool:
        return self._path is not None

    @property
    def path(self) -> Path | None:
        return self._path

    def configure(self, state_dir: str | Path | None) -> Path | None:
        """Enable persistence under ``state_dir`` (empty/None disables it).

        Returns the resolved snapshot file path, or ``None`` when persistence
        is disabled.
        """
        with self._lock:
            if state_dir is None or not str(state_dir).strip():
                self._path = None
                return None
            base = Path(str(state_dir).strip())
            if not base.is_absolute():
                base = _BACKEND_ROOT / base
            self._path = base / SNAPSHOT_FILENAME
            return self._path

    def disable(self) -> None:
        with self._lock:
            self._path = None

    # -- snapshot I/O -----------------------------------------------------
    def save(self) -> bool:
        """Persist the current store contents. No-op when disabled."""
        with self._lock:
            if self._path is None:
                return False
            from app.core import store  # local import: store imports this module

            payload = {
                "version": STATE_VERSION,
                "saved_at": datetime.now().isoformat(),
                "agents": {k: v.model_dump(mode="json") for k, v in store.AGENTS.items()},
                "test_runs": {k: v.model_dump(mode="json") for k, v in store.TEST_RUNS.items()},
                "environments": {
                    k: v.model_dump(mode="json") for k, v in store.ENVIRONMENTS.items()
                },
                "events": {
                    k: [event.model_dump(mode="json") for event in events]
                    for k, events in store.EVENTS.items()
                },
                "reports": {k: v.model_dump(mode="json") for k, v in store.REPORTS.items()},
                "tool_traces": store.TOOL_TRACES,
                "workflow_reports": store.WORKFLOW_REPORTS,
                "crm_leads": store.CRM_LEADS,
            }

            target = self._path
            tmp = target.parent / f"{target.name}.tmp"
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                tmp.write_text(
                    json.dumps(payload, default=_json_default, ensure_ascii=False),
                    encoding="utf-8",
                )
                os.replace(tmp, target)
                return True
            except OSError as exc:  # pragma: no cover - exercised via injected FS errors
                _logger.warning("unable to persist store snapshot: %s", exc)
                try:
                    tmp.unlink(missing_ok=True)
                except OSError:  # pragma: no cover - best effort cleanup
                    pass
                return False

    def load(self) -> bool:
        """Replace in-memory state with the on-disk snapshot.

        Returns ``True`` when a snapshot was loaded.  A missing, unreadable or
        structurally invalid snapshot returns ``False`` and leaves the store
        empty — corruption must never prevent startup.
        """
        with self._lock:
            if self._path is None or not self._path.exists():
                return False
            from app.core import store

            try:
                raw = self._path.read_text(encoding="utf-8-sig")
                data = json.loads(raw)
            except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                _logger.warning(
                    "store snapshot unreadable; starting empty (%s): %s", self._path, exc
                )
                return False
            if not isinstance(data, dict):
                _logger.warning("store snapshot has unexpected shape; starting empty")
                return False

            try:
                _hydrate_store(store, data)
            except Exception as exc:  # noqa: BLE001 - never block startup on bad data
                _logger.warning(
                    "store snapshot malformed; starting empty (%s): %s", self._path, exc
                )
                _clear_store(store)
                return False
            return True


def _clear_store(store_module: Any) -> None:
    store_module.AGENTS.clear()
    store_module.TEST_RUNS.clear()
    store_module.ENVIRONMENTS.clear()
    store_module.EVENTS.clear()
    store_module.REPORTS.clear()
    store_module.TOOL_TRACES.clear()
    store_module.WORKFLOW_REPORTS.clear()
    store_module.CRM_LEADS.clear()


def _model_map(raw: Any, model_cls: Any) -> dict[str, Any]:
    """Rehydrate ``{id: model_dump}`` into ``{id: model}``, skipping bad rows."""
    if not isinstance(raw, dict):
        return {}
    restored: dict[str, Any] = {}
    for key, value in raw.items():
        try:
            restored[str(key)] = model_cls.model_validate(value)
        except Exception as exc:  # noqa: BLE001 - one bad record must not drop the rest
            _logger.warning("skipping invalid %s record '%s': %s", model_cls.__name__, key, exc)
    return restored


def _hydrate_store(store_module: Any, data: dict[str, Any]) -> None:
    """Rebuild every store collection from a parsed snapshot (atomic)."""
    from app.schemas.agent import AgentConfig
    from app.schemas.environment import SyntheticEnvironment
    from app.schemas.events import ExecutionEvent
    from app.schemas.evaluation import ReportSummary
    from app.schemas.test_run import RunDetail

    # Stage into local containers first so a mid-way failure cannot leave the
    # store half-cleared (load() clears on error, but staging keeps it clean).
    agents = _model_map(data.get("agents"), AgentConfig)
    runs = _model_map(data.get("test_runs"), RunDetail)
    environments = _model_map(data.get("environments"), SyntheticEnvironment)
    reports = _model_map(data.get("reports"), ReportSummary)

    events: dict[str, list[Any]] = {}
    raw_events = data.get("events")
    if isinstance(raw_events, dict):
        for run_id, items in raw_events.items():
            if not isinstance(items, list):
                continue
            restored: list[Any] = []
            for item in items:
                try:
                    restored.append(ExecutionEvent.model_validate(item))
                except Exception as exc:  # noqa: BLE001
                    _logger.warning("skipping invalid event for run '%s': %s", run_id, exc)
            events[str(run_id)] = restored

    def plain_dict(value: Any) -> dict[str, Any]:
        return {str(k): v for k, v in value.items()} if isinstance(value, dict) else {}

    _clear_store(store_module)
    store_module.AGENTS.update(agents)
    store_module.TEST_RUNS.update(runs)
    store_module.ENVIRONMENTS.update(environments)
    store_module.REPORTS.update(reports)
    store_module.EVENTS.update(events)
    store_module.TOOL_TRACES.update(plain_dict(data.get("tool_traces")))
    store_module.WORKFLOW_REPORTS.update(plain_dict(data.get("workflow_reports")))
    store_module.CRM_LEADS.update(plain_dict(data.get("crm_leads")))


# Process-wide singleton used by the store mutators and the app lifespan.
persistence = StorePersistence()


def configure_from_settings() -> Path | None:
    """Configure persistence from ``settings.state_dir`` (startup helper)."""
    return persistence.configure(settings.state_dir)
