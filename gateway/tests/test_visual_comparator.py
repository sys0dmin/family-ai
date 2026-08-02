"""Tests for the dependency-free PNG visual comparator."""

from gateway.smoke import _solid_png
from scripts.visual.compare_png import different_pixel_ratio, read_png


def test_png_comparator_accepts_identical_rgb_images(tmp_path) -> None:
    image_path = tmp_path / "image.png"
    image_path.write_bytes(_solid_png(4, 3))

    image = read_png(image_path)

    assert image.width == 4
    assert image.height == 3
    assert different_pixel_ratio(image, image, channel_tolerance=0) == 0
