"""Unit tests for provider-independent audio helpers."""

import io
import wave

from family_ai_speech.backends import pcm16_to_wav, resolve_voice


def test_cloud_voice_aliases_resolve_to_local_voices() -> None:
    assert resolve_voice("lulwa", "xenia") == "xenia"
    assert resolve_voice("noura", "xenia") == "baya"
    assert resolve_voice("aisha", "xenia") == "kseniya"
    assert resolve_voice("fahad", "xenia") == "aidar"


def test_unknown_voice_uses_configured_default() -> None:
    assert resolve_voice("unknown-cloud-voice", "baya") == "baya"


def test_pcm_is_wrapped_in_finalized_wav() -> None:
    content = pcm16_to_wav(b"\x00\x00\x01\x00", sample_rate=16000)

    with wave.open(io.BytesIO(content), "rb") as wav_file:
        assert wav_file.getnchannels() == 1
        assert wav_file.getsampwidth() == 2
        assert wav_file.getframerate() == 16000
        assert wav_file.getnframes() == 2
