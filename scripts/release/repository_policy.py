"""Fail closed on repository content that must never enter a release commit."""

from __future__ import annotations

import argparse
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

DEFAULT_MAX_BYTES = 2 * 1024 * 1024

FORBIDDEN_SUFFIXES = {
    ".aab",
    ".apk",
    ".backup",
    ".db",
    ".dump",
    ".jks",
    ".key",
    ".keystore",
    ".log",
    ".p12",
    ".pem",
    ".pfx",
    ".sqlite",
    ".sqlite3",
}

SECRET_PATTERNS = (
    ("private key", re.compile(rb"-----BEGIN (?:[A-Z]+ )?PRIVATE KEY-----")),
    ("OpenAI-style API key", re.compile(rb"\bsk-[A-Za-z0-9_-]{24,}\b")),
    ("Groq API key", re.compile(rb"\bgsk_[A-Za-z0-9_-]{24,}\b")),
    ("GitHub token", re.compile(rb"\bgh[opsu]_[A-Za-z0-9]{30,}\b")),
    ("AWS access key", re.compile(rb"\bAKIA[0-9A-Z]{16}\b")),
)


@dataclass(frozen=True)
class PolicyViolation:
    path: str
    reason: str


class RepositoryPolicyError(RuntimeError):
    def __init__(self, violations: list[PolicyViolation]) -> None:
        self.violations = violations
        details = "\n".join(f"- {item.path}: {item.reason}" for item in violations)
        super().__init__(f"Repository policy failed:\n{details}")


def tracked_paths(repo: Path) -> list[str]:
    result = subprocess.run(
        ["git", "-C", str(repo), "ls-files", "-z"],
        check=True,
        capture_output=True,
    )
    return sorted(item.decode("utf-8") for item in result.stdout.split(b"\0") if item)


def working_tree_changes(repo: Path) -> list[str]:
    result = subprocess.run(
        ["git", "-C", str(repo), "status", "--porcelain", "--untracked-files=all"],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return [line for line in result.stdout.splitlines() if line]


def inspect_paths(
    repo: Path,
    paths: list[str],
    *,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> list[PolicyViolation]:
    violations: list[PolicyViolation] = []
    for relative in paths:
        normalized = PurePosixPath(relative.replace("\\", "/"))
        file_path = repo.joinpath(*normalized.parts)
        if not file_path.is_file():
            violations.append(PolicyViolation(relative, "tracked file is missing"))
            continue
        name = normalized.name.casefold()
        suffix = normalized.suffix.casefold()
        if name.startswith(".env") and name != ".env.example":
            violations.append(PolicyViolation(relative, "environment file is forbidden"))
        if suffix in FORBIDDEN_SUFFIXES:
            violations.append(PolicyViolation(relative, f"forbidden artifact type {suffix}"))
        size = file_path.stat().st_size
        if size > max_bytes:
            violations.append(
                PolicyViolation(relative, f"file is larger than {max_bytes} bytes ({size})")
            )
            continue
        payload = file_path.read_bytes()
        for label, pattern in SECRET_PATTERNS:
            if pattern.search(payload):
                violations.append(PolicyViolation(relative, f"high-confidence {label} detected"))
    return violations


def enforce_repository_policy(
    repo: Path,
    *,
    require_clean: bool = True,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> int:
    if require_clean:
        changes = working_tree_changes(repo)
        if changes:
            raise RepositoryPolicyError(
                [PolicyViolation("working-tree", f"uncommitted change: {line}") for line in changes]
            )
    paths = tracked_paths(repo)
    violations = inspect_paths(repo, paths, max_bytes=max_bytes)
    if violations:
        raise RepositoryPolicyError(violations)
    return len(paths)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--allow-dirty", action="store_true")
    parser.add_argument("--max-file-mib", type=float, default=2.0)
    args = parser.parse_args()
    count = enforce_repository_policy(
        args.repo.resolve(),
        require_clean=not args.allow_dirty,
        max_bytes=int(args.max_file_mib * 1024 * 1024),
    )
    print(f"Repository policy passed for {count} tracked files.")


if __name__ == "__main__":
    main()
