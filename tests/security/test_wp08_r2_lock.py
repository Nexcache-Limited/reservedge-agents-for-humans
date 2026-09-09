"""WP-08-R2: the lock honors google-adk declared minimums without uv overrides."""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _package_version(lock: str, name: str) -> str:
    marker = f'name = "{name}"\n'
    start = lock.find(marker)
    assert start != -1, f"{name} missing from uv.lock"
    block = lock[start:].split("[[package]]", 1)[0]
    for line in block.splitlines():
        if line.startswith("version = "):
            return line.split("=", 1)[1].strip().strip('"')
    raise AssertionError(f"version missing for {name}")


def test_root_pyproject_has_no_dependency_overrides() -> None:
    text = _read(REPO / "pyproject.toml")
    assert "override-dependencies" not in text
    lock = _read(REPO / "uv.lock")
    assert "overrides = [" not in lock


def test_locked_versions_meet_google_adk_2_7_1_requires() -> None:
    lock = _read(REPO / "uv.lock")
    assert _package_version(lock, "google-adk") == "2.7.1"
    assert _package_version(lock, "fastapi") == "0.133.0"
    assert _package_version(lock, "pydantic") == "2.12.5"
    starlette = _package_version(lock, "starlette")
    parts = tuple(int(part) for part in starlette.split(".")[:3])
    assert parts >= (1, 3, 1), starlette
    assert _package_version(lock, "httpx2") == "2.12.0"
