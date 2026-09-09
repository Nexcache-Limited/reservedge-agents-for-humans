from __future__ import annotations

import sys

import pytest

from itaa_application.errors import ApplicationError
from itaa_aws_adapter.agent import FakeOrchestrator, compose_orchestrator
from itaa_aws_adapter.mode import resolve_model_mode


def test_default_mode_is_fake_and_does_not_import_live(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ITAA_AWS_MODEL_MODE", raising=False)
    monkeypatch.delenv("ITAA_AWS_LIVE", raising=False)
    sys.modules.pop("itaa_aws_adapter.live", None)
    assert resolve_model_mode() == "fake"
    agent = compose_orchestrator()
    assert isinstance(agent._inner, FakeOrchestrator)  # noqa: SLF001
    assert "itaa_aws_adapter.live" not in sys.modules


def test_unknown_mode_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ITAA_AWS_MODEL_MODE", "prod")
    with pytest.raises(ApplicationError, match="model: schema_invalid"):
        resolve_model_mode()
    with pytest.raises(ApplicationError, match="model: schema_invalid"):
        compose_orchestrator()


def test_live_mode_does_not_use_fake(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ITAA_AWS_MODEL_MODE", "live")
    monkeypatch.setenv("ITAA_AWS_TIMEOUT_MS", "30000")
    agent = compose_orchestrator()
    inner = agent._inner  # noqa: SLF001
    assert type(inner).__name__ == "LiveOrchestrator"
    assert type(inner).__module__ == "itaa_aws_adapter.live"
    assert not isinstance(inner, FakeOrchestrator)


def test_live_does_not_fall_back_to_fake(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ITAA_AWS_MODEL_MODE", "live")
    monkeypatch.setenv("ITAA_AWS_TIMEOUT_MS", "30000")
    agent = compose_orchestrator()
    inner = agent._inner  # noqa: SLF001
    assert type(inner).__name__ == "LiveOrchestrator"
    with pytest.raises(ApplicationError, match="model: unavailable"):
        inner.plan_turn("hello")


def test_live_unknown_model_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ITAA_AWS_MODEL_MODE", "live")
    monkeypatch.setenv("ITAA_AWS_TIMEOUT_MS", "30000")
    monkeypatch.setenv("ITAA_AWS_MODEL", "anthropic.claude-opus-4")
    with pytest.raises(ApplicationError, match="model: schema_invalid"):
        compose_orchestrator()


def test_deprecated_live_alias_selects_live_only_when_mode_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ITAA_AWS_MODEL_MODE", raising=False)
    monkeypatch.setenv("ITAA_AWS_LIVE", "1")
    monkeypatch.setenv("ITAA_AWS_TIMEOUT_MS", "30000")
    assert resolve_model_mode() == "live"
    monkeypatch.setenv("ITAA_AWS_MODEL_MODE", "fake")
    assert resolve_model_mode() == "fake"
    assert isinstance(compose_orchestrator()._inner, FakeOrchestrator)  # noqa: SLF001


def test_live_timeout_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ITAA_AWS_MODEL_MODE", "live")
    monkeypatch.delenv("ITAA_AWS_TIMEOUT_MS", raising=False)
    with pytest.raises(ApplicationError, match="model: schema_invalid"):
        compose_orchestrator()
    monkeypatch.setenv("ITAA_AWS_TIMEOUT_MS", "1000")
    with pytest.raises(ApplicationError, match="model: schema_invalid"):
        compose_orchestrator()
