"""Workflow orchestration service (Rahul / Work Package D).

Coordinates the full lifecycle of an automated test run:

    validate run -> verify environment -> build scenario input
      -> invoke target agent -> collect traces -> evaluate expected vs actual
      -> publish report -> cleanup -> finalize run state

The service is deterministic and needs no LLM credentials or Docker: the
default agent client is the synthetic mock, and environment readiness is a
store lookup (a real Docker-backed environment plugs in behind the same
check once Rajath's provider is merged).

Operational rules enforced here:
- A run executes at most once: only ``queued`` runs may start.
- Cancellation is checked before every node; a cancelled run is never marked
  passed and never receives a success report.
- Agent and environment failures produce a useful failed-run report where
  possible, with evidence references instead of secrets.
- The whole workflow is bounded by :data:`WORKFLOW_TOTAL_TIMEOUT_SECONDS`.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from app.core.config import settings
from app.core.store import (
    get_agent,
    get_environment,
    get_events_for_run,
    get_test_run,
    get_traces_for_run,
    record_execution_event,
    submit_evaluation,
    save_workflow_report,
    update_test_run_state,
)
from app.schemas.environment import SyntheticEnvironment
from app.schemas.events import ExecutionEvent
from app.schemas.evaluation import EvaluationSubmission
from app.schemas.test_run import RunCreateRequest, RunDetail
from app.schemas.workflow_report import CriterionScore, Finding, ReportEvidence, WorkflowReport
from app.workflow.agent_client import AgentTurnOutcome, SyntheticToolAgentClient, WorkflowAgentClient
from app.workflow.evaluator import (
    CRITERION_WEIGHTS,
    DEFAULT_PASS_THRESHOLD,
    EvaluationOutcome,
    InvalidPassThreshold,
    evaluate_run,
    validate_pass_threshold,
)
from app.workflow.graph import WorkflowGraph, WorkflowState
from app.workflow.runtime import (
    RunContextRecord,
    RunContextStore,
    get_logger,
    get_metrics,
    incr,
    recover_interrupted_runs,
    resolve_state_path,
)
from app.workflow.scenarios import (
    ScenarioDefinition,
    ensure_seed_lead,
    get_scenario,
    list_scenario_ids,
)

_log = get_logger("service")

# Launch configuration is settings-driven (env overridable); the module
# constants remain as defaults so nothing that imported them breaks.
WORKFLOW_TOTAL_TIMEOUT_SECONDS = 30.0
DEFAULT_AGENT_TIMEOUT_SECONDS = 10.0


def _total_timeout() -> float:
    return settings.workflow_total_timeout_seconds


def _default_agent_timeout() -> float:
    return settings.workflow_agent_timeout_seconds


@dataclass
class RunContext:
    """Inputs captured when a run is created, consumed at execution time.

    ``RunDetail`` intentionally stays within the shared contract, so the
    scenario binding lives here instead of being added to the shared schema.
    """

    run_id: str
    scenario_id: str
    variables: dict[str, Any] = field(default_factory=dict)
    agent_ids: list[str] = field(default_factory=list)
    environment_id: str | None = None
    pass_threshold: float = DEFAULT_PASS_THRESHOLD
    agent_timeout_seconds: float = DEFAULT_AGENT_TIMEOUT_SECONDS

    def to_record(self) -> RunContextRecord:
        return RunContextRecord(
            run_id=self.run_id,
            scenario_id=self.scenario_id,
            variables=dict(self.variables),
            agent_ids=list(self.agent_ids),
            environment_id=self.environment_id,
            pass_threshold=self.pass_threshold,
            agent_timeout_seconds=self.agent_timeout_seconds,
        )

    @classmethod
    def from_record(cls, record: RunContextRecord) -> "RunContext":
        return cls(
            run_id=record.run_id,
            scenario_id=record.scenario_id,
            variables=dict(record.variables),
            agent_ids=list(record.agent_ids),
            environment_id=record.environment_id,
            pass_threshold=record.pass_threshold,
            agent_timeout_seconds=record.agent_timeout_seconds,
        )


# Durable run-context store: survives a process restart so a queued run keeps
# its scenario binding.  ``RUN_CONTEXTS`` remains a process-local cache kept in
# sync with the store so existing callers (and tests) can read it directly.
_CONTEXT_STORE: RunContextStore | None = None
RUN_CONTEXTS: dict[str, RunContext] = {}


def _context_store() -> RunContextStore:
    global _CONTEXT_STORE
    if _CONTEXT_STORE is None:
        _CONTEXT_STORE = RunContextStore(resolve_state_path(settings.workflow_state_dir))
        # Warm the in-process cache from the durable snapshot.
        for record in _CONTEXT_STORE.all():
            RUN_CONTEXTS[record.run_id] = RunContext.from_record(record)
    return _CONTEXT_STORE


def build_run_context(run_id: str, payload: RunCreateRequest) -> RunContext | None:
    """Derive a run context from the create-run request.

    Returns ``None`` when the request carries no scenario, which keeps
    scenario-less runs in the legacy ``queued`` state.  Invalid overrides
    (bad threshold/timeout) are preserved here and rejected by the validate
    node with a clear finding.
    """
    if payload.suite_name and payload.scenario is not None and payload.scenario.name:
        config = payload.config or {}
        variables = dict(payload.scenario.variables or {})
        context = RunContext(
            run_id=run_id,
            scenario_id=payload.scenario.name,
            variables=variables,
            agent_ids=list(payload.target_agents or []),
            environment_id=str(config["environment_id"]) if config.get("environment_id") else None,
            pass_threshold=settings.workflow_default_pass_threshold,
            agent_timeout_seconds=_default_agent_timeout(),
        )
        if "pass_threshold" in config:
            try:
                context.pass_threshold = validate_pass_threshold(config["pass_threshold"])
            except InvalidPassThreshold:
                # Keep the raw intent so the validate node can fail the run
                # with an explicit, safe error instead of silently coercing.
                context.pass_threshold = float("nan")
        if "agent_timeout_seconds" in config:
            try:
                timeout = float(config["agent_timeout_seconds"])
                context.agent_timeout_seconds = timeout if timeout > 0 else float("nan")
            except (TypeError, ValueError):
                context.agent_timeout_seconds = float("nan")
        return context
    return None


def register_run_context(context: RunContext) -> None:
    """Persist a run context durably and cache it in-process."""
    RUN_CONTEXTS[context.run_id] = context
    _context_store().put(context.to_record())
    _log.info(
        "run context registered",
        extra={"run_id": context.run_id, "scenario_id": context.scenario_id},
    )


def get_run_context(run_id: str) -> RunContext | None:
    cached = RUN_CONTEXTS.get(run_id)
    if cached is not None:
        return cached
    # Fall back to durable storage (for contexts registered before a restart
    # within the same snapshot, or written by another worker).
    record = _context_store().get(run_id)
    if record is None:
        return None
    context = RunContext.from_record(record)
    RUN_CONTEXTS[run_id] = context
    return context


def release_run_context(run_id: str) -> None:
    """Drop a finished run's context from both cache and durable storage."""
    RUN_CONTEXTS.pop(run_id, None)
    _context_store().pop(run_id)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _record_event(run_id: str, event_type: str, message: str, payload: dict[str, Any] | None = None) -> str:
    event = ExecutionEvent(
        event_id=f"event-{uuid4().hex[:8]}",
        run_id=run_id,
        event_type=event_type,
        sequence=len(get_events_for_run(run_id)) + 1,
        message=message,
        payload=payload or {},
        timestamp=_utc_now(),
    )
    record_execution_event(run_id, event)
    return event.event_id


def _failed_outcome(call_id: str, tool_name: str, code: str, message: str) -> AgentTurnOutcome:
    return AgentTurnOutcome(
        call_id=call_id,
        tool_name=tool_name,
        success=False,
        summary=None,
        record=None,
        error={"code": code, "message": message},
        execution_time_ms=0.0,
    )


class WorkflowRunExecutor:
    """Builds and executes the workflow graph for one run."""

    def __init__(self, run_id: str, agent_client: WorkflowAgentClient | None = None) -> None:
        self.run_id = run_id
        # Injectable agent seam: defaults to the deterministic mock, but a
        # live provider implementing the WorkflowAgentClient protocol can be
        # passed in without changing this service (see agent_client.py).
        self.agent_client: WorkflowAgentClient = agent_client or SyntheticToolAgentClient()
        self.context = get_run_context(run_id)
        self.scenario: ScenarioDefinition | None = None
        self.agent_outcome: AgentTurnOutcome | None = None
        self.evaluation: EvaluationOutcome | None = None
        self.service_findings: list[Finding] = []
        self.report_id: str | None = None
        self.summary_report_id: str | None = None

    # -- nodes -------------------------------------------------------------

    def n_validate(self, state: WorkflowState) -> None:
        run = get_test_run(self.run_id)
        if run is None:
            state.error = {"code": "run_not_found", "message": f"Test run '{self.run_id}' was not found."}
            return
        if self.context is None:
            state.error = {
                "code": "missing_run_context",
                "message": "No scenario context is bound to this run; nothing to execute.",
            }
            return
        if run.state != "queued":
            state.error = {
                "code": "run_not_queued",
                "message": f"Run is '{run.state}'; only queued runs can execute.",
            }
            return
        if self.context.pass_threshold != self.context.pass_threshold:  # NaN check
            state.error = {
                "code": "invalid_run_configuration",
                "message": "pass_threshold must be a number between 0 and 100.",
            }
            return
        if self.context.agent_timeout_seconds != self.context.agent_timeout_seconds:  # NaN check
            state.error = {
                "code": "invalid_run_configuration",
                "message": "agent_timeout_seconds must be a positive number.",
            }
            return
        self.scenario = get_scenario(self.context.scenario_id)
        if self.scenario is None:
            state.error = {
                "code": "unknown_scenario",
                "message": (
                    f"Scenario '{self.context.scenario_id}' is not registered. "
                    f"Available scenarios: {', '.join(list_scenario_ids())}."
                ),
            }
            return

        update_test_run_state(self.run_id, "running", "Workflow execution started.", mark_started=True)
        _record_event(
            self.run_id,
            "started",
            f"Workflow started for scenario '{self.scenario.scenario_id}'.",
            {"scenario_id": self.scenario.scenario_id, "pass_threshold": self.context.pass_threshold},
        )

    def n_verify_environment(self, state: WorkflowState) -> None:
        env_id = self.context.environment_id if self.context else None
        if not env_id:
            state.data["environment"] = {"mode": "local", "ready": True}
            _record_event(self.run_id, "heartbeat", "Local mock environment assumed ready.")
            return

        environment: SyntheticEnvironment | None = get_environment(env_id)
        if environment is None:
            state.error = {
                "code": "environment_not_found",
                "message": f"Bound environment '{env_id}' was not found.",
            }
            return
        if environment.status != "ready":
            state.error = {
                "code": "environment_not_ready",
                "message": f"Bound environment '{env_id}' is '{environment.status}', not 'ready'.",
            }
            return

        state.data["environment"] = {"mode": "bound", "environment_id": env_id, "ready": True}
        _record_event(self.run_id, "heartbeat", f"Environment '{env_id}' is ready.")

    def n_build_scenario(self, state: WorkflowState) -> None:
        assert self.scenario is not None and self.context is not None
        variables = dict(self.context.variables)
        lead_id = variables.get("lead_id")
        if not lead_id:
            seed_lead = ensure_seed_lead()
            lead_id = seed_lead["id"]
            variables["lead_id"] = lead_id
            _record_event(
                self.run_id,
                "heartbeat",
                "No lead_id supplied; using the deterministic synthetic seed lead.",
                {"lead_id": lead_id},
            )
        state.data["tool_parameters"] = variables

    async def n_invoke_agent(self, state: WorkflowState) -> None:
        assert self.scenario is not None and self.context is not None
        parameters = state.data.get("tool_parameters", {})
        outcome = await self.agent_client.run_turn(
            run_id=self.run_id,
            tool_name=self.scenario.tool_name,
            parameters=parameters,
            behavior=self.scenario.agent_behavior,
            timeout_seconds=self.context.agent_timeout_seconds,
            summary_fields=self.scenario.summary_fields,
            forbidden_markers=self.scenario.forbidden_markers,
        )
        self.agent_outcome = outcome
        _record_event(
            self.run_id,
            "tool_call",
            f"Agent turn via '{self.scenario.tool_name}' "
            + ("succeeded." if outcome.success else f"failed: {(outcome.error or {}).get('message', 'unknown error')}"),
            {
                "call_id": outcome.call_id,
                "tool_name": outcome.tool_name,
                "success": outcome.success,
                "execution_time_ms": outcome.execution_time_ms,
            },
        )

    def n_evaluate(self, state: WorkflowState) -> None:
        assert self.scenario is not None and self.context is not None

        outcome = self.agent_outcome or _failed_outcome(
            "missing", self.scenario.tool_name, "missing_outcome", "Agent produced no outcome."
        )
        evaluation = evaluate_run(
            self.scenario,
            outcome,
            get_traces_for_run(self.run_id),
            threshold=self.context.pass_threshold,
            run_variables=self.context.variables,
            agent_ids=self.context.agent_ids,
        )
        self.evaluation = evaluation

        # Surface unregistered target agents as a non-blocking warning.
        for agent_id in self.context.agent_ids:
            if get_agent(agent_id) is None:
                self.service_findings.append(
                    Finding(
                        severity="warning",
                        code="agent_not_registered",
                        message=f"Target agent '{agent_id}' is not registered; the deterministic mock was used.",
                    )
                )

        _record_event(
            self.run_id,
            "result",
            evaluation.summary,
            {"score": evaluation.score, "status": evaluation.status},
        )

    def n_publish_report(self, state: WorkflowState) -> None:
        assert self.scenario is not None and self.context is not None
        evaluation = self.evaluation
        assert evaluation is not None

        outcome = self.agent_outcome
        completed = _utc_now()
        findings = list(evaluation.findings) + self.service_findings
        events = get_events_for_run(self.run_id)

        report = self._build_report(
            status=evaluation.status,
            score=evaluation.score,
            summary=evaluation.summary,
            criteria=evaluation.criteria,
            findings=findings,
            tool_call_ids=[outcome.call_id] if outcome else [],
            event_ids=[event.event_id for event in events],
            completed=completed,
            workflow_state="passed" if evaluation.status == "pass" else "failed",
        )
        save_workflow_report(report.model_dump())
        self.report_id = report.report_id

        # Project into the existing ReportSummary contract so the Phase 2
        # GET /reports/{report_id} endpoint serves workflow runs unchanged.
        summary = submit_evaluation(
            EvaluationSubmission(
                run_id=self.run_id,
                score=report.score,
                status="pass" if report.status == "pass" else "fail",
                summary=report.summary,
                metrics={
                    "pass_threshold": report.pass_threshold,
                    **{criterion.criterion: criterion.score for criterion in report.criteria},
                },
                issues=[finding.message for finding in findings if finding.severity == "critical"],
            )
        )
        self.summary_report_id = summary.report_id

    def _publish_failure_report(self, error: dict[str, Any]) -> None:
        """Publish a useful failed-run report for an early workflow failure.

        The Phase 3 guide requires environment (and other post-validation)
        failures to produce a failed report "where possible".  Once the
        validate node has resolved the scenario and context we can always
        build one: zero-scored criteria, a critical finding carrying the
        error code, and evidence references.  Validation-stage errors
        (bad config, unknown scenario) stay report-less because the run was
        never a legitimate evaluation.
        """
        if self.scenario is None or self.context is None or self.report_id is not None:
            return

        message = str(error.get("message", "Workflow failed."))
        error_code = str(error.get("code", "workflow_error"))
        completed = _utc_now()
        events = get_events_for_run(self.run_id)

        criteria = [
            CriterionScore(
                criterion=name,
                weight=weight,
                score=0.0,
                rationale=f"Not evaluated: the workflow stopped before evaluation ({error_code}).",
            )
            for name, weight in CRITERION_WEIGHTS.items()
        ]
        findings = [
            Finding(
                severity="critical",
                code=error_code,
                message=message,
            )
        ]

        report = self._build_report(
            status="fail",
            score=0.0,
            summary=(
                f"Scenario '{self.scenario.scenario_id}' failed before evaluation: {message}"
            ),
            criteria=criteria,
            findings=findings,
            tool_call_ids=[],
            event_ids=[event.event_id for event in events],
            completed=completed,
            workflow_state="failed",
        )
        save_workflow_report(report.model_dump())
        self.report_id = report.report_id

        submit_evaluation(
            EvaluationSubmission(
                run_id=self.run_id,
                score=report.score,
                status="fail",
                summary=report.summary,
                metrics={"pass_threshold": report.pass_threshold},
                issues=[message],
            )
        )

    def _build_report(
        self,
        *,
        status: str,
        score: float,
        summary: str,
        criteria: list[CriterionScore],
        findings: list[Finding],
        tool_call_ids: list[str],
        event_ids: list[str],
        completed: datetime,
        workflow_state: str,
    ) -> WorkflowReport:
        """Assemble the workflow report from its parts (shared by success and failure paths)."""
        assert self.scenario is not None and self.context is not None
        run = get_test_run(self.run_id)
        started = run.started_at if run else None
        duration_ms = 0.0
        if started is not None:
            duration_ms = max((completed - started).total_seconds() * 1000.0, 0.0)

        return WorkflowReport(
            report_id=f"wfreport-{uuid4().hex[:8]}",
            run_id=self.run_id,
            scenario_id=self.scenario.scenario_id,
            status=status,  # type: ignore[arg-type]
            score=score,
            pass_threshold=self.context.pass_threshold,
            summary=summary,
            criteria=criteria,
            findings=findings,
            evidence=ReportEvidence(
                scenario_id=self.scenario.scenario_id,
                agent_ids=list(self.context.agent_ids),
                tool_call_ids=tool_call_ids,
                event_ids=event_ids,
            ),
            workflow_state=workflow_state,
            duration_ms=round(duration_ms, 3),
            generated_at=completed,
        )

    def n_cleanup(self, state: WorkflowState) -> None:
        """Release scenario-owned resources before finalize (guide: explicit cleanup).

        Built-in scenarios never own a temporary environment — they run
        against the shared synthetic store or a caller-bound environment that
        belongs to the platform's lifecycle, not the scenario — so cleanup is
        an explicit, idempotent no-op that records what it inspected.  If a
        future scenario provisions its own resources, this is the single
        place that must release them; the engine routes success, failure,
        and cancellation through here exactly once.
        """
        if state.data.get("cleanup_completed"):
            return
        environment = state.data.get("environment") or {}
        _record_event(
            self.run_id,
            "heartbeat",
            "Workflow cleanup complete: no scenario-owned temporary resources to release.",
            {"environment_mode": environment.get("mode", "unresolved")},
        )
        state.data["cleanup_completed"] = True

    def n_finalize(self, state: WorkflowState) -> None:
        if state.cancelled:
            update_test_run_state(
                self.run_id,
                "cancelled",
                "Test run cancelled during workflow execution.",
                mark_completed=True,
            )
            _record_event(self.run_id, "completed", "Workflow cancelled; run marked cancelled.")
            return

        if state.error is not None:
            message = state.error.get("message", "Workflow failed.")
            # Post-validation failures (environment, agent crash) still get a
            # useful failed report; validation-stage errors stay report-less.
            self._publish_failure_report(state.error)
            update_test_run_state(self.run_id, "failed", message, mark_completed=True)
            _record_event(
                self.run_id,
                "error",
                message,
                {"code": state.error.get("code"), "report_id": self.report_id},
            )
            return

        if self.evaluation is None:
            update_test_run_state(self.run_id, "failed", "Workflow ended without an evaluation.", mark_completed=True)
            _record_event(self.run_id, "error", "Workflow ended without an evaluation.")
            return

        final_state = "passed" if self.evaluation.status == "pass" else "failed"
        update_test_run_state(
            self.run_id,
            final_state,
            self.evaluation.summary,
            mark_completed=True,
        )
        _record_event(
            self.run_id,
            "completed",
            f"Workflow finished: {final_state} (score {self.evaluation.score:.2f}, report {self.report_id}).",
            {"report_id": self.report_id, "score": self.evaluation.score},
        )

    # -- graph wiring ------------------------------------------------------

    def _build_graph(self):
        return (
            WorkflowGraph()
            .add_node("validate", self.n_validate)
            .add_node("verify_environment", self.n_verify_environment)
            .add_node("build_scenario", self.n_build_scenario)
            .add_node("invoke_agent", self.n_invoke_agent)
            .add_node("evaluate", self.n_evaluate)
            .add_node("publish_report", self.n_publish_report)
            .add_node("cleanup", self.n_cleanup)
            .add_node("finalize", self.n_finalize)
            .add_edge("validate", "verify_environment")
            .add_edge("verify_environment", "build_scenario")
            .add_edge("build_scenario", "invoke_agent")
            .add_edge("invoke_agent", "evaluate")
            .add_edge("evaluate", "publish_report")
            .add_edge("publish_report", "cleanup")
            .add_edge("cleanup", "finalize")
            .set_entry("validate")
            .set_cleanup("cleanup")
            .set_finalize("finalize")
            .compile()
        )

    async def execute(self) -> dict[str, Any]:
        run = get_test_run(self.run_id)
        if run is None:
            incr("rejected")
            _log.warning("execute rejected: run not found", extra={"run_id": self.run_id})
            return {"run_id": self.run_id, "executed": False, "reason": "run_not_found"}
        if run.state != "queued":
            incr("rejected")
            _log.info(
                "execute rejected: run not queued",
                extra={"run_id": self.run_id, "state": run.state},
            )
            return {"run_id": self.run_id, "executed": False, "reason": f"run_is_{run.state}"}

        graph = self._build_graph()

        def should_abort() -> bool:
            current = get_test_run(self.run_id)
            return current is not None and current.state == "cancelled"

        state = WorkflowState(
            run_id=self.run_id,
            context={"scenario_id": self.context.scenario_id if self.context else None},
            should_abort=should_abort,
        )

        timeout = _total_timeout()
        incr("started")
        _log.info(
            "workflow run starting",
            extra={"run_id": self.run_id, "timeout_seconds": timeout},
        )

        try:
            await asyncio.wait_for(graph.invoke(state), timeout=timeout)
        except TimeoutError:
            message = f"Workflow exceeded the {timeout:.0f}s total timeout."
            # The graph was cut off before finalize, so publish the failed-run
            # report here too (the report is still possible when the scenario
            # was resolved before the timeout).
            self._publish_failure_report({"code": "workflow_timeout", "message": message})
            update_test_run_state(self.run_id, "failed", message, mark_completed=True)
            _record_event(
                self.run_id,
                "error",
                "Workflow timed out and was failed safely.",
                {"code": "workflow_timeout", "report_id": self.report_id},
            )
            self._finish("failed")
            _log.error("workflow run timed out", extra={"run_id": self.run_id, "timeout_seconds": timeout})
            return {
                "run_id": self.run_id,
                "executed": True,
                "state": "failed",
                "report_id": self.report_id,
            }
        except Exception as exc:  # noqa: BLE001 - background safety net; run must reach a terminal state
            message = f"Workflow crashed safely: {type(exc).__name__}."
            self._publish_failure_report({"code": "workflow_crash", "message": message})
            update_test_run_state(self.run_id, "failed", message, mark_completed=True)
            _record_event(
                self.run_id,
                "error",
                "Workflow crashed and was failed safely.",
                {"code": "workflow_crash", "report_id": self.report_id},
            )
            self._finish("failed")
            _log.exception("workflow run crashed safely", extra={"run_id": self.run_id})
            return {
                "run_id": self.run_id,
                "executed": True,
                "state": "failed",
                "report_id": self.report_id,
            }

        final_run = get_test_run(self.run_id)
        final_state = final_run.state if final_run else "unknown"
        self._finish(final_state)
        _log.info(
            "workflow run finished",
            extra={
                "run_id": self.run_id,
                "state": final_state,
                "report_id": self.report_id,
                "score": self.evaluation.score if self.evaluation else None,
            },
        )
        return {
            "run_id": self.run_id,
            "executed": True,
            "state": final_state,
            "report_id": self.report_id,
            "summary_report_id": self.summary_report_id,
        }

    def _finish(self, state: str) -> None:
        """Record terminal metrics and release the run context.

        Contexts are only needed while a run is queued/executing; once a run is
        terminal the durable snapshot no longer needs to carry it.
        """
        incr("finished")
        if state == "passed":
            incr("passed")
        elif state == "cancelled":
            incr("cancelled")
        else:
            incr("failed")
        release_run_context(self.run_id)


async def execute_workflow_run(run_id: str) -> dict[str, Any]:
    """Execute the workflow for a run exactly once; safe to call repeatedly.

    The executor's ``queued``-state guard is the single source of truth for
    idempotency: a run that already executed (or was cancelled) is terminal
    and can never start again.

    Execution is bounded by the process-wide concurrency limiter so a burst of
    run creations degrades gracefully instead of exhausting the event loop.
    """
    from app.workflow.runtime import get_limiter

    async with get_limiter().slot():
        return await WorkflowRunExecutor(run_id).execute()


def workflow_readiness() -> dict[str, Any]:
    """Readiness snapshot for the workflow subsystem (used by health checks).

    Reports whether the durable context store is reachable and exposes the
    process metrics so operators can confirm the subsystem is live.
    """
    try:
        store = _context_store()
        pending = len(store)
        store_ok = True
        path = str(store.path)
    except Exception:  # noqa: BLE001 - readiness must never raise
        pending = 0
        store_ok = False
        path = None
    metrics = get_metrics().snapshot()
    return {
        "ready": store_ok,
        "state_store_path": path,
        "pending_run_contexts": pending,
        "metrics": metrics,
    }


def recover_startup_runs() -> int:
    """Terminalize runs interrupted by a previous process crash.

    Called from application startup.  Any run left ``queued``/``running`` by a
    dead process is marked failed so it can never dangle in a non-terminal
    state; its stale context is released at the same time.
    """
    from app.core.store import TEST_RUNS

    terminal = {"passed", "failed", "cancelled", "completed"}

    def get_runs():
        return list(TEST_RUNS.values())

    def is_terminal(state: str) -> bool:
        return state in terminal

    def update_state(run_id: str, message: str) -> None:
        update_test_run_state(run_id, "failed", message, mark_completed=True)
        release_run_context(run_id)

    return recover_interrupted_runs(
        get_runs=get_runs, is_terminal=is_terminal, update_state=update_state
    )
