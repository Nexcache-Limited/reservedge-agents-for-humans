from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

PROVIDER_SUBSTRINGS = (
    "google-adk",
    "google-generativeai",
    "google-cloud-aiplatform",
    "boto3",
    "botocore",
    "strands-agents",
    "amazon-bedrock",
    "revenuecat",
    "@revenuecat",
    "react-native",
    '"expo"',
    "sqlalchemy",
)

# React/Vite is authorized only for apps/web (UI-01). Core and shared
# TypeScript packages still must not depend on them.
CORE_REACT_SUBSTRINGS = (
    "react-dom",
    '"react"',
)

CORE_MANIFESTS = (
    "package.json",
    "ui-kit-package.json",
    "contracts-package.json",
    "pyproject.toml",
    "uv.lock",
    "domain-pyproject",
    "application-pyproject",
    "policy-pyproject",
    "observability-pyproject",
    "ranking-pyproject",
    "simulator-pyproject",
)

CORE_FORBIDDEN_FASTAPI = (
    "pyproject.toml",
    "domain-pyproject",
    "application-pyproject",
    "policy-pyproject",
    "observability-pyproject",
    "ranking-pyproject",
    "simulator-pyproject",
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def test_lockfiles_and_manifests_exclude_provider_and_product_sdks() -> None:
    haystacks = {
        "pyproject.toml": _read(REPO_ROOT / "pyproject.toml"),
        "uv.lock": _read(REPO_ROOT / "uv.lock"),
        "package.json": _read(REPO_ROOT / "package.json"),
        "ui-kit-package.json": _read(REPO_ROOT / "packages" / "ui-kit" / "package.json"),
        "contracts-package.json": _read(REPO_ROOT / "packages" / "contracts" / "package.json"),
        "pnpm-lock.yaml": _read(REPO_ROOT / "pnpm-lock.yaml"),
        "domain-pyproject": _read(REPO_ROOT / "packages" / "domain" / "pyproject.toml"),
        "application-pyproject": _read(REPO_ROOT / "packages" / "application" / "pyproject.toml"),
        "policy-pyproject": _read(REPO_ROOT / "packages" / "policy" / "pyproject.toml"),
        "observability-pyproject": _read(
            REPO_ROOT / "packages" / "observability" / "pyproject.toml"
        ),
        "ranking-pyproject": _read(REPO_ROOT / "packages" / "ranking" / "pyproject.toml"),
        "simulator-pyproject": _read(REPO_ROOT / "apps" / "supplier-simulator" / "pyproject.toml"),
    }
    failures: list[str] = []
    for label, text in haystacks.items():
        for needle in PROVIDER_SUBSTRINGS:
            if needle in text:
                if label == "uv.lock" and needle.startswith("google-"):
                    continue
                # AWS live extra: strands-agents==1.54.0 pulls boto3/botocore into uv.lock only.
                if label == "uv.lock" and needle in {"strands-agents", "boto3", "botocore"}:
                    continue
                failures.append(f"{label} contains {needle}")
        if label in CORE_MANIFESTS:
            for needle in CORE_REACT_SUBSTRINGS:
                if needle in text:
                    failures.append(f"{label} contains {needle}")
        if label in CORE_FORBIDDEN_FASTAPI and '"fastapi"' in text:
            failures.append(f"{label} contains fastapi")
    assert failures == []
