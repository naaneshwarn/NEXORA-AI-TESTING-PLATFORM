"""Environment lifecycle routes (Rajath — Work Package B).

Thin HTTP layer over :class:`~app.integrations.environment.manager.EnvironmentManager`.
The Phase 2 contract is preserved exactly:

    POST /environments                  -> 201, status "provisioning"
    GET  /environments/{environment_id} -> 200 / 404
    POST /environments/{environment_id}/stop -> 200 / 404

Additive (documented, non-breaking) endpoints for the Phase 3 lifecycle:

    POST /environments/{environment_id}/reset   -> 200 / 404
    POST /environments/{environment_id}/destroy -> 200 / 404  (idempotent cleanup)

Provisioning is performed **in the background** so the create call can honour
the existing synchronous ``201 + provisioning`` contract while the real Docker
work (create, wait, seed) happens out of band.  When Docker is unavailable the
environment transitions to ``failed`` with a safe message instead of pretending
to be ready — the guide's "never claim a container is running unless verified".

The manager is resolved through :func:`get_manager`, which tests can override to
inject a Docker-free mock provider.  Routes contain no business logic.
"""

from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, HTTPException

from app.core.store import create_environment, get_environment, update_environment
from app.integrations.environment.manager import EnvironmentManager, redact_connection
from app.schemas.common import ApiEnvelope
from app.schemas.environment import SyntheticEnvironment, SyntheticEnvironmentRequest

router = APIRouter(tags=["environments"])

# Process-wide manager.  A test or deployment may replace it with
# ``set_manager(...)`` to inject a provider (e.g. a Docker-free mock).
_MANAGER: EnvironmentManager | None = None


def get_manager() -> EnvironmentManager:
    """Return the active environment manager, creating the default on first use."""
    global _MANAGER
    if _MANAGER is None:
        _MANAGER = EnvironmentManager()
    return _MANAGER


def set_manager(manager: EnvironmentManager | None) -> None:
    """Override the active manager (tests/deployments).  ``None`` resets to default."""
    global _MANAGER
    _MANAGER = manager


def _redacted(environment: SyntheticEnvironment) -> SyntheticEnvironment:
    """Return a copy safe to serialize: credentials stripped from metadata."""
    safe = environment.model_copy(deep=True)
    safe.metadata = redact_connection(safe.metadata)
    return safe


def _provision_in_background(environment_id: str, payload: SyntheticEnvironmentRequest) -> None:
    """Background worker: provision into the caller's environment id, then persist.

    Failures never raise out of the background task; the environment record
    carries the failure so the API stays healthy.  The record's original
    ``created_at`` (set by the route) is preserved so the lifecycle timeline
    stays truthful across the background hop.
    """
    manager = get_manager()
    existing = get_environment(environment_id)
    result = manager.provision(payload, environment_id=environment_id)
    provisioned = result.environment
    if existing is not None and existing.created_at is not None:
        provisioned.created_at = existing.created_at
    update_environment(provisioned)


@router.post("/environments", status_code=201, response_model=ApiEnvelope[SyntheticEnvironment])
async def create_environment_endpoint(
    payload: SyntheticEnvironmentRequest, background_tasks: BackgroundTasks
) -> ApiEnvelope[SyntheticEnvironment]:
    """Create an environment record and schedule real provisioning in the background.

    The response honours the Phase 2 contract (``201``, ``status: provisioning``)
    immediately; the record is later updated to ``ready`` or ``failed``.
    """
    environment = SyntheticEnvironment(
        environment_id=f"env-{uuid4().hex[:8]}",
        environment_type=payload.environment_type,
        label=payload.label,
        status="provisioning",
        endpoint=None,
        metadata={"lifecycle": "provisioning"},
        created_at=None,
        updated_at=None,
    )
    record = create_environment(environment)
    background_tasks.add_task(_provision_in_background, record.environment_id, payload)
    return ApiEnvelope(success=True, data=_redacted(record))


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
        raise HTTPException(status_code=404, detail={"message": f"Environment '{environment_id}' was not found."})
    return ApiEnvelope(success=True, data=_redacted(environment))


@router.post("/environments/{environment_id}/stop", response_model=ApiEnvelope[SyntheticEnvironment])
async def stop_environment_endpoint(environment_id: str) -> ApiEnvelope[SyntheticEnvironment]:
    """Safely stop an active synthetic environment.

    This operation is idempotent: stopping an already stopped environment succeeds safely.
    """
    environment = get_environment(environment_id)
    if environment is None:
        raise HTTPException(status_code=404, detail={"message": f"Environment '{environment_id}' was not found."})
    stopped = get_manager().stop(environment)
    update_environment(stopped)
    return ApiEnvelope(success=True, data=_redacted(stopped))


@router.post("/environments/{environment_id}/ready", response_model=ApiEnvelope[SyntheticEnvironment])
async def mark_environment_ready(environment_id: str) -> ApiEnvelope[SyntheticEnvironment]:
    """Mark an environment ready (compatibility endpoint used by run provisioning).

    Kept for Phase 2 compatibility: run execution binds to an environment and
    requires ``status == "ready"``.  Real provisioning marks itself ready; this
    endpoint lets a test or operator force readiness deterministically.
    """
    environment = get_environment(environment_id)
    if environment is None:
        raise HTTPException(status_code=404, detail={"message": f"Environment '{environment_id}' was not found."})
    environment.status = "ready"
    environment.metadata["lifecycle"] = "ready"
    update_environment(environment)
    return ApiEnvelope(success=True, data=_redacted(environment))


@router.post("/environments/{environment_id}/reset", response_model=ApiEnvelope[SyntheticEnvironment])
async def reset_environment_endpoint(environment_id: str) -> ApiEnvelope[SyntheticEnvironment]:
    """Reset an environment back to its deterministic synthetic seed."""
    environment = get_environment(environment_id)
    if environment is None:
        raise HTTPException(status_code=404, detail={"message": f"Environment '{environment_id}' was not found."})
    reset = get_manager().reset(environment)
    update_environment(reset)
    return ApiEnvelope(success=True, data=_redacted(reset))


@router.post("/environments/{environment_id}/destroy", response_model=ApiEnvelope[SyntheticEnvironment])
async def destroy_environment_endpoint(environment_id: str) -> ApiEnvelope[SyntheticEnvironment]:
    """Destroy all resources owned by the environment.  Idempotent and safe to repeat."""
    environment = get_environment(environment_id)
    if environment is None:
        raise HTTPException(status_code=404, detail={"message": f"Environment '{environment_id}' was not found."})
    destroyed = get_manager().cleanup_environment(environment)
    update_environment(destroyed)
    return ApiEnvelope(success=True, data=_redacted(destroyed))
