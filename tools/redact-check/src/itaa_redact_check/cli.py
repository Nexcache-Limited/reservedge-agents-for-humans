"""Scan the workspace for common credential patterns.

This is a foundation check used by local commands and CI. It is not a complete
DLP program. `.env.example` local-development defaults are allowlisted.
"""

from __future__ import annotations

import argparse
import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

SKIP_DIRS = {
    ".git",
    ".venv",
    "node_modules",
    "dist",
    "build",
    ".ruff_cache",
    ".mypy_cache",
    ".pytest_cache",
    "htmlcov",
    "__pycache__",
    ".pnpm-store",
    "coverage",
}

SKIP_SUFFIXES = {
    ".docx",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".ico",
    ".pdf",
    ".lock",
    ".woff",
    ".woff2",
}

ALLOWLIST_RELATIVE_PATHS = {
    ".env.example",
}

PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("pem-private-key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----")),
    ("aws-access-key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("github-pat", re.compile(r"\bghp_[A-Za-z0-9]{36}\b")),
    ("github-fine-grained-pat", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b")),
    ("slack-bot-token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")),
)


@dataclass(frozen=True)
class Finding:
    relative_path: str
    line: int
    rule: str


def repo_root() -> Path:
    here = Path(__file__).resolve()
    for candidate in here.parents:
        if (candidate / "pyproject.toml").exists() and (candidate / "packages").exists():
            return candidate
    raise RuntimeError("Unable to locate the ITAA repository root")


def iter_files(root: Path) -> Iterable[Path]:
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.suffix.lower() in SKIP_SUFFIXES:
            continue
        yield path


def scan_text(relative_path: str, text: str) -> list[Finding]:
    if relative_path in ALLOWLIST_RELATIVE_PATHS:
        return []
    findings: list[Finding] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        for rule, pattern in PATTERNS:
            if pattern.search(line):
                findings.append(Finding(relative_path=relative_path, line=line_number, rule=rule))
    return findings


def scan_workspace(root: Path | None = None) -> list[Finding]:
    root = root or repo_root()
    findings: list[Finding] = []
    for path in iter_files(root):
        relative = path.relative_to(root).as_posix()
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        findings.extend(scan_text(relative, text))
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ITAA secret-pattern scan")
    parser.parse_args(argv)
    findings = scan_workspace()
    if not findings:
        print("PASS: secret-pattern scan found no credential material in the workspace.")
        return 0
    for finding in findings:
        print(f"{finding.relative_path}:{finding.line}: {finding.rule}")
    print(f"FAIL: {len(findings)} secret-pattern finding(s).")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
