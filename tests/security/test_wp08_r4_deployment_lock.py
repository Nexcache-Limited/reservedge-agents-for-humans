"""Deployment evidence must not leak into reusable production templates."""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ADAPTER_SRC = REPO / "adapters" / "google" / "src"
INFRA = REPO / "infra" / "google"
EVIDENCE = INFRA / "DEPLOYMENT.md"
OWNER_PROJECT = "example-gcp-project"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_owner_project_is_not_in_reusable_production_source() -> None:
    templates = (
        INFRA / "env.example",
        INFRA / "cloudrun.yaml",
        INFRA / "Dockerfile",
        REPO / ".env.example",
    )
    for path in templates:
        assert OWNER_PROJECT not in _read(path), path
    for path in ADAPTER_SRC.rglob("*.py"):
        assert OWNER_PROJECT not in path.read_text(encoding="utf-8"), path


def test_deployment_evidence_locks_future_resource_names() -> None:
    text = _read(EVIDENCE)
    assert "deployment evidence" in text.lower()
    assert OWNER_PROJECT in text
    assert "us-central1" in text
    assert "itaa-containers" in text
    assert "google-adapter" in text
    assert "itaa-google-adapter" in text
    assert "runtime@example-gcp-project.iam.gserviceaccount.com" in text
    assert "gemini-2.5-flash" in text
    assert "private" in text.lower()
    assert "unauthenticated" in text.lower()
    assert "prohibited" in text.lower()
    assert "unused-runtime@example-gcp-project.iam.gserviceaccount.com" in text
    assert "not** use" in text.lower() or "do not use" in text.replace("*", "").lower()
    assert ":latest" in text
    assert "@sha256:" in text
    assert "git-sha" in text
    assert "AIza" not in text
    assert "BEGIN PRIVATE KEY" not in text


def test_generic_cloudrun_image_is_not_latest() -> None:
    manifest = _read(INFRA / "cloudrun.yaml")
    assert ":latest" not in manifest
    assert "itaa-google-adapter:local" in manifest
