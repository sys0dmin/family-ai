"""Tests for protected Speech runtime controls."""


import pytest
from httpx import ASGITransport, AsyncClient

from gateway.admin.auth import verify_admin
from gateway.admin.main import app as admin_app
from gateway.app.dependencies import get_speech_runtime_service
from gateway.app.speech_runtime.schemas import SpeechRuntimeSettings


class StubSpeechRuntimeService:
    def __init__(self) -> None:
        self.update = None

    async def current(self) -> SpeechRuntimeSettings:
        return SpeechRuntimeSettings(
            stt_beam_size=5,
            stt_vad_filter=True,
            instance_id="instance-a",
        )

    async def apply_and_restart(self, update) -> SpeechRuntimeSettings:
        self.update = update
        return SpeechRuntimeSettings(
            stt_beam_size=update.stt_beam_size,
            stt_vad_filter=update.stt_vad_filter,
            instance_id="instance-b",
        )


@pytest.mark.anyio
async def test_admin_reads_and_applies_speech_runtime_settings() -> None:
    service = StubSpeechRuntimeService()
    admin_app.dependency_overrides[verify_admin] = lambda: "admin"
    admin_app.dependency_overrides[get_speech_runtime_service] = lambda: service
    try:
        transport = ASGITransport(app=admin_app)
        async with AsyncClient(transport=transport, base_url="http://admin") as client:
            current = await client.get("/api/speech/runtime-settings")
            updated = await client.put(
                "/api/speech/runtime-settings",
                json={"stt_beam_size": 3, "stt_vad_filter": False},
            )
            invalid = await client.put(
                "/api/speech/runtime-settings",
                json={"stt_beam_size": 99, "stt_vad_filter": True},
            )
    finally:
        admin_app.dependency_overrides.clear()

    assert current.status_code == 200
    assert current.json()["stt_beam_size"] == 5
    assert updated.status_code == 200
    assert updated.json()["instance_id"] == "instance-b"
    assert service.update.stt_beam_size == 3
    assert invalid.status_code == 422
