from __future__ import annotations

from wp08_helpers import locked_ranking_facts

from itaa_google_adapter.agent import compose_agent
from itaa_google_adapter.explanation import deterministic_explanation, ground_explanation
from itaa_google_adapter.fake import FakeModel
from itaa_google_adapter.ports import ExplanationRequest


def test_fake_explanation_names_skyshield_without_changing_numbers() -> None:
    facts = locked_ranking_facts()
    result = compose_agent().explain(ExplanationRequest(facts=facts))
    assert "SkyShield" in result.explanation
    assert "671000" not in result.explanation.replace(",", "")
    assert "999999" not in result.explanation
    assert result.grounded is True


def test_price_ranking_hallucination_is_replaced() -> None:
    facts = locked_ranking_facts()
    result = compose_agent(model=FakeModel(hallucinate_scores=True)).explain(
        ExplanationRequest(facts=facts)
    )
    assert result.explanation == deterministic_explanation(facts)
    assert result.fallback == "deterministic_facts"


def test_explanation_contradicting_winner_is_replaced() -> None:
    facts = locked_ranking_facts()
    result = compose_agent(model=FakeModel(contradict_winner=True)).explain(
        ExplanationRequest(facts=facts)
    )
    assert result.explanation == deterministic_explanation(facts)
    assert "ParkDirect is recommended" not in result.explanation


def test_grounding_rejects_wrong_scores_directly() -> None:
    facts = locked_ranking_facts()
    result = ground_explanation("SkyShield wins with score 888888 and downside 1.", facts)
    assert result.fallback == "deterministic_facts"
