"""Audit the exact uv-locked Gateway and Speech dependency sets."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import tempfile
from pathlib import Path

PIP_AUDIT_VERSION = "2.10.1"


def _export(uv: Path, project: Path, output: Path) -> None:
    subprocess.run(
        [
            str(uv),
            "export",
            "--frozen",
            "--no-dev",
            "--no-emit-project",
            "--no-hashes",
            "--format",
            "requirements-txt",
            "--output-file",
            str(output),
        ],
        cwd=project,
        check=True,
        stdout=subprocess.DEVNULL,
    )


def _normalize_for_advisory_lookup(requirements: Path) -> None:
    content = requirements.read_text(encoding="utf-8")
    # PyTorch CPU wheels use a PEP 440 local version. Advisory databases index
    # the upstream release, whose vulnerability range also applies to the wheel.
    content = re.sub(r"^(torch==[0-9.]+)\+cpu", r"\1", content, flags=re.MULTILINE)
    requirements.write_text(content, encoding="utf-8")


def _audit(uv: Path, requirements: Path, report: Path) -> dict[str, object]:
    subprocess.run(
        [
            str(uv),
            "tool",
            "run",
            "--from",
            f"pip-audit=={PIP_AUDIT_VERSION}",
            "pip-audit",
            "--requirement",
            str(requirements),
            "--no-deps",
            "--disable-pip",
            "--strict",
            "--format",
            "json",
            "--progress-spinner",
            "off",
            "--output",
            str(report),
        ],
        check=True,
    )
    return json.loads(report.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--uv", type=Path, required=True)
    args = parser.parse_args()
    repo = args.repo.resolve()
    uv = args.uv.resolve()

    with tempfile.TemporaryDirectory(prefix="family-ai-audit-") as temp:
        temp_path = Path(temp)
        for name, project in (("gateway", repo), ("speech", repo / "speech")):
            requirements = temp_path / f"{name}.txt"
            report = temp_path / f"{name}.json"
            _export(uv, project, requirements)
            _normalize_for_advisory_lookup(requirements)
            result = _audit(uv, requirements, report)
            dependencies = result.get("dependencies", [])
            if not isinstance(dependencies, list) or not dependencies:
                raise RuntimeError(f"{name} dependency audit returned no packages")
            if name == "speech" and not any(
                item.get("name") == "torch" for item in dependencies if isinstance(item, dict)
            ):
                raise RuntimeError("Speech audit did not include the PyTorch CPU release")
            print(f"{name}: audited {len(dependencies)} locked packages, no known vulnerabilities")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
