"""Cloud Run live config must set the bounded timeout without a project id."""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
INFRA = REPO / "infra" / "google"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_cloudrun_sets_approved_live_timeout() -> None:
    manifest = _read(INFRA / "cloudrun.yaml")
    assert "ITAA_GOOGLE_TIMEOUT_MS" in manifest
    assert (
        'value: "30000"' in manifest or "value: '30000'" in manifest or "value: 30000" in manifest
    )
    assert "timeoutSeconds: 60" in manifest
    assert "example-gcp-project" not in manifest
    assert ":latest" not in manifest


def test_env_example_documents_timeout_without_project() -> None:
    example = _read(INFRA / "env.example")
    assert "ITAA_GOOGLE_TIMEOUT_MS" in example
    assert "30000" in example
    assert "example-gcp-project" not in example
    assert "AIza" not in example
