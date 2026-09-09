from __future__ import annotations

from pathlib import Path

from boundaries import (
    FORBIDDEN_APPLICATION_MODULES,
    FORBIDDEN_CORE_MODULES,
    scan_python_file,
    scan_tree,
)

REPO = Path(__file__).resolve().parents[2]


def test_progress_port_stays_provider_neutral() -> None:
    progress = REPO / "packages" / "application" / "src" / "itaa_application" / "progress_events.py"
    bus = REPO / "packages" / "application" / "src" / "itaa_application" / "local_progress.py"
    assert scan_python_file(progress, FORBIDDEN_APPLICATION_MODULES) == []
    assert scan_python_file(bus, FORBIDDEN_APPLICATION_MODULES) == []
    source = progress.read_text(encoding="utf-8")
    for needle in ("fastapi", "google", "boto3", "redis", "kafka", "starlette"):
        assert needle not in source.lower()


def test_api_progress_module_does_not_import_cloud_or_vercel() -> None:
    forbidden = FORBIDDEN_CORE_MODULES - {"fastapi", "starlette", "uvicorn"}
    violations = scan_tree(REPO / "apps" / "api" / "src", forbidden)
    assert violations == []
    sse = (REPO / "apps" / "api" / "src" / "itaa_api" / "progress_sse.py").read_text(
        encoding="utf-8"
    )
    assert "from redis" not in sse
    assert "import kafka" not in sse
    assert "import websocket" not in sse.lower()
    assert "vercel" not in sse.lower()
