from __future__ import annotations

import pytest

from itaa_aws_adapter.agent import compose_orchestrator
from itaa_aws_adapter.projector import extract_facts, project_plan
from itaa_aws_adapter.schemas import PlanAnswers

MILAN = "I'm travelling to Milan from Mumbai from 20 to 30 October"
PARK = "I need parking at JFK from 3 to 8 September"
RENTAL = "I need a rental car in Edinburgh 14–19 October 2026"


def test_milan_does_not_map_to_jfk_or_parking() -> None:
    facts = extract_facts(MILAN)
    assert facts.destination == "Milan"
    assert facts.originCity == "Mumbai"
    assert facts.parkingStated is False
    assert facts.parkingAirport == ""
    projection = project_plan(MILAN)
    assert all(task.kind != "parking" for task in projection.tasks)
    blob = projection.model_dump_json().lower()
    assert "jfk" not in blob
    assert "parkdirect" not in blob
    assert "skyshield" not in blob


def test_parking_and_rental_remain_isolated_from_stay_research() -> None:
    parking = project_plan(PARK)
    rental = project_plan(RENTAL)
    park_kinds = {task.kind for task in parking.tasks}
    rent_kinds = {task.kind for task in rental.tasks}
    assert "parking" in park_kinds
    assert parking.facts.parkingAirport == "JFK"
    assert parking.facts.destination != "Milan"
    assert "rental" in rent_kinds
    assert rental.facts.destination == "Edinburgh"
    milan = project_plan(MILAN)
    assert {task.kind for task in milan.tasks}.isdisjoint({"parking"})
    combined = project_plan(f"{MILAN} I also need parking at JFK")
    kinds = {task.kind: task for task in combined.tasks}
    assert kinds["parking"].provenance == "explicit"
    assert combined.facts.parkingAirport == "JFK"
    assert combined.facts.destination == "Milan"


def test_stay_search_never_returns_parking_inventory(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ITAA_STAY_SEARCH_MODE", "fake")
    monkeypatch.delenv("ITAA_LITEAPI_API_KEY", raising=False)
    agent = compose_orchestrator()
    _model, projection, _events = agent.plan_turn(MILAN, PlanAnswers())
    assert projection.facts.destination == "Milan"
    result = agent.execute_turn(
        "search_stay_offers",
        {
            "destination": projection.facts.destination,
            "checkIn": projection.facts.startDate,
            "checkOut": projection.facts.endDate,
            "origin": projection.facts.originCity,
        },
    )
    blob = str(result).lower()
    assert "skyshield" not in blob
    assert "parkdirect" not in blob
    assert "terminalflex" not in blob
    assert result.get("bookingAuthority") == "none"
