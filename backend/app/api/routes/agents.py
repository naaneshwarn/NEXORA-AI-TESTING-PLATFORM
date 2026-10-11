from fastapi import APIRouter, HTTPException

from app.core.store import AGENTS, get_agent, register_agent
from app.schemas.agent import AgentConfig
from app.schemas.common import ApiEnvelope

router = APIRouter(tags=["agents"])


@router.post("/agents", status_code=201, response_model=ApiEnvelope[AgentConfig])
async def register_agent_endpoint(payload: AgentConfig) -> ApiEnvelope[AgentConfig]:
    if payload.agent_id in AGENTS:
        raise HTTPException(status_code=409, detail={"message": f"Agent '{payload.agent_id}' already exists."})

    agent = register_agent(payload)
    return ApiEnvelope(success=True, data=agent)


@router.get("/agents/{agent_id}", response_model=ApiEnvelope[AgentConfig])
async def get_agent_endpoint(agent_id: str) -> ApiEnvelope[AgentConfig]:
    agent = get_agent(agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail={"message": f"Agent '{agent_id}' was not found."})
    return ApiEnvelope(success=True, data=agent)
