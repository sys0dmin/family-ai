"""Child-safe agent discovery API."""

from fastapi import APIRouter, Depends

from gateway.app.config import Settings, get_settings
from gateway.app.dependencies import get_agent_service
from gateway.app.schemas.agents import AgentListResponse, AgentResponse
from gateway.app.services.agent_service import AgentService

router = APIRouter(prefix="/v1/agents", tags=["agents"])


@router.get("", response_model=AgentListResponse)
def list_agents(
    service: AgentService = Depends(get_agent_service),
    settings: Settings = Depends(get_settings),
) -> AgentListResponse:
    """Return enabled presentation metadata without exposing system prompts."""

    items: list[AgentResponse] = []
    for agent in service.list_available():
        supports_images = "image_understanding" in agent.tools
        items.append(
            AgentResponse(
                id=agent.id,
                display_name=agent.display_name,
                description=agent.description,
                icon=agent.icon,
                color=agent.color,
                greeting=agent.greeting,
                supports_image_upload=supports_images,
                image_upload_max_bytes=(
                    settings.vision_max_image_bytes if supports_images else None
                ),
            )
        )
    return AgentListResponse(items=items)
