"""OpenAI-compatible request schemas."""

from typing import Literal

from pydantic import BaseModel, Field


class SynthesisRequest(BaseModel):
    """Subset of the OpenAI speech request used by the Gateway."""

    model: str = Field(min_length=1, max_length=200)
    input: str = Field(min_length=1)
    voice: str = Field(min_length=1, max_length=100)
    response_format: Literal["wav"] = "wav"
