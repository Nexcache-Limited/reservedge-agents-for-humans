from __future__ import annotations

import ast
from pathlib import Path

from wp05_ranking_helpers import rank_golden  # type: ignore[import-not-found]

from itaa_google_adapter.app import CLOUDFLARE_PAGES_PLACEHOLDER, DEFAULT_CORS_ORIGIN

REPO = Path(__file__).resolve().parents[2]
ADAPTER_SRC = REPO / "adapters" / "google" / "src" / "itaa_google_adapter"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def test_google_imports_stay_in_live_py() -> None:
    for path in ADAPTER_SRC.glob("*.py"):
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            else:
                continue
            for name in names:
                if name == "google" or name.startswith("google."):
                    assert path.name == "live.py", f"{path} imports {name}"


def test_lock_marks_google_adk_as_live_extra_only() -> None:
    lock = _read(REPO / "uv.lock")
    assert 'name = "google-adk"' in lock
    assert "google-adk==2.7.1" in _read(REPO / "adapters" / "google" / "pyproject.toml")
    assert "marker = \"extra == 'live'\"" in lock
    assert 'provides-extras = ["live"]' in lock
    adapter_block = lock.split('name = "itaa-google-adapter"', 1)[1].split("[[package]]", 1)[0]
    default_deps = adapter_block.split("[package.optional-dependencies]", 1)[0]
    assert "google-adk" not in default_deps


def test_dev_group_installs_live_extra_for_non_credentialed_adk_shape() -> None:
    import google.adk

    assert google.adk.__name__ == "google.adk"


def test_dockerfile_installs_adapter_live_extra() -> None:
    dockerfile = _read(REPO / "infra" / "google" / "Dockerfile")
    assert "uv sync --frozen --package itaa-google-adapter --extra live" in dockerfile
    assert "python:3.12" in dockerfile
    assert "useradd" in dockerfile
    assert "nonroot" in dockerfile
    assert "vercel" not in dockerfile.lower()


def test_cloudrun_manifest_selects_live_mode() -> None:
    manifest = _read(REPO / "infra" / "google" / "cloudrun.yaml")
    assert "ITAA_GOOGLE_MODEL_MODE" in manifest
    assert "value: live" in manifest
    assert "GOOGLE_GENAI_USE_VERTEXAI" in manifest
    assert "gemini-2.5-flash" in manifest
    assert "us-central1" in manifest
    assert "ITAA_GOOGLE_LIVE" not in manifest
    assert "AIza" not in manifest
    assert "BEGIN PRIVATE KEY" not in manifest


def test_no_secrets_committed_in_adapter_or_infra() -> None:
    needles = ("AIza", "GEMINI_API_KEY=", "BEGIN PRIVATE KEY", "sk-")
    for root in (REPO / "adapters" / "google", REPO / "infra" / "google"):
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix in {".png", ".jpg", ".pyc"}:
                continue
            if "tests" in path.parts:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            for needle in needles:
                assert needle not in text, f"{path} contains {needle}"


def test_cors_restricted_to_cloudflare_and_local_origins() -> None:
    assert DEFAULT_CORS_ORIGIN == "http://localhost:5173"
    assert CLOUDFLARE_PAGES_PLACEHOLDER == "https://app.example.invalid"


def test_locked_jfk_ranking_unchanged() -> None:
    result = rank_golden()
    assert [item.score_micros for item in result.ranked] == [671_000, 660_000, 535_000]
    assert result.recommended_offer_id is not None
    assert result.downside is not None
    assert result.downside.delta == 2900
    winner = result.ranked[0]
    assert winner.total_minor == 14_800
