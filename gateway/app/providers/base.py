"""Base interface for AI providers."""

from abc import ABC, abstractmethod

from gateway.app.providers.schemas import (
    ChatRequest,
    ChatResponse,
    SpeechRequest,
    SpeechResponse,
    TranscriptionRequest,
    TranscriptionResponse,
)


class AIProvider(ABC):
    """Abstract base class for all AI service providers (STT, LLM, TTS)."""

    @abstractmethod
    async def transcribe_audio(self, request: TranscriptionRequest) -> TranscriptionResponse:
        """Convert speech to text (STT)."""
        raise NotImplementedError

    @abstractmethod
    async def generate_response(self, request: ChatRequest) -> ChatResponse:
        """Generate a text response from a chat context (LLM)."""
        raise NotImplementedError

    @abstractmethod
    async def synthesize_speech(self, request: SpeechRequest) -> SpeechResponse:
        """Convert text to speech (TTS)."""
        raise NotImplementedError
