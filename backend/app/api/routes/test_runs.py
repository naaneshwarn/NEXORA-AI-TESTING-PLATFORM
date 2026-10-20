from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, HTTPException

from app.core.store import (
    cancel_test_run,
    create_test_run,
    get_events_for_run,
    get_test_run,
    get_traces_for_run,
)
from app.schemas.common import ApiEnvelope
from app.schemas.events import ExecutionEvent
from app.schemas.test_run import ExecutionStatus, RunCreateRequest, RunDetail
from app.schemas.tracing import ToolCallTraceResponse
from app.workflow.scenarios import is_registered_scenario, list_scenario_ids
from app.workflow.service import (
    build_run_context,
    execute_workflow_run,
    get_run_context,
    register_run_context,
)

router = APIRouter(tags=["test-runs"])


@router.post("/test-runs", status_code=201, response_model=ApiEnvelope[RunDetail])
async def create_test_run_endpoint(payload: RunCreateRequest, background_tasks: BackgroundTasks) -> ApiEnvelope[RunDetail]:
    """Create a test run and schedule workflow execution for registered scenarios.

    Runs bound to a registered scenario (for example
    ``crm-read-customer-summary``) are executed by the deterministic workflow
    engine in the background; the response still reports ``queued`` per the
    Phase 2 contract.  Unrecognized or missing scenarios keep the legacy
    behavior and stay ``queued`` until explicitly cancelled.
    """
    run = create_test_run(payload)
    context = build_run_context(run.run_id, payload)
    if context is not None and is_registered_scenario(context.scenario_id):
        register_run_context(context)
        background_tasks.add_task(execute_workflow_run, run.run_id)
    return ApiEnvelope(success=True, data=run)


@router.post("/test-runs/{run_id}/execute", response_model=ApiEnvelope[ExecutionStatus])
async def execute_test_run_endpoint(run_id: str) -> ApiEnvelope[ExecutionStatus]:
    """Execute a queued run through the workflow engine (additive endpoint).

    Synchronous and deterministic: the response reflects the terminal run
    state.  Auto-scheduled runs and this endpoint share the same idempotent
    executor, so a run can never execute twice.
    """
    run = get_test_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail={"message": f"Test run '{run_id}' was not found."})
    if run.state != "queued":
        raise HTTPException(
            status_code=409,
            detail={"message": f"Test run '{run_id}' is '{run.state}'; only queued runs can be executed."},
        )

    context = get_run_context(run_id)
    if context is None or not is_registered_scenario(context.scenario_id):
        raise HTTPException(
            status_code=409,
            detail={
                "message": (
                    f"Test run '{run_id}' has no registered scenario bound. "
                    f"Available scenarios: {', '.join(list_scenario_ids())}."
                )
            },
        )

    await execute_workflow_run(run_id)
    run = get_test_run(run_id)
    assert run is not None  # execution always leaves a terminal run record
    status = ExecutionStatus(
        run_id=run_id,
        state=run.state,
        message=run.message,
        updated_at=run.completed_at or run.started_at,
    )
    return ApiEnvelope(success=True, data=status)


@router.get("/test-runs/{run_id}", response_model=ApiEnvelope[RunDetail])
async def get_test_run_endpoint(run_id: str) -> ApiEnvelope[RunDetail]:
    run = get_test_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail={"message": f"Test run '{run_id}' was not found."})
    return ApiEnvelope(success=True, data=run)


@router.post("/test-runs/{run_id}/cancel", response_model=ApiEnvelope[ExecutionStatus])
async def cancel_test_run_endpoint(run_id: str) -> ApiEnvelope[ExecutionStatus]:
    if get_test_run(run_id) is None:
        raise HTTPException(status_code=404, detail={"message": f"Test run '{run_id}' was not found."})

    run = cancel_test_run(run_id)
    status = ExecutionStatus(
        run_id=run_id,
        state=run.state,
        message=run.message,
        updated_at=run.completed_at,
    )
    return ApiEnvelope(success=True, data=status)


@router.get("/test-runs/{run_id}/events", response_model=ApiEnvelope[list[ExecutionEvent]])
async def get_test_run_events_endpoint(run_id: str) -> ApiEnvelope[list[ExecutionEvent]]:
    events = get_events_for_run(run_id)
    if not events:
        raise HTTPException(status_code=404, detail={"message": f"No execution events were found for run '{run_id}'."})
    return ApiEnvelope(success=True, data=events)


@router.get("/test-runs/{run_id}/traces", response_model=ApiEnvelope[list[ToolCallTraceResponse]])
async def get_test_run_traces_endpoint(run_id: str) -> ApiEnvelope[list[ToolCallTraceResponse]]:
    traces = get_traces_for_run(run_id)
    if not traces:
        raise HTTPException(status_code=404, detail={"message": f"No tool traces were found for run '{run_id}'."})
    return ApiEnvelope(success=True, data=traces)
