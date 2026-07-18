"""Shared schemas for AI providers."""

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class ProviderRole(StrEnum):
    """Role of the message author in a chat completion."""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


@dataclass(frozen=True)
class ChatMessage:
    """A single message in a chat completion request."""
    role: ProviderRole
    content: str


@dataclass(frozen=True)
class ChatRequest:
    """Request for a chat completion (LLM)."""
    messages: list[ChatMessage]
    temperature: float = 0.7
    max_tokens: int | None = None


@dataclass(frozen=True)
class ChatResponse:
    """Response from a chat completion (LLM)."""
    content: str
    raw_response: Any = None


@dataclass(frozen=True)
class TranscriptionRequest:
    """Request for a speech-to-text (STT) transcription."""

    audio_content: bytes
    filename: str
    content_type: str
    language: str = "ru"


@dataclass(frozen=True)
class TranscriptionResponse:
    """Response from a speech-to-text (STT) provider."""
    text: str
    raw_response: Any = None


@dataclass(frozen=True)
class SpeechRequest:
    """Request for a text-to-speech (TTS) synthesis."""

    text: str


@dataclass(frozen=True)
class SpeechResponse:
    """Response from a text-to-speech (TTS) provider."""
    audio_content: bytes
    content_type: str = "audio/mpeg"
    raw_response: Any = None
