"""Tests for replaceable, agent-scoped melody recognition."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from gateway.app.music import MusicRecognitionRequest
from gateway.app.music.acrcloud import AcrCloudMusicRecognitionProvider
from gateway.app.services.music_recognition_service import MusicRecognitionService


@pytest.mark.anyio
async def test_acrcloud_adapter_normalizes_humming_candidates() -> None:
    captured: dict[str, object] = {}

    def transport(request, timeout):
        captured.update(url=request.full_url, body=request.data, timeout=timeout)
        return {
            "status": {"code": 0},
            "metadata": {
                "humming": [
                    {
                        "title": "Песенка",
                        "artists": [{"name": "Автор"}],
                        "album": {"name": "Мультфильм"},
                        "score": 91,
                    }
                ]
            },
        }

    provider = AcrCloudMusicRecognitionProvider(
        host="identify-eu-west-1.acrcloud.com",
        access_key="access-key",
        access_secret="access-secret",
        timeout_seconds=4.5,
        transport=transport,
    )

    result = await provider.recognize(
        MusicRecognitionRequest(b"audio", "song.webm", "audio/webm")
    )

    assert captured["url"] == "https://identify-eu-west-1.acrcloud.com/v1/identify"
    assert captured["timeout"] == 4.5
    assert b'access_key' in captured["body"]
    assert b'filename="song.webm"' in captured["body"]
    assert result.matches[0].title == "Песенка"
    assert result.matches[0].artist == "Автор"
    assert result.matches[0].album == "Мультфильм"
    assert result.matches[0].score == 91


def test_acrcloud_adapter_rejects_untrusted_host() -> None:
    with pytest.raises(ValueError, match="HTTPS acrcloud.com"):
        AcrCloudMusicRecognitionProvider(
            host="https://example.org",
            access_key="key",
            access_secret="secret",
        )


@pytest.mark.anyio
async def test_music_tool_is_only_called_for_authorized_agent() -> None:
    provider = AsyncMock()
    service = MusicRecognitionService(provider)

    result = await service.recognize_for_agent(
        agent=SimpleNamespace(tools=()),
        audio_content=b"audio",
        filename="recording.webm",
        content_type="audio/webm",
    )

    assert result is None
    provider.recognize.assert_not_awaited()


@pytest.mark.anyio
async def test_disabled_music_provider_returns_honest_child_safe_context() -> None:
    service = MusicRecognitionService(None)

    result = await service.recognize_for_agent(
        agent=SimpleNamespace(tools=("music_recognition",)),
        audio_content=b"audio",
        filename="recording.webm",
        content_type="audio/webm",
    )

    assert result is not None
    assert "не угадывай уверенно" in result.prompt_context
