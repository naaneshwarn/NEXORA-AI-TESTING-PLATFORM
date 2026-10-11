from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, HTTPException

from app.core.store import create_environment, get_environment, stop_environment
from app.schemas.common import ApiEnvelope
from app.schemas.environment import SyntheticEnvironment, SyntheticEnvironmentRequest

router = APIRouter(tags=["environments"])


@router.post("/environments", status_code=201, response_model=ApiEnvelope[SyntheticEnvironment])
async def create_environment_endpoint(payload: SyntheticEnvironmentRequest) -> ApiEnvelope[SyntheticEnvironment]:
    now = datetime.now(timezone.utc)
    environment = SyntheticEnvironment(
        environment_id=f"env-{uuid4().hex[:8]}",
        environment_type=payload.environment_type,
        label=payload.label,
        status="provisioning",
        endpoint=f"{payload.environment_type}://localhost:{uuid4().hex[:4]}",
        metadata={"config": payload.config},
        created_at=now,
        updated_at=now,
    )
    record = create_environment(environment)
    return ApiEnvelope(success=True, data=record)


@router.get("/environments/{environment_id}", response_model=ApiEnvelope[SyntheticEnvironment])
async def get_environment_endpoint(environment_id: str) -> ApiEnvelope[SyntheticEnvironment]:
    environment = get_environment(environment_id)
    if environment is None:
        raise HTTPException(status_code=404, detail={"message": f"Environment '{environment_id}' was not found."})
    return ApiEnvelope(success=True, data=environment)


@router.post("/environments/{environment_id}/stop", response_model=ApiEnvelope[SyntheticEnvironment])
async def stop_environment_endpoint(environment_id: str) -> ApiEnvelope[SyntheticEnvironment]:
    environment = get_environment(environment_id)
    if environment is None:
        raise HTTPException(status_code=404, detail={"message": f"Environment '{environment_id}' was not found."})

    updated = stop_environment(environment_id)
    return ApiEnvelope(success=True, data=updated)
