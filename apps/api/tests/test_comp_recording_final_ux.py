from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from wp06_fakes import build_facade

from itaa_api.agent_session import PREFIX, build_agent_app
from itaa_api.app import create_app
from itaa_api.composition import build_facade as api_facade
from itaa_api.search_authorization import search_ask_prompt
from itaa_aws_adapter.agent import compose_orchestrator

LONDON_UAT = (
    "Travelling from New York to London on 17 October. Need hotel in London for two days. "
    "Also need covered parking in London from 5pm on the 17th October to 5pm on the 18th. "
    "If any sightseeing attractions are there, show me that too."
)
MANCHESTER = (
    "I need a flight from Manchester to Heathrow on 25 October, "
    "a hotel near Heathrow, and airport parking in Manchester."
)
DEMO_A = (
    "I'm flying from JFK on September 3 at 1 PM and returning September 8 at 10 PM. "
    "I have a standard EV, prefer covered parking, and don't want a shuttle longer than 20 minutes."
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
        self.execute_payloads: list[dict[str, object]] = []

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
        held = inner if isinstance(inner, dict) else {}
        self.execute_payloads.append({"tool": tool, "payload": dict(held)})
        result = self.orch.execute_turn(tool, held)
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


def _parking_window(body: dict[str, object]) -> tuple[str, str]:
    parking = (body.get("domains") or {}).get("parking") or {}
    fields = parking.get("fields") if isinstance(parking, dict) else {}
    start = ((fields or {}).get("start") or {}).get("value")
    end = ((fields or {}).get("end") or {}).get("value")
    return str(start or ""), str(end or "")


def test_london_uat_resolves_future_year_and_domain_parking_window() -> None:
    client, provider = _client()
    created = client.post(f"{PREFIX}/sessions", json={"objective": LONDON_UAT})
    assert created.status_code == 200, created.text
    body = created.json()
    facts = body["projection"]["facts"]
    assert facts["destination"] == "London"
    assert facts["originCity"] == "New York"
    assert facts["startDate"] == "2026-10-17"
    assert facts["endDate"] == "2026-10-19"
    assert "2025" not in str(facts["startDate"])
    assert "2025" not in str(facts["endDate"])
    start, end = _parking_window(body)
    assert start == "2026-10-17T17:00:00"
    assert end == "2026-10-18T17:00:00"
    assert not start.endswith("Z")
    assert not end.endswith("Z")
    assert not end.startswith("2026-10-19")
    kinds = {item["kind"]: item for item in body["projection"]["tasks"]}
    assert kinds["hotel"]["provenance"] == "explicit"
    assert kinds["experience"]["provenance"] == "explicit"
    assert kinds["parking"]["provenance"] == "explicit"
    assert kinds["flight"]["provenance"] == "proposed"
    assert kinds["flight"]["accepted"] is False
    assert body.get("staySearch") in (None, {})
    assert body.get("experienceSearch") in (None, {})
    assert body.get("flightSearch") in (None, {})
    assert provider.execute_tools == []
    message = (body.get("buyerSafeMessage") or "").lower()
    assert "heathrow" in message or "which london airport" in message
    assert "shall i search" not in message
    assert "flight" in message or "travelling from new york" in message
    pending = body.get("pendingSearchAuthorization")
    assert pending in (None, {})
    parking = body["domains"]["parking"]
    assert "airportCode" in parking["missing"]
    assert parking["fields"].get("airportCode", {}).get("value") in (None, "", "")


def test_london_uat_readiness_names_only_pending_capabilities() -> None:
    client, provider = _client()
    created = client.post(f"{PREFIX}/sessions", json={"objective": LONDON_UAT}).json()
    session_id = created["sessionId"]
    airport = client.post(f"{PREFIX}/sessions/{session_id}/turns", json={"message": "lhr"})
    assert airport.status_code == 200, airport.text
    body = airport.json()
    assert provider.execute_tools == []
    pending = body.get("pendingSearchAuthorization")
    assert isinstance(pending, dict)
    caps = pending["capabilities"]
    assert "parking.search" in caps
    assert "stay.search" in caps
    assert "experience.search" in caps
    assert "flight.search" not in caps
    prompt = str(pending.get("prompt") or "").lower()
    assert "hotel" in prompt
    assert "parking" in prompt
    assert "things to do" in prompt
    assert "flight" not in prompt
    message = (body.get("buyerSafeMessage") or "").lower()
    assert "shall i search" in message
    assert "hotel" in message
    assert "preferred departure time" not in message
    start, end = _parking_window(body)
    assert start == "2026-10-17T17:00:00"
    assert end == "2026-10-18T17:00:00"
    parking = body["domains"]["parking"]
    assert parking["fields"]["airportCode"]["value"] == "LHR"
    assert parking["fields"].get("covered", {}).get("value") in {"preferred", "required"}


def test_london_uat_yes_searches_ready_domains_not_unconfirmed_flight() -> None:
    client, provider = _wired()
    created = client.post(f"{PREFIX}/sessions", json={"objective": LONDON_UAT}).json()
    session_id = created["sessionId"]
    client.post(f"{PREFIX}/sessions/{session_id}/turns", json={"message": "lhr"})
    yes = client.post(f"{PREFIX}/sessions/{session_id}/turns", json={"message": "yes"})
    assert yes.status_code == 200, yes.text
    body = yes.json()
    tools = provider.execute_tools
    assert "search_stay_offers" in tools
    assert "search_experience_offers" in tools
    assert "search_flight_offers" not in tools
    stay_payload = next(
        item for item in provider.execute_payloads if item["tool"] == "search_stay_offers"
    )
    stay_body = stay_payload["payload"]
    assert stay_body["destination"] == "London"
    assert str(stay_body["checkIn"]).startswith("2026-10-17")
    assert str(stay_body["checkOut"]).startswith("2026-10-19")
    assert "2025" not in str(stay_body)
    stay = body.get("staySearch") or {}
    assert isinstance(stay, dict)
    assert stay.get("status") == "ok"
    names = " ".join(str(item.get("name") or "") for item in stay.get("offers") or []).lower()
    assert "london" in names or "savoy" in names or "citizenm" in names
    parking_start, parking_end = _parking_window(body)
    assert parking_start == "2026-10-17T17:00:00"
    assert parking_end == "2026-10-18T17:00:00"
    offers = (
        ((body.get("domains") or {}).get("parking") or {}).get("offerSet", {}).get("snapshot", {})
    )
    snapshot = offers if isinstance(offers, dict) else {}
    ranked = snapshot.get("offers") or []
    assert isinstance(ranked, list) and ranked
    experience = body.get("experienceSearch")
    if isinstance(experience, dict):
        assert experience.get("bookingAuthority") == "none"
    assert body.get("flightSearch") in (None, {})
    kinds = [item["kind"] for item in body["projection"]["tasks"]]
    assert kinds[0] == "flight"
    assert kinds.index("hotel") < kinds.index("parking")
    assert kinds.index("parking") < kinds.index("experience")


def test_demo_a_does_not_create_flight_task() -> None:
    client, provider = _client()
    body = client.post(f"{PREFIX}/sessions", json={"objective": DEMO_A}).json()
    kinds = {item["kind"] for item in body["projection"]["tasks"]}
    assert "flight" not in kinds
    assert "parking" in kinds
    assert provider.execute_tools == []


def test_manchester_smoke_still_authorizes_flight_hotel_parking() -> None:
    client, provider = _wired()
    created = client.post(f"{PREFIX}/sessions", json={"objective": MANCHESTER})
    assert created.status_code == 200, created.text
    body = created.json()
    session_id = str(body["sessionId"])
    kinds = {str(item.get("kind")) for item in body["projection"]["tasks"]}
    assert {"flight", "hotel", "parking"} <= kinds
    pending = body.get("pendingSearchAuthorization")
    if not isinstance(pending, dict) or "flight.search" not in pending.get("capabilities", []):
        follow = client.post(
            f"{PREFIX}/sessions/{session_id}/turns",
            json={"message": "covered parking 8am on the 25th to 6pm on the 26th"},
        )
        assert follow.status_code == 200, follow.text
        body = follow.json()
        pending = body.get("pendingSearchAuthorization")
    assert isinstance(pending, dict), body.get("buyerSafeMessage")
    assert "flight.search" in pending["capabilities"]
    assert "search_flight_offers" not in provider.execute_tools
    yes = client.post(f"{PREFIX}/sessions/{session_id}/turns", json={"message": "yes"})
    assert yes.status_code == 200, yes.text
    assert "search_flight_offers" in provider.execute_tools
    assert "search_stay_offers" in provider.execute_tools


def test_search_ask_prompt_names_only_ready_capabilities() -> None:
    prompt = search_ask_prompt(["parking.search"], place="LHR")
    assert "parking" in prompt.lower()
    assert "hotel" not in prompt.lower()
    assert "flight" not in prompt.lower()
    mixed = search_ask_prompt(
        ["stay.search", "parking.search", "experience.search"], place="London"
    )
    assert "hotel" in mixed.lower()
    assert "parking" in mixed.lower()
    assert "things to do" in mixed.lower()
    assert "flight" not in mixed.lower()


def test_london_provider_utc_is_converted_from_airport_local() -> None:
    from itaa_api.agent_requirements import execution_fields

    client, _provider = _client()
    created = client.post(f"{PREFIX}/sessions", json={"objective": LONDON_UAT}).json()
    session_id = created["sessionId"]
    body = client.post(f"{PREFIX}/sessions/{session_id}/turns", json={"message": "lhr"}).json()
    parking = body["domains"]["parking"]
    start, end = _parking_window(body)
    assert start == "2026-10-17T17:00:00"
    assert end == "2026-10-18T17:00:00"
    converted = execution_fields(parking)
    assert converted["start"] == "2026-10-17T16:00:00Z"
    assert converted["end"] == "2026-10-18T16:00:00Z"
    assert converted["airportCode"] == "LHR"


def test_hotel_and_parking_first_does_not_wait_for_flight() -> None:
    client, provider = _wired()
    created = client.post(f"{PREFIX}/sessions", json={"objective": LONDON_UAT}).json()
    session_id = created["sessionId"]
    airport = client.post(f"{PREFIX}/sessions/{session_id}/turns", json={"message": "lhr"}).json()
    message = str(airport.get("buyerSafeMessage") or "").lower()
    assert "shall i search" in message
    assert "preferred departure time" not in message
    subset = client.post(
        f"{PREFIX}/sessions/{session_id}/turns",
        json={"message": "search the hotel and parking first"},
    )
    assert subset.status_code == 200, subset.text
    body = subset.json()
    tools = provider.execute_tools
    assert "search_stay_offers" in tools
    assert "search_flight_offers" not in tools
    assert "search_experience_offers" not in tools
    stay = body.get("staySearch") or {}
    assert isinstance(stay, dict) and stay.get("status") == "ok"
    ranked = ((body.get("domains") or {}).get("parking") or {}).get("offerSet", {}).get(
        "snapshot", {}
    ).get("offers") or []
    assert isinstance(ranked, list) and ranked
    assert body.get("flightSearch") in (None, {})
    kinds = {item["kind"]: item for item in body["projection"]["tasks"]}
    assert kinds["flight"]["provenance"] == "proposed"
    assert kinds["flight"]["accepted"] is False
    start, end = _parking_window(body)
    assert start == "2026-10-17T17:00:00"
    assert end == "2026-10-18T17:00:00"
