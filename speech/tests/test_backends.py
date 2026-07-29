"""Unit tests for provider-independent audio helpers."""

import io
import wave

from family_ai_speech.backends import (
    normalize_silero_text,
    pcm16_to_wav,
    resolve_voice,
)


def test_cloud_voice_aliases_resolve_to_local_voices() -> None:
    assert resolve_voice("lulwa", "xenia") == "xenia"
    assert resolve_voice("noura", "xenia") == "baya"
    assert resolve_voice("aisha", "xenia") == "kseniya"
    assert resolve_voice("fahad", "xenia") == "aidar"


def test_unknown_voice_uses_configured_default() -> None:
    assert resolve_voice("unknown-cloud-voice", "baya") == "baya"


def test_silero_text_transliterates_latin_and_removes_unsupported_symbols() -> None:
    assert (
        normalize_silero_text("Серая чайка — Larus canus. USB-C, Wi-Fi 🐦")
        == "Серая чайка — Ларус канус. УСБ-К, Ви-Фи"
    )


def test_silero_text_removes_other_scripts_and_control_characters() -> None:
    assert normalize_silero_text("Ёжик, привет\x00 世界!") == "Ёжик, привет !"


def test_pcm_is_wrapped_in_finalized_wav() -> None:
    content = pcm16_to_wav(b"\x00\x00\x01\x00", sample_rate=16000)

    with wave.open(io.BytesIO(content), "rb") as wav_file:
        assert wav_file.getnchannels() == 1
        assert wav_file.getsampwidth() == 2
        assert wav_file.getframerate() == 16000
        assert wav_file.getnframes() == 2
