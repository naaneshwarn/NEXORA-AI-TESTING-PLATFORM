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
TOOL_TRACES: dict[str, list[dict]] = {}
WORKFLOW_REPORTS: dict[str, dict] = {}


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


def update_test_run_state(
    run_id: str,
    state: str,
    message: str | None = None,
    mark_started: bool = False,
    mark_completed: bool = False,
) -> RunDetail | None:
    """Transition a run to a new lifecycle state.

    Returns ``None`` for unknown runs.  ``mark_started``/``mark_completed``
    stamp the corresponding timestamps so reports can show real durations.
    """
    run = TEST_RUNS.get(run_id)
    if run is None:
        return None
    run.state = state
    if message is not None:
        run.message = message
    if mark_started:
        run.started_at = utc_now()
    if mark_completed:
        run.completed_at = utc_now()
    return run


def save_workflow_report(report: dict) -> dict:
    """Persist a rich workflow evaluation report keyed by its report ID."""
    WORKFLOW_REPORTS[report["report_id"]] = report
    return report


def get_workflow_report(report_id: str) -> dict | None:
    return WORKFLOW_REPORTS.get(report_id)


def get_workflow_report_for_run(run_id: str) -> dict | None:
    """Return the most recent workflow report generated for a run, if any."""
    for report in reversed(list(WORKFLOW_REPORTS.values())):
        if report.get("run_id") == run_id:
            return report
    return None


# CRM Leads state
CRM_LEADS: dict[str, dict] = {}


def create_crm_lead(lead_data: dict) -> dict:
    from uuid import uuid4
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    lead_id = 'lead-' + uuid4().hex[:8]
    lead = {**lead_data, 'id': lead_id, 'created_at': now, 'updated_at': None}
    CRM_LEADS[lead_id] = lead
    return lead


def get_crm_lead(lead_id: str) -> dict | None:
    return CRM_LEADS.get(lead_id)


def list_crm_leads() -> list[dict]:
    return list(CRM_LEADS.values())


def update_crm_lead(lead_id: str, lead_data: dict) -> dict:
    from datetime import datetime, timezone
    existing = CRM_LEADS[lead_id]
    now = datetime.now(timezone.utc).isoformat()
    updated = {**existing, **lead_data, 'updated_at': now}
    CRM_LEADS[lead_id] = updated
    return updated


def delete_crm_lead(lead_id: str) -> None:
    CRM_LEADS.pop(lead_id, None)


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
    record_execution_event = record_execution_event
    record_tool_trace = record_tool_trace
    get_traces_for_run = get_traces_for_run
    submit_evaluation = submit_evaluation
    get_report = get_report
    update_test_run_state = update_test_run_state
    save_workflow_report = save_workflow_report
    get_workflow_report = get_workflow_report
    get_workflow_report_for_run = get_workflow_report_for_run
    create_crm_lead = create_crm_lead
    get_crm_lead = get_crm_lead
    list_crm_leads = list_crm_leads
    update_crm_lead = update_crm_lead
    delete_crm_lead = delete_crm_lead


store = Store()






