"""Temporary local corpus and low-priority STT calibration benchmark."""

from __future__ import annotations

import asyncio
import json
import logging
import re
import shutil
import time
import uuid
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from pathlib import Path
from statistics import fmean
from typing import Any

from family_ai_speech.schemas import (
    CalibrationConfigurationResult,
    CalibrationPrompt,
    CalibrationStateResponse,
)
from family_ai_speech.service import LocalSpeechService

logger = logging.getLogger(__name__)

_CONFIGURATIONS = tuple(
    (beam_size, vad_filter)
    for vad_filter in (True, False)
    for beam_size in (1, 3, 5)
)


def select_recommended_configuration(
    results: list[CalibrationConfigurationResult],
) -> CalibrationConfigurationResult:
    """Prefer predictable latency when accuracy remains within three points."""

    best_accuracy = max(item.spoken_accuracy_percent for item in results)
    accuracy_floor = best_accuracy - 3.0
    accurate_candidates = [
        item for item in results if item.spoken_accuracy_percent >= accuracy_floor
    ]
    best_silence_rejection = max(
        item.silence_rejection_percent for item in accurate_candidates
    )
    safe_candidates = [
        item
        for item in accurate_candidates
        if item.silence_rejection_percent == best_silence_rejection
    ]
    return min(
        safe_candidates,
        key=lambda item: (
            item.p95_processing_ms,
            item.average_processing_ms,
            item.beam_size,
        ),
    )


class CalibrationConflictError(RuntimeError):
    """Raised when a calibration lifecycle transition is invalid."""


class CalibrationNotFoundError(LookupError):
    """Raised when a session or prompt does not exist."""


class CalibrationManager:
    """Own one explicit calibration session and delete its audio automatically."""

    def __init__(
        self,
        directory: Path,
        expiry_hours: int,
        speech_service: LocalSpeechService,
    ) -> None:
        self._directory = directory
        self._expiry_hours = expiry_hours
        self._speech_service = speech_service
        self._directory.mkdir(parents=True, exist_ok=True)
        self._state_path = self._directory / "state.json"
        self._task: asyncio.Task[None] | None = None
        self._housekeeping_task: asyncio.Task[None] | None = None
        self._state = self._load_state()
        if self._state and self._state["status"] == "running":
            self._state["status"] = "failed"
            self._state["error"] = "Speech Service restarted during calibration"
            self._delete_audio(self._state["id"])
            self._save_state()
        self._expire_if_needed()

    def start_housekeeping(self) -> None:
        """Guarantee expiry cleanup even when no API requests arrive."""
        if self._housekeeping_task is None or self._housekeeping_task.done():
            self._housekeeping_task = asyncio.create_task(self._housekeeping())

    async def close(self) -> None:
        if self._housekeeping_task and not self._housekeeping_task.done():
            self._housekeeping_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._housekeeping_task

    def start(
        self,
        prompts: list[CalibrationPrompt],
        initial_prompt: str,
    ) -> CalibrationStateResponse:
        self._expire_if_needed()
        if self._state and self._state["status"] in {"collecting", "running"}:
            raise CalibrationConflictError("Calibration is already active")
        session_id = str(uuid.uuid4())
        now = datetime.now(UTC)
        session_dir = self._session_dir(session_id)
        session_dir.mkdir(parents=True, exist_ok=False)
        self._state = {
            "id": session_id,
            "status": "collecting",
            "created_at": now.isoformat(),
            "expires_at": (now + timedelta(hours=self._expiry_hours)).isoformat(),
            "prompts": [prompt.model_dump() for prompt in prompts],
            "initial_prompt": initial_prompt,
            "samples": {},
            "collected_prompt_ids": [],
            "current_trial": 0,
            "total_trials": len(prompts) * len(_CONFIGURATIONS),
            "results": [],
            "recommended_beam_size": None,
            "recommended_vad_filter": None,
            "error": None,
        }
        self._save_state()
        return self.current()

    def current(self) -> CalibrationStateResponse:
        self._expire_if_needed()
        if self._state is None:
            raise CalibrationNotFoundError("Calibration does not exist")
        return self._to_response(self._state)

    def add_sample(self, session_id: str, prompt_id: str, audio: bytes) -> None:
        state = self._require_session(session_id, "collecting")
        prompt_ids = {prompt["id"] for prompt in state["prompts"]}
        if prompt_id not in prompt_ids:
            raise CalibrationNotFoundError("Calibration prompt does not exist")
        previous = state["samples"].get(prompt_id)
        if previous:
            (self._session_dir(session_id) / previous).unlink(missing_ok=True)
        filename = f"{uuid.uuid4()}.wav"
        (self._session_dir(session_id) / filename).write_bytes(audio)
        state["samples"][prompt_id] = filename
        state["collected_prompt_ids"] = sorted(state["samples"])
        self._save_state()

    def complete(self, session_id: str) -> CalibrationStateResponse:
        state = self._require_session(session_id, "collecting")
        required = {prompt["id"] for prompt in state["prompts"]}
        if set(state["samples"]) != required:
            raise CalibrationConflictError("Not all calibration samples are collected")
        state["status"] = "running"
        state["current_trial"] = 0
        self._save_state()
        self._task = asyncio.create_task(self._run(session_id))
        return self._to_response(state)

    def cancel(self, session_id: str) -> CalibrationStateResponse:
        state = self._require_session(session_id)
        if self._task and not self._task.done():
            self._task.cancel()
        state["status"] = "cancelled"
        state["error"] = None
        self._delete_audio(session_id)
        state["samples"] = {}
        self._save_state()
        return self._to_response(state)

    async def _run(self, session_id: str) -> None:
        try:
            state = self._require_session(session_id, "running")
            results = []
            for beam_size, vad_filter in _CONFIGURATIONS:
                result = await self._run_configuration(
                    state,
                    beam_size=beam_size,
                    vad_filter=vad_filter,
                )
                results.append(result)
                state["results"] = [item.model_dump() for item in results]
                self._save_state()
            recommended = select_recommended_configuration(results)
            state["recommended_beam_size"] = recommended.beam_size
            state["recommended_vad_filter"] = recommended.vad_filter
            state["status"] = "completed"
        except asyncio.CancelledError:
            return
        except Exception:
            logger.exception(
                "STT calibration benchmark failed",
                extra={"session_id": session_id},
            )
            if self._state and self._state.get("id") == session_id:
                self._state["status"] = "failed"
                self._state["error"] = "Calibration benchmark failed"
        finally:
            if self._state and self._state.get("id") == session_id:
                self._delete_audio(session_id)
                self._state["samples"] = {}
                self._save_state()

    async def _run_configuration(
        self,
        state: dict[str, Any],
        *,
        beam_size: int,
        vad_filter: bool,
    ) -> CalibrationConfigurationResult:
        spoken_errors = 0
        spoken_words = 0
        silence_total = 0
        silence_rejected = 0
        processing_times = []
        confidences = []
        prompts = {prompt["id"]: prompt for prompt in state["prompts"]}
        for prompt_id, filename in state["samples"].items():
            prompt = prompts[prompt_id]
            audio = (self._session_dir(state["id"]) / filename).read_bytes()
            started_at = time.perf_counter()
            transcription = await self._speech_service.benchmark_transcribe(
                audio,
                "ru",
                state["initial_prompt"],
                beam_size=beam_size,
                vad_filter=vad_filter,
            )
            processing_times.append((time.perf_counter() - started_at) * 1000)
            if transcription.confidence is not None:
                confidences.append(transcription.confidence)
            if prompt["kind"] == "silence":
                silence_total += 1
                silence_rejected += not bool(transcription.text.strip())
            else:
                expected = _words(prompt["expected_text"])
                actual = _words(transcription.text)
                spoken_errors += _edit_distance(expected, actual)
                spoken_words += max(1, len(expected))
            state["current_trial"] += 1
            self._save_state()
            await asyncio.sleep(0.05)
        ordered_times = sorted(processing_times)
        p95_index = min(
            len(ordered_times) - 1,
            max(0, round(len(ordered_times) * 0.95) - 1),
        )
        return CalibrationConfigurationResult(
            beam_size=beam_size,
            vad_filter=vad_filter,
            spoken_accuracy_percent=round(
                max(0.0, 1 - spoken_errors / max(1, spoken_words)) * 100,
                1,
            ),
            silence_rejection_percent=round(
                silence_rejected / max(1, silence_total) * 100,
                1,
            ),
            average_processing_ms=round(fmean(processing_times), 1),
            p95_processing_ms=round(ordered_times[p95_index], 1),
            average_confidence=(
                round(fmean(confidences), 4) if confidences else None
            ),
        )

    def _require_session(
        self,
        session_id: str,
        required_status: str | None = None,
    ) -> dict[str, Any]:
        self._expire_if_needed()
        if self._state is None or self._state.get("id") != session_id:
            raise CalibrationNotFoundError("Calibration does not exist")
        if required_status and self._state["status"] != required_status:
            raise CalibrationConflictError("Calibration is not in the required state")
        return self._state

    def _to_response(self, state: dict[str, Any]) -> CalibrationStateResponse:
        return CalibrationStateResponse(
            id=state["id"],
            status=state["status"],
            created_at=state["created_at"],
            expires_at=state["expires_at"],
            prompts_total=len(state["prompts"]),
            samples_collected=len(state.get("collected_prompt_ids", state["samples"])),
            collected_prompt_ids=state.get(
                "collected_prompt_ids",
                sorted(state["samples"]),
            ),
            current_trial=state["current_trial"],
            total_trials=state["total_trials"],
            results=state["results"],
            recommended_beam_size=state["recommended_beam_size"],
            recommended_vad_filter=state["recommended_vad_filter"],
            error=state["error"],
        )

    def _expire_if_needed(self) -> None:
        if not self._state:
            return
        expires_at = datetime.fromisoformat(self._state["expires_at"])
        if datetime.now(UTC) <= expires_at:
            return
        if self._task and not self._task.done():
            self._task.cancel()
        self._delete_audio(self._state["id"])
        self._state["samples"] = {}
        self._state["status"] = "cancelled"
        self._state["error"] = "Calibration expired"
        self._save_state()

    async def _housekeeping(self) -> None:
        while True:
            await asyncio.sleep(60)
            self._expire_if_needed()

    def _session_dir(self, session_id: str) -> Path:
        return self._directory / session_id

    def _delete_audio(self, session_id: str) -> None:
        shutil.rmtree(self._session_dir(session_id), ignore_errors=True)

    def _load_state(self) -> dict[str, Any] | None:
        if not self._state_path.exists():
            return None
        try:
            state = json.loads(self._state_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        return state if isinstance(state, dict) else None

    def _save_state(self) -> None:
        if self._state is None:
            return
        temporary = self._state_path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(self._state, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary.replace(self._state_path)


def _words(text: str) -> list[str]:
    return re.findall(r"[а-яёa-z0-9]+", text.lower())


def _edit_distance(expected: list[str], actual: list[str]) -> int:
    previous = list(range(len(actual) + 1))
    for expected_word in expected:
        current = [previous[0] + 1]
        for index, actual_word in enumerate(actual, start=1):
            current.append(
                min(
                    current[-1] + 1,
                    previous[index] + 1,
                    previous[index - 1] + (expected_word != actual_word),
                )
            )
        previous = current
    return previous[-1]
