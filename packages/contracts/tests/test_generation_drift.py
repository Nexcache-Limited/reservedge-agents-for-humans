from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from itaa_validate_contracts.drift import check_drift
from itaa_validate_contracts.generate import committed_python_dir, committed_typescript_dir


def _tree_digest(directory: Path) -> dict[str, str]:
    digest: dict[str, str] = {}
    for path in sorted(directory.rglob("*")):
        if path.is_file() and path.name != ".DS_Store":
            if any(part == "__pycache__" or part.endswith(".pyc") for part in path.parts):
                continue
            digest[path.relative_to(directory).as_posix()] = hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
    return digest


@pytest.mark.contract
def test_committed_generated_output_matches_regeneration() -> None:
    python_before = _tree_digest(committed_python_dir())
    typescript_before = _tree_digest(committed_typescript_dir())
    assert check_drift() == []
    assert _tree_digest(committed_python_dir()) == python_before
    assert _tree_digest(committed_typescript_dir()) == typescript_before


@pytest.mark.contract
def test_intentional_generated_edit_is_detected_then_restored() -> None:
    target = next((committed_python_dir() / "itaa_contracts_generated").glob("offer.py"))
    original = target.read_text(encoding="utf-8")
    try:
        target.write_text(original + "\n# intentional-drift\n", encoding="utf-8")
        violations = check_drift()
        assert any(item.keyword == "drift" for item in violations)
    finally:
        target.write_text(original, encoding="utf-8")
    assert check_drift() == []
    assert target.read_text(encoding="utf-8") == original
