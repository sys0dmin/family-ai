"""Tests for the privacy-safe synthetic voice benchmark."""

import json
import time

import httpx

from gateway.app.config import Settings
from gateway.voice_soak import SYNTHETIC_PHRASES, VoiceSoakRunner


def _benchmark_response(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    if path == "/api/history/summary":
        return httpx.Response(200, json={"total_messages": 12})
    if path == "/api/studio/agent-test":
        time.sleep(0.005)
        return httpx.Response(200, json={"final_response": "synthetic llm body"})
    if path == "/api/studio/speech":
        time.sleep(0.005)
        return httpx.Response(
            200,
            content=b"RIFF" + b"\x00" * 256,
            headers={"content-type": "audio/wav"},
        )
    if path == "/api/studio/transcription":
        time.sleep(0.005)
        return httpx.Response(
            200,
            json={
                "text": "synthetic transcript body",
                "confidence": 0.92,
                "duration_ms": 14,
            },
        )
    if path == "/api/voice-observability":
        return httpx.Response(
            200,
            json={
                "gateway": {"status": "healthy", "data": {}},
                "speech": {
                    "status": "healthy",
                    "data": {"queue_depth": 1, "active_stage": "stt"},
                },
            },
        )
    if path == "/api/infrastructure":
        return httpx.Response(
            200,
            json={
                "nodes": [
                    {
                        "id": "speech",
                        "cpu_percent": 77,
                        "memory": {"percent": 55},
                        "disk": {"percent": 22},
                    }
                ]
            },
        )
    return httpx.Response(404)


def test_voice_soak_reports_aggregates_without_retaining_payloads() -> None:
    with httpx.Client(transport=httpx.MockTransport(_benchmark_response)) as client:
        report = VoiceSoakRunner(
            client,
            Settings(admin_password="test-password"),
            admin_url="http://admin",
            concurrency_levels=(1, 2),
            rounds=1,
            monitor_interval_seconds=0.1,
            cooldown_seconds=0,
            minimum_similarity=0,
        ).run()

    assert report["status"] == "passed"
    assert report["privacy"]["history_message_delta"] == 0
    assert report["configuration"]["total_measured_samples"] == 3
    assert report["levels"][1]["concurrency"] == 2
    assert report["levels"][1]["successes"] == 2
    assert report["monitoring"]["max_queue_depth"] == 1
    assert report["resources"]["speech"]["cpu_percent"]["max"] == 77

    serialized = json.dumps(report, ensure_ascii=False)
    assert "synthetic llm body" not in serialized
    assert "synthetic transcript body" not in serialized
    for _phrase_id, phrase in SYNTHETIC_PHRASES:
        assert phrase not in serialized


def test_voice_soak_fails_when_stateless_path_changes_history() -> None:
    history_reads = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal history_reads
        if request.url.path == "/api/history/summary":
            history_reads += 1
            return httpx.Response(200, json={"total_messages": 10 + history_reads})
        return _benchmark_response(request)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        report = VoiceSoakRunner(
            client,
            Settings(admin_password="test-password"),
            admin_url="http://admin",
            concurrency_levels=(1,),
            rounds=1,
            monitor_interval_seconds=0.1,
            cooldown_seconds=0,
            minimum_similarity=0,
        ).run()

    assert report["status"] == "failed"
    assert report["privacy"]["history_message_delta"] == 1
