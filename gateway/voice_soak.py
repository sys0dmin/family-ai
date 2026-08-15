"""Privacy-safe synthetic load benchmark for the Family AI voice pipeline."""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from difflib import SequenceMatcher
from pathlib import Path
from statistics import fmean
from typing import Any

import httpx

from gateway.app.config import Settings

SYNTHETIC_PHRASES = (
    ("forest_weather", "Сегодня в лесу солнечно и спокойно."),
    ("server_cooling", "Серверу помогают вентиляторы и прохладный воздух."),
    ("space_signal", "Космический корабль передаёт короткий сигнал."),
    ("friendly_raccoon", "Добрый енот аккуратно собирает компьютер."),
)
ALLOWED_CONCURRENCY = {1, 2, 4}


class BenchmarkStageError(RuntimeError):
    """A sanitized failure in one synthetic benchmark stage."""

    def __init__(self, stage: str, reason: str) -> None:
        super().__init__(f"{stage}: {reason}")
        self.stage = stage
        self.reason = reason


@dataclass(frozen=True)
class VoiceSample:
    phrase_id: str
    status: str
    total_ms: int
    llm_ms: int | None = None
    tts_ms: int | None = None
    stt_ms: int | None = None
    stt_provider_ms: int | None = None
    stt_confidence: float | None = None
    transcript_similarity: float | None = None
    audio_bytes: int | None = None
    error_stage: str | None = None
    error_type: str | None = None


@dataclass(frozen=True)
class MetricObservation:
    elapsed_ms: int
    queue_depth: float | None
    active_stage: str | None
    nodes: dict[str, dict[str, float | None]]


class VoiceSoakRunner:
    """Run bounded stateless TTS/STT/LLM work while observing local metrics."""

    def __init__(
        self,
        client: httpx.Client,
        settings: Settings,
        *,
        admin_url: str,
        concurrency_levels: tuple[int, ...] = (1, 2, 4),
        rounds: int = 2,
        monitor_interval_seconds: float = 0.5,
        cooldown_seconds: float = 2.0,
        minimum_similarity: float = 0.65,
        verify_history: bool = True,
    ) -> None:
        if not concurrency_levels or any(
            level not in ALLOWED_CONCURRENCY for level in concurrency_levels
        ):
            raise ValueError("concurrency levels must contain only 1, 2 and 4")
        if not 1 <= rounds <= 10:
            raise ValueError("rounds must be between 1 and 10")
        if not 0.1 <= monitor_interval_seconds <= 10:
            raise ValueError("monitor interval must be between 0.1 and 10 seconds")
        self._client = client
        self._settings = settings
        self._admin_url = admin_url.rstrip("/")
        self._concurrency_levels = concurrency_levels
        self._rounds = rounds
        self._monitor_interval = monitor_interval_seconds
        self._cooldown = max(0.0, cooldown_seconds)
        self._minimum_similarity = minimum_similarity
        self._verify_history = verify_history
        self._auth = (settings.admin_username, settings.admin_password.get_secret_value())
        self._started_at = 0.0
        self._observations: list[MetricObservation] = []
        self._monitor_error_count = 0

    def run(self) -> dict[str, Any]:
        history_before = self._history_total() if self._verify_history else None
        warmup = self._run_sample(*SYNTHETIC_PHRASES[0])
        self._started_at = time.perf_counter()
        stop_monitor = threading.Event()
        monitor = threading.Thread(
            target=self._monitor_loop,
            args=(stop_monitor,),
            name="family-ai-voice-soak-monitor",
            daemon=True,
        )
        monitor.start()
        level_runs: list[tuple[int, int, int, list[VoiceSample]]] = []
        try:
            for level in self._concurrency_levels:
                level_started = self._elapsed_ms()
                samples = self._run_level(level)
                level_finished = self._elapsed_ms()
                level_runs.append((level, level_started, level_finished, samples))
                if self._cooldown:
                    time.sleep(self._cooldown)
        finally:
            stop_monitor.set()
            monitor.join(timeout=max(5.0, self._monitor_interval * 4))

        history_after = self._history_total() if self._verify_history else None
        history_delta = (
            history_after - history_before
            if history_before is not None and history_after is not None
            else None
        )
        levels = [
            self._summarize_level(level, started, finished, samples)
            for level, started, finished, samples in level_runs
        ]
        all_samples = [sample for _level, _start, _end, items in level_runs for sample in items]
        passed = (
            warmup.status == "passed"
            and all(sample.status == "passed" for sample in all_samples)
            and (history_delta in {None, 0})
            and bool(self._observations)
        )
        return {
            "schema": "family-ai-voice-soak/v1",
            "status": "passed" if passed else "failed",
            "generated_at": datetime.now(UTC).isoformat(),
            "privacy": {
                "stateless_admin_studio": True,
                "audio_retained": False,
                "transcripts_retained": False,
                "llm_responses_retained": False,
                "history_message_delta": history_delta,
            },
            "configuration": {
                "concurrency_levels": list(self._concurrency_levels),
                "rounds_per_worker": self._rounds,
                "total_measured_samples": len(all_samples),
                "monitor_interval_ms": round(self._monitor_interval * 1000),
                "minimum_transcript_similarity": self._minimum_similarity,
                "synthetic_phrase_ids": [item[0] for item in SYNTHETIC_PHRASES],
            },
            "warmup": asdict(warmup),
            "levels": levels,
            "resources": self._resource_summary(),
            "monitoring": {
                "observations": len(self._observations),
                "errors": self._monitor_error_count,
                "max_queue_depth": self._max_queue(self._observations),
            },
        }

    def _run_level(self, concurrency: int) -> list[VoiceSample]:
        total = concurrency * self._rounds
        with ThreadPoolExecutor(max_workers=concurrency) as executor:
            futures = [
                executor.submit(
                    self._run_sample, *SYNTHETIC_PHRASES[index % len(SYNTHETIC_PHRASES)]
                )
                for index in range(total)
            ]
            return [future.result() for future in futures]

    def _run_sample(self, phrase_id: str, phrase: str) -> VoiceSample:
        started = time.perf_counter()
        llm_ms = tts_ms = stt_ms = None
        try:
            llm_response, llm_ms = self._request(
                "llm",
                "POST",
                "/api/studio/agent-test",
                json={
                    "agent_id": self._settings.default_agent_id,
                    "prompt": "Ответь одним коротким словом: готово.",
                },
            )
            if not str(llm_response.json().get("final_response", "")).strip():
                raise BenchmarkStageError("llm", "empty_response")

            speech, tts_ms = self._request(
                "tts",
                "POST",
                "/api/studio/speech",
                json={"text": phrase, "voice": self._settings.tts_voice},
            )
            content_type = speech.headers.get("content-type", "").split(";", 1)[0]
            if not content_type.startswith("audio/") or len(speech.content) < 128:
                raise BenchmarkStageError("tts", "invalid_audio")
            extension = "wav" if "wav" in content_type else "mp3"
            transcription, stt_ms = self._request(
                "stt",
                "POST",
                "/api/studio/transcription",
                files={"file": (f"{phrase_id}.{extension}", speech.content, content_type)},
            )
            payload = transcription.json()
            transcript = str(payload.get("text", "")).strip()
            if not transcript:
                raise BenchmarkStageError("stt", "empty_transcript")
            similarity = self._similarity(phrase, transcript)
            if similarity < self._minimum_similarity:
                raise BenchmarkStageError("stt", "low_similarity")
            return VoiceSample(
                phrase_id=phrase_id,
                status="passed",
                total_ms=self._duration_ms(started),
                llm_ms=llm_ms,
                tts_ms=tts_ms,
                stt_ms=stt_ms,
                stt_provider_ms=self._integer(payload.get("duration_ms")),
                stt_confidence=self._number(payload.get("confidence")),
                transcript_similarity=round(similarity, 3),
                audio_bytes=len(speech.content),
            )
        except BenchmarkStageError as exc:
            return VoiceSample(
                phrase_id=phrase_id,
                status="failed",
                total_ms=self._duration_ms(started),
                llm_ms=llm_ms,
                tts_ms=tts_ms,
                stt_ms=stt_ms,
                error_stage=exc.stage,
                error_type=exc.reason,
            )
        except Exception as exc:  # pragma: no cover - defensive CLI boundary
            return VoiceSample(
                phrase_id=phrase_id,
                status="failed",
                total_ms=self._duration_ms(started),
                llm_ms=llm_ms,
                tts_ms=tts_ms,
                stt_ms=stt_ms,
                error_stage="client",
                error_type=type(exc).__name__,
            )

    def _request(
        self,
        stage: str,
        method: str,
        path: str,
        **kwargs: Any,
    ) -> tuple[httpx.Response, int]:
        started = time.perf_counter()
        try:
            response = self._client.request(
                method,
                f"{self._admin_url}{path}",
                auth=self._auth,
                **kwargs,
            )
            response.raise_for_status()
            return response, self._duration_ms(started)
        except httpx.HTTPStatusError as exc:
            raise BenchmarkStageError(stage, f"http_{exc.response.status_code}") from exc
        except httpx.HTTPError as exc:
            raise BenchmarkStageError(stage, type(exc).__name__) from exc

    def _history_total(self) -> int:
        response, _duration = self._request(
            "history",
            "GET",
            "/api/history/summary?days=30",
        )
        try:
            return int(response.json()["total_messages"])
        except (KeyError, TypeError, ValueError) as exc:
            raise BenchmarkStageError("history", "invalid_summary") from exc

    def _monitor_loop(self, stop: threading.Event) -> None:
        next_infrastructure_at = 0.0
        latest_nodes: dict[str, dict[str, float | None]] = {}
        while not stop.is_set():
            queue_depth: float | None = None
            active_stage: str | None = None
            try:
                voice, _duration = self._request(
                    "monitoring",
                    "GET",
                    "/api/voice-observability",
                )
                speech = (voice.json().get("speech") or {}).get("data") or {}
                queue_depth = self._number(speech.get("queue_depth"))
                stage = speech.get("active_stage")
                active_stage = str(stage)[:40] if stage else None
            except BenchmarkStageError:
                self._monitor_error_count += 1

            elapsed = time.perf_counter() - self._started_at
            if elapsed >= next_infrastructure_at:
                try:
                    infrastructure, _duration = self._request(
                        "monitoring",
                        "GET",
                        "/api/infrastructure",
                    )
                    latest_nodes = self._node_metrics(infrastructure.json().get("nodes"))
                except BenchmarkStageError:
                    self._monitor_error_count += 1
                next_infrastructure_at = elapsed + max(2.0, self._monitor_interval * 4)

            self._observations.append(
                MetricObservation(
                    elapsed_ms=round(elapsed * 1000),
                    queue_depth=queue_depth,
                    active_stage=active_stage,
                    nodes=latest_nodes,
                )
            )
            stop.wait(self._monitor_interval)

    def _summarize_level(
        self,
        concurrency: int,
        started_ms: int,
        finished_ms: int,
        samples: list[VoiceSample],
    ) -> dict[str, Any]:
        successful = [item for item in samples if item.status == "passed"]
        observations = [
            item for item in self._observations if started_ms <= item.elapsed_ms <= finished_ms
        ]
        return {
            "concurrency": concurrency,
            "samples": len(samples),
            "successes": len(successful),
            "errors": len(samples) - len(successful),
            "error_rate": round((len(samples) - len(successful)) / len(samples), 3),
            "wall_ms": finished_ms - started_ms,
            "stages": {
                name: self._distribution(
                    [value for item in successful if (value := getattr(item, field)) is not None]
                )
                for name, field in (
                    ("llm", "llm_ms"),
                    ("tts", "tts_ms"),
                    ("stt", "stt_ms"),
                    ("total", "total_ms"),
                    ("transcript_similarity", "transcript_similarity"),
                )
            },
            "queue": {
                "max": self._max_queue(observations),
                "average": self._average_queue(observations),
                "observations": len(observations),
            },
            "samples_detail": [asdict(item) for item in samples],
        }

    def _resource_summary(self) -> dict[str, Any]:
        node_ids = sorted({node_id for item in self._observations for node_id in item.nodes})
        return {
            node_id: {
                metric: self._distribution(
                    [
                        value
                        for item in self._observations
                        if (value := item.nodes.get(node_id, {}).get(metric)) is not None
                    ]
                )
                for metric in ("cpu_percent", "memory_percent", "disk_percent")
            }
            for node_id in node_ids
        }

    @classmethod
    def _node_metrics(cls, nodes: object) -> dict[str, dict[str, float | None]]:
        if not isinstance(nodes, list):
            return {}
        result: dict[str, dict[str, float | None]] = {}
        for node in nodes:
            if not isinstance(node, dict) or not isinstance(node.get("id"), str):
                continue
            result[node["id"]] = {
                "cpu_percent": cls._number(node.get("cpu_percent")),
                "memory_percent": cls._nested_percent(node.get("memory")),
                "disk_percent": cls._nested_percent(node.get("disk")),
            }
        return result

    @staticmethod
    def _nested_percent(value: object) -> float | None:
        if not isinstance(value, dict):
            return None
        return VoiceSoakRunner._number(value.get("percent"))

    @staticmethod
    def _distribution(values: list[float | int]) -> dict[str, float | int | None]:
        if not values:
            return {"count": 0, "average": None, "p50": None, "p95": None, "max": None}
        ordered = sorted(values)
        return {
            "count": len(ordered),
            "average": round(fmean(ordered), 2),
            "p50": VoiceSoakRunner._percentile(ordered, 50),
            "p95": VoiceSoakRunner._percentile(ordered, 95),
            "max": ordered[-1],
        }

    @staticmethod
    def _percentile(values: list[float | int], percentile: int) -> float | int:
        index = max(0, min(len(values) - 1, math.ceil(len(values) * percentile / 100) - 1))
        return values[index]

    @staticmethod
    def _max_queue(observations: list[MetricObservation]) -> float | None:
        values = [item.queue_depth for item in observations if item.queue_depth is not None]
        return max(values) if values else None

    @staticmethod
    def _average_queue(observations: list[MetricObservation]) -> float | None:
        values = [item.queue_depth for item in observations if item.queue_depth is not None]
        return round(fmean(values), 2) if values else None

    @staticmethod
    def _similarity(expected: str, actual: str) -> float:
        def normalize(value: str) -> str:
            return " ".join(re.findall(r"[а-яёa-z0-9]+", value.lower()))

        return SequenceMatcher(None, normalize(expected), normalize(actual)).ratio()

    @staticmethod
    def _number(value: object) -> float | None:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        return float(value)

    @staticmethod
    def _integer(value: object) -> int | None:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        return round(value)

    def _elapsed_ms(self) -> int:
        return round((time.perf_counter() - self._started_at) * 1000)

    @staticmethod
    def _duration_ms(started: float) -> int:
        return round((time.perf_counter() - started) * 1000)


def _parse_levels(value: str) -> tuple[int, ...]:
    try:
        levels = tuple(int(item.strip()) for item in value.split(",") if item.strip())
    except ValueError as exc:
        raise argparse.ArgumentTypeError("levels must be comma-separated integers") from exc
    if (
        not levels
        or len(set(levels)) != len(levels)
        or any(item not in ALLOWED_CONCURRENCY for item in levels)
    ):
        raise argparse.ArgumentTypeError("levels must be a unique subset of 1,2,4")
    return levels


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--admin-url", default="http://127.0.0.1:8001")
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--levels", type=_parse_levels, default=(1, 2, 4))
    parser.add_argument("--rounds", type=int, default=2)
    parser.add_argument("--monitor-interval", type=float, default=0.5)
    parser.add_argument("--cooldown", type=float, default=2.0)
    parser.add_argument("--timeout", type=float, default=180.0)
    parser.add_argument("--minimum-similarity", type=float, default=0.65)
    parser.add_argument("--skip-history-check", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    settings = Settings(_env_file=args.env_file) if args.env_file else Settings()
    with httpx.Client(timeout=args.timeout) as client:
        report = VoiceSoakRunner(
            client,
            settings,
            admin_url=args.admin_url,
            concurrency_levels=args.levels,
            rounds=args.rounds,
            monitor_interval_seconds=args.monitor_interval,
            cooldown_seconds=args.cooldown,
            minimum_similarity=args.minimum_similarity,
            verify_history=not args.skip_history_check,
        ).run()

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    for level in report["levels"]:
        total = level["stages"]["total"]
        print(
            f"[concurrency={level['concurrency']}] success={level['successes']}/"
            f"{level['samples']} total_p50={total['p50']}ms total_p95={total['p95']}ms "
            f"queue_max={level['queue']['max']}"
        )
    print(
        json.dumps(
            {
                "status": report["status"],
                "history_message_delta": report["privacy"]["history_message_delta"],
                "output": str(args.output) if args.output else None,
            },
            ensure_ascii=False,
        )
    )
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())
