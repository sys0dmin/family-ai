"""Public child-safe agent manifests."""

from pydantic import BaseModel


class AgentResponse(BaseModel):
    id: str
    display_name: str
    description: str
    icon: str
    color: str
    greeting: str
    supports_image_upload: bool = False


class AgentListResponse(BaseModel):
    items: list[AgentResponse]
