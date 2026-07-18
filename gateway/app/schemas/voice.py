"""Validated contracts for voice output endpoints."""

from pydantic import BaseModel, Field


class SynthesizeTextRequest(BaseModel):
    """Assistant text that should be spoken with the conversation agent's voice."""

    text: str = Field(min_length=1, max_length=8000)
