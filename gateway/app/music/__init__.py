"""Provider-independent music recognition contracts."""

from gateway.app.music.base import MusicRecognitionProvider
from gateway.app.music.schemas import (
    MusicRecognitionRequest,
    MusicRecognitionResponse,
    RecognizedTrack,
)

__all__ = [
    "MusicRecognitionProvider",
    "MusicRecognitionRequest",
    "MusicRecognitionResponse",
    "RecognizedTrack",
]
