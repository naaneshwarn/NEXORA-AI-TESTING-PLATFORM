from fastapi import APIRouter, HTTPException

from app.core.store import get_report, get_test_run, get_workflow_report_for_run, submit_evaluation
from app.schemas.common import ApiEnvelope
from app.schemas.evaluation import EvaluationSubmission, ReportSummary
from app.schemas.workflow_report import WorkflowReport

router = APIRouter(tags=["evaluations"])


@router.post("/evaluations", status_code=201, response_model=ApiEnvelope[ReportSummary])
async def submit_evaluation_endpoint(payload: EvaluationSubmission) -> ApiEnvelope[ReportSummary]:
    report = submit_evaluation(payload)
    return ApiEnvelope(success=True, data=report)


@router.get("/reports/{report_id}", response_model=ApiEnvelope[ReportSummary])
async def get_report_endpoint(report_id: str) -> ApiEnvelope[ReportSummary]:
    report = get_report(report_id)
    if report is None:
        raise HTTPException(status_code=404, detail={"message": f"Report '{report_id}' was not found."})
    return ApiEnvelope(success=True, data=report)


@router.get("/test-runs/{run_id}/report", response_model=ApiEnvelope[WorkflowReport])
async def get_workflow_report_endpoint(run_id: str) -> ApiEnvelope[WorkflowReport]:
    """Retrieve the rich automated evaluation report for a workflow run.

    Additive endpoint: the Phase 2 ``GET /reports/{report_id}`` contract is
    unchanged and still serves the ``ReportSummary`` projection.  Workflow
    reports include criteria scores, findings, evidence references, and the
    pass threshold used — never secret values.
    """
    if get_test_run(run_id) is None:
        raise HTTPException(status_code=404, detail={"message": f"Test run '{run_id}' was not found."})
    report = get_workflow_report_for_run(run_id)
    if report is None:
        raise HTTPException(status_code=404, detail={"message": f"No workflow report was found for run '{run_id}'."})
    return ApiEnvelope(success=True, data=WorkflowReport(**report))
