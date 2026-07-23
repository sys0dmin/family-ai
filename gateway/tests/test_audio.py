"""Tests for normalized audio containers returned by the Gateway."""

from struct import pack_into, unpack_from

from gateway.app.audio import finalize_wav_container


def _streaming_wav() -> bytes:
    content = bytearray(48)
    content[0:4] = b"RIFF"
    content[8:12] = b"WAVE"
    content[12:16] = b"fmt "
    pack_into("<I", content, 16, 16)
    pack_into("<H", content, 20, 1)
    pack_into("<H", content, 22, 1)
    pack_into("<I", content, 24, 24_000)
    pack_into("<I", content, 28, 48_000)
    pack_into("<H", content, 32, 2)
    pack_into("<H", content, 34, 16)
    content[36:40] = b"data"
    pack_into("<I", content, 4, 0xFFFFFFFF)
    pack_into("<I", content, 40, 0xFFFFFFFF)
    content[44:48] = b"\x01\x02\x03\x04"
    return bytes(content)


def test_finalize_wav_container_replaces_streaming_sizes() -> None:
    normalized = finalize_wav_container(_streaming_wav())

    assert unpack_from("<I", normalized, 4)[0] == 40
    assert unpack_from("<I", normalized, 40)[0] == 4
    assert normalized[44:] == b"\x01\x02\x03\x04"


def test_finalize_wav_container_ignores_non_wav_content() -> None:
    content = b"ID3-valid-mp3"

    assert finalize_wav_container(content) is content
