from __future__ import annotations

from itaa_api.search_authorization import search_ask_prompt
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


def test_yearless_london_request_is_never_silently_past() -> None:
    facts = extract_facts(LONDON_UAT)
    assert facts.startDate.startswith("2026-10-17") or facts.startDate.startswith("2027-10-17")
    assert not facts.startDate.startswith("2025")
    assert not facts.endDate.startswith("2025")


def test_parking_window_does_not_inherit_stay_checkout() -> None:
    from itaa_api.calendar_resolve import parse_parking_clock_window

    facts = extract_facts(LONDON_UAT)
    assert facts.endDate.endswith("10-19")
    window = parse_parking_clock_window(LONDON_UAT)
    assert window is not None
    assert window[0].startswith("2026-10-17") or window[0].startswith("2027-10-17")
    assert window[1][8:10] == "18"
    assert facts.endDate[8:10] == "19"


def test_readiness_prompt_cannot_name_unready_flight() -> None:
    prompt = search_ask_prompt(
        ["stay.search", "parking.search", "experience.search"], place="London"
    ).lower()
    assert "shall i search" in prompt
    assert "flight" not in prompt
    parking_only = search_ask_prompt(["parking.search"], place="LHR").lower()
    assert "hotel" not in parking_only
    assert "things to do" not in parking_only


def test_demo_a_does_not_mint_a_flight_from_flying_from_jfk() -> None:
    projection = project_plan(DEMO_A)
    assert all(task.kind != "flight" for task in projection.tasks)
    assert any(task.kind == "parking" for task in projection.tasks)
