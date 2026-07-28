"""Independent provider ports used by Gateway application services."""

from abc import ABC, abstractmethod

from gateway.app.providers.schemas import (
    ChatRequest,
    ChatResponse,
    SpeechRequest,
    SpeechResponse,
    TranscriptionRequest,
    TranscriptionResponse,
)


class ChatProvider(ABC):
    """Generate one language-model response from an explicit chat context."""

    @abstractmethod
    async def generate_response(self, request: ChatRequest) -> ChatResponse:
        raise NotImplementedError


class SpeechRecognitionProvider(ABC):
    """Convert an audio recording into text and technical confidence data."""

    @abstractmethod
    async def transcribe_audio(
        self,
        request: TranscriptionRequest,
    ) -> TranscriptionResponse:
        raise NotImplementedError


class SpeechSynthesisProvider(ABC):
    """Convert trusted response text into playable audio."""

    @abstractmethod
    async def synthesize_speech(self, request: SpeechRequest) -> SpeechResponse:
        raise NotImplementedError
