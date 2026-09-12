from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from wp06_fakes import build_facade

from itaa_api.agent_session import PREFIX, build_agent_app
from itaa_aws_adapter.agent import compose_orchestrator

MILAN = "I'm travelling to Milan from Mumbai from 20 to 30 October"
LONDON = "I'm travelling to London from Mumbai from 20 to 30 October"
HOTEL_THINGS = "Flights are booked. I need a hotel and some things to do while I'm there."
PARKING = "I also need parking at Mumbai airport."
CHECKOUT = "Change my hotel checkout to 31 October."
EVENING = "Show me evening activities instead."


@pytest.fixture(autouse=True)
def _fake_providers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ITAA_STAY_SEARCH_MODE", "fake")
    monkeypatch.setenv("ITAA_EXPERIENCE_SEARCH_MODE", "fake")
    monkeypatch.delenv("ITAA_LITEAPI_API_KEY", raising=False)
    monkeypatch.delenv("ITAA_PRIOTICKET_CLIENT_ID", raising=False)
    monkeypatch.delenv("ITAA_PRIOTICKET_CLIENT_SECRET", raising=False)


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


def test_travel_alone_does_not_make_experience_explicit() -> None:
    client, provider = _client()
    body = client.post(f"{PREFIX}/sessions", json={"objective": MILAN}).json()
    kinds = {item["kind"] for item in body["projection"]["tasks"]}
    assert "experience" not in kinds
    assert body.get("experienceSearch") in (None, {})
    assert "search_experience_offers" not in provider.execute_tools
    assert "jfk" not in str(body).lower()


def test_hotel_and_things_to_do_dispatch_both_searches() -> None:
    client, provider = _client()
    created = client.post(f"{PREFIX}/sessions", json={"objective": MILAN}).json()
    session_id = created["sessionId"]
    refined = client.post(
        f"{PREFIX}/sessions/{session_id}/turns",
        json={"message": HOTEL_THINGS},
    )
    assert refined.status_code == 200, refined.text
    body = refined.json()
    by_kind = {item["kind"]: item for item in body["projection"]["tasks"]}
    assert by_kind["hotel"]["provenance"] == "explicit"
    assert by_kind["experience"]["provenance"] == "explicit"
    assert "parking" not in by_kind
    assert "rental" not in by_kind
    facts = body["projection"]["facts"]
    assert facts.get("flightSatisfied") is True
    assert body.get("staySearch") in (None, {})
    pending = body.get("pendingSearchAuthorization")
    assert isinstance(pending, dict)
    assert "stay.search" in pending["capabilities"]
    assert "experience.search" in pending["capabilities"]
    yes = client.post(
        f"{PREFIX}/sessions/{session_id}/turns",
        json={"message": "yes"},
    )
    assert yes.status_code == 200, yes.text
    later = yes.json()
    stay = later["staySearch"]
    experience = later["experienceSearch"]
    assert isinstance(stay, dict) and stay["status"] == "ok"
    assert isinstance(experience, dict) and experience["status"] == "ok"
    assert stay["providerId"] != experience["providerId"]
    assert "search_stay_offers" in provider.execute_tools
    assert "search_experience_offers" in provider.execute_tools
    stay_names = " ".join(str(item.get("name") or "") for item in stay["offers"]).lower()
    exp_titles = " ".join(str(item.get("title") or "") for item in experience["offers"]).lower()
    assert "milan" in stay_names or "milan" in str(stay["query"]).lower()
    assert "milan" in exp_titles or "milan" in str(experience["query"]).lower()
    assert all("checkIn" not in item for item in experience["offers"])
    assert "client_secret" not in yes.text.lower()
    assert "itaa_prioticket" not in yes.text.lower()


def test_london_things_to_do_is_not_milan_hardcode() -> None:
    client, provider = _client()
    created = client.post(f"{PREFIX}/sessions", json={"objective": LONDON}).json()
    session_id = created["sessionId"]
    refined = client.post(
        f"{PREFIX}/sessions/{session_id}/turns",
        json={"message": "Find things to do in London"},
    ).json()
    assert refined.get("experienceSearch") in (None, {})
    yes = client.post(
        f"{PREFIX}/sessions/{session_id}/turns",
        json={"message": "yes"},
    ).json()
    experience = yes["experienceSearch"]
    assert isinstance(experience, dict)
    blob = str(experience).lower()
    assert "london" in blob
    assert "duomo" not in blob
    assert "jfk" not in blob
    assert "search_experience_offers" in provider.execute_tools


def test_parking_does_not_stale_stay_or_experience() -> None:
    client, _provider = _client()
    created = client.post(f"{PREFIX}/sessions", json={"objective": MILAN}).json()
    session_id = created["sessionId"]
    client.post(f"{PREFIX}/sessions/{session_id}/turns", json={"message": HOTEL_THINGS})
    client.post(f"{PREFIX}/sessions/{session_id}/turns", json={"message": "yes"})
    parked = client.post(
        f"{PREFIX}/sessions/{session_id}/turns",
        json={"message": PARKING},
    ).json()
    assert parked["domains"]["parking"]["provenance"] == "explicit"
    assert parked["staySearch"].get("stale") is not True
    assert parked["experienceSearch"].get("stale") is not True


def test_checkout_change_stales_only_stay() -> None:
    client, provider = _client()
    created = client.post(f"{PREFIX}/sessions", json={"objective": MILAN}).json()
    session_id = created["sessionId"]
    client.post(f"{PREFIX}/sessions/{session_id}/turns", json={"message": HOTEL_THINGS})
    client.post(f"{PREFIX}/sessions/{session_id}/turns", json={"message": "yes"})
    before_experience = provider.execute_tools.count("search_experience_offers")
    changed = client.post(
        f"{PREFIX}/sessions/{session_id}/turns",
        json={"message": CHECKOUT},
    ).json()
    assert changed["projection"]["facts"]["endDate"] == "2026-10-31"
    stay = changed["staySearch"]
    experience = changed["experienceSearch"]
    assert isinstance(stay, dict)
    assert stay.get("query", {}).get("checkOut") == "2026-10-31" or stay.get("stale") is True
    assert experience.get("stale") is not True
    assert provider.execute_tools.count("search_experience_offers") == before_experience


def test_evening_preference_stales_only_experience() -> None:
    client, provider = _client()
    created = client.post(f"{PREFIX}/sessions", json={"objective": MILAN}).json()
    session_id = created["sessionId"]
    client.post(f"{PREFIX}/sessions/{session_id}/turns", json={"message": HOTEL_THINGS})
    client.post(f"{PREFIX}/sessions/{session_id}/turns", json={"message": "yes"})
    before_stay = provider.execute_tools.count("search_stay_offers")
    evening = client.post(
        f"{PREFIX}/sessions/{session_id}/turns",
        json={"message": EVENING},
    ).json()
    prefs = evening["projection"]["facts"].get("experiencePreferences") or []
    assert "evening" in prefs
    experience = evening["experienceSearch"]
    assert isinstance(experience, dict)
    assert experience.get("stale") is True
    pending = evening.get("pendingSearchAuthorization")
    assert isinstance(pending, dict)
    assert "experience.search" in pending["capabilities"]
    assert evening["staySearch"].get("stale") is not True
    assert provider.execute_tools.count("search_stay_offers") == before_stay
    assert provider.execute_tools.count("search_experience_offers") == 1
    assert "show" not in {item["kind"] for item in evening["projection"]["tasks"]}
    assert all(item["kind"] != "ents" for item in evening["projection"]["tasks"])
