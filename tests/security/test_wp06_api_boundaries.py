from __future__ import annotations

from pathlib import Path

from boundaries import FORBIDDEN_APPLICATION_MODULES, FORBIDDEN_CORE_MODULES, scan_tree

REPO = Path(__file__).resolve().parents[2]


def test_application_still_forbids_fastapi_and_simulator() -> None:
    violations = scan_tree(REPO / "packages" / "application" / "src", FORBIDDEN_APPLICATION_MODULES)
    assert violations == []


def test_api_may_import_fastapi_but_not_cloud_or_vercel() -> None:
    forbidden = FORBIDDEN_CORE_MODULES - {"fastapi", "starlette", "uvicorn"}
    violations = scan_tree(REPO / "apps" / "api" / "src", forbidden)
    assert violations == []


def test_api_manifest_does_not_add_provider_sdks() -> None:
    text = (REPO / "apps" / "api" / "pyproject.toml").read_text(encoding="utf-8")
    for needle in ("vercel", "boto3", "sqlalchemy", "redis", "celery", "revenuecat"):
        assert needle not in text.lower()
