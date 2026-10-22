from __future__ import annotations

from fastapi import APIRouter

from app.core.errors import NotFoundError
from app.core.store import get_report, get_report_by_run_id, get_test_run, submit_evaluation
from app.schemas.common import ApiEnvelope
from app.schemas.evaluation import EvaluationSubmission, ReportSummary

router = APIRouter(tags=["evaluations"])


@router.post("/evaluations", status_code=201, response_model=ApiEnvelope[ReportSummary])
async def submit_evaluation_endpoint(payload: EvaluationSubmission) -> ApiEnvelope[ReportSummary]:
    """Submit benchmark evaluation results for an existing test run.

    Validates that the referenced test run exists in the store before generating a report summary.
    """
    if get_test_run(payload.run_id) is None:
        raise NotFoundError(
            f"Test run '{payload.run_id}' was not found. Evaluation cannot be submitted for an unknown run.",
            details={"run_id": payload.run_id},
        )

    report = submit_evaluation(payload)
    return ApiEnvelope(success=True, data=report)


@router.get("/reports/{report_id}", response_model=ApiEnvelope[ReportSummary])
async def get_report_endpoint(report_id: str) -> ApiEnvelope[ReportSummary]:
    """Retrieve an evaluation report summary by report ID."""
    report = get_report(report_id)
    if report is None:
        raise NotFoundError(f"Report '{report_id}' was not found.")
    return ApiEnvelope(success=True, data=report)


@router.get("/reports/runs/{run_id}", response_model=ApiEnvelope[ReportSummary])
async def get_report_by_run_endpoint(run_id: str) -> ApiEnvelope[ReportSummary]:
    """Retrieve an evaluation report summary associated with a specific test run."""
    if get_test_run(run_id) is None:
        raise NotFoundError(f"Test run '{run_id}' was not found.")

    report = get_report_by_run_id(run_id)
    if report is None:
        raise NotFoundError(f"No evaluation report has been generated for test run '{run_id}'.")
    return ApiEnvelope(success=True, data=report)

