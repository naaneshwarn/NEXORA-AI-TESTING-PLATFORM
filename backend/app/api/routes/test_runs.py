from __future__ import annotations

from fastapi import APIRouter

from app.core.errors import BadStateError, NotFoundError, ValidationError
from app.core.store import (
    cancel_test_run,
    create_test_run,
    get_events_for_run,
    get_test_run,
    list_test_runs,
    store,
)
from app.schemas.common import ApiEnvelope
from app.schemas.events import ExecutionEvent
from app.schemas.test_run import ExecutionStatus, RunCreateRequest, RunDetail
from app.schemas.tracing import ToolCallTraceResponse

router = APIRouter(tags=["test-runs"])


@router.post("/test-runs", status_code=201, response_model=ApiEnvelope[RunDetail])
async def create_test_run_endpoint(payload: RunCreateRequest) -> ApiEnvelope[RunDetail]:
    """Create a new test-run record and initialize its execution lifecycle.

    Validates referenced target agents against the registered agent store unless
    mock execution mode is explicitly enabled.
    """
    allow_mock = payload.config.get("allow_mock", False)
    if not allow_mock and payload.target_agents:
        for agent_id in payload.target_agents:
            if not store.has_agent(agent_id):
                raise NotFoundError(
                    f"Referenced target agent '{agent_id}' does not exist. Register the agent before launching runs.",
                    details={"missing_agent_id": agent_id},
                )

    run = create_test_run(payload)
    return ApiEnvelope(success=True, data=run)


@router.get("/test-runs", response_model=ApiEnvelope[list[RunDetail]])
async def list_test_runs_endpoint() -> ApiEnvelope[list[RunDetail]]:
    """List all recorded test runs."""
    runs = list_test_runs()
    return ApiEnvelope(success=True, data=runs)


@router.get("/test-runs/{run_id}", response_model=ApiEnvelope[RunDetail])
async def get_test_run_endpoint(run_id: str) -> ApiEnvelope[RunDetail]:
    """Retrieve details for a specific test run by ID."""
    run = get_test_run(run_id)
    if run is None:
        raise NotFoundError(f"Test run '{run_id}' was not found.")
    return ApiEnvelope(success=True, data=run)


@router.post("/test-runs/{run_id}/cancel", response_model=ApiEnvelope[ExecutionStatus])
async def cancel_test_run_endpoint(run_id: str) -> ApiEnvelope[ExecutionStatus]:
    """Request cancellation of an active or queued test run.

    Validates that the test run is not already in a terminal state (passed, failed, or cancelled).
    """
    run = cancel_test_run(run_id)
    status_payload = ExecutionStatus(
        run_id=run.run_id,
        state=run.state,
        message=run.message,
        updated_at=run.completed_at,
    )
    return ApiEnvelope(success=True, data=status_payload)


@router.get("/test-runs/{run_id}/events", response_model=ApiEnvelope[list[ExecutionEvent]])
async def get_test_run_events_endpoint(run_id: str) -> ApiEnvelope[list[ExecutionEvent]]:
    """Retrieve execution events and traces for a test run."""
    run = get_test_run(run_id)
    if run is None:
        raise NotFoundError(f"Test run '{run_id}' was not found.")

    events = get_events_for_run(run_id)
    return ApiEnvelope(success=True, data=events)

