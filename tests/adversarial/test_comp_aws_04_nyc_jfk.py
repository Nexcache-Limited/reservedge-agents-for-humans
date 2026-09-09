"""COMP-AWS-04: New York city names must not invent JFK; Explicit parking stays Explicit."""

from __future__ import annotations

from collections.abc import Sequence

from itaa_aws_adapter.agent import compose_orchestrator
from itaa_aws_adapter.projector import extract_facts, project_plan
from itaa_aws_adapter.schemas import PlanAnswers, PlanTask

NYC = "travelling to New York for 10 days."
NYC_PARK = "travelling to New York for 10 days. need parking and rental car."
FOLLOW = "I also need parking"


def _by_kind(tasks: Sequence[PlanTask]) -> dict[str, PlanTask]:
    out: dict[str, PlanTask] = {}
    for task in tasks:
        out[task.kind] = task
    return out


def test_new_york_trip_does_not_invent_jfk_or_reject_parking() -> None:
    facts = extract_facts(NYC)
    assert facts.destination == "New York"
    assert facts.parkingAirport == ""
    assert facts.destinationAirport == ""
    assert "JFK" not in (facts.parkingAirport, facts.destinationAirport)
    projection = project_plan(NYC)
    blob = projection.model_dump_json()
    assert "JFK" not in blob
    parking = _by_kind(projection.tasks).get("parking")
    if parking is not None:
        assert parking.provenance != "explicit"
        assert parking.accepted is False


def test_explicit_parking_and_rental_stay_explicit_without_jfk() -> None:
    facts = extract_facts(NYC_PARK)
    assert facts.destination == "New York"
    assert facts.parkingStated is True
    assert facts.rentalStated is True
    assert facts.parkingAirport == ""
    _model, projection, _events = compose_orchestrator().plan_turn(NYC_PARK)
    by_kind = _by_kind(projection.tasks)
    assert by_kind["parking"].provenance == "explicit"
    assert by_kind["parking"].accepted is True
    assert by_kind["rental"].provenance == "explicit"
    assert by_kind["rental"].accepted is True
    assert projection.facts.destination == "New York"
    assert projection.facts.parkingAirport != "JFK"
    assert "JFK" not in projection.model_dump_json()


def test_follow_up_parking_becomes_explicit_on_combined_objective() -> None:
    combined = f"{NYC} {FOLLOW}"
    _model, projection, _events = compose_orchestrator().plan_turn(combined, PlanAnswers())
    parking = _by_kind(projection.tasks)["parking"]
    assert parking.provenance == "explicit"
    assert parking.accepted is True
    assert projection.facts.parkingAirport != "JFK"
    assert "JFK" not in projection.model_dump_json()
