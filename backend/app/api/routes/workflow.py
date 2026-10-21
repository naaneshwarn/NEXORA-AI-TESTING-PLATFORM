"""Workflow subsystem readiness and metrics (Rahul / Work Package D).

Additive, workflow-owned observability endpoint.  Kept in its own router so the
shared Phase 2 health contract (``GET /health``) is untouched.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.schemas.common import ApiEnvelope
from app.workflow.service import workflow_readiness

router = APIRouter(prefix="/workflow", tags=["workflow"])


@router.get("/readiness", response_model=ApiEnvelope[dict])
async def workflow_readiness_endpoint() -> ApiEnvelope[dict]:
    """Report workflow subsystem readiness and process-lifetime metrics.

    ``ready`` is true when the durable run-context store is reachable; metrics
    expose runs started/finished/passed/failed/cancelled regardless.
    """
    return ApiEnvelope(success=True, data=workflow_readiness())
