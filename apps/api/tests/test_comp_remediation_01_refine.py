"""COMP-REMEDIATION-01 conversational requirement mutations."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from wp06_fakes import build_facade

from itaa_api.agent_session import PREFIX, build_agent_app
from itaa_api.app import create_app
from itaa_api.composition import build_facade as api_facade
from itaa_api.conversation_refine import parse_refinement, parse_trip_dates
from itaa_aws_adapter.agent import compose_orchestrator

HEATHROW = "I need a hotel and covered parking at Heathrow from 10 to 15 November."
MILAN = "I need a hotel in Milan from 20 to 30 October"
TIMES = "8am on the 10th to 6pm on the 15th"


@pytest.fixture(autouse=True)
def _fake_search(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ITAA_STAY_SEARCH_MODE", "fake")
    monkeypatch.setenv("ITAA_EXPERIENCE_SEARCH_MODE", "fake")
    monkeypatch.delenv("ITAA_LITEAPI_API_KEY", raising=False)
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


def _wired() -> tuple[TestClient, OrchestratorProvider]:
    facade = api_facade()
    provider = OrchestratorProvider()
    provider.orch = compose_orchestrator(facade)
    app = create_app(facade=facade)
    app.state.aws_provider = provider
    return TestClient(app), provider


def _client() -> tuple[TestClient, OrchestratorProvider]:
    provider = OrchestratorProvider()
    return TestClient(build_agent_app(provider)), provider


def _open_heathrow(client: TestClient) -> tuple[str, dict[str, object]]:
    created = client.post(f"{PREFIX}/sessions", json={"objective": HEATHROW}).json()
    session_id = str(created["sessionId"])
    timed = client.post(f"{PREFIX}/sessions/{session_id}/turns", json={"message": TIMES}).json()
    return session_id, timed


def _yes(client: TestClient, session_id: str) -> dict[str, object]:
    return client.post(
        f"{PREFIX}/sessions/{session_id}/turns", json={"message": "yes, go ahead"}
    ).json()


def _ctx(body: dict[str, object], key: str) -> str:
    shared = body.get("sharedBookingContext")
    facts = shared if isinstance(shared, dict) else {}
    items = facts.get("facts") if isinstance(facts, dict) else []
    if isinstance(items, list):
        for item in items:
            if isinstance(item, dict) and item.get("id") == key:
                return str(item.get("value") or "")
    projection = body.get("projection") if isinstance(body.get("projection"), dict) else {}
    held = projection.get("facts") if isinstance(projection, dict) else {}
    if isinstance(held, dict):
        return str(held.get(key) or "")
    return ""


def _parking_start(body: dict[str, object]) -> str:
    parking = (body.get("domains") or {}).get("parking") or {}
    fields = parking.get("fields") if isinstance(parking, dict) else {}
    held = fields.get("start") if isinstance(fields, dict) else {}
    return str(held.get("value") or "") if isinstance(held, dict) else ""


def _parking_end(body: dict[str, object]) -> str:
    parking = (body.get("domains") or {}).get("parking") or {}
    fields = parking.get("fields") if isinstance(parking, dict) else {}
    held = fields.get("end") if isinstance(fields, dict) else {}
    return str(held.get("value") or "") if isinstance(held, dict) else ""


def _parking_airport(body: dict[str, object]) -> str:
    parking = (body.get("domains") or {}).get("parking") or {}
    fields = parking.get("fields") if isinstance(parking, dict) else {}
    held = fields.get("airportCode") if isinstance(fields, dict) else {}
    return str(held.get("value") or "") if isinstance(held, dict) else ""


def _parking_stale(body: dict[str, object]) -> bool:
    parking = (body.get("domains") or {}).get("parking") or {}
    offer = parking.get("offerSet") if isinstance(parking, dict) else {}
    return isinstance(offer, dict) and offer.get("stale") is True


def test_parse_november_span_does_not_use_clock_days() -> None:
    assert parse_trip_dates("change the dates to 9 to 14 november") == (
        "2026-11-09",
        "2026-11-14",
    )
    change = parse_refinement("change only the hotel dates to 9 to 14 November")
    assert change.date_scope == "stay"
    assert change.start_date == "2026-11-09"
    parking = parse_refinement("change only the parking dates to 9 to 14 November")
    assert parking.date_scope == "parking"
    hold = parse_refinement(
        "change the dates to 9 to 14 November. keep parking on the original dates"
    )
    assert hold.hold_parking_dates is True
    assert hold.start_date == "2026-11-09"


def test_change_all_trip_dates_updates_stay_and_parking() -> None:
    client, provider = _wired()
    session_id, ready = _open_heathrow(client)
    assert _ctx(ready, "startDate") == "2026-11-10"
    assert str(_parking_start(ready)).startswith("2026-11-10T08:00:00")
    changed = client.post(
        f"{PREFIX}/sessions/{session_id}/turns",
        json={"message": "change the dates to 9 to 14 november"},
    )
    assert changed.status_code == 200, changed.text
    body = changed.json()
    assert _ctx(body, "startDate") == "2026-11-09"
    assert _ctx(body, "endDate") == "2026-11-14"
    assert str(_parking_start(body)).startswith("2026-11-09T08:00:00")
    assert str(_parking_end(body)).startswith("2026-11-14T18:00:00")
    pending = body.get("pendingSearchAuthorization")
    assert isinstance(pending, dict)
    assert set(pending["capabilities"]) >= {"stay.search", "parking.search"}
    assert "search_stay_offers" not in provider.execute_tools
    message = (body.get("buyerSafeMessage") or "").lower()
    assert "updated the trip dates" in message
    assert "shall i search" in message


def test_stay_only_date_change_preserves_parking() -> None:
    client, provider = _wired()
    session_id, _ready = _open_heathrow(client)
    searched = _yes(client, session_id)
    assert searched["staySearch"].get("stale") is not True
    stay_count = provider.execute_tools.count("search_stay_offers")
    changed = client.post(
        f"{PREFIX}/sessions/{session_id}/turns",
        json={"message": "change only the hotel dates to 9 to 14 November"},
    ).json()
    assert _ctx(changed, "startDate") == "2026-11-09"
    assert _ctx(changed, "endDate") == "2026-11-14"
    assert str(_parking_start(changed)).startswith("2026-11-10T08:00:00")
    assert str(_parking_end(changed)).startswith("2026-11-15T18:00:00")
    assert changed["staySearch"].get("stale") is True
    assert not _parking_stale(changed)
    pending = changed.get("pendingSearchAuthorization")
    assert isinstance(pending, dict)
    assert pending["capabilities"] == ["stay.search"]
    assert provider.execute_tools.count("search_stay_offers") == stay_count
    assert "parking dates are unchanged" in (changed.get("buyerSafeMessage") or "").lower()


def test_parking_only_date_change_preserves_stay() -> None:
    client, provider = _wired()
    session_id, _ready = _open_heathrow(client)
    _yes(client, session_id)
    stay_count = provider.execute_tools.count("search_stay_offers")
    changed = client.post(
        f"{PREFIX}/sessions/{session_id}/turns",
        json={"message": "change only the parking dates to 9 to 14 November"},
    ).json()
    assert _ctx(changed, "startDate") == "2026-11-10"
    assert _ctx(changed, "endDate") == "2026-11-15"
    assert str(_parking_start(changed)).startswith("2026-11-09T08:00:00")
    assert str(_parking_end(changed)).startswith("2026-11-14T18:00:00")
    assert _parking_stale(changed)
    assert changed["staySearch"].get("stale") is not True
    pending = changed.get("pendingSearchAuthorization")
    assert isinstance(pending, dict)
    assert pending["capabilities"] == ["parking.search"]
    assert provider.execute_tools.count("search_stay_offers") == stay_count


def test_date_change_after_results_stales_and_requires_new_auth() -> None:
    client, provider = _wired()
    session_id, _ready = _open_heathrow(client)
    searched = _yes(client, session_id)
    assert searched["staySearch"]["status"] == "ok"
    assert searched["staySearch"].get("stale") is not True
    assert not _parking_stale(searched)
    stay_count = provider.execute_tools.count("search_stay_offers")
    changed = client.post(
        f"{PREFIX}/sessions/{session_id}/turns",
        json={"message": "change the dates to 9 to 14 november"},
    ).json()
    assert changed["staySearch"].get("stale") is True
    assert _parking_stale(changed)
    assert _ctx(changed, "startDate") == "2026-11-09"
    pending = changed.get("pendingSearchAuthorization")
    assert isinstance(pending, dict)
    assert set(pending["capabilities"]) >= {"stay.search", "parking.search"}
    assert provider.execute_tools.count("search_stay_offers") == stay_count
    yes = _yes(client, session_id)
    assert provider.execute_tools.count("search_stay_offers") == stay_count + 1
    assert yes["staySearch"].get("stale") is not True
    assert _ctx(yes, "startDate") == "2026-11-09"


def test_date_change_while_search_auth_pending_invalidates() -> None:
    client, provider = _wired()
    session_id, ready = _open_heathrow(client)
    prior = ready.get("pendingSearchAuthorization")
    assert isinstance(prior, dict)
    changed = client.post(
        f"{PREFIX}/sessions/{session_id}/turns",
        json={"message": "change the dates to 9 to 14 november"},
    ).json()
    pending = changed.get("pendingSearchAuthorization")
    assert isinstance(pending, dict)
    assert pending["fingerprints"] != prior["fingerprints"]
    assert "search_stay_offers" not in provider.execute_tools
    assert "yes, go ahead" not in (changed.get("buyerSafeMessage") or "").lower()


def test_destination_change_after_results_stales_stay_only() -> None:
    client, provider = _wired()
    session_id, _ready = _open_heathrow(client)
    _yes(client, session_id)
    stay_count = provider.execute_tools.count("search_stay_offers")
    changed = client.post(
        f"{PREFIX}/sessions/{session_id}/turns",
        json={"message": "change the destination to Gatwick"},
    ).json()
    assert _ctx(changed, "destination") == "Gatwick"
    assert changed["staySearch"].get("stale") is True
    assert not _parking_stale(changed)
    assert _parking_airport(changed) == "LHR"
    pending = changed.get("pendingSearchAuthorization")
    assert isinstance(pending, dict)
    assert pending["capabilities"] == ["stay.search"]
    assert provider.execute_tools.count("search_stay_offers") == stay_count


def test_airport_change_after_parking_results_stales_parking_only() -> None:
    client, provider = _wired()
    session_id, _ready = _open_heathrow(client)
    searched = _yes(client, session_id)
    assert searched["staySearch"].get("stale") is not True
    stay_count = provider.execute_tools.count("search_stay_offers")
    changed = client.post(
        f"{PREFIX}/sessions/{session_id}/turns",
        json={"message": "change the parking airport to Manchester"},
    ).json()
    assert _parking_airport(changed) == "MAN"
    assert _parking_stale(changed)
    assert changed["staySearch"].get("stale") is not True
    pending = changed.get("pendingSearchAuthorization")
    assert isinstance(pending, dict)
    assert pending["capabilities"] == ["parking.search"]
    assert provider.execute_tools.count("search_stay_offers") == stay_count


def test_remove_parking_task() -> None:
    client, _provider = _wired()
    session_id, _ready = _open_heathrow(client)
    searched = _yes(client, session_id)
    assert "parking" in searched["domains"]
    dropped = client.post(
        f"{PREFIX}/sessions/{session_id}/turns",
        json={"message": "I don't need parking anymore"},
    ).json()
    kinds = {str(item.get("kind")) for item in dropped["projection"]["tasks"]}
    assert "parking" not in kinds
    assert "parking" not in (dropped.get("domains") or {})
    assert dropped["staySearch"].get("stale") is not True
    message = (dropped.get("buyerSafeMessage") or "").lower()
    assert "removed parking" in message
    pending = dropped.get("pendingSearchAuthorization")
    if isinstance(pending, dict):
        assert "parking.search" not in pending["capabilities"]


def test_add_things_to_do_task() -> None:
    client, provider = _wired()
    session_id, _ready = _open_heathrow(client)
    searched = _yes(client, session_id)
    assert searched["staySearch"].get("stale") is not True
    added = client.post(
        f"{PREFIX}/sessions/{session_id}/turns",
        json={"message": "also find things to do"},
    ).json()
    kinds = {str(item.get("kind")) for item in added["projection"]["tasks"]}
    assert "experience" in kinds
    assert added["staySearch"].get("stale") is not True
    assert not _parking_stale(added)
    pending = added.get("pendingSearchAuthorization")
    assert isinstance(pending, dict)
    assert pending["capabilities"] == ["experience.search"]
    assert "search_experience_offers" not in provider.execute_tools


def test_preference_refinement_budget() -> None:
    client, provider = _client()
    created = client.post(f"{PREFIX}/sessions", json={"objective": MILAN}).json()
    session_id = created["sessionId"]
    searched = _yes(client, session_id)
    offers = searched["staySearch"]["offers"]
    assert len(offers) >= 2
    stay_count = provider.execute_tools.count("search_stay_offers")
    refined = client.post(
        f"{PREFIX}/sessions/{session_id}/turns",
        json={"message": "only show hotels under £200"},
    ).json()
    assert refined["staySearch"].get("stale") is True
    pending = refined.get("pendingSearchAuthorization")
    assert isinstance(pending, dict)
    assert pending["capabilities"] == ["stay.search"]
    assert provider.execute_tools.count("search_stay_offers") == stay_count
    yes = _yes(client, session_id)
    assert provider.execute_tools.count("search_stay_offers") == stay_count + 1
    kept = yes["staySearch"]["offers"]
    assert kept
    for item in kept:
        amount = (item.get("price") or {}).get("amountMinor")
        assert isinstance(amount, int) and amount <= 20_000


def test_sandbox_flight_search_waits_for_authorization() -> None:
    client, provider = _client()
    created = client.post(
        f"{PREFIX}/sessions",
        json={
            "objective": "I need a flight from Manchester to Heathrow on 25 October",
        },
    ).json()
    session_id = created["sessionId"]
    pending = created.get("pendingSearchAuthorization")
    assert isinstance(pending, dict)
    assert pending["capabilities"] == ["flight.search"]
    assert "search_flight_offers" not in provider.execute_tools
    assert created.get("flightSearch") in (None, {})
    yes = _yes(client, session_id)
    assert "search_flight_offers" in provider.execute_tools
    flight = yes["flightSearch"]
    assert isinstance(flight, dict)
    assert flight["status"] == "ok"
    assert len(flight["offers"]) == 2
    assert flight["bookingAuthority"] == "none"
    assert flight["offers"][0]["origin"] == "MAN"
    assert flight["offers"][0]["destination"] == "LHR"


def test_combined_flight_stay_parking_authorizes_ready_set() -> None:
    client, provider = _wired()
    created = client.post(
        f"{PREFIX}/sessions",
        json={
            "objective": (
                "I need a flight from Manchester to Heathrow on 25 October, "
                "a hotel near Heathrow, and airport parking in Manchester."
            )
        },
    )
    assert created.status_code == 200, created.text
    body = created.json()
    session_id = str(body["sessionId"])
    kinds = {str(item.get("kind")) for item in body["projection"]["tasks"]}
    assert {"flight", "hotel", "parking"} <= kinds
    assert "search_flight_offers" not in provider.execute_tools
    assert "search_stay_offers" not in provider.execute_tools
    pending = body.get("pendingSearchAuthorization")
    if not isinstance(pending, dict) or "flight.search" not in pending.get("capabilities", []):
        dated = client.post(
            f"{PREFIX}/sessions/{session_id}/turns",
            json={"message": "the hotel is 25 to 26 October"},
        )
        assert dated.status_code == 200, dated.text
        timed = client.post(
            f"{PREFIX}/sessions/{session_id}/turns",
            json={"message": "8am on the 25th to 6pm on the 26th"},
        )
        assert timed.status_code == 200, timed.text
        body = timed.json()
        pending = body.get("pendingSearchAuthorization")
        if not isinstance(pending, dict) or "flight.search" not in pending.get("capabilities", []):
            covered = client.post(
                f"{PREFIX}/sessions/{session_id}/turns",
                json={"message": "covered is fine"},
            )
            assert covered.status_code == 200, covered.text
            body = covered.json()
            pending = body.get("pendingSearchAuthorization")
    assert isinstance(pending, dict), body.get("buyerSafeMessage")
    assert "flight.search" in pending["capabilities"]
    assert "search_flight_offers" not in provider.execute_tools
    yes = _yes(client, session_id)
    assert "search_flight_offers" in provider.execute_tools
    flight = yes["flightSearch"]
    assert isinstance(flight, dict)
    assert flight["status"] == "ok"
    assert flight["offers"][0]["origin"] == "MAN"
    assert flight["offers"][0]["destination"] == "LHR"
    blob = str(flight).lower()
    assert "spadari" not in blob
    assert "skyshield" not in blob
    if "stay.search" in pending["capabilities"]:
        assert "search_stay_offers" in provider.execute_tools
        stay = yes["staySearch"]
        assert isinstance(stay, dict)
        assert stay.get("stale") is not True
    if "parking.search" in pending["capabilities"]:
        offers = yes["domains"]["parking"]["offerSet"]["snapshot"]["offers"]
        assert offers


def test_keep_parking_on_original_dates() -> None:
    client, _provider = _wired()
    session_id, _ready = _open_heathrow(client)
    changed = client.post(
        f"{PREFIX}/sessions/{session_id}/turns",
        json={
            "message": "change the dates to 9 to 14 November. keep parking on the original dates",
        },
    ).json()
    assert _ctx(changed, "startDate") == "2026-11-09"
    assert str(_parking_start(changed)).startswith("2026-11-10T08:00:00")
    assert "parking stays on the original dates" in (changed.get("buyerSafeMessage") or "").lower()
