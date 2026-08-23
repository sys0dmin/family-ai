"""OpenAI-compatible speech routes and content-free runtime metrics."""

import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import JSONResponse, PlainTextResponse, Response

from family_ai_speech.http_context import SpeechHttpContext
from family_ai_speech.runtime_identity import runtime_identity
from family_ai_speech.schemas import (
    SpeechRuntimeMetricsResponse,
    SynthesisRequest,
    TranscriptionSegmentResponse,
    TranscriptionVerboseResponse,
)
from family_ai_speech.service import LocalSpeechService

logger = logging.getLogger(__name__)

SUPPORTED_AUDIO_TYPES = frozenset(
    {
        "audio/flac",
        "audio/mp4",
        "audio/mpeg",
        "audio/ogg",
        "audio/wav",
        "audio/webm",
        "audio/x-m4a",
        "audio/x-wav",
    }
)


def build_audio_router(context: SpeechHttpContext) -> APIRouter:
    """Build routes whose only runtime dependency is the loaded speech service."""

    router = APIRouter()
    settings = context.settings

    @router.get("/healthz")
    async def health() -> dict[str, str]:
        return {
            "status": "ok",
            "service": "family-ai-speech",
            "stt_model": settings.stt_model,
            "tts_model": settings.tts_model,
        }

    @router.get(
        "/internal/metrics",
        response_model=SpeechRuntimeMetricsResponse,
        dependencies=[Depends(context.authorize)],
    )
    async def runtime_metrics(
        speech_service: LocalSpeechService = Depends(context.service),
    ) -> SpeechRuntimeMetricsResponse:
        return speech_service.metrics_snapshot().model_copy(
            update={"runtime": runtime_identity()}
        )

    @router.post(
        "/v1/audio/transcriptions",
        dependencies=[Depends(context.authorize)],
    )
    async def transcribe(
        file: Annotated[UploadFile, File()],
        model: Annotated[str, Form()],
        language: Annotated[str, Form()] = "ru",
        response_format: Annotated[str, Form()] = "text",
        temperature: Annotated[float, Form()] = 0.0,
        prompt: Annotated[str | None, Form()] = None,
        speech_service: LocalSpeechService = Depends(context.service),
        x_request_id: uuid.UUID | None = Header(default=None, alias="X-Request-ID"),
    ) -> Response:
        del temperature
        if model != settings.stt_model:
            raise HTTPException(status_code=400, detail="Unsupported transcription model")
        if response_format not in {"text", "verbose_json"}:
            raise HTTPException(
                status_code=400,
                detail="Unsupported transcription response format",
            )
        if (file.content_type or "").lower() not in SUPPORTED_AUDIO_TYPES:
            raise HTTPException(status_code=415, detail="Unsupported audio format")

        content = await file.read(settings.max_audio_bytes + 1)
        if not content:
            raise HTTPException(status_code=400, detail="Empty audio file")
        if len(content) > settings.max_audio_bytes:
            raise HTTPException(status_code=413, detail="Audio file is too large")

        try:
            result = await speech_service.transcribe(content, language, prompt)
        except Exception as exc:
            logger.exception(
                "local_transcription_failed",
                extra={"request_id": str(x_request_id) if x_request_id else None},
            )
            raise HTTPException(status_code=502, detail="Local transcription failed") from exc
        headers = {"X-Request-ID": str(x_request_id)} if x_request_id else None
        if response_format == "text":
            return PlainTextResponse(result.text, headers=headers)
        verbose_response = TranscriptionVerboseResponse(
            language=result.language,
            duration=result.duration_seconds,
            text=result.text,
            segments=[
                TranscriptionSegmentResponse(
                    id=segment.id,
                    start=segment.start,
                    end=segment.end,
                    text=segment.text,
                    avg_logprob=segment.avg_logprob,
                    no_speech_prob=segment.no_speech_probability,
                )
                for segment in result.segments
            ],
        )
        return JSONResponse(verbose_response.model_dump(), headers=headers)

    @router.post(
        "/v1/audio/speech",
        response_class=Response,
        dependencies=[Depends(context.authorize)],
    )
    async def synthesize(
        payload: SynthesisRequest,
        speech_service: LocalSpeechService = Depends(context.service),
        x_request_id: uuid.UUID | None = Header(default=None, alias="X-Request-ID"),
    ) -> Response:
        if payload.model != settings.tts_model:
            raise HTTPException(status_code=400, detail="Unsupported speech model")
        text = payload.input.strip()
        if not text:
            raise HTTPException(status_code=400, detail="Speech input is empty")
        if len(text) > settings.max_text_characters:
            raise HTTPException(status_code=413, detail="Speech input is too long")

        try:
            audio = await speech_service.synthesize(text, payload.voice)
        except Exception as exc:
            logger.exception(
                "local_synthesis_failed",
                extra={"request_id": str(x_request_id) if x_request_id else None},
            )
            raise HTTPException(status_code=502, detail="Local synthesis failed") from exc
        return Response(
            content=audio,
            media_type="audio/wav",
            headers={
                "Content-Disposition": 'inline; filename="speech.wav"',
                **({"X-Request-ID": str(x_request_id)} if x_request_id else {}),
            },
        )

    return router
