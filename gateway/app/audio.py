"""Audio container normalization shared by provider adapters."""

from struct import pack_into, unpack_from


def finalize_wav_container(content: bytes) -> bytes:
    """Replace streaming RIFF/data sizes with the actual buffered lengths."""
    if len(content) < 12 or content[:4] != b"RIFF" or content[8:12] != b"WAVE":
        return content

    chunk_offset = 12
    while chunk_offset + 8 <= len(content):
        chunk_name = content[chunk_offset : chunk_offset + 4]
        chunk_size = unpack_from("<I", content, chunk_offset + 4)[0]
        if chunk_name == b"data":
            actual_riff_size = len(content) - 8
            actual_data_size = len(content) - chunk_offset - 8
            current_riff_size = unpack_from("<I", content, 4)[0]
            if current_riff_size == actual_riff_size and chunk_size == actual_data_size:
                return content

            normalized = bytearray(content)
            pack_into("<I", normalized, 4, actual_riff_size)
            pack_into("<I", normalized, chunk_offset + 4, actual_data_size)
            return bytes(normalized)
        if chunk_size == 0xFFFFFFFF:
            return content
        chunk_offset += 8 + chunk_size + (chunk_size % 2)

    return content
