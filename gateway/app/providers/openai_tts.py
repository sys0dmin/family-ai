"""OpenAI-compatible speech synthesis provider adapter."""

from typing import Literal

from gateway.app.audio import finalize_wav_container
from gateway.app.providers.contracts import SpeechSynthesisProvider
from gateway.app.providers.openai_client import create_openai_client
from gateway.app.providers.schemas import SpeechRequest, SpeechResponse


class OpenAISpeechSynthesisProvider(SpeechSynthesisProvider):
    """TTS-only adapter for OpenAI-compatible speech APIs."""

    CONTENT_TYPES = {
        "mp3": "audio/mpeg",
        "wav": "audio/wav",
    }

    def __init__(
        self,
        api_key: str,
        model: str = "tts-1",
        base_url: str | None = None,
        default_voice: str = "alloy",
        response_format: Literal["mp3", "wav"] = "mp3",
    ) -> None:
        self._client = create_openai_client(api_key, base_url)
        self._model = model
        self._default_voice = default_voice
        self._response_format = response_format

    async def synthesize_speech(self, request: SpeechRequest) -> SpeechResponse:
        parameters = {
            "model": self._model,
            "voice": request.voice or self._default_voice,
            "input": request.text,
            "response_format": self._response_format,
        }
        if request.request_id:
            parameters["extra_headers"] = {"X-Request-ID": str(request.request_id)}
        response = await self._client.audio.speech.create(**parameters)
        audio_content = response.content
        if self._response_format == "wav":
            audio_content = finalize_wav_container(audio_content)
        return SpeechResponse(
            audio_content=audio_content,
            content_type=self.CONTENT_TYPES[self._response_format],
            raw_response=response,
        )
