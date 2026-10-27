from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query

from app.core.adapters import UnknownProtocolError
from app.core.auth import verify_optional_auth
from app.integrations.target_agents import TargetAgentNotFoundError
from app.services.agent_execution import RunNotFoundError, execute_agent_tool_call

router = APIRouter(tags=["synthetic-agent"])


@router.post("/synthetic/agent/execute/{protocol}")
async def execute_agent_tool_endpoint(
    protocol: str,
    run_id: str | None = Query(default=None, description="Test run to attach tool-call telemetry to."),
    agent_id: str | None = Query(
        default=None,
        description="Target agent to execute through (registered via POST /agents or the target-agent registry). Defaults to the deterministic mock agent.",
    ),
    payload: dict[str, Any] | None = Body(default=None),
    auth_info: dict = Depends(verify_optional_auth),
) -> dict[str, Any]:
    """Parse, execute and re-format an agent tool call for the given protocol.

    When ``run_id`` is supplied, a redacted telemetry record is persisted and can
    be retrieved from ``GET /test-runs/{run_id}/traces``.  When ``agent_id`` is
    supplied the call executes through that target agent (Work Package A);
    otherwise the shared deterministic mock agent is used.
    """
    try:
        return await execute_agent_tool_call(
            protocol,
            payload or {},
            run_id=run_id,
            agent_id=agent_id,
        )
    except UnknownProtocolError as exc:
        raise HTTPException(status_code=400, detail={"message": str(exc)}) from exc
    except RunNotFoundError as exc:
        raise HTTPException(status_code=404, detail={"message": str(exc)}) from exc
    except TargetAgentNotFoundError as exc:
        raise HTTPException(status_code=404, detail={"message": str(exc)}) from exc
