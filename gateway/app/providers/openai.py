"""OpenAI implementation of the AIProvider interface."""

from typing import BinaryIO

from openai import AsyncOpenAI

from gateway.app.providers.base import AIProvider
from gateway.app.providers.schemas import (
    ChatMessage,
    ChatRequest,
    ChatResponse,
    ProviderRole,
    SpeechResponse,
    TranscriptionResponse,
)


class OpenAIProvider(AIProvider):
    """Provider using OpenAI's Whisper, GPT, and TTS models."""

    def __init__(self, api_key: str, model: str = "gpt-4o-mini") -> None:
        self._client = AsyncOpenAI(api_key=api_key)
        self._model = model

    async def transcribe_audio(self, audio_file: BinaryIO) -> TranscriptionResponse:
        """Convert speech to text using Whisper."""
        response = await self._client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_file,
            response_format="text",
        )
        # response is a string when response_format="text"
        return TranscriptionResponse(text=str(response), raw_response=response)

    async def generate_response(self, request: ChatRequest) -> ChatResponse:
        """Generate a text response using GPT."""
        messages = [
            {"role": m.role.value, "content": m.content} for m in request.messages
        ]
        response = await self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
        )
        content = response.choices[0].message.content or ""
        return ChatResponse(content=content, raw_response=response)

    async def synthesize_speech(self, text: str) -> SpeechResponse:
        """Convert text to speech using OpenAI TTS."""
        response = await self._client.audio.speech.create(
            model="tts-1",
            voice="alloy",
            input=text,
        )
        # response.content returns the binary audio data
        return SpeechResponse(audio_content=response.content, raw_response=response)
