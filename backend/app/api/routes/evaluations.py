from fastapi import APIRouter, HTTPException

from app.core.store import get_report, submit_evaluation
from app.schemas.common import ApiEnvelope
from app.schemas.evaluation import EvaluationSubmission, ReportSummary

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
