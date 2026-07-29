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
    supports_spoken_image_question: bool = False
    image_upload_max_bytes: int | None = None


class AgentListResponse(BaseModel):
    items: list[AgentResponse]
