from __future__ import annotations

import sys

from wp08_helpers import CORRELATION, JFK_TEXT, locked_ranking_facts

from itaa_application.errors import ApplicationError
from itaa_google_adapter.agent import compose_agent
from itaa_google_adapter.fake import FakeModel
from itaa_google_adapter.ports import ExplanationRequest, ExtractionRequest, ModelRequest


def test_default_agent_is_fake_and_does_not_import_live() -> None:
    sys.modules.pop("itaa_google_adapter.live", None)
    agent = compose_agent()
    result = agent.extract(
        ExtractionRequest(text=JFK_TEXT, category="airport_parking", correlation_id=CORRELATION)
    )
    assert result.proposal is not None
    assert "itaa_google_adapter.live" not in sys.modules
    assert isinstance(agent._model, FakeModel)  # noqa: SLF001


def test_over_disclosure_never_auto_creates_intent() -> None:
    text = (
        f"{JFK_TEXT} Email buyer@example.com. Charge visa 4111111111111111. "
        "Full itinerary dump PNR XYZABC flight AA100 passenger synthetic-user."
    )
    result = compose_agent().extract(
        ExtractionRequest(text=text, category="airport_parking", correlation_id=CORRELATION)
    )
    assert result.proposal is None
    assert result.accepted is False
    assert result.requires_a1 is True


def test_unsupported_category_fails_closed() -> None:
    try:
        compose_agent().extract(
            ExtractionRequest(text=JFK_TEXT, category="hotel", correlation_id=CORRELATION)
        )
    except ApplicationError as exc:
        assert exc.field == "category"
        assert exc.code == "must_be_airport_parking"
    else:
        raise AssertionError("expected category failure")


def test_explanation_uses_locked_facts() -> None:
    result = compose_agent().explain(ExplanationRequest(facts=locked_ranking_facts()))
    assert "SkyShield" in result.explanation
    assert result.grounded is True


def test_live_model_is_unavailable_without_opt_in() -> None:
    from itaa_google_adapter.live import LiveModel, describe_live_path

    described = describe_live_path()
    assert described["model"] == "gemini-2.5-flash"
    assert described["region"] == "us-central1"
    assert described["sdk"] == "google.adk"
    try:
        LiveModel().complete(ModelRequest(task="extract", correlation_id=CORRELATION, payload={}))
    except ApplicationError as exc:
        assert exc.field == "model"
        assert exc.code == "unavailable"
    else:
        raise AssertionError("expected live model unavailable")
