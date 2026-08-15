"""OpenAI-compatible speech recognition provider adapter."""

import math
from typing import Any

from gateway.app.providers.contracts import SpeechRecognitionProvider
from gateway.app.providers.openai_client import create_openai_client
from gateway.app.providers.schemas import (
    TranscriptionRequest,
    TranscriptionResponse,
)


class OpenAISpeechRecognitionProvider(SpeechRecognitionProvider):
    """STT-only adapter for OpenAI-compatible transcription APIs."""

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o-transcribe",
        base_url: str | None = None,
        temperature: float = 0.0,
        initial_prompt: str | None = None,
    ) -> None:
        self._client = create_openai_client(api_key, base_url)
        self._model = model
        self._temperature = temperature
        self._initial_prompt = initial_prompt

    async def transcribe_audio(
        self,
        request: TranscriptionRequest,
    ) -> TranscriptionResponse:
        parameters: dict[str, Any] = {
            "model": self._model,
            "file": (request.filename, request.audio_content, request.content_type),
            "language": request.language,
            "response_format": "verbose_json",
            "temperature": self._temperature,
        }
        if self._initial_prompt:
            parameters["prompt"] = self._initial_prompt
        if request.request_id:
            parameters["extra_headers"] = {"X-Request-ID": str(request.request_id)}
        response = await self._client.audio.transcriptions.create(**parameters)
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
            average_log_probability = self._number(self._value(segment, "avg_logprob"))
            no_speech_probability = self._number(self._value(segment, "no_speech_prob"))
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
                min(
                    1.0,
                    math.exp(weighted_log_probability / log_probability_weight),
                ),
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
