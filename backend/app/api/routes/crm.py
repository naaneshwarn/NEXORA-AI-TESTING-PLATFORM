from __future__ import annotations

import asyncio
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from app.core.store import (
    create_crm_lead,
    delete_crm_lead,
    get_crm_lead,
    list_crm_leads,
    update_crm_lead,
)
from app.schemas.common import ApiEnvelope
from app.schemas.crm import CRMLeadCreate, CRMLeadResponse

router = APIRouter(tags=["crm"])

# Fault-injection query parameters are shared by the read endpoints below. They
# exist solely to exercise agent resiliency (timeouts, rate limiting and server
# failures) against this synthetic CRM surface, never real infrastructure.
SimulatedLatencyMs = Annotated[
    int | None,
    Query(
        ge=0,
        le=60_000,
        description="Inject a synthetic delay (in milliseconds) before responding.",
    ),
]
InjectError = Annotated[
    int | None,
    Query(
        ge=400,
        le=599,
        description="Simulate an HTTP error status (e.g. 429 rate limit, 500 server error).",
    ),
]


async def _apply_fault_injection(
    simulated_latency_ms: int | None,
    inject_error: int | None,
) -> None:
    """Apply deterministic fault injection for agent resiliency testing.

    Raises immediately when ``inject_error`` is set (matching the reference
    behaviour), otherwise introduces a non-blocking latency so the event loop
    stays free to service concurrent requests.
    """
    if inject_error is not None:
        raise HTTPException(
            status_code=inject_error,
            detail={"message": f"Simulated fault triggered with error code {inject_error}"},
        )

    if simulated_latency_ms:
        await asyncio.sleep(simulated_latency_ms / 1000.0)


@router.post("/leads", status_code=201, response_model=ApiEnvelope[CRMLeadResponse])
async def create_lead_endpoint(payload: CRMLeadCreate) -> ApiEnvelope[CRMLeadResponse]:
    lead_data = payload.model_dump()
    lead = create_crm_lead(lead_data)
    return ApiEnvelope(success=True, data=lead)


@router.get("/leads", response_model=ApiEnvelope[list[CRMLeadResponse]])
async def list_leads_endpoint(
    simulated_latency_ms: SimulatedLatencyMs = None,
    inject_error: InjectError = None,
) -> ApiEnvelope[list[CRMLeadResponse]]:
    await _apply_fault_injection(simulated_latency_ms, inject_error)
    leads = list_crm_leads()
    return ApiEnvelope(success=True, data=leads)


@router.get("/leads/{lead_id}", response_model=ApiEnvelope[CRMLeadResponse])
async def get_lead_endpoint(
    lead_id: str,
    simulated_latency_ms: SimulatedLatencyMs = None,
    inject_error: InjectError = None,
) -> ApiEnvelope[CRMLeadResponse]:
    await _apply_fault_injection(simulated_latency_ms, inject_error)
    lead = get_crm_lead(lead_id)
    if lead is None:
        raise HTTPException(status_code=404, detail={"message": f"Lead '{lead_id}' was not found."})
    return ApiEnvelope(success=True, data=lead)


@router.put("/leads/{lead_id}", response_model=ApiEnvelope[CRMLeadResponse])
async def update_lead_endpoint(lead_id: str, payload: CRMLeadCreate) -> ApiEnvelope[CRMLeadResponse]:
    if get_crm_lead(lead_id) is None:
        raise HTTPException(status_code=404, detail={"message": f"Lead '{lead_id}' was not found."})
    lead_data = payload.model_dump()
    lead = update_crm_lead(lead_id, lead_data)
    return ApiEnvelope(success=True, data=lead)


@router.delete("/leads/{lead_id}", status_code=204)
async def delete_lead_endpoint(lead_id: str):
    if get_crm_lead(lead_id) is None:
        raise HTTPException(status_code=404, detail={"message": f"Lead '{lead_id}' was not found."})
    delete_crm_lead(lead_id)
    return None
