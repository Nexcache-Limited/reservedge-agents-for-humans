from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from wp06_fakes import build_facade

from itaa_api.agent_session import PREFIX, build_agent_app
from itaa_aws_adapter.agent import compose_orchestrator

MILAN = "I'm travelling to Milan from Mumbai from 20 to 30 October"
HOTEL_RENTAL = "Flights are booked. I need a hotel and rental car."
PARKING = "I also need parking."
CHECKOUT = "Change my hotel checkout to the 31st"


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


def test_milan_shared_context_without_forced_domains() -> None:
    client, provider = _client()
    body = client.post(f"{PREFIX}/sessions", json={"objective": MILAN}).json()
    shared = body["sharedBookingContext"]
    values = {item["id"]: item["value"] for item in shared["facts"]}
    assert values["destination"] == "Milan"
    assert values["originCity"] == "Mumbai"
    assert "2026-10-20" in values["dates"] or values["startDate"] == "2026-10-20"
    domains = body.get("domains") or {}
    assert "parking" not in domains
    assert "rental" not in domains
    assert "stay" not in domains
    assert body.get("staySearch") in (None, {})
    assert "search_stay_offers" not in provider.execute_tools
    assert body["workspace"]["persistence"] == "process-local"


def test_hotel_and_rental_activate_independent_lanes() -> None:
    client, provider = _client()
    created = client.post(f"{PREFIX}/sessions", json={"objective": MILAN}).json()
    session_id = created["sessionId"]
    refined = client.post(
        f"{PREFIX}/sessions/{session_id}/turns",
        json={"message": HOTEL_RENTAL},
    ).json()
    by_kind = {item["kind"]: item for item in refined["projection"]["tasks"]}
    assert by_kind["hotel"]["provenance"] == "explicit"
    assert by_kind["rental"]["provenance"] == "explicit"
    assert "parking" not in by_kind
    assert "stay" in refined["domains"]
    assert refined["domains"]["stay"]["provenance"] == "explicit"
    assert "rental" in refined["domains"]
    assert "parking" not in refined["domains"]
    assert refined.get("staySearch") in (None, {})
    yes = client.post(
        f"{PREFIX}/sessions/{session_id}/turns",
        json={"message": "yes"},
    ).json()
    stay = yes["staySearch"]
    assert isinstance(stay, dict)
    assert stay["stale"] is False
    assert stay["offerKind"] == "regular"
    assert all(item.get("offerKind") == "regular" for item in stay["offers"])
    assert "search_stay_offers" in provider.execute_tools
    assert "no rental inventory" in (yes.get("buyerSafeMessage") or "").lower()


def test_adding_parking_does_not_stale_stay() -> None:
    client, _provider = _client()
    created = client.post(f"{PREFIX}/sessions", json={"objective": MILAN}).json()
    session_id = created["sessionId"]
    client.post(f"{PREFIX}/sessions/{session_id}/turns", json={"message": HOTEL_RENTAL})
    client.post(f"{PREFIX}/sessions/{session_id}/turns", json={"message": "yes"})
    parked = client.post(
        f"{PREFIX}/sessions/{session_id}/turns",
        json={"message": PARKING},
    ).json()
    assert parked["domains"]["parking"]["provenance"] == "explicit"
    stay = parked["staySearch"]
    assert isinstance(stay, dict)
    assert stay.get("stale") is not True
    parking_offers = (parked["domains"]["parking"].get("offerSet") or {}).get("stale")
    assert parking_offers is not True


def test_stay_checkout_change_does_not_mark_parking_stale() -> None:
    client, provider = _client()
    created = client.post(f"{PREFIX}/sessions", json={"objective": MILAN}).json()
    session_id = created["sessionId"]
    client.post(f"{PREFIX}/sessions/{session_id}/turns", json={"message": HOTEL_RENTAL})
    client.post(f"{PREFIX}/sessions/{session_id}/turns", json={"message": "yes"})
    client.post(f"{PREFIX}/sessions/{session_id}/turns", json={"message": PARKING})
    before = len(provider.execute_tools)
    changed = client.post(
        f"{PREFIX}/sessions/{session_id}/turns",
        json={"message": CHECKOUT},
    ).json()
    parking = changed["domains"]["parking"]
    assert parking["offerSet"]["stale"] is not True
    stay = changed.get("staySearch")
    assert isinstance(stay, dict)
    assert stay.get("stale") is True
    assert len(provider.execute_tools) == before
