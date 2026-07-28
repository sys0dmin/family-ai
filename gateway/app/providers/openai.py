"""Backward-compatible facade over independent OpenAI-compatible adapters."""

from typing import Literal

from gateway.app.providers.base import AIProvider
from gateway.app.providers.openai_chat import OpenAIChatProvider
from gateway.app.providers.openai_stt import OpenAISpeechRecognitionProvider
from gateway.app.providers.openai_tts import OpenAISpeechSynthesisProvider
from gateway.app.providers.schemas import (
    ChatRequest,
    ChatResponse,
    SpeechRequest,
    SpeechResponse,
    TranscriptionRequest,
    TranscriptionResponse,
)


class OpenAIProvider(AIProvider):
    """Legacy composite kept for callers migrating to the narrow contracts."""

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o-mini",
        base_url: str | None = None,
        speech_api_key: str | None = None,
        speech_base_url: str | None = None,
        stt_model: str = "gpt-4o-transcribe",
        stt_temperature: float = 0.0,
        stt_initial_prompt: str | None = None,
        tts_model: str = "tts-1",
        tts_voice: str = "alloy",
        tts_response_format: Literal["mp3", "wav"] = "mp3",
        web_search_tool_type: Literal["disabled", "browser_search"] = "disabled",
    ) -> None:
        resolved_speech_key = speech_api_key or api_key
        resolved_speech_base_url = speech_base_url or base_url
        self.chat = OpenAIChatProvider(
            api_key=api_key,
            model=model,
            base_url=base_url,
            web_search_tool_type=web_search_tool_type,
        )
        self.recognition = OpenAISpeechRecognitionProvider(
            api_key=resolved_speech_key,
            model=stt_model,
            base_url=resolved_speech_base_url,
            temperature=stt_temperature,
            initial_prompt=stt_initial_prompt,
        )
        self.synthesis = OpenAISpeechSynthesisProvider(
            api_key=resolved_speech_key,
            model=tts_model,
            base_url=resolved_speech_base_url,
            default_voice=tts_voice,
            response_format=tts_response_format,
        )

    async def generate_response(self, request: ChatRequest) -> ChatResponse:
        return await self.chat.generate_response(request)

    async def transcribe_audio(
        self,
        request: TranscriptionRequest,
    ) -> TranscriptionResponse:
        return await self.recognition.transcribe_audio(request)

    async def synthesize_speech(self, request: SpeechRequest) -> SpeechResponse:
        return await self.synthesis.synthesize_speech(request)
