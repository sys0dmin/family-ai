"""Base interface for AI providers."""

from abc import ABC, abstractmethod
from typing import BinaryIO

from gateway.app.providers.schemas import ChatRequest, ChatResponse, SpeechResponse, TranscriptionResponse


class AIProvider(ABC):
    """Abstract base class for all AI service providers (STT, LLM, TTS)."""

    @abstractmethod
    async def transcribe_audio(self, audio_file: BinaryIO) -> TranscriptionResponse:
        """Convert speech to text (STT)."""
        pass

    @abstractmethod
    async def generate_response(self, request: ChatRequest) -> ChatResponse:
        """Generate a text response from a chat context (LLM)."""
        pass

    @abstractmethod
    async def synthesize_speech(self, text: str) -> SpeechResponse:
        """Convert text to speech (TTS)."""
        pass
