"""Build a deterministic runtime archive from one exact Git commit."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import subprocess
import tarfile
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Component:
    paths: tuple[str, ...]
    strip_prefix: str = ""


COMPONENTS = {
    "gateway": Component(
        paths=(
            "gateway",
            "alembic",
            "scripts/run_retention.py",
            "pyproject.toml",
            "uv.lock",
            "alembic.ini",
            "README.md",
        )
    ),
    "speech": Component(
        paths=(
            "speech/family_ai_speech",
            "speech/pyproject.toml",
            "speech/uv.lock",
        ),
        strip_prefix="speech/",
    ),
}


def _git(repo: Path, *args: str, text: bool = False) -> bytes | str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=text,
    )
    return result.stdout


def resolve_commit(repo: Path, revision: str) -> str:
    commit = str(_git(repo, "rev-parse", "--verify", f"{revision}^{{commit}}", text=True)).strip()
    if len(commit) != 40:
        raise ValueError("Git did not return a full commit SHA")
    return commit


def _normalized_name(name: str, strip_prefix: str) -> str | None:
    if strip_prefix:
        if name == strip_prefix.rstrip("/"):
            return None
        if not name.startswith(strip_prefix):
            raise ValueError(f"Unexpected archive member outside {strip_prefix}: {name}")
        name = name[len(strip_prefix) :]
    path = Path(name)
    if path.is_absolute() or ".." in path.parts or not name:
        raise ValueError(f"Unsafe archive member: {name}")
    return path.as_posix()


def build_release(repo: Path, component_name: str, revision: str, output: Path) -> dict[str, str]:
    component = COMPONENTS[component_name]
    commit = resolve_commit(repo, revision)
    commit_time = str(_git(repo, "show", "-s", "--format=%cI", commit, text=True)).strip()
    archive = _git(repo, "archive", "--format=tar", commit, "--", *component.paths)
    assert isinstance(archive, bytes)

    lock_path = "uv.lock" if component_name == "gateway" else "speech/uv.lock"
    lock_bytes = _git(repo, "show", f"{commit}:{lock_path}")
    assert isinstance(lock_bytes, bytes)
    manifest = {
        "schema": "family-ai-release/v1",
        "component": component_name,
        "commit": commit,
        "commit_time": commit_time,
        "lock_sha256": hashlib.sha256(lock_bytes).hexdigest(),
    }

    output.parent.mkdir(parents=True, exist_ok=True)
    tar_buffer = io.BytesIO()
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:") as source:
        with tarfile.open(fileobj=tar_buffer, mode="w", format=tarfile.PAX_FORMAT) as target:
            for member in source.getmembers():
                normalized = _normalized_name(member.name, component.strip_prefix)
                if normalized is None:
                    continue
                member.name = normalized
                member.uid = 0
                member.gid = 0
                member.uname = ""
                member.gname = ""
                file_object = source.extractfile(member) if member.isfile() else None
                target.addfile(member, file_object)

            payload = (json.dumps(manifest, ensure_ascii=False, sort_keys=True) + "\n").encode()
            info = tarfile.TarInfo("release.json")
            info.size = len(payload)
            info.mode = 0o644
            info.mtime = 0
            target.addfile(info, io.BytesIO(payload))

    with output.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as compressed:
            compressed.write(tar_buffer.getvalue())

    manifest["archive_sha256"] = hashlib.sha256(output.read_bytes()).hexdigest()
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("component", choices=sorted(COMPONENTS))
    parser.add_argument("--commit", default="HEAD")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[2])
    args = parser.parse_args()

    manifest = build_release(
        args.repo.resolve(),
        args.component,
        args.commit,
        args.output.resolve(),
    )
    print(json.dumps(manifest, ensure_ascii=False))


if __name__ == "__main__":
    main()
