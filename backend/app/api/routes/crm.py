from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.core.auth import verify_optional_auth
from app.integrations.synthetic_api.faults import (
    InjectError,
    SimulatedLatencyMs,
    apply_fault_injection,
)
from app.integrations.synthetic_api.repository import lead_repository
from app.schemas.common import ApiEnvelope
from app.schemas.crm import CRMLeadCreate, CRMLeadResponse

router = APIRouter(tags=["crm"])


@router.post("/leads", status_code=201, response_model=ApiEnvelope[CRMLeadResponse])
async def create_lead_endpoint(
    payload: CRMLeadCreate,
    auth_info: dict = Depends(verify_optional_auth),
) -> ApiEnvelope[CRMLeadResponse]:
    lead_data = payload.model_dump()
    lead = lead_repository.create(lead_data)
    return ApiEnvelope(success=True, data=lead)


@router.get("/leads", response_model=ApiEnvelope[list[CRMLeadResponse]])
async def list_leads_endpoint(
    simulated_latency_ms: SimulatedLatencyMs = None,
    inject_error: InjectError = None,
    auth_info: dict = Depends(verify_optional_auth),
) -> ApiEnvelope[list[CRMLeadResponse]]:
    await apply_fault_injection(simulated_latency_ms, inject_error)
    leads = lead_repository.list()
    return ApiEnvelope(success=True, data=leads)


@router.get("/leads/{lead_id}", response_model=ApiEnvelope[CRMLeadResponse])
async def get_lead_endpoint(
    lead_id: str,
    simulated_latency_ms: SimulatedLatencyMs = None,
    inject_error: InjectError = None,
    auth_info: dict = Depends(verify_optional_auth),
) -> ApiEnvelope[CRMLeadResponse]:
    await apply_fault_injection(simulated_latency_ms, inject_error)
    lead = lead_repository.get(lead_id)
    if lead is None:
        raise HTTPException(status_code=404, detail={"message": f"Lead '{lead_id}' was not found."})
    return ApiEnvelope(success=True, data=lead)


@router.put("/leads/{lead_id}", response_model=ApiEnvelope[CRMLeadResponse])
async def update_lead_endpoint(
    lead_id: str,
    payload: CRMLeadCreate,
    auth_info: dict = Depends(verify_optional_auth),
) -> ApiEnvelope[CRMLeadResponse]:
    if not lead_repository.exists(lead_id):
        raise HTTPException(status_code=404, detail={"message": f"Lead '{lead_id}' was not found."})
    lead_data = payload.model_dump()
    lead = lead_repository.update(lead_id, lead_data)
    return ApiEnvelope(success=True, data=lead)


@router.delete("/leads/{lead_id}", status_code=204)
async def delete_lead_endpoint(
    lead_id: str,
    auth_info: dict = Depends(verify_optional_auth),
):
    if not lead_repository.exists(lead_id):
        raise HTTPException(status_code=404, detail={"message": f"Lead '{lead_id}' was not found."})
    lead_repository.delete(lead_id)
    return None
