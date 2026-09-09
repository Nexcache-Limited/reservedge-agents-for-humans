"""Locate the contracts package from any working directory."""

from __future__ import annotations

from pathlib import Path


def repo_root() -> Path:
    here = Path(__file__).resolve()
    for candidate in here.parents:
        if (candidate / "pyproject.toml").exists() and (candidate / "packages").exists():
            return candidate
    raise RuntimeError("Unable to locate the ITAA repository root")


def contracts_root(root: Path | None = None) -> Path:
    return (root or repo_root()) / "packages" / "contracts"
