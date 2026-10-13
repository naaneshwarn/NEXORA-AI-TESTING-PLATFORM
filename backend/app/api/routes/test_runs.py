from __future__ import annotations

from fastapi import APIRouter, HTTPException

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

router = APIRouter(tags=["test-runs"])


@router.post("/test-runs", status_code=201, response_model=ApiEnvelope[RunDetail])
async def create_test_run_endpoint(payload: RunCreateRequest) -> ApiEnvelope[RunDetail]:
    run = create_test_run(payload)
    return ApiEnvelope(success=True, data=run)


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
