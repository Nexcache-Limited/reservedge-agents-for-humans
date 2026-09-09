from __future__ import annotations

import sys

import pytest
from wp08_helpers import CORRELATION, JFK_TEXT

from itaa_application.errors import ApplicationError
from itaa_google_adapter.agent import compose_agent
from itaa_google_adapter.fake import FakeModel
from itaa_google_adapter.mode import resolve_model_mode
from itaa_google_adapter.ports import ExtractionRequest, ModelRequest


def test_default_mode_is_fake_and_deterministic(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ITAA_GOOGLE_MODEL_MODE", raising=False)
    monkeypatch.delenv("ITAA_GOOGLE_LIVE", raising=False)
    sys.modules.pop("itaa_google_adapter.live", None)
    assert resolve_model_mode() == "fake"
    agent = compose_agent()
    assert isinstance(agent._model, FakeModel)  # noqa: SLF001
    assert "itaa_google_adapter.live" not in sys.modules
    first = agent.extract(ExtractionRequest(JFK_TEXT, "airport_parking", CORRELATION))
    second = compose_agent().extract(ExtractionRequest(JFK_TEXT, "airport_parking", CORRELATION))
    assert first.proposal == second.proposal


def test_unknown_mode_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ITAA_GOOGLE_MODEL_MODE", "prod")
    with pytest.raises(ApplicationError, match="model: schema_invalid"):
        resolve_model_mode()
    with pytest.raises(ApplicationError, match="model: schema_invalid"):
        compose_agent()


def test_live_mode_wires_live_model_not_fake(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ITAA_GOOGLE_MODEL_MODE", "live")
    monkeypatch.setenv("ITAA_GOOGLE_TIMEOUT_MS", "30000")
    agent = compose_agent()
    model = agent._model  # noqa: SLF001
    assert type(model).__name__ == "LiveModel"
    assert type(model).__module__ == "itaa_google_adapter.live"
    assert not isinstance(model, FakeModel)


def test_live_misconfig_does_not_fall_back_to_fake(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ITAA_GOOGLE_MODEL_MODE", "live")
    monkeypatch.setenv("ITAA_GOOGLE_TIMEOUT_MS", "30000")
    monkeypatch.delenv("GOOGLE_GENAI_USE_VERTEXAI", raising=False)
    monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)
    agent = compose_agent()
    model = agent._model  # noqa: SLF001
    assert type(model).__name__ == "LiveModel"
    assert not isinstance(model, FakeModel)
    with pytest.raises(ApplicationError, match="model: unavailable"):
        model.complete(
            ModelRequest(
                task="extract",
                correlation_id=CORRELATION,
                payload={"text": JFK_TEXT, "category": "airport_parking"},
            )
        )


def test_deprecated_live_alias_selects_live_only_when_mode_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ITAA_GOOGLE_MODEL_MODE", raising=False)
    monkeypatch.setenv("ITAA_GOOGLE_LIVE", "1")
    assert resolve_model_mode() == "live"
    monkeypatch.setenv("ITAA_GOOGLE_MODEL_MODE", "fake")
    assert resolve_model_mode() == "fake"
    assert isinstance(compose_agent()._model, FakeModel)  # noqa: SLF001
