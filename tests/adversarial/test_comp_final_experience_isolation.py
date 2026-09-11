from __future__ import annotations

import pytest

from itaa_aws_adapter.agent import compose_orchestrator
from itaa_aws_adapter.projector import extract_facts, project_plan
from itaa_aws_adapter.schemas import PlanAnswers

MILAN = "I'm travelling to Milan from Mumbai from 20 to 30 October"


def test_experience_search_never_returns_stay_or_parking_inventory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ITAA_EXPERIENCE_SEARCH_MODE", "fake")
    monkeypatch.delenv("ITAA_PRIOTICKET_CLIENT_SECRET", raising=False)
    agent = compose_orchestrator()
    result = agent.execute_turn(
        "search_experience_offers",
        {"destination": "Milan", "preferences": ["evening"]},
    )
    blob = str(result).lower()
    assert "skyshield" not in blob
    assert "parkdirect" not in blob
    assert "spadari" not in blob
    assert result.get("bookingAuthority") == "none"
    assert "client_secret" not in blob
    offers = result.get("offers")
    assert isinstance(offers, list)
    for offer in offers:
        assert isinstance(offer, dict)
        assert "title" in offer
        assert "checkIn" not in offer


def test_experience_does_not_leak_jfk_from_new_york() -> None:
    facts = extract_facts("Find museum options in New York")
    assert facts.destination == "New York"
    assert facts.experienceStated is True
    assert facts.parkingAirport != "JFK"
    projection = project_plan("Find museum options in New York")
    assert "jfk" not in projection.model_dump_json().lower()


def test_checkout_overlay_does_not_invent_experience() -> None:
    facts = extract_facts(f"{MILAN} Change my hotel checkout to 31 October")
    assert facts.experienceStated is False
    assert facts.endDate == "2026-10-31"
    _ = PlanAnswers()
