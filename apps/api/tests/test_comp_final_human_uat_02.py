"""COMP-FINAL-HUMAN-UAT-02 state chain and journey regressions."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from wp06_fakes import build_facade

from itaa_api.agent_session import PREFIX, build_agent_app
from itaa_api.app import create_app
from itaa_api.composition import build_facade as api_facade
from itaa_api.conversation_refine import (
    bind_day_shift,
    parse_date_cascade_reply,
    parse_refinement,
    parse_trip_dates,
    refinement_copy,
)
from itaa_api.search_authorization import EXPERIENCE, FLIGHT, PARKING, STAY, match_confirmation
from itaa_aws_adapter.agent import compose_orchestrator
from itaa_aws_adapter.projector import extract_facts

JOURNEY_A = (
    "travelling to New York to London from 5th to 10th October. "
    "Need flight, hotel and covered parking at Heathrow from 8am to 9pm."
)
JOURNEY_B = (
    "Travelling from Mumbai to London from 8 to 12 November. "
    "Need flight, hotel and car parking. I need car parking in Heathrow from 8 am to 9 pm, "
    "preferable covered."
)
DUBAI_LHR = (
    "I am travelling from Dubai to London on the the 12th of october. "
    "flight booking needed. hotel in London needed fro 12 to 16 October. "
    "covered parking also needed in heathrow from 12 to 16 from 7 am to 10 pm"
)


@pytest.fixture(autouse=True)
def _fake_search(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ITAA_STAY_SEARCH_MODE", "fake")
    monkeypatch.setenv("ITAA_EXPERIENCE_SEARCH_MODE", "fake")
    monkeypatch.setenv("ITAA_FLIGHT_SEARCH_MODE", "fake")
    monkeypatch.delenv("ITAA_LITEAPI_API_KEY", raising=False)
    monkeypatch.delenv("ITAA_PRIOTICKET_CLIENT_ID", raising=False)
    monkeypatch.delenv("ITAA_PRIOTICKET_CLIENT_SECRET", raising=False)


class OrchestratorProvider:
    def __init__(self) -> None:
        self.orch = compose_orchestrator(build_facade())
        self.execute_tools: list[str] = []
        self.plan_payloads: list[dict[str, object]] = []

    def plan_turn(self, payload: dict[str, object]) -> dict[str, object]:
        from itaa_aws_adapter.schemas import PlanAnswers, PlanTurnContext

        self.plan_payloads.append(dict(payload))
        answers = PlanAnswers.model_validate(payload.get("answers") or {})
        context = PlanTurnContext(
            lastUserMessage=str(payload.get("lastUserMessage") or ""),
            trustedDomains=payload.get("trustedDomains")
            if isinstance(payload.get("trustedDomains"), dict)
            else {},
        )
        model, projection, events = self.orch.plan_turn(str(payload["objective"]), answers, context)
        return {
            "planTurn": model.model_dump(mode="json"),
            "projection": projection.model_dump(mode="json"),
            "events": events,
        }

    def execute_turn(self, payload: dict[str, object]) -> dict[str, object]:
        tool = str(payload["tool"])
        self.execute_tools.append(tool)
        inner = payload.get("payload")
        result = self.orch.execute_turn(tool, inner if isinstance(inner, dict) else {})
        return {"tool": tool, "result": result}


def _client() -> tuple[TestClient, OrchestratorProvider]:
    provider = OrchestratorProvider()
    return TestClient(build_agent_app(provider)), provider


def _wired() -> tuple[TestClient, OrchestratorProvider]:
    facade = api_facade()
    provider = OrchestratorProvider()
    provider.orch = compose_orchestrator(facade)
    app = create_app(facade=facade)
    app.state.aws_provider = provider
    return TestClient(app), provider


def _confirm_flight_airports(
    client: TestClient, body: dict[str, object], message: str = "all airports"
) -> dict[str, object]:
    pending = body.get("pendingSearchAuthorization")
    caps = pending.get("capabilities") if isinstance(pending, dict) else []
    if isinstance(caps, list) and "flight.search" in caps:
        return body
    later = client.post(
        f"{PREFIX}/sessions/{body['sessionId']}/turns",
        json={"message": message},
    )
    assert later.status_code == 200, later.text
    return later.json()


def test_to_city_to_city_projects_origin_and_destination() -> None:
    facts = extract_facts("travelling to New York to London from 5th to 10th October")
    assert facts.originCity == "New York"
    assert facts.destination == "London"


def test_stale_copy_only_after_successful_search() -> None:
    change = parse_refinement("change the hotel dates to 10 to 15 November")
    assert "out of date" not in refinement_copy(change).lower()
    assert "out of date" in refinement_copy(change, had_results=True).lower()


def test_flight_date_change_is_scoped() -> None:
    change = parse_refinement("change the flight dates to 10 to 15 November")
    assert change.date_scope == "flight"
    assert change.start_date == "2026-11-10"
    assert change.end_date == "2026-11-15"
    modified = parse_refinement("modify the flight booking to 15th October to 18th.")
    assert modified.date_scope == "flight"
    assert modified.start_date == "2026-10-15"
    assert modified.end_date == "2026-10-18"
    assert parse_trip_dates("15th October to 18th") == ("2026-10-15", "2026-10-18")
    stay = parse_refinement("change only the hotel dates to 10 to 15 November")
    assert stay.date_scope == "stay"
    parking = parse_refinement("change only the parking dates to 10 to 15 November")
    assert parking.date_scope == "parking"
    trip = parse_refinement("change all trip dates to 10 to 15 November")
    assert trip.date_scope == "all"
    assert parse_date_cascade_reply("same dates for everything") == "follow"
    assert parse_date_cascade_reply("keep hotel and parking as they are") == "hold"
    assert parse_date_cascade_reply("yes") == "follow"
    assert parse_date_cascade_reply("proceed") == "follow"
    assert parse_date_cascade_reply("go ahead") == "follow"
    bare = parse_refinement("change the dates to 23rd to 25th")
    assert bare.start_day == 23
    assert bare.end_day == 25
    assert bare.date_scope == "all"
    bound_bare = bind_day_shift(
        bare,
        stay_start="2026-10-19",
        stay_end="2026-10-22",
        parking_authorized=True,
        last_text="change the dates to 23rd to 25th",
        flight_start="2026-10-19",
        flight_end="2026-10-22",
    )
    assert bound_bare.date_scope == "all"
    assert bound_bare.start_date == "2026-10-23"
    assert bound_bare.end_date == "2026-10-25"
    flight_bare = parse_refinement("change the flight search to 23rd to 25th")
    assert flight_bare.date_scope == "flight"
    bound_flight = bind_day_shift(
        flight_bare,
        stay_start="2026-10-19",
        stay_end="2026-10-22",
        last_text="change the flight search to 23rd to 25th",
        flight_start="2026-10-19",
        flight_end="2026-10-22",
    )
    assert bound_flight.date_scope == "flight"
    assert bound_flight.start_date == "2026-10-23"
    assert bound_flight.end_date == "2026-10-25"


def test_truncated_checkin_shift_binds_to_held_hotel_window() -> None:
    change = parse_refinement("king to 13th instead of 12")
    assert change.start_day == 13
    assert change.instead_of_day == 12
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
    assert bound.hold_parking_dates is True
    note = refinement_copy(bound)
    assert "hotel dates" in note.lower()
    assert "parking dates are unchanged" in note.lower()


def test_yes_executes_named_pending_set_not_hotel_only() -> None:
    pending = {
        "capabilities": [FLIGHT, STAY, PARKING],
        "fingerprints": {
            "flight.search": "f",
            "stay.search": "s",
            "parking.search": "p",
        },
        "prompt": "Shall I search now?",
    }
    assert match_confirmation("yes", pending) == (FLIGHT, STAY, PARKING)
    assert match_confirmation(
        "yes, search the hotel, parking and sightseeing",
        {**pending, "capabilities": [FLIGHT, STAY, PARKING, EXPERIENCE]},
    ) == (STAY, PARKING, EXPERIENCE)


def test_journey_a_projects_endpoints_and_executes_authorized_set() -> None:
    client, provider = _wired()
    created = client.post(f"{PREFIX}/sessions", json={"objective": JOURNEY_A})
    assert created.status_code == 200, created.text
    body = created.json()
    facts = body["projection"]["facts"]
    assert facts["originCity"] == "New York"
    assert facts["destination"] == "London"
    assert body.get("lastRevisedKind") in (None, "")
    body = _confirm_flight_airports(client, body)
    flight = body["domains"]["flight"]["fields"]
    assert flight["origin"]["value"]
    assert flight["destination"]["value"]
    pending = body.get("pendingSearchAuthorization")
    if pending is None:
        body = client.post(
            f"{PREFIX}/sessions/{body['sessionId']}/turns",
            json={"message": "any airline is fine"},
        ).json()
        pending = body.get("pendingSearchAuthorization")
    assert isinstance(pending, dict)
    ready = set(pending["capabilities"])
    assert "flight.search" in ready
    assert "stay.search" in ready
    session_id = body["sessionId"]
    yes = client.post(f"{PREFIX}/sessions/{session_id}/turns", json={"message": "yes"})
    assert yes.status_code == 200, yes.text
    later = yes.json()
    tools = provider.execute_tools
    assert tools.count("search_flight_offers") == 1
    assert tools.count("search_stay_offers") == 1
    execution = {item["capability"]: item for item in later.get("searchExecution") or []}
    for cap in pending["capabilities"]:
        held = execution.get(cap)
        assert held is not None
        assert held["authorized"] is True
        assert held["dispatched"] is True
    message = (later.get("buyerSafeMessage") or "").lower()
    assert "panel on the right" in message
    assert "you can review them there" not in message
    assert "accept the recommended offer" not in message


def test_dubai_lhr_captures_parking_clocks_from_first_utterance() -> None:
    client, _provider = _wired()
    created = client.post(f"{PREFIX}/sessions", json={"objective": DUBAI_LHR})
    assert created.status_code == 200, created.text
    body = created.json()
    parking = body["domains"]["parking"]["fields"]
    assert parking["airportCode"]["value"] == "LHR"
    assert str(parking["start"]["value"]).startswith("2026-10-12T07:00:00")
    assert str(parking["end"]["value"]).startswith("2026-10-16T22:00:00")
    assert parking["covered"]["value"] in {"preferred", "required"}
    missing = body["domains"]["parking"].get("missing") or []
    assert "start" not in missing
    assert "end" not in missing
    message = (body.get("buyerSafeMessage") or "").lower()
    assert "what time should parking start" not in message


def test_dubai_lhr_first_turn_asks_airports_not_updates() -> None:
    client, _provider = _wired()
    created = client.post(f"{PREFIX}/sessions", json={"objective": DUBAI_LHR})
    assert created.status_code == 200, created.text
    body = created.json()
    facts = body["projection"]["facts"]
    assert facts["originCity"] == "Dubai"
    assert facts["destination"] == "London"
    message = body.get("buyerSafeMessage") or ""
    lowered = message.lower()
    assert "i've updated" not in lowered
    assert "i have updated" not in lowered
    assert "clear origin and destination" not in lowered
    assert "dubai" in lowered
    assert "london" in lowered
    assert "all airports" in lowered
    assert "flight booking" in lowered
    assert "dxb" in lowered or "dubai international" in lowered
    assert "lhr" in lowered or "heathrow" in lowered
    pending = body.get("pendingSearchAuthorization")
    assert isinstance(pending, dict)
    assert "stay.search" in pending["capabilities"]
    assert "parking.search" in pending["capabilities"]
    assert "flight.search" not in pending["capabilities"]
    flight = ((body.get("domains") or {}).get("flight") or {}).get("fields") or {}
    dest = (flight.get("destination") or {}).get("value") or ""
    origin = (flight.get("origin") or {}).get("value") or ""
    assert dest in {"", None} or dest == "London"
    assert origin in {"", None} or origin == "Dubai"
    later = client.post(
        f"{PREFIX}/sessions/{body['sessionId']}/turns",
        json={"message": "DXB to LHR"},
    )
    assert later.status_code == 200, later.text
    ready = later.json()
    pending = ready.get("pendingSearchAuthorization")
    assert isinstance(pending, dict)
    assert "flight.search" in pending["capabilities"]
    fields = ready["domains"]["flight"]["fields"]
    assert fields["origin"]["value"] == "DXB"
    assert fields["destination"]["value"] == "LHR"
    note = (ready.get("buyerSafeMessage") or "").lower()
    assert "clear origin and destination" not in note


def test_dubai_all_short_reply_resolves_city_airports() -> None:
    client, provider = _wired()
    created = client.post(f"{PREFIX}/sessions", json={"objective": DUBAI_LHR})
    assert created.status_code == 200, created.text
    body = created.json()
    later = client.post(
        f"{PREFIX}/sessions/{body['sessionId']}/turns",
        json={"message": "all"},
    )
    assert later.status_code == 200, later.text
    ready = later.json()
    trusted = provider.plan_payloads[-1]["trustedDomains"]
    assert isinstance(trusted, dict)
    assert "which airports should i search" in str(trusted.get("lastAgentMessage") or "").lower()
    fields = ready["domains"]["flight"]["fields"]
    assert fields["origin"]["value"] == "DXB"
    assert fields["destination"]["value"] == "LON"
    pending = ready.get("pendingSearchAuthorization")
    assert isinstance(pending, dict)
    assert "flight.search" in pending["capabilities"]
    assert "stay.search" in pending["capabilities"]
    assert "parking.search" in pending["capabilities"]
    note = (ready.get("buyerSafeMessage") or "").lower()
    assert "which airports should i search" not in note
    assert "shall i search" in note
    assert "preferred departure" not in note


def test_model_airport_facts_are_applied_when_reply_is_paraphrase() -> None:
    client, provider = _wired()
    created = client.post(f"{PREFIX}/sessions", json={"objective": DUBAI_LHR}).json()
    session_id = created["sessionId"]
    original = provider.plan_turn

    def overlay(payload: dict[str, object]) -> dict[str, object]:
        result = original(payload)
        trusted = payload.get("trustedDomains")
        assert isinstance(trusted, dict)
        assert (
            "which airports should i search" in str(trusted.get("lastAgentMessage") or "").lower()
        )
        plan = result["planTurn"]
        assert isinstance(plan, dict)
        facts = dict(plan.get("facts") or {})
        facts["departureAirport"] = "DXB"
        facts["destinationAirport"] = "LON"
        plan["facts"] = facts
        return result

    provider.plan_turn = overlay  # type: ignore[method-assign]
    later = client.post(
        f"{PREFIX}/sessions/{session_id}/turns",
        json={"message": "search everywhere in those cities"},
    )
    assert later.status_code == 200, later.text
    ready = later.json()
    fields = ready["domains"]["flight"]["fields"]
    assert fields["origin"]["value"] == "DXB"
    assert fields["destination"]["value"] == "LON"
    pending = ready.get("pendingSearchAuthorization")
    assert isinstance(pending, dict)
    assert "flight.search" in pending["capabilities"]


def test_journey_b_parking_clocks_and_no_repeat_time_ask() -> None:
    client, provider = _wired()
    created = client.post(f"{PREFIX}/sessions", json={"objective": JOURNEY_B})
    assert created.status_code == 200, created.text
    body = created.json()
    parking = body["domains"]["parking"]["fields"]
    assert parking["airportCode"]["value"] == "LHR"
    assert str(parking["start"]["value"]).startswith("2026-11-08T08:00:00")
    assert str(parking["end"]["value"]).startswith("2026-11-12T21:00:00")
    assert parking["covered"]["value"] in {"preferred", "required"}
    message = (body.get("buyerSafeMessage") or "").lower()
    assert "what time should parking start" not in message
    assert "08:00" not in message or "preferred departure" in message
    facts = body["projection"]["facts"]
    assert facts["originCity"] == "Mumbai"
    assert facts["destination"] == "London"
    assert facts["startDate"] == "2026-11-08"
    assert facts["endDate"] == "2026-11-12"
    body = _confirm_flight_airports(client, body)
    pending = body.get("pendingSearchAuthorization")
    if pending is None:
        body = client.post(
            f"{PREFIX}/sessions/{body['sessionId']}/turns",
            json={"message": "any airline is fine"},
        ).json()
        pending = body.get("pendingSearchAuthorization")
    assert isinstance(pending, dict)
    assert set(pending["capabilities"]) >= {"flight.search", "stay.search", "parking.search"}
    session_id = body["sessionId"]
    yes = client.post(f"{PREFIX}/sessions/{session_id}/turns", json={"message": "yes"})
    assert yes.status_code == 200, yes.text
    later = yes.json()
    assert provider.execute_tools.count("search_flight_offers") == 1
    assert provider.execute_tools.count("search_stay_offers") == 1
    stay = later["staySearch"]
    assert stay["query"]["checkIn"] == "2026-11-08"
    assert stay["query"]["checkOut"] == "2026-11-12"
    refine = client.post(
        f"{PREFIX}/sessions/{session_id}/turns",
        json={"message": "change the flight dates to 10 to 15 November"},
    )
    assert refine.status_code == 200, refine.text
    changed = refine.json()
    note = (changed.get("buyerSafeMessage") or "").lower()
    assert "hotel and parking follow" in note
    stay_after = changed["staySearch"]
    assert stay_after["query"]["checkIn"] == "2026-11-08"
    assert stay_after["query"]["checkOut"] == "2026-11-12"
    flight_query = (changed.get("flightSearch") or {}).get("query") or {}
    assert str(flight_query.get("date") or "").startswith("2026-11-08")
    assert str(flight_query.get("dateEnd") or "").startswith("2026-11-12")
    assert changed["projection"]["facts"]["startDate"] == "2026-11-08"
    flight_draft = changed["domains"]["flight"]["fields"]["date"]["value"]
    assert str(flight_draft).startswith("2026-11-10")
    hold = client.post(
        f"{PREFIX}/sessions/{session_id}/turns",
        json={"message": "keep hotel and parking as they are"},
    )
    assert hold.status_code == 200, hold.text
    held = hold.json()
    assert held["projection"]["facts"]["startDate"] == "2026-11-08"
    parking_end = held["domains"]["parking"]["fields"]["end"]["value"]
    assert str(parking_end).startswith("2026-11-12")
    assert provider.execute_tools.count("search_flight_offers") == 2
    assert provider.execute_tools.count("search_stay_offers") == 1
    held_flight = (held.get("flightSearch") or {}).get("query") or {}
    assert str(held_flight.get("date") or "").startswith("2026-11-10")
    assert held.get("pendingSearchAuthorization") in (None, {})
    assert "airline payment" not in (held.get("buyerSafeMessage") or "").lower()
    assert "existing ticket" not in (held.get("buyerSafeMessage") or "").lower()


def test_pre_search_date_change_is_updated_not_stale() -> None:
    client, _provider = _client()
    created = client.post(
        f"{PREFIX}/sessions",
        json={"objective": "I need a hotel in London from 8 to 12 November"},
    ).json()
    assert created.get("staySearch") in (None, {})
    session_id = created["sessionId"]
    changed = client.post(
        f"{PREFIX}/sessions/{session_id}/turns",
        json={"message": "change the hotel dates to 10 to 15 November"},
    ).json()
    note = (changed.get("buyerSafeMessage") or "").lower()
    assert "out of date" not in note
    assert "updated" in note or "shall i search" in note
    assert changed["projection"]["facts"]["startDate"] == "2026-11-08"
    assert changed["stayDraft"]["checkIn"] == "2026-11-10"
    assert changed["stayDraft"]["checkOut"] == "2026-11-15"


def test_scoped_date_mutations_do_not_cross_domains() -> None:
    client, _provider = _wired()
    created = client.post(f"{PREFIX}/sessions", json={"objective": JOURNEY_B}).json()
    session_id = created["sessionId"]
    stay_only = client.post(
        f"{PREFIX}/sessions/{session_id}/turns",
        json={"message": "change only the hotel dates to 10 to 15 November"},
    ).json()
    assert stay_only["projection"]["facts"]["startDate"] == "2026-11-08"
    assert stay_only["stayDraft"]["checkIn"] == "2026-11-10"
    assert str(stay_only["domains"]["parking"]["fields"]["start"]["value"]).startswith("2026-11-08")
    parking_only = client.post(
        f"{PREFIX}/sessions/{session_id}/turns",
        json={"message": "change only the parking dates to 9 to 11 November"},
    ).json()
    assert parking_only["projection"]["facts"]["startDate"] == "2026-11-08"
    assert parking_only["stayDraft"]["checkIn"] == "2026-11-10"
    assert str(parking_only["domains"]["parking"]["fields"]["start"]["value"]).startswith(
        "2026-11-09"
    )
    trip = client.post(
        f"{PREFIX}/sessions/{session_id}/turns",
        json={"message": "change all trip dates to 10 to 15 November"},
    ).json()
    assert trip["projection"]["facts"]["startDate"] == "2026-11-10"
    assert trip["stayDraft"]["checkIn"] == "2026-11-10"
    assert str(trip["domains"]["parking"]["fields"]["start"]["value"]).startswith("2026-11-10")


def test_cascade_follow_updates_hotel_and_parking() -> None:
    client, _provider = _wired()
    created = client.post(f"{PREFIX}/sessions", json={"objective": JOURNEY_B}).json()
    session_id = created["sessionId"]
    client.post(
        f"{PREFIX}/sessions/{session_id}/turns",
        json={"message": "change the flight dates to 10 to 15 November"},
    )
    followed = client.post(
        f"{PREFIX}/sessions/{session_id}/turns",
        json={"message": "same dates for everything"},
    ).json()
    assert followed["projection"]["facts"]["startDate"] == "2026-11-10"
    assert followed["stayDraft"]["checkIn"] == "2026-11-10"
    assert str(followed["domains"]["parking"]["fields"]["start"]["value"]).startswith("2026-11-10")
    assert str(followed["domains"]["flight"]["fields"]["date"]["value"]).startswith("2026-11-10")


def test_modify_flight_booking_asks_then_proceed_reruns_related_searches() -> None:
    client, provider = _wired()
    created = client.post(f"{PREFIX}/sessions", json={"objective": JOURNEY_B})
    assert created.status_code == 200, created.text
    body = _confirm_flight_airports(client, created.json())
    pending = body.get("pendingSearchAuthorization")
    if pending is None:
        body = client.post(
            f"{PREFIX}/sessions/{body['sessionId']}/turns",
            json={"message": "any airline is fine"},
        ).json()
        pending = body.get("pendingSearchAuthorization")
    assert isinstance(pending, dict)
    session_id = body["sessionId"]
    searched = client.post(
        f"{PREFIX}/sessions/{session_id}/turns",
        json={"message": "yes"},
    )
    assert searched.status_code == 200, searched.text
    flight_count = provider.execute_tools.count("search_flight_offers")
    stay_count = provider.execute_tools.count("search_stay_offers")
    asked = client.post(
        f"{PREFIX}/sessions/{session_id}/turns",
        json={"message": "modify the flight booking to 15th November to 18th."},
    )
    assert asked.status_code == 200, asked.text
    changed = asked.json()
    note = (changed.get("buyerSafeMessage") or "").lower()
    assert "hotel and parking follow" in note
    assert "airline payment" not in note
    assert "existing ticket" not in note
    assert "**" not in (changed.get("buyerSafeMessage") or "")
    assert changed.get("pendingDateCascade")
    assert changed.get("lastRevisedKind") == "flight"
    assert changed["staySearch"]["query"]["checkIn"] == "2026-11-08"
    assert provider.execute_tools.count("search_flight_offers") == flight_count
    proceeded = client.post(
        f"{PREFIX}/sessions/{session_id}/turns",
        json={"message": "proceed"},
    )
    assert proceeded.status_code == 200, proceeded.text
    done = proceeded.json()
    assert done["projection"]["facts"]["startDate"] == "2026-11-15"
    assert done["stayDraft"]["checkIn"] == "2026-11-15"
    assert str(done["domains"]["parking"]["fields"]["start"]["value"]).startswith("2026-11-15")
    flight_query = (done.get("flightSearch") or {}).get("query") or {}
    assert str(flight_query.get("date") or "").startswith("2026-11-15")
    assert str(flight_query.get("dateEnd") or "").startswith("2026-11-18")
    assert done["staySearch"]["query"]["checkIn"] == "2026-11-15"
    assert provider.execute_tools.count("search_flight_offers") == flight_count + 1
    assert provider.execute_tools.count("search_stay_offers") == stay_count + 1
    done_note = (done.get("buyerSafeMessage") or "").lower()
    assert "follow the flight dates" in done_note
    assert "airline payment" not in done_note
    assert "existing ticket" not in done_note
    assert "**" not in (done.get("buyerSafeMessage") or "")
    assert done.get("pendingSearchAuthorization") in (None, {})
    assert done.get("lastRevisedKind") == "trip"
    again = client.post(
        f"{PREFIX}/sessions/{session_id}/turns",
        json={"message": "change the dates to 23rd to 25th"},
    )
    assert again.status_code == 200, again.text
    second = again.json()
    assert second["projection"]["facts"]["startDate"] == "2026-11-23"
    assert second["stayDraft"]["checkIn"] == "2026-11-23"
    assert second["stayDraft"]["checkOut"] == "2026-11-25"
    assert str(second["domains"]["parking"]["fields"]["start"]["value"]).startswith("2026-11-23")
    second_flight = (second.get("flightSearch") or {}).get("query") or {}
    assert str(second_flight.get("date") or "").startswith("2026-11-23")
    assert str(second_flight.get("dateEnd") or "").startswith("2026-11-25")
    assert second["staySearch"]["query"]["checkIn"] == "2026-11-23"
    assert provider.execute_tools.count("search_flight_offers") == flight_count + 2
    assert provider.execute_tools.count("search_stay_offers") == stay_count + 2
    assert second.get("pendingSearchAuthorization") in (None, {})
    assert second.get("lastRevisedKind") == "trip"
    assert "shall i request offers" not in (second.get("buyerSafeMessage") or "").lower()


def test_fly_from_mumbai_does_not_become_destination_fly() -> None:
    facts = extract_facts("i want to fly from mumbai to london on 27th november to 30th november")
    assert facts.originCity == "Mumbai"
    assert facts.destination == "London"
    assert facts.destination.lower() != "fly"
    assert facts.flightStated is True
    assert facts.departureAirport != "FLY"
    assert facts.destinationAirport != "FLY"


def test_heathrow_to_gatwick_names_specific_airports() -> None:
    facts = extract_facts(
        "I am travelling from Heathrow to Gatwick from 15 to 18 October. "
        "Flight booking needed. Hotel in Gatwick needed. Parking also needed at Gatwick."
    )
    assert facts.originCity in {"Heathrow", "London"}
    assert facts.destination in {"Gatwick", "London"}
    assert facts.departureAirport == "LHR"
    client, _provider = _wired()
    created = client.post(
        f"{PREFIX}/sessions",
        json={
            "objective": (
                "I am travelling from Heathrow to Gatwick from 15 to 18 October. "
                "Flight booking needed. Hotel in Gatwick needed. Parking also needed at Gatwick."
            )
        },
    )
    assert created.status_code == 200, created.text
    body = created.json()
    message = body.get("buyerSafeMessage") or ""
    lowered = message.lower()
    assert "which airports should i search" not in lowered
    assert "all airports in heathrow" not in lowered
    assert lowered.count("what time should parking start") <= 1
    assert lowered.count("do you want covered parking") <= 1
    fields = ((body.get("domains") or {}).get("flight") or {}).get("fields") or {}
    assert (fields.get("origin") or {}).get("value") == "LHR"
    assert (fields.get("destination") or {}).get("value") == "LGW"


def test_go_from_heathrow_to_manchester_is_lhr_man() -> None:
    objective = (
        "i want to go from london heathrow to manchester airport from 27th to 30th november "
        "and i want to stay at a hotel in manchester as well during my stay"
    )
    facts = extract_facts(objective)
    assert facts.originCity == "London"
    assert facts.destination == "Manchester"
    assert facts.departureAirport == "LHR"
    client, _provider = _wired()
    created = client.post(f"{PREFIX}/sessions", json={"objective": objective})
    assert created.status_code == 200, created.text
    body = created.json()
    fields = ((body.get("domains") or {}).get("flight") or {}).get("fields") or {}
    origin = (fields.get("origin") or {}).get("value")
    dest = (fields.get("destination") or {}).get("value")
    assert origin == "LHR"
    assert dest == "MAN"
    message = (body.get("buyerSafeMessage") or "").lower()
    assert "from man to man" not in message
    assert "from manchester to manchester" not in message
    tasks = body["projection"]["tasks"]
    flight = next(item for item in tasks if item["kind"] == "flight")
    assert flight["provenance"] == "explicit"


def _parking_code(body: dict[str, object]) -> str:
    parking = ((body.get("domains") or {}).get("parking") or {}).get("fields") or {}
    held = parking.get("airportCode") if isinstance(parking, dict) else {}
    return str(held.get("value") or "") if isinstance(held, dict) else ""


def _flight_code(body: dict[str, object], field_id: str) -> str:
    fields = ((body.get("domains") or {}).get("flight") or {}).get("fields") or {}
    held = fields.get(field_id) if isinstance(fields, dict) else {}
    return str(held.get("value") or "") if isinstance(held, dict) else ""


def _advance_until_searched(
    client: TestClient, body: dict[str, object], *, session_id: str
) -> dict[str, object]:
    current = body
    for message in ("all airports", "any airline is fine", "yes"):
        pending = current.get("pendingSearchAuthorization")
        flight_search = current.get("flightSearch")
        if isinstance(flight_search, dict) and flight_search.get("offers"):
            return current
        if isinstance(pending, dict) and pending.get("capabilities"):
            later = client.post(
                f"{PREFIX}/sessions/{session_id}/turns",
                json={"message": "yes"},
            )
            assert later.status_code == 200, later.text
            current = later.json()
            continue
        later = client.post(
            f"{PREFIX}/sessions/{session_id}/turns",
            json={"message": message},
        )
        assert later.status_code == 200, later.text
        current = later.json()
    return current


def test_departure_airport_change_does_not_move_parking() -> None:
    change = parse_refinement("I want to change the departure airport from lhr to Mumbai")
    assert change.parking_airport is None
    assert change.flight_origin == "BOM"
    assert change.flight_destination is None
    note = refinement_copy(change, had_results=True).lower()
    assert "departure airport" in note
    assert "parking airport" not in note

    objective = (
        "I am travelling from Heathrow to Gatwick from 14 to 16 November. "
        "Flight booking needed. Hotel in Gatwick needed. "
        "Covered parking also needed at Gatwick from 7 am to 5 pm."
    )
    client, _provider = _wired()
    created = client.post(f"{PREFIX}/sessions", json={"objective": objective})
    assert created.status_code == 200, created.text
    body = created.json()
    session_id = str(body["sessionId"])
    body = _advance_until_searched(client, body, session_id=session_id)
    assert _flight_code(body, "origin") == "LHR"
    assert _flight_code(body, "destination") == "LGW"
    assert _parking_code(body) == "LGW"
    changed = client.post(
        f"{PREFIX}/sessions/{session_id}/turns",
        json={"message": "I want to change the departure airport from lhr to Mumbai"},
    )
    assert changed.status_code == 200, changed.text
    later = changed.json()
    assert _parking_code(later) == "LGW"
    assert _flight_code(later, "origin") == "BOM"
    assert _flight_code(later, "destination") == "LGW"
    facts = later["projection"]["facts"]
    assert facts["originCity"] == "Mumbai"
    assert facts["destination"] in {"Gatwick", "London"}
    message = (later.get("buyerSafeMessage") or "").lower()
    assert "parking airport" not in message
    assert "departure airport" in message
    assert "mumbai" in message
    pending = later.get("pendingSearchAuthorization")
    assert isinstance(pending, dict)
    assert pending.get("capabilities") == ["flight.search"]
    assert later.get("lastRevisedKind") == "flight"


NYC_LONDON = (
    "I am flying from New York to London from 14 to 16. need flight, hotel and covered parking, "
    "parking needed from 6 pm to 10 am"
)


def test_monthless_nyc_london_has_stay_dates() -> None:
    facts = extract_facts(NYC_LONDON)
    assert facts.originCity == "New York"
    assert facts.destination == "London"
    assert facts.startDate.endswith("-14")
    assert facts.endDate.endswith("-16")
    assert facts.startDate[:7] == facts.endDate[:7]


def test_all_airports_does_not_fail_closed_or_fill_parking() -> None:
    client, _provider = _wired()
    created = client.post(f"{PREFIX}/sessions", json={"objective": NYC_LONDON})
    assert created.status_code == 200, created.text
    body = created.json()
    first = (body.get("buyerSafeMessage") or "").lower()
    assert "still need a destination and dates on the hotel" not in first
    assert "which airports should i search" in first
    later = client.post(
        f"{PREFIX}/sessions/{body['sessionId']}/turns",
        json={"message": "all airports"},
    )
    assert later.status_code == 200, later.text
    ready = later.json()
    note = (ready.get("buyerSafeMessage") or "").lower()
    assert "could not complete this step" not in note
    assert _parking_code(ready) == ""
    assert "airport" in note
    fields = ((ready.get("domains") or {}).get("flight") or {}).get("fields") or {}
    origin = (fields.get("origin") or {}).get("value")
    dest = (fields.get("destination") or {}).get("value")
    assert origin in {"NYC", "JFK"}
    assert dest in {"LON", "LHR"}
    pending = ready.get("pendingSearchAuthorization")
    if isinstance(pending, dict):
        assert "parking.search" not in pending.get("capabilities") or _parking_code(ready)


def test_all_airports_survives_plan_turn_failure() -> None:
    client, provider = _wired()
    created = client.post(f"{PREFIX}/sessions", json={"objective": NYC_LONDON}).json()
    original = provider.plan_turn

    def boom(payload: dict[str, object]) -> dict[str, object]:
        if str(payload.get("lastUserMessage") or "").lower() == "all airports":
            from itaa_application.errors import ApplicationError

            raise ApplicationError("model", "unavailable")
        return original(payload)

    provider.plan_turn = boom  # type: ignore[method-assign]
    later = client.post(
        f"{PREFIX}/sessions/{created['sessionId']}/turns",
        json={"message": "all airports"},
    )
    assert later.status_code == 200, later.text
    ready = later.json()
    note = (ready.get("buyerSafeMessage") or "").lower()
    assert "could not complete this step" not in note
    fields = ((ready.get("domains") or {}).get("flight") or {}).get("fields") or {}
    assert (fields.get("origin") or {}).get("value") in {"NYC", "JFK"}
    assert (fields.get("destination") or {}).get("value") in {"LON", "LHR"}
    assert _parking_code(ready) == ""
