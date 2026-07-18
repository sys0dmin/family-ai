"""Provider-independent agent domain values."""

from dataclasses import dataclass


@dataclass(frozen=True)
class AgentManifest:
    id: str
    display_name: str
    description: str
    icon: str
    color: str
    greeting: str
    tts_voice: str | None
    tools: tuple[str, ...]
    permissions: tuple[str, ...]


@dataclass(frozen=True)
class ActiveAgent(AgentManifest):
    revision_id: str
    version: int
    system_prompt: str
