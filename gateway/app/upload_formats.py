"""Validated upload media metadata shared by voice transports."""

from pathlib import Path

AUDIO_EXTENSIONS = {
    "audio/m4a": "m4a",
    "audio/mp4": "mp4",
    "audio/mpeg": "mp3",
    "audio/ogg": "ogg",
    "audio/wav": "wav",
    "audio/webm": "webm",
    "video/webm": "webm",
}


def normalized_content_type(content_type: str | None) -> str:
    """Remove optional codec parameters and normalize case."""

    return (content_type or "").split(";", maxsplit=1)[0].lower()


def safe_audio_filename(filename: str | None, content_type: str) -> str | None:
    """Return a bounded provider filename for a supported audio type."""

    extension = AUDIO_EXTENSIONS.get(content_type)
    if extension is None:
        return None
    original_stem = Path(filename or "recording").stem[:80] or "recording"
    return f"{original_stem}.{extension}"
