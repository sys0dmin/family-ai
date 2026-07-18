"""Replaceable provider interface for recognizing music from audio."""

from abc import ABC, abstractmethod

from gateway.app.music.schemas import MusicRecognitionRequest, MusicRecognitionResponse


class MusicRecognitionProvider(ABC):
    @abstractmethod
    async def recognize(
        self,
        request: MusicRecognitionRequest,
    ) -> MusicRecognitionResponse:
        """Return normalized candidates for a recorded melody or song fragment."""

        raise NotImplementedError
