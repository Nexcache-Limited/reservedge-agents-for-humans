"""COMP-AWS-02 conversation-first parking domains and grants."""

from __future__ import annotations

from fastapi.testclient import TestClient
from test_comp_aws_02_agent_session import DEMO_A, OrchestratorProvider, _client, created_blob

from itaa_api.agent_session import PREFIX
from itaa_api.app import create_app
from itaa_api.composition import build_facade
from itaa_aws_adapter.agent import compose_orchestrator

NYC = "travelling to New York for 10 days. Dates: 20th to 30th October. Departing from Mumbai."
PARKING_NY = (
    "I need airport parking for a New York trip from September 3 at 1 PM to "
    "September 8 at 10 PM. Standard EV, prefer covered parking, shuttle under 20 minutes."
)


def _wired() -> tuple[TestClient, OrchestratorProvider]:
    facade = build_facade()
    provider = OrchestratorProvider()
    provider.facade = facade
    provider.orch = compose_orchestrator(facade)
    app = create_app(facade=facade)
    app.state.aws_provider = provider
    return TestClient(app), provider


def test_nyc_does_not_invent_parking_airport() -> None:
    client, _provider = _client()
    body = client.post(f"{PREFIX}/sessions", json={"objective": NYC}).json()
    facts = body["projection"]["facts"]
    assert facts["destination"] == "New York"
    assert facts["parkingAirport"] == ""
    assert "jfk" not in created_blob(body)
    parking = body["domains"].get("parking")
    if parking is not None:
        airport = (parking.get("fields") or {}).get("airportCode")
        if airport is not None:
            assert airport.get("value") != "JFK"


def test_accepted_parking_without_iata_asks_airport() -> None:
    client, _provider = _client()
    body = client.post(f"{PREFIX}/sessions", json={"objective": PARKING_NY}).json()
    parking = body["domains"]["parking"]
    airport = (parking.get("fields") or {}).get("airportCode") or {}
    assert airport.get("value") in {None, ""}
    assert body["projection"]["facts"]["parkingAirport"] == ""
    blob = f"{body.get('buyerSafeMessage') or ''} {parking.get('ask') or ''}".lower()
    assert "airport" in blob
    assert "jfk" in blob or "which airport do you need parking at" in blob
    assert airport.get("value") != "JFK"


def test_demo_a_domain_is_execution_ready_without_intent() -> None:
    client, _provider = _client()
    body = client.post(f"{PREFIX}/sessions", json={"objective": DEMO_A}).json()
    parking = body["domains"]["parking"]
    fields = parking["fields"]
    assert fields["airportCode"]["value"] == "JFK"
    assert fields["airportCode"]["provenance"] == "explicit"
    assert fields["vehicleClass"]["value"] == "standard"
    assert fields["covered"]["value"] == "preferred"
    assert fields["shuttleMaxMinutes"]["provenance"] == "explicit"
    assert parking["completeness"] in {"ready", "awaiting_grant"}
    pending = body.get("pendingSearchAuthorization")
    assert isinstance(pending, dict)
    assert "parking.search" in pending["capabilities"]
    prompt = (pending.get("prompt") or body.get("buyerSafeMessage") or "").lower()
    assert "shall i" in prompt or "request offers" in prompt
    assert parking.get("intentId") in {None, ""}
    assert body.get("transcript")


def test_typed_yes_authorizes_pending_parking_search() -> None:
    client, _provider = _wired()
    created = client.post(f"{PREFIX}/sessions", json={"objective": DEMO_A}).json()
    session_id = created["sessionId"]
    turned = client.post(
        f"{PREFIX}/sessions/{session_id}/turns",
        json={"message": "yes"},
    )
    assert turned.status_code == 200
    body = turned.json()
    offers = body["domains"]["parking"]["offerSet"]["snapshot"]["offers"]
    assert {item["rank"] for item in offers} == {1, 2, 3}
    assert body["pendingAuthorization"]["gate"] == "A3"


def test_typed_yes_then_take_offer_authorizes_simulation() -> None:
    client, _provider = _wired()
    created = client.post(f"{PREFIX}/sessions", json={"objective": DEMO_A}).json()
    session_id = created["sessionId"]
    turned = client.post(f"{PREFIX}/sessions/{session_id}/turns", json={"message": "yes"})
    assert turned.status_code == 200, turned.text
    snapshot = turned.json()["domains"]["parking"]["offerSet"]["snapshot"]
    offer_id = snapshot["recommendedOfferId"]
    a3 = client.post(
        f"{PREFIX}/sessions/{session_id}/grants",
        json={"gate": "A3", "domain": "parking", "offerId": offer_id},
    )
    assert a3.status_code == 200, a3.text
    assert a3.json()["pendingAuthorization"]["gate"] == "A4"
    a4 = client.post(
        f"{PREFIX}/sessions/{session_id}/grants",
        json={"gate": "A4", "domain": "parking"},
    )
    assert a4.status_code == 200, a4.text
    txn = a4.json()["domains"]["parking"]["offerSet"]["snapshot"]["transaction"]
    assert txn["mode"] == "SIMULATED"
    assert a4.json()["pendingAuthorization"] is None


def test_direct_patch_and_stale_flag() -> None:
    client, _provider = _wired()
    created = client.post(f"{PREFIX}/sessions", json={"objective": DEMO_A}).json()
    session_id = created["sessionId"]
    granted = client.post(
        f"{PREFIX}/sessions/{session_id}/grants",
        json={"gate": "A2", "domain": "parking"},
    )
    assert granted.status_code == 200, granted.text
    offers = granted.json()["domains"]["parking"]["offerSet"]["snapshot"]["offers"]
    assert offers
    patched = client.post(
        f"{PREFIX}/sessions/{session_id}/turns",
        json={
            "patches": [{"domain": "parking", "fieldId": "start", "value": "2026-09-03T01:00:00Z"}]
        },
    )
    assert patched.status_code == 200, patched.text
    parking = patched.json()["domains"]["parking"]
    assert parking["fields"]["start"]["value"] == "2026-09-03T01:00:00"
    assert parking["fields"]["start"]["source"] == "direct_edit"
    assert parking["offerSet"]["stale"] is True


def test_grants_run_a1_a4_without_leaving_agent_prefix() -> None:
    client, _provider = _wired()
    created = client.post(f"{PREFIX}/sessions", json={"objective": DEMO_A}).json()
    session_id = created["sessionId"]
    a2 = client.post(
        f"{PREFIX}/sessions/{session_id}/grants",
        json={"gate": "A2", "domain": "parking"},
    )
    assert a2.status_code == 200, a2.text
    parking = a2.json()["domains"]["parking"]
    snapshot = parking["offerSet"]["snapshot"]
    by_rank = {item["rank"]: item for item in snapshot["offers"]}
    assert set(by_rank) == {1, 2, 3}
    assert by_rank[1]["totalMinor"] == 14800
    assert snapshot["recommendedOfferId"] == by_rank[1]["offerId"]
    assert a2.json()["pendingAuthorization"]["gate"] == "A3"
    a3_prompt = (a2.json()["pendingAuthorization"].get("prompt") or "").lower()
    assert "rank 1" in a3_prompt
    assert "select a simulated offer on the parking card" in a3_prompt
    assert "accept the recommended offer" not in a3_prompt
    a3 = client.post(
        f"{PREFIX}/sessions/{session_id}/grants",
        json={
            "gate": "A3",
            "domain": "parking",
            "offerId": snapshot["recommendedOfferId"],
        },
    )
    assert a3.status_code == 200, a3.text
    assert a3.json()["pendingAuthorization"]["gate"] == "A4"
    a4 = client.post(
        f"{PREFIX}/sessions/{session_id}/grants",
        json={"gate": "A4", "domain": "parking"},
    )
    assert a4.status_code == 200, a4.text
    txn = a4.json()["domains"]["parking"]["offerSet"]["snapshot"]["transaction"]
    assert txn["mode"] == "SIMULATED"
    assert a4.json()["pendingAuthorization"] is None


LONDON_PARKING = "travelling to London. need parking from 15th to 16th october"


def test_london_parking_captures_dates_and_asks_airport_not_trip_funnel() -> None:
    client, provider = _wired()
    body = client.post(f"{PREFIX}/sessions", json={"objective": LONDON_PARKING}).json()
    parking = body["domains"]["parking"]
    fields = parking["fields"]
    assert parking["provenance"] == "explicit"
    assert str(fields["start"]["value"]).startswith("2026-10-15")
    assert str(fields["end"]["value"]).startswith("2026-10-16")
    airport = (fields.get("airportCode") or {}).get("value")
    assert airport in {None, ""}
    questions = {item["id"] for item in body["projection"]["questions"]}
    assert questions.isdisjoint({"dates", "departureAirport", "carNeed"})
    message = (body.get("buyerSafeMessage") or "").lower()
    assert "date" not in message
    assert "departing" not in message
    assert "airport" in message
    assert "london" in message
    assert "jfk" not in created_blob(body)
    assert provider.plan_payloads[-1]["lastUserMessage"]
    follow = client.post(
        f"{PREFIX}/sessions/{body['sessionId']}/turns",
        json={"message": "heathrow"},
    )
    assert follow.status_code == 200, follow.text
    later = follow.json()
    later_fields = later["domains"]["parking"]["fields"]
    assert later_fields["airportCode"]["value"] == "LHR"
    later_message = (later.get("buyerSafeMessage") or "").lower()
    assert "which london airport" not in later_message
    assert "departing" not in later_message
    rental = client.post(
        f"{PREFIX}/sessions/{body['sessionId']}/turns",
        json={"message": "I also need a rental car"},
    )
    assert rental.status_code == 200, rental.text
    both = rental.json()
    assert both["domains"]["parking"]["fields"]["airportCode"]["value"] == "LHR"
    assert both["domains"]["rental"]["provenance"] == "explicit"
    assert both["domains"]["rental"]["accepted"] is True
    assert "departing" not in (both.get("buyerSafeMessage") or "").lower()
    preference = client.post(
        f"{PREFIX}/sessions/{body['sessionId']}/turns",
        json={"message": "SUV, covered parking from 1pm to 5pm"},
    )
    assert preference.status_code == 200, preference.text
    pref = preference.json()["domains"]["parking"]["fields"]
    assert pref["vehicleClass"]["value"] == "suv"
    assert pref["covered"]["value"] == "preferred"
    assert pref["start"]["value"].endswith("13:00:00") or "13:00" in pref["start"]["value"]


GATWICK_PARKING = "need parking from 1st November to 5th November near Gatwick airport"


def test_parking_asks_times_not_vehicle_class_and_honours_uncovered() -> None:
    client, _provider = _wired()
    body = client.post(f"{PREFIX}/sessions", json={"objective": GATWICK_PARKING}).json()
    parking = body["domains"]["parking"]
    fields = parking["fields"]
    assert fields["airportCode"]["value"] == "LGW"
    assert str(fields["start"]["value"]).startswith("2026-11-01")
    assert str(fields["end"]["value"]).startswith("2026-11-05")
    assert "T12:00:00" not in str(fields["start"]["value"])
    assert fields["vehicleClass"]["value"] == "standard"
    assert fields["vehicleClass"]["provenance"] == "proposed"
    blob = f"{body.get('buyerSafeMessage') or ''} {parking.get('ask') or ''}".lower()
    assert "vehicle class" not in blob
    assert "time" in blob
    session_id = body["sessionId"]
    timed = client.post(
        f"{PREFIX}/sessions/{session_id}/turns",
        json={"message": "11am to 3pm"},
    )
    assert timed.status_code == 200, timed.text
    timed_fields = timed.json()["domains"]["parking"]["fields"]
    assert "T11:00:00" in str(timed_fields["start"]["value"])
    assert "T15:00:00" in str(timed_fields["end"]["value"])
    timed_blob = (timed.json().get("buyerSafeMessage") or "").lower()
    assert "vehicle class" not in timed_blob
    assert "covered" in timed_blob
    refused = client.post(
        f"{PREFIX}/sessions/{session_id}/turns",
        json={"message": "I dont need covered parking"},
    )
    assert refused.status_code == 200, refused.text
    later = refused.json()
    later_fields = later["domains"]["parking"]["fields"]
    assert later_fields["covered"]["value"] == "none"
    later_blob = (later.get("buyerSafeMessage") or "").lower()
    assert "vehicle class" not in later_blob
    assert later_fields["covered"]["value"] != "preferred"


HEATHROW_PARKING = "need parking at Heathrow airport from 15th to 20th september"


def test_heathrow_parking_simulates_offers_after_times() -> None:
    client, _provider = _wired()
    created = client.post(f"{PREFIX}/sessions", json={"objective": HEATHROW_PARKING}).json()
    parking = created["domains"]["parking"]
    assert parking["fields"]["airportCode"]["value"] == "LHR"
    assert "T12:00:00" not in str(parking["fields"]["start"]["value"])
    assert "T12:00:00" not in str(parking["fields"]["end"]["value"])
    assert "time" in (created.get("buyerSafeMessage") or "").lower()
    session_id = created["sessionId"]
    timed = client.post(
        f"{PREFIX}/sessions/{session_id}/turns",
        json={"message": "10am to 4pm"},
    )
    assert timed.status_code == 200, timed.text
    covered = client.post(
        f"{PREFIX}/sessions/{session_id}/turns",
        json={"message": "uncovered is fine"},
    )
    assert covered.status_code == 200, covered.text
    assert covered.json()["domains"]["parking"]["fields"]["covered"]["value"] == "none"
    a2 = client.post(
        f"{PREFIX}/sessions/{session_id}/grants",
        json={"gate": "A2", "domain": "parking"},
    )
    assert a2.status_code == 200, a2.text
    offers = a2.json()["domains"]["parking"]["offerSet"]["snapshot"]["offers"]
    assert len(offers) == 3
    assert a2.json()["pendingAuthorization"]["gate"] == "A3"
    assert "rank 1" in (a2.json()["pendingAuthorization"].get("prompt") or "").lower()


DATES_ONLY_PARKING = "parking needed from 5 to 10 October"
RENTAL_ONLY_LHR = "rental car needed on the 6th September in lhr"


def test_parking_asks_all_remaining_fields_in_one_message() -> None:
    client, _provider = _wired()
    body = client.post(f"{PREFIX}/sessions", json={"objective": DATES_ONLY_PARKING}).json()
    message = (body.get("buyerSafeMessage") or "").lower()
    assert "airport" in message
    assert "time" in message
    assert "covered" in message
    session_id = body["sessionId"]
    follow = client.post(
        f"{PREFIX}/sessions/{session_id}/turns",
        json={"message": "manchester"},
    )
    assert follow.status_code == 200, follow.text
    later = follow.json()
    later_fields = later["domains"]["parking"]["fields"]
    assert later_fields["airportCode"]["value"] == "MAN"
    later_message = (later.get("buyerSafeMessage") or "").lower()
    assert "which airport" not in later_message
    assert "time" in later_message
    assert "covered" in later_message
    timed = client.post(
        f"{PREFIX}/sessions/{session_id}/turns",
        json={"message": "7 am to 10 pm"},
    )
    assert timed.status_code == 200, timed.text
    clocks = timed.json()["domains"]["parking"]["fields"]
    assert "T07:00:00" in str(clocks["start"]["value"])
    assert "T22:00:00" in str(clocks["end"]["value"])
    assert "T00:00:00" not in str(clocks["start"]["value"])
    assert "T00:00:00" not in str(clocks["end"]["value"])


def test_rental_only_does_not_drive_parking_questions() -> None:
    from itaa_api.agent_requirements import RENTAL_NO_ADAPTER_COPY

    client, _provider = _wired()
    body = client.post(f"{PREFIX}/sessions", json={"objective": RENTAL_ONLY_LHR}).json()
    parking = (body.get("domains") or {}).get("parking")
    if parking is not None:
        assert parking.get("provenance") != "explicit"
        assert parking.get("accepted") is not True
    tasks = {item["kind"]: item for item in body["projection"]["tasks"]}
    assert tasks["rental"]["provenance"] == "explicit"
    parking_task = tasks.get("parking")
    if parking_task is not None:
        assert parking_task["provenance"] != "explicit"
        assert parking_task["accepted"] is not True
    message = body.get("buyerSafeMessage") or ""
    assert message == RENTAL_NO_ADAPTER_COPY
    assert "when should parking" not in message.lower()


def test_rental_then_parking_uses_parking_place_and_dates() -> None:
    client, _provider = _wired()
    created = client.post(
        f"{PREFIX}/sessions",
        json={"objective": "need car rental from 19 to 23 October in Heathrow"},
    ).json()
    session_id = created["sessionId"]
    parked = client.post(
        f"{PREFIX}/sessions/{session_id}/turns",
        json={"message": "parking in Manchester from 26 to 28"},
    )
    assert parked.status_code == 200, parked.text
    fields = parked.json()["domains"]["parking"]["fields"]
    assert fields["airportCode"]["value"] == "MAN"
    assert str(fields["start"]["value"]).startswith("2026-10-26")
    assert str(fields["end"]["value"]).startswith("2026-10-28")
    blob = (parked.json().get("buyerSafeMessage") or "").lower()
    assert "19 october" not in blob
    assert "23 october" not in blob
    timed = client.post(
        f"{PREFIX}/sessions/{session_id}/turns",
        json={"message": "covered, 7 am to 10 pm"},
    )
    assert timed.status_code == 200, timed.text
    later = timed.json()["domains"]["parking"]["fields"]
    assert later["airportCode"]["value"] == "MAN"
    assert str(later["start"]["value"]).startswith("2026-10-26T07:00")
    assert str(later["end"]["value"]).startswith("2026-10-28T22:00")
    pending = timed.json().get("pendingSearchAuthorization")
    assert isinstance(pending, dict)
    assert "parking.search" in pending["capabilities"]
    prompt = (pending.get("prompt") or timed.json().get("buyerSafeMessage") or "").lower()
    assert "shall i" in prompt or "request offers" in prompt
    assert "confirm this requirement" not in prompt


GATWICK_IN_DAYS = "parking needed in 13 to 16 Gatwick for 2 am to 10 pm with covered parking"


def test_gatwick_in_day_range_keeps_dates_and_clocks() -> None:
    from itaa_api.agent_requirements import infer_year_month_for_day

    client, _provider = _wired()
    body = client.post(f"{PREFIX}/sessions", json={"objective": GATWICK_IN_DAYS}).json()
    fields = body["domains"]["parking"]["fields"]
    year, month = infer_year_month_for_day(13)
    assert fields["airportCode"]["value"] == "LGW"
    assert fields["covered"]["value"] == "preferred"
    assert str(fields["start"]["value"]) == f"{year}-{month}-13T02:00:00"
    assert str(fields["end"]["value"]) == f"{year}-{month}-16T22:00:00"
    message = (body.get("buyerSafeMessage") or "").lower()
    assert "when should parking start" not in message
    assert "when should parking finish" not in message
    pending = body.get("pendingSearchAuthorization")
    assert isinstance(pending, dict)
    assert "parking.search" in pending["capabilities"]
    session_id = body["sessionId"]
    follow = client.post(
        f"{PREFIX}/sessions/{session_id}/turns",
        json={"message": "I had already given 2 am to 10 pm in my previous message"},
    )
    assert follow.status_code == 200, follow.text
    later = follow.json()["domains"]["parking"]["fields"]
    assert str(later["start"]["value"]) == f"{year}-{month}-13T02:00:00"
    assert str(later["end"]["value"]) == f"{year}-{month}-16T22:00:00"
    follow_message = (follow.json().get("buyerSafeMessage") or "").lower()
    assert "when should parking start" not in follow_message


def test_time_only_follow_up_without_parking_word_overlays_clocks() -> None:
    from itaa_api.agent_requirements import infer_year_month_for_day

    client, _provider = _wired()
    created = client.post(
        f"{PREFIX}/sessions",
        json={"objective": "parking needed in 13 to 16 Gatwick with covered parking"},
    ).json()
    year, month = infer_year_month_for_day(13)
    fields = created["domains"]["parking"]["fields"]
    assert str(fields["start"]["value"]).startswith(f"{year}-{month}-13")
    assert str(fields["end"]["value"]).startswith(f"{year}-{month}-16")
    assert "T02:00:00" not in str(fields["start"]["value"])
    session_id = created["sessionId"]
    timed = client.post(
        f"{PREFIX}/sessions/{session_id}/turns",
        json={"message": "I had already given 2 am to 10 pm in my previous message"},
    )
    assert timed.status_code == 200, timed.text
    clocks = timed.json()["domains"]["parking"]["fields"]
    assert str(clocks["start"]["value"]) == f"{year}-{month}-13T02:00:00"
    assert str(clocks["end"]["value"]) == f"{year}-{month}-16T22:00:00"
    pending = timed.json().get("pendingSearchAuthorization")
    assert isinstance(pending, dict)
    assert "parking.search" in pending["capabilities"]
