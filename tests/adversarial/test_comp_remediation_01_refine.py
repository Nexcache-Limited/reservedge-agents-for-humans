"""Adversarial coverage for code-owned conversational refinements."""

from __future__ import annotations

from itaa_api.conversation_refine import parse_refinement, parse_trip_dates, refinement_copy
from itaa_application.external_search_port import FlightSearchQuery
from itaa_aws_adapter.agent import compose_orchestrator
from itaa_liteapi_hotels.fake_flights import FakeFlightSearchAdapter
from itaa_liteapi_hotels.flights import flights_request_body


def test_date_span_is_calendar_not_clock() -> None:
    assert parse_trip_dates("2 am to 10 pm") is None
    assert parse_trip_dates("9 to 14 november") == ("2026-11-09", "2026-11-14")


def test_scoped_mutations_are_explicit() -> None:
    stay = parse_refinement("change only the hotel dates to 9 to 14 November")
    assert stay.date_scope == "stay"
    parking = parse_refinement("change only the parking dates to 9 to 14 November")
    assert parking.date_scope == "parking"
    drop = parse_refinement("I don't need parking anymore")
    assert drop.drop_parking is True
    add = parse_refinement("also find things to do")
    assert add.add_experience is True
    budget = parse_refinement("only show hotels under £200")
    assert budget.stay_max_minor == 20_000
    dest = parse_refinement("change the destination to Gatwick")
    assert dest.destination == "Gatwick"
    airport = parse_refinement("change the parking airport to Manchester")
    assert airport.parking_airport == "MAN"
    flight = parse_refinement("I need a flight from Manchester to Heathrow on 25 October")
    assert flight.flight_origin == "MAN"
    assert flight.flight_destination == "LHR"
    assert flight.flight_date == "2026-10-25"


def test_refinement_copy_acknowledges_and_stales() -> None:
    note = refinement_copy(parse_refinement("change the dates to 9 to 14 november"))
    assert "9 Nov 2026" in note
    assert "out of date" in note.lower()


def test_fake_flight_search_is_not_stay_inventory() -> None:
    page = FakeFlightSearchAdapter().search(
        FlightSearchQuery(origin="MAN", destination="LHR", date="2026-10-25")
    )
    assert page.offers[0].origin == "MAN"  # type: ignore[union-attr]
    blob = str(page).lower()
    assert "spadari" not in blob
    assert "skyshield" not in blob
    body = flights_request_body(
        FlightSearchQuery(origin="MAN", destination="LHR", date="2026-10-25")
    )
    legs = body["legs"]
    assert isinstance(legs, list)
    assert legs[0] == {
        "origin": "MAN",
        "destination": "LHR",
        "date": "2026-10-25",
        "direction": "OUTBOUND",
    }


def test_closed_tool_can_search_flights() -> None:
    agent = compose_orchestrator()
    result = agent.execute_turn(
        "search_flight_offers",
        {"origin": "MAN", "destination": "LHR", "date": "2026-10-25"},
    )
    blob = str(result).lower()
    assert "skyshield" not in blob
    assert "spadari" not in blob
    assert result.get("bookingAuthority") == "none"
    offers = result.get("offers")
    assert isinstance(offers, list)
    assert len(offers) == 2
