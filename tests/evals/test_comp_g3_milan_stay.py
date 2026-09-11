from __future__ import annotations

import pytest

from itaa_aws_adapter.agent import compose_orchestrator
from itaa_aws_adapter.projector import buyer_invite_copy, extract_facts, project_plan
from itaa_aws_adapter.schemas import PlanAnswers

MILAN = "I'm travelling to Milan from Mumbai from 20 to 30 October"
LONDON = "I'm travelling to London from Mumbai from 20 to 30 October"
NYC = "I'm travelling to New York from 20 to 30 October"
EDINBURGH = "Going to Edinburgh for a conference next weekend and I'll need a car."
HOTEL_RENTAL = "Flights are booked. I need a hotel and rental car."
PARKING = "I also need parking at Mumbai airport from 5am on the 20th until 8pm on the 30th."


def test_milan_keeps_destination_origin_dates_and_not_jfk() -> None:
    facts = extract_facts(MILAN)
    assert facts.destination == "Milan"
    assert facts.originCity == "Mumbai"
    assert facts.startDate == "2026-10-20"
    assert facts.endDate == "2026-10-30"
    assert facts.parkingAirport == ""
    assert facts.parkingStated is False
    assert facts.hotelStated is False
    assert facts.rentalStated is False
    assert "JFK" not in (facts.destinationAirport, facts.parkingAirport, facts.departureAirport)
    spoken = extract_facts("heading to Milan 20th October to 25th")
    assert spoken.destination == "Milan"
    assert spoken.hasExactDates is True
    assert spoken.startDate == "2026-10-20"
    assert spoken.endDate == "2026-10-25"
    london = extract_facts("travelling to London")
    assert london.destination == "London"
    assert "When are you travelling" in buyer_invite_copy(london)
    assert "Where and when" not in buyer_invite_copy(london)
    miami = extract_facts("Miami 15th October to 20th October, hotel")
    assert miami.destination == "Miami"
    assert miami.hotelStated is True
    assert miami.startDate == "2026-10-15"
    assert miami.endDate == "2026-10-20"
    inverted = extract_facts("Miami 20th October to 15th October, hotel")
    assert inverted.destination == "Miami"
    assert inverted.hasExactDates is False
    random_city = extract_facts("Osaka 15 to 20 October hotel")
    assert random_city.destination == "Osaka"
    projection = project_plan(MILAN)
    blob = projection.model_dump_json().lower()
    assert "jfk" not in blob
    assert "skyshield" not in blob
    assert projection.facts.destination == "Milan"
    kinds = {task.kind: task for task in projection.tasks}
    assert "parking" not in kinds
    assert "rental" not in kinds
    assert "hotel" not in kinds
    assert "flight" not in kinds
    assert not any(question.id == "helpWith" for question in projection.questions)
    assert projection.phase == "forming"


def test_london_and_new_york_are_not_hardcoded_milan() -> None:
    london = project_plan(LONDON)
    nyc = project_plan(NYC)
    assert london.facts.destination == "London"
    assert nyc.facts.destination == "New York"
    assert london.facts.parkingAirport != "JFK"
    assert nyc.facts.parkingAirport != "JFK"
    assert "jfk" not in london.model_dump_json().lower()
    assert "jfk" not in nyc.model_dump_json().lower()
    assert "parking" not in {task.kind for task in london.tasks}
    assert "parking" not in {task.kind for task in nyc.tasks}
    assert all(task.kind != "hotel" for task in london.tasks)
    assert all(task.kind != "hotel" for task in nyc.tasks)


def test_hotel_and_rental_become_explicit_after_buyer_names_them() -> None:
    projection = project_plan(f"{MILAN} {HOTEL_RENTAL}")
    by_kind = {task.kind: task for task in projection.tasks}
    assert by_kind["hotel"].provenance == "explicit"
    assert by_kind["rental"].provenance == "explicit"
    assert "parking" not in by_kind
    assert projection.facts.flightSatisfied is True
    assert projection.facts.flightStated is False
    assert all(task.kind != "flight" or task.provenance != "explicit" for task in projection.tasks)


def test_parking_activates_independently_with_mumbai_evidence() -> None:
    projection = project_plan(f"{MILAN} {HOTEL_RENTAL} {PARKING}")
    by_kind = {task.kind: task for task in projection.tasks}
    assert by_kind["parking"].provenance == "explicit"
    assert by_kind["hotel"].provenance == "explicit"
    assert by_kind["rental"].provenance == "explicit"
    assert projection.facts.originCity == "Mumbai"
    assert projection.facts.destination == "Milan"
    assert projection.facts.parkingAirport != "JFK"
    blob = projection.model_dump_json().lower()
    assert "jfk" not in blob


def test_edinburgh_uses_the_same_task_mechanism() -> None:
    facts = extract_facts(EDINBURGH)
    assert facts.destination == "Edinburgh"
    assert facts.rentalStated is True
    assert facts.conference is True
    assert facts.hotelStated is False
    projection = project_plan(EDINBURGH)
    by_kind = {task.kind: task for task in projection.tasks}
    assert by_kind["rental"].provenance == "explicit"
    assert by_kind["hotel"].provenance == "proposed"
    assert "parking" not in by_kind
    assert "milan" not in projection.model_dump_json().lower()
    assert not any(question.id == "helpWith" for question in projection.questions)


def test_chat_can_name_hotel_and_rental_together() -> None:
    projection = project_plan(f"{MILAN} I need a hotel and a rental car.")
    by_kind = {task.kind: task for task in projection.tasks}
    assert by_kind["hotel"].provenance == "explicit"
    assert by_kind["rental"].provenance == "explicit"
    kinds = [task.kind for task in projection.tasks]
    if "flight" in kinds:
        assert kinds.index("hotel") < kinds.index("flight")
    london = project_plan("I'm travelling to London from 20 to 25 October. hotel booking")
    london_kinds = [task.kind for task in london.tasks]
    assert london_kinds[0] == "hotel"
    if "flight" in london_kinds:
        assert london_kinds.index("hotel") < london_kinds.index("flight")
    assert not any(question.id == "helpWith" for question in projection.questions)
    assert not any(question.id == "departureAirport" for question in projection.questions)
    assert "jfk" not in projection.model_dump_json().lower()


def test_help_with_stay_makes_hotel_explicit_without_searching_on_dates_alone() -> None:
    first = project_plan(MILAN)
    assert all(task.kind != "hotel" or task.provenance != "explicit" for task in first.tasks)
    second = project_plan(MILAN, PlanAnswers(helpWith="stay"))
    hotel = next(task for task in second.tasks if task.kind == "hotel")
    assert hotel.provenance == "explicit"


def test_fake_stay_search_tool_is_milan_labelled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ITAA_STAY_SEARCH_MODE", "fake")
    monkeypatch.delenv("ITAA_LITEAPI_API_KEY", raising=False)
    agent = compose_orchestrator()
    result = agent.execute_turn(
        "search_stay_offers",
        {
            "destination": "Milan",
            "origin": "Mumbai",
            "checkIn": "2026-10-20",
            "checkOut": "2026-10-30",
        },
    )
    assert result["status"] == "ok"
    assert result["source"] == "fake"
    assert result["label"] == "Labelled fake hotel search"
    offers = result["offers"]
    assert isinstance(offers, list)
    names = " ".join(str(item.get("name")) for item in offers if isinstance(item, dict))
    assert "milan" in names.lower() or "milan" in str(result).lower()
    assert "jfk" not in str(result).lower()
    assert "skyshield" not in str(result).lower()
    assert result["bookingAuthority"] == "none"
