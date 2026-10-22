from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter

from app.core.errors import ConflictError, NotFoundError
from app.core.store import get_agent, list_agents, register_agent, store
from app.schemas.agent import AgentConfig
from app.schemas.common import ApiEnvelope

router = APIRouter(tags=["agents"])


@router.post("/agents", status_code=201, response_model=ApiEnvelope[AgentConfig])
async def register_agent_endpoint(payload: AgentConfig) -> ApiEnvelope[AgentConfig]:
    """Register and configure a target AI agent for testing.

    If an agent_id is not supplied, a unique identifier is generated automatically.
    Private credentials and tokens in configuration are sanitized before being returned.
    """
    assigned_id = payload.agent_id.strip() if payload.agent_id and payload.agent_id.strip() else f"agent-{uuid4().hex[:8]}"

    if store.has_agent(assigned_id):
        raise ConflictError(f"Agent '{assigned_id}' already exists.")

    agent_data = payload.model_copy()
    agent_data.agent_id = assigned_id

    saved = register_agent(agent_data)
    return ApiEnvelope(success=True, data=saved.sanitized())


@router.get("/agents", response_model=ApiEnvelope[list[AgentConfig]])
async def list_agents_endpoint() -> ApiEnvelope[list[AgentConfig]]:
    """List all registered AI agents with sensitive credentials redacted."""
    all_agents = [agent.sanitized() for agent in list_agents()]
    return ApiEnvelope(success=True, data=all_agents)


@router.get("/agents/{agent_id}", response_model=ApiEnvelope[AgentConfig])
async def get_agent_endpoint(agent_id: str) -> ApiEnvelope[AgentConfig]:
    """Retrieve details for a registered AI agent by ID."""
    agent = get_agent(agent_id)
    if agent is None:
        raise NotFoundError(f"Agent '{agent_id}' was not found.")
    return ApiEnvelope(success=True, data=agent.sanitized())

