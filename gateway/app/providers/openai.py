"""OpenAI-compatible implementation of the AIProvider interface."""

from typing import Literal

from openai import AsyncOpenAI

from gateway.app.providers.base import AIProvider
from gateway.app.providers.schemas import (
    ChatRequest,
    ChatResponse,
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
        tts_model: str = "tts-1",
        tts_voice: str = "alloy",
        tts_response_format: Literal["mp3", "wav"] = "mp3",
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
        self._tts_model = tts_model
        self._tts_voice = tts_voice
        self._tts_response_format = tts_response_format

    @staticmethod
    def _create_client(api_key: str, base_url: str | None) -> AsyncOpenAI:
        if base_url:
            return AsyncOpenAI(api_key=api_key, base_url=base_url)
        return AsyncOpenAI(api_key=api_key)

    async def transcribe_audio(self, request: TranscriptionRequest) -> TranscriptionResponse:
        """Convert speech to text using provider transcription API."""
        response = await self._speech_client.audio.transcriptions.create(
            model=self._stt_model,
            file=(request.filename, request.audio_content, request.content_type),
            language=request.language,
            response_format="text",
            temperature=self._stt_temperature,
        )
        return TranscriptionResponse(text=str(response), raw_response=response)

    async def generate_response(self, request: ChatRequest) -> ChatResponse:
        """Generate a text response using GPT."""
        messages = [
            {"role": m.role.value, "content": m.content} for m in request.messages
        ]
        response = await self._chat_client.chat.completions.create(
            model=self._model,
            messages=messages,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
        )
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
        return SpeechResponse(
            audio_content=response.content,
            content_type=self.TTS_CONTENT_TYPES[self._tts_response_format],
            raw_response=response,
        )
