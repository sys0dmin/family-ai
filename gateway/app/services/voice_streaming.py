"""Provider-neutral sentence streaming for already safe assistant text."""

import asyncio
import base64
import json
import re
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from uuid import UUID, uuid4

from gateway.app.observability.voice_metrics import VoiceMetricsRegistry
from gateway.app.providers.contracts import SpeechSynthesisProvider
from gateway.app.providers.schemas import SpeechRequest

VOICE_STREAM_PROTOCOL = "family-ai-voice/2"
VOICE_RESPONSE_CONTEXT = (
    "Ответ будет озвучен ребёнку. Если Лера не просила подробный рассказ, ответь "
    "двумя-четырьмя короткими предложениями без Markdown и длинных списков. "
    "Самую важную мысль и предупреждение скажи в начале. Не сокращай явно "
    "запрошенную сказку, песню или подробное объяснение."
)
_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?…])\s+")
_CLAUSE_BOUNDARY = re.compile(r"(?<=[,;:—])\s+")


@dataclass
class VoiceTurnTelemetry:
    """Mutable timings for one request without conversation content."""

    metrics: VoiceMetricsRegistry
    mode: str
    recording_duration_ms: int | None
    streamed: bool
    turn_id: UUID = field(default_factory=uuid4)
    started_at: float = field(default_factory=time.perf_counter)
    stt_duration_ms: int | None = None
    vision_duration_ms: int | None = None
    llm_duration_ms: int | None = None
    tts_duration_ms: int | None = None
    stt_confidence: float | None = None
    first_audio_ready_ms: int | None = None
    chunk_count: int | None = None
    _recorded: bool = False

    def record(
        self,
        *,
        status: str,
        error_stage: str | None = None,
        cancelled: bool = False,
    ) -> None:
        if self._recorded:
            return
        self._recorded = True
        self.metrics.record(
            turn_id=str(self.turn_id) if self.streamed else None,
            mode=self.mode,
            status=status,
            error_stage=error_stage,
            recording_duration_ms=self.recording_duration_ms,
            stt_duration_ms=self.stt_duration_ms,
            vision_duration_ms=self.vision_duration_ms,
            llm_duration_ms=self.llm_duration_ms,
            tts_duration_ms=self.tts_duration_ms,
            total_duration_ms=round((time.perf_counter() - self.started_at) * 1000),
            stt_confidence=self.stt_confidence,
            streamed=self.streamed,
            first_audio_ready_ms=self.first_audio_ready_ms,
            chunk_count=self.chunk_count,
            cancelled=cancelled,
        )


@dataclass(frozen=True)
class PreparedVoiceResponse:
    """Safe stored assistant response ready for one or more TTS calls."""

    message_id: UUID
    text: str
    voice: str
    telemetry: VoiceTurnTelemetry
    request_id: UUID


class VoiceStreamRegistry:
    """Track cancellable Gateway tasks without storing child content."""

    def __init__(self) -> None:
        self._tasks: dict[UUID, asyncio.Task[object]] = {}

    def register(self, turn_id: UUID) -> None:
        task = asyncio.current_task()
        if task is not None:
            self._tasks[turn_id] = task

    def unregister(self, turn_id: UUID) -> None:
        self._tasks.pop(turn_id, None)

    def cancel(self, turn_id: UUID) -> bool:
        task = self._tasks.get(turn_id)
        if task is None or task.done():
            return False
        task.cancel()
        return True


voice_stream_registry = VoiceStreamRegistry()


def combine_runtime_context(*contexts: str | None) -> str | None:
    """Join independent system contexts without coupling their producers."""

    combined = "\n\n".join(
        context.strip() for context in contexts if context and context.strip()
    )
    return combined or None


def split_speech_chunks(
    text: str,
    *,
    first_max_characters: int = 180,
    max_characters: int = 320,
) -> tuple[str, ...]:
    """Split safe text on natural boundaries while bounding Silero work units."""

    normalized = re.sub(r"\s+", " ", text).strip()
    if not normalized:
        return ()
    sentences = _SENTENCE_BOUNDARY.split(normalized)
    units: list[str] = []
    for sentence in sentences:
        limit = first_max_characters if not units else max_characters
        units.extend(_split_long_unit(sentence.strip(), limit))

    chunks: list[str] = []
    for unit in units:
        limit = first_max_characters if not chunks else max_characters
        if len(chunks) > 1 and len(chunks[-1]) + 1 + len(unit) <= limit:
            chunks[-1] = f"{chunks[-1]} {unit}"
        else:
            chunks.append(unit)
    return tuple(chunk for chunk in chunks if chunk)


def _split_long_unit(text: str, limit: int) -> list[str]:
    if len(text) <= limit:
        return [text]
    clauses = _CLAUSE_BOUNDARY.split(text)
    pieces: list[str] = []
    current = ""
    for clause in clauses:
        if len(clause) > limit:
            if current:
                pieces.append(current)
                current = ""
            pieces.extend(_split_words(clause, limit))
        elif not current:
            current = clause
        elif len(current) + 1 + len(clause) <= limit:
            current = f"{current} {clause}"
        else:
            pieces.append(current)
            current = clause
    if current:
        pieces.append(current)
    return pieces


def _split_words(text: str, limit: int) -> list[str]:
    pieces: list[str] = []
    current = ""
    for word in text.split():
        if not current:
            current = word
        elif len(current) + 1 + len(word) <= limit:
            current = f"{current} {word}"
        else:
            pieces.append(current)
            current = word
    if current:
        pieces.append(current)
    return pieces


async def stream_speech_events(
    prepared: PreparedVoiceResponse,
    synthesis_provider: SpeechSynthesisProvider,
) -> AsyncIterator[bytes]:
    """Yield independently playable audio parts after full output safety."""

    chunks = split_speech_chunks(prepared.text)
    if not chunks:
        raise ValueError("Assistant response did not contain speakable text")
    prepared.telemetry.chunk_count = len(chunks)
    yield encode_stream_event(
        "message",
        message_id=str(prepared.message_id),
        chunk_count=len(chunks),
    )

    tts_started_at = time.perf_counter()
    try:
        for index, chunk in enumerate(chunks):
            speech = await synthesis_provider.synthesize_speech(
                SpeechRequest(
                    text=chunk,
                    voice=prepared.voice,
                    request_id=prepared.request_id,
                )
            )
            if index == 0:
                prepared.telemetry.first_audio_ready_ms = round(
                    (time.perf_counter() - prepared.telemetry.started_at) * 1000
                )
            yield encode_stream_event(
                "audio",
                index=index,
                content_type=speech.content_type,
                audio_base64=base64.b64encode(speech.audio_content).decode("ascii"),
            )
    finally:
        prepared.telemetry.tts_duration_ms = round(
            (time.perf_counter() - tts_started_at) * 1000
        )
    prepared.telemetry.record(status="success")
    yield encode_stream_event("complete")


def encode_stream_event(event_type: str, **payload: object) -> bytes:
    """Encode one compact, newline-delimited protocol event."""

    return (
        json.dumps(
            {"type": event_type, "protocol": VOICE_STREAM_PROTOCOL, **payload},
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        + b"\n"
    )
