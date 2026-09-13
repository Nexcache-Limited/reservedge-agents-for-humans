from __future__ import annotations

from datetime import date

from itaa_api.calendar_resolve import (
    nearest_future_year,
    parse_anchor_date,
    parse_parking_clock_window,
    rewrite_past_iso_if_year_omitted,
)
from itaa_aws_adapter.projector import extract_facts, project_plan

LONDON_UAT = (
    "Travelling from New York to London on 17 October. Need hotel in London for two days. "
    "Also need covered parking in London from 5pm on the 17th October to 5pm on the 18th. "
    "If any sightseeing attractions are there, show me that too."
)
DEMO_A = (
    "I'm flying from JFK on September 3 at 1 PM and returning September 8 at 10 PM. "
    "I have a standard EV, prefer covered parking, and don't want a shuttle longer than 20 minutes."
)


def test_yearless_october_from_september_2026_is_current_year() -> None:
    today = date(2026, 9, 13)
    assert nearest_future_year(10, 17, today=today) == 2026
    assert parse_anchor_date("on 17 October", today=today) == "2026-10-17"
    assert (
        rewrite_past_iso_if_year_omitted("2025-10-17", "on 17 October", today=today) == "2026-10-17"
    )


def test_yearless_october_after_that_date_rolls_to_next_year() -> None:
    today = date(2026, 10, 18)
    assert nearest_future_year(10, 17, today=today) == 2027
    assert parse_anchor_date("17 October", today=today) == "2027-10-17"


def test_year_boundary_in_december_uses_next_year() -> None:
    today = date(2026, 12, 31)
    assert nearest_future_year(10, 17, today=today) == 2027
    assert nearest_future_year(1, 5, today=today) == 2027


def test_same_calendar_day_stays_current_year() -> None:
    today = date(2026, 10, 17)
    assert nearest_future_year(10, 17, today=today) == 2026


def test_london_uat_facts_use_2026_and_keep_parking_window() -> None:
    facts = extract_facts(LONDON_UAT)
    assert facts.destination == "London"
    assert facts.originCity == "New York"
    assert facts.startDate == "2026-10-17"
    assert facts.endDate == "2026-10-19"
    assert facts.hotelStated is True
    assert facts.experienceStated is True
    assert facts.parkingStated is True
    assert facts.parkingAirport == ""
    window = parse_parking_clock_window(LONDON_UAT, today=date(2026, 9, 13))
    assert window == ("2026-10-17T17:00:00", "2026-10-18T17:00:00")


def test_london_uat_proposes_flight_and_orders_domains() -> None:
    projection = project_plan(LONDON_UAT)
    kinds = [task.kind for task in projection.tasks]
    assert kinds == ["flight", "hotel", "parking", "experience"]
    by_kind = {task.kind: task for task in projection.tasks}
    assert by_kind["flight"].provenance == "proposed"
    assert by_kind["hotel"].provenance == "explicit"
    assert by_kind["parking"].provenance == "explicit"
    assert by_kind["experience"].provenance == "explicit"


def test_demo_a_does_not_open_a_flight_lane() -> None:
    projection = project_plan(DEMO_A)
    assert [task.kind for task in projection.tasks] == ["parking"]
    assert extract_facts(DEMO_A).destination == ""


def test_other_transport_does_not_propose_flight() -> None:
    projection = project_plan(
        "Travelling from Paris to London on 17 October by Eurostar. Need a hotel."
    )
    assert all(task.kind != "flight" for task in projection.tasks)


def test_lhr_october_window_stays_airport_local() -> None:
    from itaa_api.calendar_resolve import (
        airport_timezone,
        from_utc_to_local,
        parking_local_naive,
        to_utc_instant,
    )

    window = parse_parking_clock_window(LONDON_UAT, today=date(2026, 9, 13))
    assert window == ("2026-10-17T17:00:00", "2026-10-18T17:00:00")
    assert airport_timezone("LHR") == "Europe/London"
    assert airport_timezone("LGW") == "Europe/London"
    assert airport_timezone("STN") == "Europe/London"
    assert airport_timezone("LTN") == "Europe/London"
    assert airport_timezone("LCY") == "Europe/London"
    assert airport_timezone("BHX") == "Europe/London"
    start, end = window
    assert parking_local_naive(start) == "2026-10-17T17:00:00"
    assert to_utc_instant(start, "LHR") == "2026-10-17T16:00:00Z"
    assert to_utc_instant(end, "LHR") == "2026-10-18T16:00:00Z"
    assert from_utc_to_local("2026-10-17T16:00:00Z", "LHR") == "2026-10-17T17:00:00"
    assert from_utc_to_local("2026-10-18T16:00:00Z", "LHR") == "2026-10-18T17:00:00"


def test_man_window_crosses_uk_dst_end() -> None:
    from itaa_api.calendar_resolve import from_utc_to_local, to_utc_instant

    text = (
        "I need airport parking in Manchester from 5pm on the 24th October "
        "to 5pm on the 25th October."
    )
    window = parse_parking_clock_window(text, today=date(2026, 9, 13))
    assert window == ("2026-10-24T17:00:00", "2026-10-25T17:00:00")
    assert to_utc_instant(window[0], "MAN") == "2026-10-24T16:00:00Z"
    assert to_utc_instant(window[1], "MAN") == "2026-10-25T17:00:00Z"
    assert from_utc_to_local("2026-10-24T16:00:00Z", "MAN") == "2026-10-24T17:00:00"
    assert from_utc_to_local("2026-10-25T17:00:00Z", "MAN") == "2026-10-25T17:00:00"


def test_jfk_uses_america_new_york() -> None:
    from itaa_api.calendar_resolve import airport_timezone, from_utc_to_local, to_utc_instant

    assert airport_timezone("JFK") == "America/New_York"
    assert airport_timezone("LGA") == "America/New_York"
    assert airport_timezone("EWR") == "America/New_York"
    local = "2026-10-17T17:00:00"
    utc = to_utc_instant(local, "JFK")
    assert utc == "2026-10-17T21:00:00Z"
    assert from_utc_to_local(utc, "JFK") == local


def test_local_parking_clock_survives_round_trip_normalization() -> None:
    from itaa_api.calendar_resolve import from_utc_to_local, parking_local_naive, to_utc_instant

    local = "2026-10-17T17:00:00"
    assert parking_local_naive("2026-10-17T17:00:00Z") == local
    utc = to_utc_instant("2026-10-17T17:00:00Z", "LHR")
    assert utc == "2026-10-17T16:00:00Z"
    assert from_utc_to_local(utc, "LHR") == local
    assert to_utc_instant(from_utc_to_local(utc, "LHR"), "LHR") == utc
