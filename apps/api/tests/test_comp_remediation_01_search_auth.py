"""COMP-REMEDIATION-01 search authorization and competition journeys."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from wp06_fakes import build_facade

from itaa_api.agent_session import PREFIX, build_agent_app
from itaa_api.app import create_app
from itaa_api.composition import build_facade as api_facade
from itaa_aws_adapter.agent import compose_orchestrator

HEATHROW = "I need a hotel and covered parking at Heathrow from 10 to 15 November."
MANCHESTER_HOTEL = "Hotel in Manchester 24-25 October."
PARK = (
    "I'm flying from JFK on September 3 at 1 PM and returning September 8 at 10 PM. "
    "I have a standard EV, prefer covered parking, and don't want a shuttle longer than 20 minutes."
)


@pytest.fixture(autouse=True)
def _fake_stay_search(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ITAA_STAY_SEARCH_MODE", "fake")
    monkeypatch.delenv("ITAA_LITEAPI_API_KEY", raising=False)


class OrchestratorProvider:
    def __init__(self) -> None:
        self.orch = compose_orchestrator(build_facade())
        self.execute_tools: list[str] = []

    def plan_turn(self, payload: dict[str, object]) -> dict[str, object]:
        from itaa_aws_adapter.schemas import PlanAnswers, PlanTurnContext

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


def test_explicit_hotel_waits_for_search_authorization() -> None:
    client, provider = _client()
    created = client.post(
        f"{PREFIX}/sessions", json={"objective": "I need a hotel in Milan from 20 to 30 October"}
    )
    assert created.status_code == 200, created.text
    body = created.json()
    assert body.get("staySearch") in (None, {})
    assert "search_stay_offers" not in provider.execute_tools
    pending = body.get("pendingSearchAuthorization")
    assert isinstance(pending, dict)
    assert "stay.search" in pending["capabilities"]
    session_id = body["sessionId"]
    confirmed = client.post(
        f"{PREFIX}/sessions/{session_id}/turns", json={"message": "yes, go ahead"}
    )
    assert confirmed.status_code == 200, confirmed.text
    later = confirmed.json()
    assert "search_stay_offers" in provider.execute_tools
    stay = later["staySearch"]
    assert isinstance(stay, dict)
    assert stay["status"] == "ok"
    transcript = " ".join(str(item.get("text") or "") for item in later["transcript"]).lower()
    assert "sandbox hotel search" not in transcript
    assert "panel on the right" in (later.get("buyerSafeMessage") or "").lower()


def test_hotel_first_does_not_search_parking() -> None:
    client, provider = _wired()
    created = client.post(f"{PREFIX}/sessions", json={"objective": HEATHROW}).json()
    session_id = created["sessionId"]
    timed = client.post(
        f"{PREFIX}/sessions/{session_id}/turns",
        json={"message": "8am on the 10th until 6pm on the 15th"},
    )
    assert timed.status_code == 200, timed.text
    ready = timed.json()
    pending = ready.get("pendingSearchAuthorization")
    assert isinstance(pending, dict)
    assert "stay.search" in pending["capabilities"]
    assert "parking.search" in pending["capabilities"]
    assert "search_stay_offers" not in provider.execute_tools
    hotel_only = client.post(
        f"{PREFIX}/sessions/{session_id}/turns", json={"message": "hotel first"}
    )
    assert hotel_only.status_code == 200, hotel_only.text
    body = hotel_only.json()
    assert "search_stay_offers" in provider.execute_tools
    parking = body["domains"]["parking"]
    offers = ((parking.get("offerSet") or {}).get("snapshot") or {}).get("offers")
    assert not offers
    assert body.get("pendingSearchAuthorization") is None or "parking.search" in (
        body.get("pendingSearchAuthorization") or {}
    ).get("capabilities", [])


def test_journey_a_yes_searches_stay_and_parking() -> None:
    client, provider = _wired()
    created = client.post(f"{PREFIX}/sessions", json={"objective": HEATHROW}).json()
    session_id = created["sessionId"]
    assert created.get("staySearch") in (None, {})
    parking = created["domains"]["parking"]
    assert parking["fields"]["airportCode"]["value"] == "LHR"
    assert "T08:00" not in str(parking["fields"].get("start", {}).get("value") or "")
    timed = client.post(
        f"{PREFIX}/sessions/{session_id}/turns",
        json={"message": "8am on the 10th to 6pm on the 15th"},
    ).json()
    start = str(timed["domains"]["parking"]["fields"]["start"]["value"])
    end = str(timed["domains"]["parking"]["fields"]["end"]["value"])
    assert start.startswith("2026-11-10T08:00:00Z")
    assert end.startswith("2026-11-15T18:00:00Z")
    pending = timed.get("pendingSearchAuthorization")
    assert isinstance(pending, dict)
    assert set(pending["capabilities"]) >= {"stay.search", "parking.search"}
    assert "search_stay_offers" not in provider.execute_tools
    yes = client.post(f"{PREFIX}/sessions/{session_id}/turns", json={"message": "yes, go ahead"})
    assert yes.status_code == 200, yes.text
    body = yes.json()
    assert "search_stay_offers" in provider.execute_tools
    stay = body["staySearch"]
    assert isinstance(stay, dict) and stay["status"] == "ok"
    offers = body["domains"]["parking"]["offerSet"]["snapshot"]["offers"]
    assert {item["rank"] for item in offers} == {1, 2, 3}
    blob = f"{body.get('buyerSafeMessage') or ''} {body['transcript']}".lower()
    assert "sandbox hotel search" not in blob
    assert "liteapi" not in (body.get("buyerSafeMessage") or "").lower()


def test_journey_b_flight_is_a_capability_and_man_resolves() -> None:
    client, provider = _client()
    created = client.post(f"{PREFIX}/sessions", json={"objective": MANCHESTER_HOTEL}).json()
    session_id = created["sessionId"]
    assert created.get("staySearch") in (None, {})
    flight = client.post(
        f"{PREFIX}/sessions/{session_id}/turns",
        json={"message": "a flight to Heathrow"},
    )
    assert flight.status_code == 200, flight.text
    body = flight.json()
    message = (body.get("buyerSafeMessage") or "").lower()
    assert "flight booking isn't available" not in message
    kinds = {str(item.get("kind")) for item in body["projection"]["tasks"]}
    assert "flight" in kinds
    assert "search_flight_offers" not in provider.execute_tools
    man = client.post(f"{PREFIX}/sessions/{session_id}/turns", json={"message": "man"})
    assert man.status_code == 200, man.text
    later = man.json()
    departure = later["projection"]["facts"].get("departureAirport")
    parking = (later.get("domains") or {}).get("parking") or {}
    airport = ((parking.get("fields") or {}).get("airportCode") or {}).get("value")
    assert departure == "MAN" or airport == "MAN"
    assert "search_stay_offers" not in provider.execute_tools


def test_parking_clock_follow_up_keeps_october_dates() -> None:
    client, _provider = _wired()
    created = client.post(
        f"{PREFIX}/sessions",
        json={"objective": "hotel needed in manchester from 24 to 25 October. need parking"},
    ).json()
    session_id = created["sessionId"]
    timed = client.post(
        f"{PREFIX}/sessions/{session_id}/turns",
        json={"message": "covered parking from 2 am to 10 pm"},
    )
    assert timed.status_code == 200, timed.text
    fields = timed.json()["domains"]["parking"]["fields"]
    assert str(fields["start"]["value"]).startswith("2026-10-24T02:00:00Z")
    assert str(fields["end"]["value"]).startswith("2026-10-25T22:00:00Z")
    assert "2026-10-02" not in str(fields["start"]["value"])
    assert "2026-10-10" not in str(fields["end"]["value"])


def test_demo_a_yes_runs_parking_search() -> None:
    client, _provider = _wired()
    created = client.post(f"{PREFIX}/sessions", json={"objective": PARK}).json()
    session_id = created["sessionId"]
    pending = created.get("pendingSearchAuthorization")
    assert isinstance(pending, dict)
    assert "parking.search" in pending["capabilities"]
    assert created.get("pendingAuthorization") in (None, {})
    yes = client.post(f"{PREFIX}/sessions/{session_id}/turns", json={"message": "yes"})
    assert yes.status_code == 200, yes.text
    offers = yes.json()["domains"]["parking"]["offerSet"]["snapshot"]["offers"]
    assert {item["rank"] for item in offers} == {1, 2, 3}


def test_requirement_change_invalidates_pending_search() -> None:
    client, provider = _client()
    created = client.post(
        f"{PREFIX}/sessions", json={"objective": "I need a hotel in Milan from 20 to 30 October"}
    ).json()
    session_id = created["sessionId"]
    assert created.get("pendingSearchAuthorization")
    changed = client.post(
        f"{PREFIX}/sessions/{session_id}/turns",
        json={"message": "Change my hotel checkout to the 31st"},
    )
    assert changed.status_code == 200, changed.text
    body = changed.json()
    assert "search_stay_offers" not in provider.execute_tools
    pending = body.get("pendingSearchAuthorization")
    assert isinstance(pending, dict)
    yes = client.post(f"{PREFIX}/sessions/{session_id}/turns", json={"message": "yes"})
    assert yes.status_code == 200, yes.text
    assert "search_stay_offers" in provider.execute_tools


def test_match_confirmation_yes_variants_and_subsets() -> None:
    from itaa_api.search_authorization import PARKING, STAY, match_confirmation

    pending = {
        "capabilities": [STAY, PARKING],
        "fingerprints": {"stay.search": "a", "parking.search": "b"},
        "prompt": "Shall I search both now?",
    }
    assert match_confirmation("yes, go ahead", pending) == (STAY, PARKING)
    assert match_confirmation("Yes!", pending) == (STAY, PARKING)
    assert match_confirmation("go ahead", pending) == (STAY, PARKING)
    assert match_confirmation("proceed", pending) == (STAY, PARKING)
    assert match_confirmation("search both", pending) == (STAY, PARKING)
    assert match_confirmation("hotel first", pending) == (STAY,)
    assert match_confirmation("parking only", pending) == (PARKING,)
    assert match_confirmation("maybe later", pending) is None


def test_heathrow_named_airport_is_stay_destination() -> None:
    client, _provider = _client()
    created = client.post(f"{PREFIX}/sessions", json={"objective": HEATHROW}).json()
    facts = created["projection"]["facts"]
    assert facts["destination"] == "Heathrow"
    assert facts["parkingAirport"] == "LHR"
    assert facts["startDate"] == "2026-11-10"
    assert facts["endDate"] == "2026-11-15"
    assert created.get("staySearch") in (None, {})
    assert created.get("pendingSearchAuthorization") is None
