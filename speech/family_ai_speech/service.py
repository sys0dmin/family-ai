"""Application orchestration for serialized CPU inference."""

import asyncio

from family_ai_speech.backends import SpeechToTextBackend, TextToSpeechBackend


class LocalSpeechService:
    """Keep model work off the event loop and avoid CPU oversubscription."""

    def __init__(
        self,
        stt: SpeechToTextBackend,
        tts: TextToSpeechBackend,
    ) -> None:
        self._stt = stt
        self._tts = tts
        self._inference_lock = asyncio.Lock()

    async def transcribe(self, audio: bytes, language: str) -> str:
        async with self._inference_lock:
            return await asyncio.to_thread(self._stt.transcribe, audio, language)

    async def synthesize(self, text: str, voice: str | None) -> bytes:
        async with self._inference_lock:
            return await asyncio.to_thread(self._tts.synthesize, text, voice)
