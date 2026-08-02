"""Compare deterministic browser screenshots without third-party image packages."""

from __future__ import annotations

import argparse
import struct
import zlib
from dataclasses import dataclass
from pathlib import Path

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


@dataclass(frozen=True)
class PngImage:
    width: int
    height: int
    channels: int
    pixels: bytes


def _paeth(left: int, above: int, upper_left: int) -> int:
    estimate = left + above - upper_left
    left_distance = abs(estimate - left)
    above_distance = abs(estimate - above)
    upper_left_distance = abs(estimate - upper_left)
    if left_distance <= above_distance and left_distance <= upper_left_distance:
        return left
    if above_distance <= upper_left_distance:
        return above
    return upper_left


def read_png(path: Path) -> PngImage:
    content = path.read_bytes()
    if not content.startswith(PNG_SIGNATURE):
        raise ValueError(f"Not a PNG file: {path}")
    offset = len(PNG_SIGNATURE)
    header: tuple[int, ...] | None = None
    compressed = bytearray()
    while offset < len(content):
        length = struct.unpack_from(">I", content, offset)[0]
        kind = content[offset + 4 : offset + 8]
        data = content[offset + 8 : offset + 8 + length]
        offset += 12 + length
        if kind == b"IHDR":
            header = struct.unpack(">IIBBBBB", data)
        elif kind == b"IDAT":
            compressed.extend(data)
        elif kind == b"IEND":
            break
    if header is None:
        raise ValueError(f"PNG has no IHDR: {path}")
    width, height, bit_depth, color_type, compression, filtering, interlace = header
    if bit_depth != 8 or color_type not in {2, 6}:
        raise ValueError("Only 8-bit RGB and RGBA screenshots are supported")
    if compression or filtering or interlace:
        raise ValueError("Interlaced or non-standard PNG screenshots are unsupported")
    channels = 3 if color_type == 2 else 4
    stride = width * channels
    source = zlib.decompress(bytes(compressed))
    expected_size = height * (stride + 1)
    if len(source) != expected_size:
        raise ValueError("Unexpected decompressed PNG size")
    rows: list[bytearray] = []
    position = 0
    for _ in range(height):
        filter_type = source[position]
        position += 1
        encoded = source[position : position + stride]
        position += stride
        previous = rows[-1] if rows else bytearray(stride)
        decoded = bytearray(stride)
        for index, value in enumerate(encoded):
            left = decoded[index - channels] if index >= channels else 0
            above = previous[index]
            upper_left = previous[index - channels] if index >= channels else 0
            predictor = {
                0: 0,
                1: left,
                2: above,
                3: (left + above) // 2,
                4: _paeth(left, above, upper_left),
            }.get(filter_type)
            if predictor is None:
                raise ValueError(f"Unsupported PNG filter: {filter_type}")
            decoded[index] = (value + predictor) & 0xFF
        rows.append(decoded)
    return PngImage(width, height, channels, b"".join(rows))


def different_pixel_ratio(
    expected: PngImage,
    actual: PngImage,
    *,
    channel_tolerance: int,
) -> float:
    if (expected.width, expected.height) != (actual.width, actual.height):
        raise ValueError(
            f"Image dimensions differ: {expected.width}x{expected.height} != "
            f"{actual.width}x{actual.height}"
        )
    different = 0
    for pixel in range(expected.width * expected.height):
        expected_offset = pixel * expected.channels
        actual_offset = pixel * actual.channels
        if any(
            abs(expected.pixels[expected_offset + channel] - actual.pixels[actual_offset + channel])
            > channel_tolerance
            for channel in range(3)
        ):
            different += 1
    return different / (expected.width * expected.height)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("expected", type=Path)
    parser.add_argument("actual", type=Path)
    parser.add_argument("--channel-tolerance", type=int, default=18)
    parser.add_argument("--max-different-ratio", type=float, default=0.002)
    args = parser.parse_args()
    ratio = different_pixel_ratio(
        read_png(args.expected),
        read_png(args.actual),
        channel_tolerance=args.channel_tolerance,
    )
    print(f"different pixels: {ratio:.4%}")
    return 0 if ratio <= args.max_different_ratio else 1


if __name__ == "__main__":
    raise SystemExit(main())
