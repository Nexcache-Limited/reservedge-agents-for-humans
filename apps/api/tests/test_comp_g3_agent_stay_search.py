from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient
from wp06_fakes import build_facade

from itaa_api.agent_session import PREFIX, build_agent_app
from itaa_aws_adapter.agent import compose_orchestrator

MILAN = "I'm travelling to Milan from Mumbai from 20 to 30 October"
LONDON = "I'm travelling to London from Mumbai from 20 to 30 October"
HOTEL = "I need a hotel in Milan from 20 to 30 October"
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


def test_milan_session_clarifies_and_does_not_auto_search() -> None:
    client, provider = _client()
    created = client.post(f"{PREFIX}/sessions", json={"objective": MILAN})
    assert created.status_code == 200, created.text
    body = created.json()
    facts = body["projection"]["facts"]
    assert facts["destination"] == "Milan"
    assert facts["originCity"] == "Mumbai"
    assert facts["startDate"] == "2026-10-20"
    assert facts["endDate"] == "2026-10-30"
    assert facts["parkingAirport"] == ""
    blob = created.text.lower()
    assert "jfk" not in blob
    assert "skyshield" not in blob
    assert "x-api-key" not in blob
    assert "itaa_liteapi_api_key" not in blob
    assert "sand_" not in blob
    assert body.get("staySearch") in (None, {})
    assert "search_stay_offers" not in provider.execute_tools
    questions = {item["id"] for item in body["projection"]["questions"]}
    assert "helpWith" not in questions
    by_kind = {item["kind"]: item for item in body["projection"]["tasks"]}
    assert "parking" not in by_kind
    assert by_kind.get("hotel", {}).get("provenance") != "explicit"
    transcript = " ".join(str(item.get("text") or "") for item in body["transcript"]).lower()
    assert "booked" not in transcript
    assert "reserved" not in transcript


def _travel_field_values(body: dict[str, object]) -> list[str]:
    """Buyer-visible travel facts and domain airport values only — never opaque IDs."""

    values: list[str] = []
    projection = body.get("projection")
    facts = projection.get("facts") if isinstance(projection, dict) else {}
    if isinstance(facts, dict):
        for key in (
            "originCity",
            "destination",
            "parkingAirport",
            "departureAirport",
            "destinationAirport",
        ):
            values.append(str(facts.get(key) or ""))
    domains = body.get("domains")
    if isinstance(domains, dict):
        for domain in domains.values():
            if not isinstance(domain, dict):
                continue
            fields = domain.get("fields") if isinstance(domain.get("fields"), dict) else {}
            if not isinstance(fields, dict):
                continue
            for field_id in ("origin", "destination", "airportCode"):
                held = fields.get(field_id)
                if isinstance(held, dict):
                    values.append(str(held.get("value") or ""))
    shared = body.get("sharedBookingContext")
    if isinstance(shared, dict):
        for item in shared.get("facts") or []:
            if isinstance(item, dict):
                values.append(str(item.get("value") or ""))
    values.append(str(body.get("buyerSafeMessage") or ""))
    transcript = body.get("transcript")
    if isinstance(transcript, list):
        for item in transcript:
            if isinstance(item, dict):
                values.append(str(item.get("text") or ""))
    return values


def test_london_dated_trip_is_not_a_milan_or_stay_hardcode() -> None:
    client, provider = _client()
    body = client.post(f"{PREFIX}/sessions", json={"objective": LONDON}).json()
    facts = body["projection"]["facts"]
    assert facts["destination"] == "London"
    assert facts["originCity"] == "Mumbai"
    assert facts["destination"] != "Milan"
    assert facts.get("parkingAirport") in ("", None)
    assert body.get("staySearch") in (None, {})
    assert "search_stay_offers" not in provider.execute_tools
    assert "search_flight_offers" not in provider.execute_tools
    flight = (body.get("domains") or {}).get("flight")
    if isinstance(flight, dict) and flight:
        fields = flight.get("fields") if isinstance(flight.get("fields"), dict) else {}
        origin = ((fields or {}).get("origin") or {}).get("value")
        destination = ((fields or {}).get("destination") or {}).get("value")
        if origin:
            assert origin == "BOM"
        if destination:
            assert destination == "LON"
    for value in _travel_field_values(body):
        assert not re.search(r"\bJFK\b", value, re.I)
        assert not re.search(r"\bMilan\b", value, re.I)


def test_explicit_hotel_dispatches_stay_search_after_yes() -> None:
    client, provider = _client()
    created = client.post(f"{PREFIX}/sessions", json={"objective": HOTEL})
    assert created.status_code == 200, created.text
    body = created.json()
    assert body.get("staySearch") in (None, {})
    assert "search_stay_offers" not in provider.execute_tools
    pending = body.get("pendingSearchAuthorization")
    assert isinstance(pending, dict)
    assert "stay.search" in pending["capabilities"]
    confirmed = client.post(f"{PREFIX}/sessions/{body['sessionId']}/turns", json={"message": "yes"})
    assert confirmed.status_code == 200, confirmed.text
    stay = confirmed.json()["staySearch"]
    assert isinstance(stay, dict)
    assert stay["status"] == "ok"
    assert stay["source"] == "fake"
    assert stay["bookingAuthority"] == "none"
    names = " ".join(str(item.get("name") or "") for item in stay["offers"]).lower()
    assert "milan" in names or "milan" in str(stay["query"]).lower()
    assert "search_stay_offers" in provider.execute_tools
    assert "jfk" not in created.text.lower()


def test_follow_up_hotel_and_rental_activates_stay_only() -> None:
    client, provider = _client()
    created = client.post(f"{PREFIX}/sessions", json={"objective": MILAN}).json()
    session_id = created["sessionId"]
    assert "search_stay_offers" not in provider.execute_tools
    refined = client.post(
        f"{PREFIX}/sessions/{session_id}/turns",
        json={"message": "Flights are booked. I need a hotel and rental car."},
    )
    assert refined.status_code == 200, refined.text
    body = refined.json()
    by_kind = {item["kind"]: item for item in body["projection"]["tasks"]}
    assert by_kind["hotel"]["provenance"] == "explicit"
    assert by_kind["rental"]["provenance"] == "explicit"
    assert "parking" not in by_kind
    assert "search_stay_offers" not in provider.execute_tools
    yes = client.post(
        f"{PREFIX}/sessions/{session_id}/turns",
        json={"message": "yes"},
    )
    assert yes.status_code == 200, yes.text
    body = yes.json()
    assert "search_stay_offers" in provider.execute_tools
    stay = body["staySearch"]
    assert isinstance(stay, dict)
    assert stay["status"] == "ok"


def test_parking_demo_does_not_invoke_stay_search() -> None:
    client, provider = _client()
    body = client.post(f"{PREFIX}/sessions", json={"objective": PARK}).json()
    assert body["projection"]["facts"]["parkingAirport"] == "JFK"
    assert body.get("staySearch") in (None, {})
    assert "search_stay_offers" not in provider.execute_tools


def test_sandbox_hold_runs_after_search_authorization() -> None:
    client, provider = _client()
    created = client.post(f"{PREFIX}/sessions", json={"objective": HOTEL})
    assert created.status_code == 200, created.text
    body = created.json()
    searched = client.post(f"{PREFIX}/sessions/{body['sessionId']}/turns", json={"message": "yes"})
    assert searched.status_code == 200, searched.text
    offer_id = searched.json()["staySearch"]["offers"][0]["id"]
    assert "rateRef" not in searched.text
    held = client.post(
        f"{PREFIX}/sessions/{body['sessionId']}/turns",
        json={"tool": "book_stay_sandbox", "payload": {"offerId": offer_id}},
    )
    assert held.status_code == 200, held.text
    payload = held.json()
    hold = payload["staySearch"]["offers"][0]["sandboxHold"]
    assert hold["status"] == "ok"
    assert hold["simulatedPayment"] is True
    assert hold["bookingId"]
    assert "book_stay_sandbox" in provider.execute_tools
    assert "rateRef" not in held.text
    assert "x-api-key" not in held.text.lower()
