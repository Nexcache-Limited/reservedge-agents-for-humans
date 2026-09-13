from __future__ import annotations

from itaa_aws_adapter.projector import extract_facts, project_plan
from itaa_aws_adapter.schemas import PlanAnswers


def test_car_parking_does_not_make_rental_explicit() -> None:
    text = "travelling to manchester from 4th October to 10th October. need car parking and hotel"
    facts = extract_facts(text)
    assert facts.parkingStated is True
    assert facts.hotelStated is True
    assert facts.rentalStated is False
    projection = project_plan(text, PlanAnswers())
    by_kind = {task.kind: task for task in projection.tasks}
    assert by_kind["parking"].provenance == "explicit"
    assert by_kind["hotel"].provenance == "explicit"
    assert "rental" not in by_kind or by_kind["rental"].provenance != "explicit"


def test_named_rental_car_stays_explicit() -> None:
    facts = extract_facts("I need a rental car in Milan from 20 to 30 October")
    assert facts.rentalStated is True
    assert facts.parkingStated is False


def test_milan_trip_does_not_force_parking_or_rental() -> None:
    text = "I'm travelling to Milan from Mumbai from 20 to 30 October"
    facts = extract_facts(text)
    assert facts.destination == "Milan"
    assert facts.originCity == "Mumbai"
    assert facts.parkingStated is False
    assert facts.rentalStated is False
    assert facts.hotelStated is False
    projection = project_plan(text, PlanAnswers())
    by_kind = {task.kind: task for task in projection.tasks}
    assert "parking" not in by_kind
    assert "rental" not in by_kind
    assert "hotel" not in by_kind
    flight = by_kind.get("flight")
    assert flight is not None
    assert flight.provenance == "proposed"
    assert flight.accepted is False
