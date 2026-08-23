from pathlib import Path

from scripts.assets.sync_character_assets import synchronize


def _write(directory: Path, name: str, content: bytes) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / name).write_bytes(content)


def test_asset_sync_reports_and_repairs_drift(tmp_path: Path) -> None:
    source = tmp_path / "source"
    mirror = tmp_path / "mirror"
    _write(source, "friend.webp", b"canonical")
    _write(mirror, "friend.webp", b"stale")
    _write(mirror, "retired.webp", b"unused")

    differences = synchronize(source, mirror, write=False)

    assert differences == [
        "missing or changed mirror asset: friend.webp",
        "unexpected mirror asset: retired.webp",
    ]
    assert synchronize(source, mirror, write=True) == differences
    assert synchronize(source, mirror, write=False) == []
    assert (mirror / "friend.webp").read_bytes() == b"canonical"
    assert not (mirror / "retired.webp").exists()
