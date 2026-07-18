"""Child-safe agent discovery API."""

from fastapi import APIRouter, Depends

from gateway.app.dependencies import get_agent_service
from gateway.app.schemas.agents import AgentListResponse, AgentResponse
from gateway.app.services.agent_service import AgentService

router = APIRouter(prefix="/v1/agents", tags=["agents"])


@router.get("", response_model=AgentListResponse)
def list_agents(
    service: AgentService = Depends(get_agent_service),
) -> AgentListResponse:
    """Return enabled presentation metadata without exposing system prompts."""

    return AgentListResponse(
        items=[
            AgentResponse(
                id=agent.id,
                display_name=agent.display_name,
                description=agent.description,
                icon=agent.icon,
                color=agent.color,
                greeting=agent.greeting,
            )
            for agent in service.list_available()
        ]
    )
