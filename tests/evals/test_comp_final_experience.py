from __future__ import annotations

from itaa_aws_adapter.projector import extract_facts, project_plan

MILAN = "I'm travelling to Milan from Mumbai from 20 to 30 October"
THINGS = "Find things to do in Milan"
FAMILY = "I'd like some family-friendly attractions"
EVENING = "Find an evening activity near the city centre"
MUSEUM = "Can you find museum or tour options while I'm there?"
HOTEL_THINGS = "Flights are booked. I need a hotel and some things to do while I'm there."


def test_travel_alone_does_not_imply_experience() -> None:
    facts = extract_facts(MILAN)
    assert facts.experienceStated is False
    assert facts.hotelStated is False
    projection = project_plan(MILAN)
    assert all(task.kind != "experience" for task in projection.tasks)


def test_natural_language_activates_experience_explicit() -> None:
    for line in (THINGS, FAMILY, EVENING, MUSEUM):
        facts = extract_facts(line)
        assert facts.experienceStated is True, line
        projection = project_plan(line)
        by_kind = {task.kind: task for task in projection.tasks}
        assert by_kind["experience"].provenance == "explicit"


def test_hotel_and_things_to_do_are_both_explicit() -> None:
    projection = project_plan(f"{MILAN} {HOTEL_THINGS}")
    by_kind = {task.kind: task for task in projection.tasks}
    assert by_kind["hotel"].provenance == "explicit"
    assert by_kind["experience"].provenance == "explicit"
    assert projection.facts.flightSatisfied is True
    assert "parking" not in by_kind
    assert "rental" not in by_kind


def test_show_me_evening_is_experience_not_entertainment() -> None:
    facts = extract_facts("Show me evening activities instead")
    assert facts.experienceStated is True
    assert facts.entsStated is False
    assert "evening" in facts.experiencePreferences


def test_second_destination_london_is_not_milan() -> None:
    projection = project_plan("Find things to do in London")
    assert projection.facts.destination == "London"
    assert projection.facts.experienceStated is True
    assert "jfk" not in projection.model_dump_json().lower()
