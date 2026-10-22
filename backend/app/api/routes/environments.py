from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter

from app.core.errors import NotFoundError
from app.core.store import create_environment, get_environment, list_environments, stop_environment
from app.schemas.common import ApiEnvelope
from app.schemas.environment import SyntheticEnvironment, SyntheticEnvironmentRequest

router = APIRouter(tags=["environments"])


@router.post("/environments", status_code=201, response_model=ApiEnvelope[SyntheticEnvironment])
async def create_environment_endpoint(payload: SyntheticEnvironmentRequest) -> ApiEnvelope[SyntheticEnvironment]:
    """Request and register a synthetic testing environment.

    Initiates lifecycle tracking with status 'provisioning'. The endpoint remains None
    until confirmed by Rajath's Docker provisioning backend, avoiding false claims
    of running containers during development.
    """
    now = datetime.now(timezone.utc)
    environment = SyntheticEnvironment(
        environment_id=f"env-{uuid4().hex[:8]}",
        environment_type=payload.environment_type,
        label=payload.label,
        status="provisioning",
        endpoint=None,  # Do not fabricate container endpoints before actual Docker confirmation
        metadata={"config": payload.config, "provider": "docker-lifecycle-interface"},
        created_at=now,
        updated_at=now,
    )
    record = create_environment(environment)
    return ApiEnvelope(success=True, data=record)


@router.get("/environments", response_model=ApiEnvelope[list[SyntheticEnvironment]])
async def list_environments_endpoint() -> ApiEnvelope[list[SyntheticEnvironment]]:
    """List all tracked synthetic environments and their current lifecycle statuses."""
    all_envs = list_environments()
    return ApiEnvelope(success=True, data=all_envs)


@router.get("/environments/{environment_id}", response_model=ApiEnvelope[SyntheticEnvironment])
async def get_environment_endpoint(environment_id: str) -> ApiEnvelope[SyntheticEnvironment]:
    """Retrieve metadata and lifecycle state for a specific environment."""
    environment = get_environment(environment_id)
    if environment is None:
        raise NotFoundError(f"Environment '{environment_id}' was not found.")
    return ApiEnvelope(success=True, data=environment)


@router.post("/environments/{environment_id}/stop", response_model=ApiEnvelope[SyntheticEnvironment])
async def stop_environment_endpoint(environment_id: str) -> ApiEnvelope[SyntheticEnvironment]:
    """Safely stop an active synthetic environment.

    This operation is idempotent: stopping an already stopped environment succeeds safely.
    """
    environment = get_environment(environment_id)
    if environment is None:
        raise NotFoundError(f"Environment '{environment_id}' was not found.")

    updated = stop_environment(environment_id)
    return ApiEnvelope(success=True, data=updated)

