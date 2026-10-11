from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from app.schemas.agent import AgentConfig
from app.schemas.environment import SyntheticEnvironment
from app.schemas.events import ExecutionEvent
from app.schemas.evaluation import EvaluationSubmission, ReportSummary
from app.schemas.test_run import RunCreateRequest, RunDetail

AGENTS: dict[str, AgentConfig] = {}
TEST_RUNS: dict[str, RunDetail] = {}
ENVIRONMENTS: dict[str, SyntheticEnvironment] = {}
EVENTS: dict[str, list[ExecutionEvent]] = {}
REPORTS: dict[str, ReportSummary] = {}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def register_agent(agent: AgentConfig) -> AgentConfig:
    agent.created_at = agent.created_at or utc_now()
    AGENTS[agent.agent_id] = agent
    return agent


def get_agent(agent_id: str) -> AgentConfig | None:
    return AGENTS.get(agent_id)


def create_test_run(payload: RunCreateRequest) -> RunDetail:
    run_id = f"run-{uuid4().hex[:8]}"
    now = utc_now()
    run = RunDetail(
        run_id=run_id,
        suite_name=payload.suite_name,
        environment=payload.environment,
        target_agents=list(payload.target_agents),
        created_at=now,
        started_at=now,
        message="Test run queued for execution.",
    )
    TEST_RUNS[run_id] = run
    EVENTS[run_id] = [
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


def get_test_run(run_id: str) -> RunDetail | None:
    return TEST_RUNS.get(run_id)


def cancel_test_run(run_id: str) -> RunDetail:
    run = TEST_RUNS[run_id]
    run.state = "cancelled"
    run.message = "Test run cancelled by user request."
    run.completed_at = utc_now()
    EVENTS.setdefault(run_id, []).append(
        ExecutionEvent(
            event_id=f"event-{uuid4().hex[:8]}",
            run_id=run_id,
            event_type="completed",
            sequence=len(EVENTS[run_id]) + 1,
            message="Test run cancelled.",
            timestamp=utc_now(),
        )
    )
    return run


def get_events_for_run(run_id: str) -> list[ExecutionEvent]:
    return EVENTS.get(run_id, [])


def create_environment(payload: SyntheticEnvironment) -> SyntheticEnvironment:
    now = utc_now()
    payload.created_at = payload.created_at or now
    payload.updated_at = payload.updated_at or now
    ENVIRONMENTS[payload.environment_id] = payload
    return payload


def get_environment(environment_id: str) -> SyntheticEnvironment | None:
    return ENVIRONMENTS.get(environment_id)


def update_environment(env: SyntheticEnvironment) -> SyntheticEnvironment:
    env.updated_at = utc_now()
    ENVIRONMENTS[env.environment_id] = env
    return env


def stop_environment(environment_id: str) -> SyntheticEnvironment:
    env = ENVIRONMENTS[environment_id]
    env.status = "stopped"
    return update_environment(env)


def submit_evaluation(payload: EvaluationSubmission) -> ReportSummary:
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
    REPORTS[report.report_id] = report
    return report


def get_report(report_id: str) -> ReportSummary | None:
    return REPORTS.get(report_id)


class Store:
    get_environment = get_environment
    update_environment = update_environment
    create_environment = create_environment
    stop_environment = stop_environment
    register_agent = register_agent
    get_agent = get_agent
    create_test_run = create_test_run
    get_test_run = get_test_run
    cancel_test_run = cancel_test_run
    get_events_for_run = get_events_for_run
    submit_evaluation = submit_evaluation
    get_report = get_report


store = Store()
