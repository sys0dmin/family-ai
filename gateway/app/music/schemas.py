"""Normalized music recognition values independent from external providers."""

from dataclasses import dataclass


@dataclass(frozen=True)
class MusicRecognitionRequest:
    audio_content: bytes
    filename: str
    content_type: str


@dataclass(frozen=True)
class RecognizedTrack:
    title: str
    artist: str
    album: str | None = None
    score: float | None = None


@dataclass(frozen=True)
class MusicRecognitionResponse:
    matches: tuple[RecognizedTrack, ...]
