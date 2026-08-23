"""Keep Flutter's packaged character artwork in sync with the web source."""

from __future__ import annotations

import argparse
import hashlib
import shutil
from pathlib import Path


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _assets(directory: Path) -> dict[str, Path]:
    return {
        path.name: path
        for path in directory.iterdir()
        if path.is_file() and path.suffix.lower() == ".webp"
    }


def synchronize(source: Path, mirror: Path, *, write: bool) -> list[str]:
    source_assets = _assets(source)
    mirror_assets = _assets(mirror)
    differences: list[str] = []

    for name in sorted(source_assets.keys() | mirror_assets.keys()):
        source_path = source_assets.get(name)
        mirror_path = mirror_assets.get(name)
        if source_path is None:
            differences.append(f"unexpected mirror asset: {name}")
            if write and mirror_path is not None:
                mirror_path.unlink()
            continue
        if mirror_path is None or _digest(source_path) != _digest(mirror_path):
            differences.append(f"missing or changed mirror asset: {name}")
            if write:
                mirror.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source_path, mirror / name)
    return differences


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument(
        "--write",
        action="store_true",
        help="replace the Flutter mirror with the canonical web assets",
    )
    args = parser.parse_args()
    repo = args.repo.resolve()
    differences = synchronize(
        repo / "gateway/static/assets/characters",
        repo / "mobile/assets/characters",
        write=args.write,
    )
    if differences and not args.write:
        print("Character asset mirror is out of sync:")
        for difference in differences:
            print(f"- {difference}")
        print("Run this command again with --write to update the mirror.")
        return 1
    if differences:
        print(f"Synchronized {len(differences)} character asset difference(s).")
    else:
        print("Character assets are synchronized.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
