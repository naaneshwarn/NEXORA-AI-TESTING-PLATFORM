from __future__ import annotations

"""In-memory data store for NEXORA platform MVP.

NOTE: All records stored here are held in-memory and will be lost when the
backend service restarts. This store provides concurrency-safe access via
threading.RLock and serves as the single source of truth across all API routes.
It can be replaced by persistent database adapters (e.g. PostgreSQL, Redis) in future phases.
"""

from datetime import datetime, timezone
import threading
from typing import Any
from uuid import uuid4

from app.core.errors import BadStateError, ConflictError, NotFoundError
from app.schemas.agent import AgentConfig
from app.schemas.environment import SyntheticEnvironment
from app.schemas.events import ExecutionEvent
from app.schemas.evaluation import EvaluationSubmission, ReportSummary
from app.schemas.test_run import RunCreateRequest, RunDetail


def utc_now() -> datetime:
    """Return the current UTC datetime."""
    return datetime.now(timezone.utc)


class InMemoryStore:
    """Thread-safe in-memory store for agents, test runs, environments, events, and reports."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self.agents: dict[str, AgentConfig] = {}
        self.test_runs: dict[str, RunDetail] = {}
        self.environments: dict[str, SyntheticEnvironment] = {}
        self.events: dict[str, list[ExecutionEvent]] = {}
        self.reports: dict[str, ReportSummary] = {}

    def reset(self) -> None:
        """Clear all in-memory records. Useful for test isolation."""
        with self._lock:
            self.agents.clear()
            self.test_runs.clear()
            self.environments.clear()
            self.events.clear()
            self.reports.clear()

    # --- Agent methods ---
    def register_agent(self, agent: AgentConfig) -> AgentConfig:
        with self._lock:
            if not agent.agent_id:
                agent.agent_id = f"agent-{uuid4().hex[:8]}"
            if agent.agent_id in self.agents:
                raise ConflictError(f"Agent '{agent.agent_id}' already exists.")
            agent.created_at = agent.created_at or utc_now()
            self.agents[agent.agent_id] = agent
            return agent

    def get_agent(self, agent_id: str) -> AgentConfig | None:
        with self._lock:
            return self.agents.get(agent_id)

    def list_agents(self) -> list[AgentConfig]:
        with self._lock:
            return list(self.agents.values())

    def has_agent(self, agent_id: str) -> bool:
        with self._lock:
            return agent_id in self.agents

    # --- Test run methods ---
    def create_test_run(self, payload: RunCreateRequest) -> RunDetail:
        with self._lock:
            run_id = f"run-{uuid4().hex[:8]}"
            now = utc_now()
            run = RunDetail(
                run_id=run_id,
                suite_name=payload.suite_name,
                environment=payload.environment,
                state="queued",
                target_agents=list(payload.target_agents),
                created_at=now,
                started_at=now,
                message="Test run queued for execution.",
            )
            self.test_runs[run_id] = run
            self.events[run_id] = [
                ExecutionEvent(
                    event_id=f"event-{uuid4().hex[:8]}",
                    run_id=run_id,
                    event_type="created",
                    sequence=1,
                    message="Test run created.",
                    timestamp=now,
                )
            ]
            return run

    def get_test_run(self, run_id: str) -> RunDetail | None:
        with self._lock:
            return self.test_runs.get(run_id)

    def list_test_runs(self) -> list[RunDetail]:
        with self._lock:
            return list(self.test_runs.values())

    def cancel_test_run(self, run_id: str) -> RunDetail:
        with self._lock:
            run = self.test_runs.get(run_id)
            if run is None:
                raise NotFoundError(f"Test run '{run_id}' was not found.")

            terminal_states = {"passed", "failed", "cancelled"}
            if run.state in terminal_states:
                raise BadStateError(
                    f"Cannot cancel test run '{run_id}' in terminal state '{run.state}'."
                )

            run.state = "cancelled"
            run.message = "Test run cancelled by user request."
            now = utc_now()
            run.completed_at = now

            self.events.setdefault(run_id, []).append(
                ExecutionEvent(
                    event_id=f"event-{uuid4().hex[:8]}",
                    run_id=run_id,
                    event_type="completed",
                    sequence=len(self.events[run_id]) + 1,
                    message="Test run cancelled.",
                    timestamp=now,
                )
            )
            return run

    def update_run_state(
        self,
        run_id: str,
        state: str,
        message: str | None = None,
    ) -> RunDetail:
        with self._lock:
            run = self.test_runs.get(run_id)
            if run is None:
                raise NotFoundError(f"Test run '{run_id}' was not found.")
            run.state = state  # type: ignore[assignment]
            if message:
                run.message = message
            if state in {"passed", "failed", "cancelled"}:
                run.completed_at = utc_now()
            return run

    # --- Event methods ---
    def add_event(self, run_id: str, event: ExecutionEvent) -> ExecutionEvent:
        with self._lock:
            if run_id not in self.test_runs:
                raise NotFoundError(f"Test run '{run_id}' was not found.")
            event.timestamp = event.timestamp or utc_now()
            self.events.setdefault(run_id, []).append(event)
            return event

    def get_events_for_run(self, run_id: str) -> list[ExecutionEvent]:
        with self._lock:
            return list(self.events.get(run_id, []))

    # --- Environment methods ---
    def create_environment(self, payload: SyntheticEnvironment) -> SyntheticEnvironment:
        with self._lock:
            now = utc_now()
            payload.created_at = payload.created_at or now
            payload.updated_at = payload.updated_at or now
            self.environments[payload.environment_id] = payload
            return payload

    def get_environment(self, environment_id: str) -> SyntheticEnvironment | None:
        with self._lock:
            return self.environments.get(environment_id)

    def list_environments(self) -> list[SyntheticEnvironment]:
        with self._lock:
            return list(self.environments.values())

    def stop_environment(self, environment_id: str) -> SyntheticEnvironment:
        with self._lock:
            env = self.environments.get(environment_id)
            if env is None:
                raise NotFoundError(f"Environment '{environment_id}' was not found.")
            # Safe and idempotent stop
            env.status = "stopped"
            env.updated_at = utc_now()
            return env

    # --- Evaluation & Report methods ---
    def submit_evaluation(self, payload: EvaluationSubmission) -> ReportSummary:
        with self._lock:
            # Validate referenced run_id exists
            if payload.run_id not in self.test_runs:
                raise NotFoundError(
                    f"Test run '{payload.run_id}' was not found. Evaluation cannot be submitted for an unknown run."
                )

            now = utc_now()
            report = ReportSummary(
                report_id=f"report-{uuid4().hex[:8]}",
                run_id=payload.run_id,
                score=payload.score,
                status="generated",
                summary=payload.summary,
                metrics=payload.metrics,
                generated_at=now,
            )
            self.reports[report.report_id] = report
            return report

    def get_report(self, report_id: str) -> ReportSummary | None:
        with self._lock:
            return self.reports.get(report_id)

    def get_report_by_run_id(self, run_id: str) -> ReportSummary | None:
        with self._lock:
            for report in self.reports.values():
                if report.run_id == run_id:
                    return report
            return None


# Module-level singleton
store = InMemoryStore()

# Global dict aliases for backward compatibility
AGENTS = store.agents
TEST_RUNS = store.test_runs
ENVIRONMENTS = store.environments
EVENTS = store.events
REPORTS = store.reports


# Module-level functional facade for convenience
def register_agent(agent: AgentConfig) -> AgentConfig:
    return store.register_agent(agent)


def get_agent(agent_id: str) -> AgentConfig | None:
    return store.get_agent(agent_id)


def list_agents() -> list[AgentConfig]:
    return store.list_agents()


def create_test_run(payload: RunCreateRequest) -> RunDetail:
    return store.create_test_run(payload)


def get_test_run(run_id: str) -> RunDetail | None:
    return store.get_test_run(run_id)


def list_test_runs() -> list[RunDetail]:
    return store.list_test_runs()


def cancel_test_run(run_id: str) -> RunDetail:
    return store.cancel_test_run(run_id)


def get_events_for_run(run_id: str) -> list[ExecutionEvent]:
    return store.get_events_for_run(run_id)


def record_execution_event(run_id: str, event: ExecutionEvent) -> ExecutionEvent:
    events = EVENTS.setdefault(run_id, [])
    events.append(event)
    return event


def record_tool_trace(run_id: str, trace_data: dict) -> dict:
    """Append a tool-call trace for a run, stamping it with a UTC timestamp."""
    trace = {**trace_data, "run_id": run_id, "timestamp": utc_now().isoformat()}
    TOOL_TRACES.setdefault(run_id, []).append(trace)
    return trace


def get_traces_for_run(run_id: str) -> list[dict]:
    return TOOL_TRACES.get(run_id, [])


def create_environment(payload: SyntheticEnvironment) -> SyntheticEnvironment:
    return store.create_environment(payload)


def get_environment(environment_id: str) -> SyntheticEnvironment | None:
    return store.get_environment(environment_id)


def list_environments() -> list[SyntheticEnvironment]:
    return store.list_environments()


def update_environment(env: SyntheticEnvironment) -> SyntheticEnvironment:
    env.updated_at = utc_now()
    ENVIRONMENTS[env.environment_id] = env
    return env


def stop_environment(environment_id: str) -> SyntheticEnvironment:
    return store.stop_environment(environment_id)


def submit_evaluation(payload: EvaluationSubmission) -> ReportSummary:
    return store.submit_evaluation(payload)


def get_report(report_id: str) -> ReportSummary | None:
    return store.get_report(report_id)


def get_report_by_run_id(run_id: str) -> ReportSummary | None:
    return store.get_report_by_run_id(run_id)


def reset_store() -> None:
    store.reset()

