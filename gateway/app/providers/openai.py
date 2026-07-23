"""OpenAI-compatible implementation of the AIProvider interface."""

import math
from typing import Any, Literal

from openai import AsyncOpenAI

from gateway.app.audio import finalize_wav_container
from gateway.app.providers.base import AIProvider
from gateway.app.providers.schemas import (
    ChatRequest,
    ChatResponse,
    ProviderTool,
    SpeechRequest,
    SpeechResponse,
    TranscriptionRequest,
    TranscriptionResponse,
)


class OpenAIProvider(AIProvider):
    """Provider using OpenAI-compatible chat, transcription and speech APIs."""

    TTS_CONTENT_TYPES = {
        "mp3": "audio/mpeg",
        "wav": "audio/wav",
    }

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
        resolved_base_url = base_url
        if resolved_base_url is None and "deepseek" in model.lower():
            resolved_base_url = "https://api.deepseek.com/v1"

        self._chat_client = self._create_client(api_key, resolved_base_url)

        resolved_speech_key = speech_api_key or api_key
        resolved_speech_base_url = speech_base_url or resolved_base_url
        self._speech_client = self._create_client(
            resolved_speech_key,
            resolved_speech_base_url,
        )
        self._model = model
        self._stt_model = stt_model
        self._stt_temperature = stt_temperature
        self._stt_initial_prompt = stt_initial_prompt
        self._tts_model = tts_model
        self._tts_voice = tts_voice
        self._tts_response_format = tts_response_format
        self._web_search_tool_type = web_search_tool_type

    @staticmethod
    def _create_client(api_key: str, base_url: str | None) -> AsyncOpenAI:
        if base_url:
            return AsyncOpenAI(api_key=api_key, base_url=base_url)
        return AsyncOpenAI(api_key=api_key)

    async def transcribe_audio(self, request: TranscriptionRequest) -> TranscriptionResponse:
        """Convert speech to text using provider transcription API."""
        parameters: dict[str, Any] = {
            "model": self._stt_model,
            "file": (request.filename, request.audio_content, request.content_type),
            "language": request.language,
            "response_format": "verbose_json",
            "temperature": self._stt_temperature,
        }
        if self._stt_initial_prompt:
            parameters["prompt"] = self._stt_initial_prompt
        response = await self._speech_client.audio.transcriptions.create(
            **parameters,
        )
        if isinstance(response, str):
            return TranscriptionResponse(text=response, raw_response=response)

        segments = self._value(response, "segments", []) or []
        duration_seconds = self._number(self._value(response, "duration"))
        speech_seconds = 0.0
        weighted_log_probability = 0.0
        weighted_no_speech = 0.0
        log_probability_weight = 0.0
        no_speech_weight = 0.0
        for segment in segments:
            start = self._number(self._value(segment, "start"))
            end = self._number(self._value(segment, "end"))
            weight = max(0.001, (end or 0.0) - (start or 0.0))
            speech_seconds += max(0.0, (end or 0.0) - (start or 0.0))
            average_log_probability = self._number(
                self._value(segment, "avg_logprob")
            )
            no_speech_probability = self._number(
                self._value(segment, "no_speech_prob")
            )
            if average_log_probability is not None:
                weighted_log_probability += average_log_probability * weight
                log_probability_weight += weight
            if no_speech_probability is not None:
                weighted_no_speech += no_speech_probability * weight
                no_speech_weight += weight

        confidence = None
        no_speech_probability = None
        if log_probability_weight:
            confidence = max(
                0.0,
                min(1.0, math.exp(weighted_log_probability / log_probability_weight)),
            )
        if no_speech_weight:
            no_speech_probability = max(
                0.0,
                min(1.0, weighted_no_speech / no_speech_weight),
            )
        return TranscriptionResponse(
            text=str(self._value(response, "text", "")),
            duration_ms=round(duration_seconds * 1000) if duration_seconds else None,
            speech_duration_ms=round(speech_seconds * 1000) if segments else None,
            confidence=confidence,
            no_speech_probability=no_speech_probability,
            raw_response=response,
        )

    @staticmethod
    def _value(value: Any, key: str, default: Any = None) -> Any:
        if isinstance(value, dict):
            return value.get(key, default)
        return getattr(value, key, default)

    @staticmethod
    def _number(value: Any) -> float | None:
        if isinstance(value, int | float):
            return float(value)
        return None

    async def generate_response(self, request: ChatRequest) -> ChatResponse:
        """Generate a text response using GPT."""
        messages = [
            {"role": m.role.value, "content": m.content} for m in request.messages
        ]
        parameters: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
        }
        if (
            ProviderTool.WEB_SEARCH in request.tools
            and self._web_search_tool_type == "browser_search"
        ):
            parameters["tools"] = [{"type": "browser_search"}]
        response = await self._chat_client.chat.completions.create(**parameters)
        content = response.choices[0].message.content or ""
        return ChatResponse(content=content, raw_response=response)

    async def synthesize_speech(self, request: SpeechRequest) -> SpeechResponse:
        """Convert text to speech using provider TTS API."""
        response = await self._speech_client.audio.speech.create(
            model=self._tts_model,
            voice=request.voice or self._tts_voice,
            input=request.text,
            response_format=self._tts_response_format,
        )
        audio_content = response.content
        if self._tts_response_format == "wav":
            audio_content = finalize_wav_container(audio_content)
        return SpeechResponse(
            audio_content=audio_content,
            content_type=self.TTS_CONTENT_TYPES[self._tts_response_format],
            raw_response=response,
        )
