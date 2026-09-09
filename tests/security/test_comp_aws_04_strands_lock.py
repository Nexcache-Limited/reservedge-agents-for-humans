"""COMP-AWS-04: Strands/boto3 stay out of core; browser never calls /v1/aws; no VITE secrets."""

from __future__ import annotations

from pathlib import Path

import pytest

from boundaries import (
    FORBIDDEN_APPLICATION_MODULES,
    FORBIDDEN_CORE_MODULES,
    FORBIDDEN_DOMAIN_MODULES,
    FORBIDDEN_POLICY_MODULES,
    FORBIDDEN_RANKING_MODULES,
    scan_tree,
)
from itaa_application.errors import ApplicationError
from itaa_aws_adapter.agent import FakeOrchestrator, compose_orchestrator
from itaa_aws_adapter.mode import resolve_model_mode

REPO = Path(__file__).resolve().parents[2]
WEB = REPO / "apps" / "web"
ADAPTER_NEEDLES = frozenset({"strands", "boto3", "botocore", "bedrock"})


def test_domain_and_application_do_not_import_strands_or_boto3() -> None:
    trees = (
        (REPO / "packages" / "domain" / "src", FORBIDDEN_DOMAIN_MODULES),
        (REPO / "packages" / "application" / "src", FORBIDDEN_APPLICATION_MODULES),
        (REPO / "packages" / "policy" / "src", FORBIDDEN_POLICY_MODULES),
        (REPO / "packages" / "ranking" / "src", FORBIDDEN_RANKING_MODULES),
        (
            REPO / "apps" / "api" / "src",
            FORBIDDEN_CORE_MODULES - {"fastapi", "starlette", "uvicorn"},
        ),
    )
    failures: list[str] = []
    for root, forbidden in trees:
        for item in scan_tree(root, forbidden):
            if any(needle in item.message for needle in ADAPTER_NEEDLES):
                failures.append(f"{item.path}: {item.message}")
    assert failures == []


def test_browser_sources_never_call_v1_aws() -> None:
    failures: list[str] = []
    for path in WEB.joinpath("src").rglob("*"):
        if path.suffix not in {".ts", ".tsx"}:
            continue
        if path.name.endswith(".test.ts") or path.name.endswith(".test.tsx"):
            continue
        if "/v1/aws" in path.read_text(encoding="utf-8"):
            failures.append(str(path.relative_to(REPO)))
    assert failures == []


def test_no_aws_secrets_in_vite_env() -> None:
    haystacks: list[str] = []
    haystacks.append((WEB / "package.json").read_text(encoding="utf-8"))
    for path in WEB.rglob("*"):
        if "node_modules" in path.parts or "dist" in path.parts or "coverage" in path.parts:
            continue
        is_source = path.suffix in {".ts", ".tsx", ".js", ".env", ".example"}
        if is_source or path.name.startswith(".env"):
            haystacks.append(path.read_text(encoding="utf-8", errors="ignore"))
    blob = "\n".join(haystacks)
    assert "VITE_ITAA_AWS" not in blob
    assert "VITE_AWS" not in blob
    assert "AWS_SECRET_ACCESS_KEY" not in blob
    assert "AWS_ACCESS_KEY_ID" not in blob


def test_live_mode_never_silently_uses_fake(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ITAA_AWS_MODEL_MODE", "live")
    monkeypatch.setenv("ITAA_AWS_TIMEOUT_MS", "30000")
    agent = compose_orchestrator()
    inner = agent._inner  # noqa: SLF001
    assert type(inner).__name__ == "LiveOrchestrator"
    assert not isinstance(inner, FakeOrchestrator)
    with pytest.raises(ApplicationError, match="model: unavailable"):
        inner.plan_turn("hello")


def test_unknown_live_mode_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ITAA_AWS_MODEL_MODE", "prod")
    with pytest.raises(ApplicationError, match="model: schema_invalid"):
        resolve_model_mode()
    with pytest.raises(ApplicationError, match="model: schema_invalid"):
        compose_orchestrator()
