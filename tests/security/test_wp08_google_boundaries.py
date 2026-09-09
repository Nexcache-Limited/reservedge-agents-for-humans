from __future__ import annotations

import ast
from pathlib import Path

from boundaries import (
    FORBIDDEN_APPLICATION_MODULES,
    FORBIDDEN_CORE_MODULES,
    FORBIDDEN_DOMAIN_MODULES,
    FORBIDDEN_POLICY_MODULES,
    FORBIDDEN_RANKING_MODULES,
    imported_modules,
    scan_tree,
)

REPO = Path(__file__).resolve().parents[2]
ADAPTER_SRC = REPO / "adapters" / "google" / "src" / "itaa_google_adapter"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def test_protected_core_has_no_google_imports() -> None:
    trees = (
        (REPO / "packages" / "domain" / "src", FORBIDDEN_DOMAIN_MODULES),
        (REPO / "packages" / "application" / "src", FORBIDDEN_APPLICATION_MODULES),
        (REPO / "packages" / "policy" / "src", FORBIDDEN_POLICY_MODULES),
        (REPO / "packages" / "ranking" / "src", FORBIDDEN_RANKING_MODULES),
        (REPO / "packages" / "contracts", FORBIDDEN_CORE_MODULES),
        (REPO / "apps" / "supplier-simulator" / "src", FORBIDDEN_CORE_MODULES),
        (
            REPO / "apps" / "api" / "src",
            FORBIDDEN_CORE_MODULES - {"fastapi", "starlette", "uvicorn"},
        ),
    )
    failures: list[str] = []
    for root, forbidden in trees:
        for item in scan_tree(root, forbidden):
            if "google" in item.message:
                failures.append(f"{item.path}: {item.message}")
    assert failures == []


def test_google_adk_is_optional_extra_not_default_core_import() -> None:
    lock = _read(REPO / "uv.lock")
    root = _read(REPO / "pyproject.toml")
    adapter = _read(REPO / "adapters" / "google" / "pyproject.toml")
    assert "google-adk==2.7.1" in adapter
    assert 'live = ["google-adk==2.7.1"]' in adapter
    project = root.split("[tool.uv]", 1)[0]
    assert "google-adk" not in project
    assert "google-adk" in lock
    package = False
    extra_only = False
    current: str | None = None
    for line in lock.splitlines():
        if line.startswith("name = "):
            current = line.split("=", 1)[1].strip().strip('"')
            package = current == "itaa-google-adapter"
        if package and "google-adk" in line and "extra" in line:
            extra_only = True
    assert extra_only or "google-adk" in adapter


def test_vercel_absent_from_adapter_and_infra() -> None:
    assert "vercel" not in _read(REPO / "adapters" / "google" / "pyproject.toml").lower()
    assert not (REPO / "vercel.json").exists()
    assert not (REPO / "infra" / "google" / "vercel.json").exists()
    dockerfile = _read(REPO / "infra" / "google" / "Dockerfile").lower()
    cloudrun = _read(REPO / "infra" / "google" / "cloudrun.yaml").lower()
    assert "vercel" not in dockerfile
    assert "vercel" not in cloudrun


def test_live_py_is_only_adapter_module_that_may_mention_adk() -> None:
    for path in ADAPTER_SRC.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        if path.name == "live.py":
            assert "google.adk" in text
            continue
        assert "google.adk" not in text
        assert "from google" not in text
        assert "import google" not in text


def test_fake_py_does_not_import_google() -> None:
    source = (ADAPTER_SRC / "fake.py").read_text(encoding="utf-8")
    assert "google" not in imported_modules(source)
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert all(not alias.name.startswith("google") for alias in node.names)
        if isinstance(node, ast.ImportFrom) and node.module:
            assert not node.module.startswith("google")


def test_secret_and_config_scan_has_no_api_keys() -> None:
    needles = ("AIza", "GEMINI_API_KEY=", "BEGIN PRIVATE KEY", "sk-")
    roots = (REPO / "adapters" / "google", REPO / "infra" / "google")
    for root in roots:
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix in {".png", ".jpg"}:
                continue
            if "tests" in path.parts or path.suffix in {".pyc"}:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            for needle in needles:
                assert needle not in text, f"{path} contains {needle}"
