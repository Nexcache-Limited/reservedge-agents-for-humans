"""Adversarial coverage for code-owned conversational refinements."""

from __future__ import annotations

from itaa_api.conversation_refine import (
    bind_day_shift,
    parse_refinement,
    parse_trip_dates,
    refinement_copy,
)
from itaa_application.external_search_port import FlightSearchQuery
from itaa_aws_adapter.agent import compose_orchestrator
from itaa_aws_adapter.projector import extract_facts
from itaa_liteapi_hotels.fake_flights import FakeFlightSearchAdapter
from itaa_liteapi_hotels.flights import flights_request_body


def test_date_span_is_calendar_not_clock() -> None:
    assert parse_trip_dates("2 am to 10 pm") is None
    assert parse_trip_dates("9 to 14 november") == ("2026-11-09", "2026-11-14")
    assert parse_trip_dates("15th October to 18th") == ("2026-10-15", "2026-10-18")
    facts = extract_facts("I am flying from New York to London from 14 to 16")
    assert facts.startDate.endswith("-14")
    assert facts.endDate.endswith("-16")
    assert facts.startDate[:7] == facts.endDate[:7]


def test_modify_flight_booking_is_flight_scoped() -> None:
    change = parse_refinement("modify the flight booking to 15th October to 18th.")
    assert change.date_scope == "flight"
    assert change.start_date == "2026-10-15"
    assert change.end_date == "2026-10-18"


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
    assert airport.flight_origin is None
    swapped = parse_refinement("change the parking airport from LHR to MAN")
    assert swapped.parking_airport == "MAN"
    origin = parse_refinement("I want to change the departure airport from lhr to Mumbai")
    assert origin.parking_airport is None
    assert origin.flight_origin == "BOM"
    assert origin.flight_origin_place == "Mumbai"
    assert origin.flight_destination is None
    flight = parse_refinement("I need a flight from Manchester to Heathrow on 25 October")
    assert flight.flight_origin == "MAN"
    assert flight.flight_destination == "LHR"
    assert flight.flight_date == "2026-10-25"


def test_truncated_checkin_instead_of_stays_on_hotel() -> None:
    change = parse_refinement("king to 13th instead of 12")
    bound = bind_day_shift(
        change,
        stay_start="2026-10-12",
        stay_end="2026-10-16",
        parking_authorized=True,
        last_text="king to 13th instead of 12",
    )
    assert bound.date_scope == "stay"
    assert bound.start_date == "2026-10-13"
    assert bound.end_date == "2026-10-16"
    assert "parking dates are unchanged" in refinement_copy(bound).lower()


def test_bare_day_range_inherits_current_trip_month() -> None:
    change = parse_refinement("change the dates to 23rd to 25th")
    bound = bind_day_shift(
        change,
        stay_start="2026-10-19",
        stay_end="2026-10-22",
        parking_authorized=True,
        last_text="change the dates to 23rd to 25th",
        flight_start="2026-10-19",
        flight_end="2026-10-22",
    )
    assert bound.date_scope == "all"
    assert bound.start_date == "2026-10-23"
    assert bound.end_date == "2026-10-25"


def test_refinement_copy_acknowledges_and_stales() -> None:
    change = parse_refinement("change the dates to 9 to 14 november")
    note = refinement_copy(change, had_results=True)
    assert "9 Nov 2026" in note
    assert "out of date" in note.lower()
    fresh = refinement_copy(change)
    assert "out of date" not in fresh.lower()


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
