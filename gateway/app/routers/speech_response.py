"""Shared no-store audio response construction."""

from uuid import UUID

from fastapi.responses import Response

from gateway.app.providers.schemas import SpeechResponse


def speech_response(
    speech: SpeechResponse,
    message_id: UUID | None = None,
) -> Response:
    headers = {"Cache-Control": "no-store"}
    if message_id is not None:
        headers["X-Family-AI-Message-Id"] = str(message_id)
    return Response(
        content=speech.audio_content,
        media_type=speech.content_type,
        headers=headers,
    )
