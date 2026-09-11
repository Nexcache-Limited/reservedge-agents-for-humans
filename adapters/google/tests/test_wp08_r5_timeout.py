"""WP-08-R5 live timeout ownership. Fake stays fast; live requires a bounded env."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from itaa_application.errors import ApplicationError
from itaa_google_adapter.agent import compose_agent
from itaa_google_adapter.app import create_google_app
from itaa_google_adapter.fake import FakeModel
from itaa_google_adapter.resilience import (
    APPROVED_LIVE_TIMEOUT_MS,
    FAKE_TIMEOUT_MS,
    LIVE_TIMEOUT_MAX_MS,
    parse_live_timeout_ms,
    production_resilience_policy,
)


def test_fake_composition_ignores_unset_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ITAA_GOOGLE_TIMEOUT_MS", raising=False)
    monkeypatch.delenv("ITAA_GOOGLE_MODEL_MODE", raising=False)
    agent = compose_agent()
    assert isinstance(agent._model, FakeModel)  # noqa: SLF001
    assert agent._policy.timeout_ms == FAKE_TIMEOUT_MS  # noqa: SLF001


def test_valid_live_timeout_is_applied(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ITAA_GOOGLE_MODEL_MODE", "live")
    monkeypatch.setenv("ITAA_GOOGLE_TIMEOUT_MS", str(APPROVED_LIVE_TIMEOUT_MS))
    policy = production_resilience_policy()
    assert policy.timeout_ms == APPROVED_LIVE_TIMEOUT_MS
    assert policy.max_attempts == 2
    agent = compose_agent()
    assert type(agent._model).__name__ == "LiveModel"  # noqa: SLF001
    assert agent._policy.timeout_ms == APPROVED_LIVE_TIMEOUT_MS  # noqa: SLF001
    assert agent._policy.max_attempts == 2  # noqa: SLF001


def test_missing_live_timeout_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ITAA_GOOGLE_MODEL_MODE", "live")
    monkeypatch.delenv("ITAA_GOOGLE_TIMEOUT_MS", raising=False)
    with pytest.raises(ApplicationError, match="model: schema_invalid"):
        parse_live_timeout_ms()
    with pytest.raises(ApplicationError, match="model: schema_invalid"):
        compose_agent()


@pytest.mark.parametrize(
    "raw",
    ["", "abc", "30.0", "-1", "0", "2000", str(LIVE_TIMEOUT_MAX_MS + 1), "60000", "030000"],
)
def test_invalid_or_excessive_timeout_fails_closed(
    monkeypatch: pytest.MonkeyPatch, raw: str
) -> None:
    monkeypatch.setenv("ITAA_GOOGLE_MODEL_MODE", "live")
    monkeypatch.setenv("ITAA_GOOGLE_TIMEOUT_MS", raw)
    with pytest.raises(ApplicationError, match="model: schema_invalid"):
        parse_live_timeout_ms()
    with pytest.raises(ApplicationError, match="model: schema_invalid"):
        compose_agent()


def test_injected_policy_remains_the_single_deadline() -> None:
    from itaa_google_adapter.resilience import ResiliencePolicy

    policy = ResiliencePolicy(timeout_ms=40, max_attempts=1)
    agent = compose_agent(policy=policy)
    assert agent._policy is policy  # noqa: SLF001
    assert agent._policy.timeout_ms == 40  # noqa: SLF001


def test_readyz_does_not_expose_timeout_or_project(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ITAA_GOOGLE_MODEL_MODE", "live")
    monkeypatch.setenv("ITAA_GOOGLE_TIMEOUT_MS", str(APPROVED_LIVE_TIMEOUT_MS))
    monkeypatch.setenv("GOOGLE_GENAI_USE_VERTEXAI", "true")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "owner-project")
    monkeypatch.setenv("ITAA_GCP_REGION", "us-central1")
    client = TestClient(create_google_app())
    ready = client.get("/readyz")
    dumped = ready.text.lower()
    assert "30000" not in dumped
    assert "timeout" not in dumped
    assert "owner-project" not in dumped
    assert "itaa-g1-dev" not in dumped
    assert "begin private key" not in dumped
