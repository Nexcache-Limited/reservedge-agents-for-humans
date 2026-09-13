from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from wp06_fakes import build_facade, intent_id, jfk_payload

from itaa_api.agent_session import (
    PARKING_INTAKE_PATH,
    PREFIX,
    adapter_base_url,
    build_agent_app,
)
from itaa_api.app import create_app
from itaa_application.errors import ApplicationError
from itaa_aws_adapter.agent import compose_orchestrator
from itaa_aws_adapter.schemas import PlanAnswers

DEMO_A = (
    "I'm flying from JFK on September 3 at 1 PM and returning September 8 at 10 PM. "
    "I have a standard EV, prefer covered parking, and don't want a shuttle longer than 20 minutes."
)
DEMO_B = (
    "I'm travelling from London to Edinburgh for a conference 14–19 October 2026 "
    "and I'll need a car when I land, somewhere near the venue."
)
DEMO_C = "I'm going away next month and I'll need a car."
GENERIC = "Can you help me organise a quiet weekend with friends in Manchester?"
MODULE = Path(__file__).resolve().parents[1] / "src" / "itaa_api" / "agent_session.py"
_OPAQUE_ID = re.compile(r"\b[a-z]{2}_[0-9a-hjkmnp-tv-z]{26}\b", re.I)


class OrchestratorProvider:
    def __init__(self) -> None:
        self.facade = build_facade()
        self.orch = compose_orchestrator(self.facade)
        self.plan_objectives: list[str] = []
        self.plan_payloads: list[dict[str, object]] = []
        self.execute_tools: list[str] = []

    def plan_turn(self, payload: dict[str, object]) -> dict[str, object]:
        objective = str(payload["objective"])
        self.plan_objectives.append(objective)
        self.plan_payloads.append(dict(payload))
        answers = PlanAnswers.model_validate(payload.get("answers") or {})
        raw_trusted = payload.get("trustedDomains")
        from itaa_aws_adapter.schemas import PlanTurnContext

        context = PlanTurnContext(
            lastUserMessage=str(payload.get("lastUserMessage") or ""),
            trustedDomains=raw_trusted if isinstance(raw_trusted, dict) else {},
        )
        model, projection, events = self.orch.plan_turn(objective, answers, context)
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


def _client(
    provider: OrchestratorProvider | None = None,
) -> tuple[TestClient, OrchestratorProvider]:
    chosen = provider or OrchestratorProvider()
    return TestClient(build_agent_app(chosen)), chosen


def _tasks(body: dict[str, object]) -> dict[str, dict[str, object]]:
    projection = body["projection"]
    assert isinstance(projection, dict)
    tasks = projection["tasks"]
    assert isinstance(tasks, list)
    out: dict[str, dict[str, object]] = {}
    for item in tasks:
        assert isinstance(item, dict)
        kind = item["kind"]
        if isinstance(kind, str):
            out[kind] = item
    return out


def test_module_has_no_provider_sdk_imports() -> None:
    source = MODULE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module.split(".")[0])
    assert names.isdisjoint({"strands", "boto3", "botocore", "bedrock", "google"})


def test_create_session_mints_id_and_demo_a_is_parking_led() -> None:
    client, provider = _client()
    created = client.post(f"{PREFIX}/sessions", json={"objective": DEMO_A})
    assert created.status_code == 200, created.text
    body = created.json()
    assert body["sessionId"].startswith("as_")
    assert len(body["sessionId"]) == 29
    parking = _tasks(body)["parking"]
    assert parking["provenance"] == "explicit"
    assert parking["support"] == "live_simulated"
    assert body["projection"]["phase"] == "forming"
    assert body["confirmed"] is False
    assert "intentId" not in created.text
    assert "planTurn" not in body
    assert "evidence" not in created.text.lower()
    assert provider.plan_objectives == [DEMO_A]


def test_demo_b_is_distinct_multitask() -> None:
    client, _provider = _client()
    body = client.post(f"{PREFIX}/sessions", json={"objective": DEMO_B}).json()
    by_kind = _tasks(body)
    assert by_kind["rental"]["provenance"] == "explicit"
    assert by_kind["rental"]["support"] == "demonstration"
    assert by_kind["parking"]["provenance"] == "inferred"
    assert by_kind["hotel"]["provenance"] == "proposed"
    assert by_kind["hotel"]["support"] == "sandbox_search"
    assert body["projection"]["facts"]["destination"] == "Edinburgh"
    assert len(by_kind) > 1


def test_demo_c_asks_clarification() -> None:
    client, _provider = _client()
    body = client.post(f"{PREFIX}/sessions", json={"objective": DEMO_C}).json()
    assert body["projection"]["phase"] == "clarify"
    assert any(item["id"] == "dates" for item in body["questions"])
    dumped = created_blob(body)
    assert "jfk" not in dumped
    assert "skyshield" not in dumped


def created_blob(body: object) -> str:
    """Scan public payloads without opaque ids (Crockford can contain the letters jfk)."""

    return _OPAQUE_ID.sub("", str(body)).lower()


def test_generic_does_not_collapse_to_jfk() -> None:
    client, _provider = _client()
    response = client.post(f"{PREFIX}/sessions", json={"objective": GENERIC})
    blob = created_blob(response.text)
    assert response.status_code == 200
    assert "jfk" not in blob
    assert "skyshield" not in blob
    assert response.json()["projection"]["facts"]["parkingAirport"] != "JFK"


def test_follow_up_answers_refine_same_session() -> None:
    client, provider = _client()
    created = client.post(f"{PREFIX}/sessions", json={"objective": DEMO_C}).json()
    session_id = created["sessionId"]
    refined = client.post(
        f"{PREFIX}/sessions/{session_id}/turns",
        json={
            "message": "The conference is in Edinburgh.",
            "answers": {
                "departureAirport": "LHR",
                "dates": "14–19 October 2026",
                "startDate": "2026-10-14",
                "endDate": "2026-10-19",
                "carNeed": "yes",
            },
        },
    )
    assert refined.status_code == 200, refined.text
    body = refined.json()
    assert body["sessionId"] == session_id
    facts = body["projection"]["facts"]
    assert facts["departureAirport"] == "LHR"
    assert facts["destination"] == "Edinburgh"
    assert "2026-10-14" in facts["dates"]
    assert "2026-10-19" in facts["dates"]
    assert facts["hasExactDates"] is True
    assert facts["startDate"] == "2026-10-14"
    assert facts["endDate"] == "2026-10-19"
    assert provider.plan_objectives[0] == DEMO_C
    assert "Edinburgh" in provider.plan_objectives[-1]
    assert provider.plan_objectives[-1].startswith(DEMO_C)
    assert provider.plan_payloads[-1]["answers"]["departureAirport"] == "LHR"
    assert provider.plan_payloads[-1]["answers"]["startDate"] == "2026-10-14"


def test_confirm_handoff_exposes_canonical_dates_for_calendar() -> None:
    client, _provider = _client()
    created = client.post(f"{PREFIX}/sessions", json={"objective": DEMO_C}).json()
    session_id = created["sessionId"]
    refined = client.post(
        f"{PREFIX}/sessions/{session_id}/turns",
        json={
            "message": "The conference is in Edinburgh and I'll need a car when I land.",
            "answers": {
                "departureAirport": "LHR",
                "startDate": "2026-10-14",
                "endDate": "2026-10-19",
                "carNeed": "yes",
            },
        },
    )
    assert refined.status_code == 200, refined.text
    facts = refined.json()["projection"]["facts"]
    assert facts["startDate"] == "2026-10-14"
    assert facts["endDate"] == "2026-10-19"
    confirmed = client.post(f"{PREFIX}/sessions/{session_id}/confirm", json={})
    assert confirmed.status_code == 200, confirmed.text
    fields = confirmed.json()["parkingHandoff"]["fields"]
    assert fields["startDate"] == "2026-10-14"
    assert fields["endDate"] == "2026-10-19"
    assert "intentId" not in fields
    payload = confirmed.json()
    payload.pop("transcript", None)
    blob = created_blob(payload)
    assert "going away next month" not in blob
    assert "jfk" not in blob


def test_free_text_follow_up_message_reaches_plan_and_refines_facts() -> None:
    """turns.message must reach /v1/aws/plan-turns via objective, not answers."""

    client, provider = _client()
    initial = "I'm travelling to Edinburgh for a conference and need a car."
    follow = "I'm leaving from LHR (Heathrow) on 14–19 October."
    created = client.post(f"{PREFIX}/sessions", json={"objective": initial})
    assert created.status_code == 200, created.text
    session_id = created.json()["sessionId"]
    before = created.json()["projection"]["facts"]
    assert before["destination"] == "Edinburgh"
    assert before["departureAirport"] == ""
    assert before.get("hasExactDates") is False
    initial_tasks = {kind: task["provenance"] for kind, task in _tasks(created.json()).items()}
    refined = client.post(
        f"{PREFIX}/sessions/{session_id}/turns",
        json={"message": follow},
    )
    assert refined.status_code == 200, refined.text
    body = refined.json()
    assert body["sessionId"] == session_id
    assert set(provider.plan_payloads[-1]) == {
        "objective",
        "answers",
        "correlationId",
        "lastUserMessage",
        "trustedDomains",
    }
    assert provider.plan_payloads[-1]["answers"] == {}
    assert provider.plan_payloads[-1]["lastUserMessage"] == follow
    assert provider.plan_payloads[-1]["objective"] == f"{initial} {follow}"
    assert follow in provider.plan_objectives[-1]
    assert provider.plan_objectives[-1].startswith(initial)
    facts = body["projection"]["facts"]
    assert facts["destination"] == "Edinburgh"
    assert facts["departureAirport"] == "LHR"
    assert "2026-10-14" in facts["dates"]
    assert "2026-10-19" in facts["dates"]
    assert facts["parkingAirport"] != "JFK"
    blob = created_blob(body)
    assert "jfk" not in blob
    assert "skyshield" not in blob
    after_tasks = {kind: task["provenance"] for kind, task in _tasks(body).items()}
    assert after_tasks["rental"] == "explicit"
    assert after_tasks.get("parking") != "explicit"
    assert after_tasks["hotel"] == "proposed"
    assert initial_tasks["rental"] == "explicit"
    assert initial_tasks["hotel"] == "proposed"


def test_exact_heathrow_october_prose_is_forwarded_on_same_session() -> None:
    """Reviewer example: free-text only; no structured answers; no session reset."""

    client, provider = _client()
    initial = "I'm travelling to Edinburgh for a conference and need a car."
    follow = "I'm leaving from Heathrow on 14 October and returning on the 19th."
    created = client.post(f"{PREFIX}/sessions", json={"objective": initial}).json()
    session_id = created["sessionId"]
    before_tasks = {kind: task["provenance"] for kind, task in _tasks(created).items()}
    refined = client.post(
        f"{PREFIX}/sessions/{session_id}/turns",
        json={"message": follow},
    )
    assert refined.status_code == 200, refined.text
    body = refined.json()
    assert body["sessionId"] == session_id
    payload = provider.plan_payloads[-1]
    assert payload["answers"] == {}
    assert payload["objective"] == f"{initial} {follow}"
    assert "Heathrow" in payload["objective"]
    assert "14 October" in payload["objective"]
    facts = body["projection"]["facts"]
    assert facts["destination"] == "Edinburgh"
    assert facts["parkingAirport"] != "JFK"
    assert "jfk" not in created_blob(body)
    after_tasks = {kind: task["provenance"] for kind, task in _tasks(body).items()}
    assert after_tasks["rental"] == before_tasks["rental"] == "explicit"
    assert after_tasks["hotel"] in {"proposed", "inferred"}
    assert after_tasks.get("parking") != "explicit"


def test_confirm_sets_ready_without_a1_or_purchase_intent() -> None:
    client, provider = _client()
    created = client.post(f"{PREFIX}/sessions", json={"objective": DEMO_A}).json()
    session_id = created["sessionId"]
    provider_phase = created["projection"]["phase"]
    confirmed = client.post(f"{PREFIX}/sessions/{session_id}/confirm", json={})
    assert confirmed.status_code == 200, confirmed.text
    body = confirmed.json()
    assert body["confirmed"] is True
    assert body["projection"]["phase"] == "ready"
    assert body["questions"] == []
    fetched = client.get(f"{PREFIX}/sessions/{session_id}")
    assert fetched.json()["projection"]["phase"] == "ready"
    assert provider_phase in {"clarify", "forming"}
    from itaa_api.calendar_resolve import nearest_future_year

    sep_year = nearest_future_year(9, 3)
    handoff = body["parkingHandoff"]
    assert handoff["path"] == PARKING_INTAKE_PATH
    assert handoff["fields"]["airportCode"] == "JFK"
    assert handoff["fields"]["startDate"] == f"{sep_year}-09-03"
    assert handoff["fields"]["endDate"] == f"{sep_year}-09-08"
    assert str(handoff["fields"]["start"]).startswith(f"{sep_year}-09-03")
    assert str(handoff["fields"]["end"]).startswith(f"{sep_year}-09-08")
    assert "intentId" not in handoff["fields"]
    assert "buyerToken" not in handoff["fields"]
    assert provider.execute_tools == ["prepare_parking_requirement"]
    with pytest.raises(ApplicationError):
        provider.facade.get_buyer_snapshot(intent_id())
    assert "671000" not in confirmed.text
    assert "SkyShield" not in confirmed.text


def test_mutating_execute_before_confirm_is_closed() -> None:
    client, _provider = _client()
    session_id = client.post(f"{PREFIX}/sessions", json={"objective": DEMO_A}).json()["sessionId"]
    response = client.post(
        f"{PREFIX}/sessions/{session_id}/turns",
        json={
            "tool": "solicit_parking_offers",
            "payload": {"intentId": "pi_01k2m3n4p5q6r7s8t9v0w1x2y3"},
        },
    )
    assert response.status_code in {409, 400, 500}
    assert response.json()["error"]["field"] in {"plan", "tool", "approvalId"}


def test_unknown_and_malformed_session_ids_fail_closed() -> None:
    client, _provider = _client()
    missing = client.get(f"{PREFIX}/sessions/as_01k2m3n4p5q6r7s8t9v0w1x2y3")
    assert missing.status_code == 404
    assert missing.json()["error"]["field"] == "sessionId"
    assert missing.json()["error"]["code"] == "unknown_resource"
    malformed = client.get(f"{PREFIX}/sessions/not-a-session")
    assert malformed.status_code == 400
    assert malformed.json()["error"]["field"] == "sessionId"
    assert malformed.json()["error"]["code"] == "invalid_opaque_syntax"


def test_extra_fields_fail_closed() -> None:
    client, _provider = _client()
    response = client.post(
        f"{PREFIX}/sessions",
        json={"objective": DEMO_A, "apiKey": "should-not-be-accepted"},
    )
    assert response.status_code == 400
    assert response.json()["error"]["field"] == "payload"
    assert "should-not-be-accepted" not in response.text


def test_agent_adapter_url_cannot_target_agent_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ITAA_AWS_ADAPTER_URL", "http://127.0.0.1:8000/v1/agent")
    with pytest.raises(ApplicationError, match="internal: closed"):
        adapter_base_url()
    client = TestClient(build_agent_app())
    response = client.post(f"{PREFIX}/sessions", json={"objective": DEMO_A})
    assert response.status_code == 500
    assert response.json()["error"]["field"] == "internal"
    assert response.json()["error"]["code"] == "closed"


def test_timeout_fails_closed_without_jfk_fixture() -> None:
    class TimeoutProvider:
        def plan_turn(self, payload: dict[str, object]) -> dict[str, object]:
            del payload
            raise TimeoutError

        def execute_turn(self, payload: dict[str, object]) -> dict[str, object]:
            del payload
            raise TimeoutError

    client = TestClient(build_agent_app(TimeoutProvider()))
    response = client.post(f"{PREFIX}/sessions", json={"objective": GENERIC})
    assert response.status_code == 400
    assert response.json()["error"]["field"] == "model"
    assert response.json()["error"]["code"] == "unavailable"
    assert "jfk" not in created_blob(response.text)
    assert "skyshield" not in response.text.lower()
    assert "projection" not in response.json()


def test_labelled_fallback_is_not_silent_jfk() -> None:
    class FallbackProvider:
        def plan_turn(self, payload: dict[str, object]) -> dict[str, object]:
            del payload
            return {
                "planTurn": {
                    "understanding": "Local planner",
                    "facts": {
                        "destination": "Manchester",
                        "parkingAirport": "",
                        "parkingStated": False,
                    },
                    "evidence": [],
                    "blockingQuestions": [],
                    "suggestedTasks": [],
                    "buyerSafeMessage": "Using the local planner (labelled)",
                    "fallback": True,
                },
                "projection": {
                    "facts": {
                        "destination": "Manchester",
                        "destinationAirport": "MAN",
                        "parkingAirport": "",
                        "departureAirport": "",
                        "dates": "",
                        "hasExactDates": False,
                        "hasLooseDates": False,
                        "carNeed": "",
                        "parkingStated": False,
                        "rentalStated": False,
                        "entsStated": False,
                        "hotelStated": False,
                        "flightStated": False,
                        "landing": False,
                        "travel": False,
                        "conference": False,
                        "nights": False,
                        "tripLike": True,
                        "dayPart": "",
                        "timeFlexible": False,
                    },
                    "questions": [],
                    "tasks": [
                        {
                            "id": "task-hotel",
                            "kind": "hotel",
                            "code": "Ht",
                            "title": "Hotel",
                            "detail": "Proposed only.",
                            "provenance": "proposed",
                            "support": "unsupported",
                            "supportLabel": "Unsupported in this build",
                            "accepted": False,
                        }
                    ],
                    "phase": "forming",
                    "title": "Manchester",
                    "summary": "0 confirmed task(s), 1 proposed.",
                    "confirmedCount": 0,
                    "proposedCount": 1,
                },
                "events": [],
            }

        def execute_turn(self, payload: dict[str, object]) -> dict[str, object]:
            del payload
            raise ApplicationError("tool", "closed")

    client = TestClient(build_agent_app(FallbackProvider()))
    body = client.post(f"{PREFIX}/sessions", json={"objective": GENERIC}).json()
    assert body["fallback"] is True
    assert body["projection"]["facts"]["destination"] == "Manchester"
    assert body["projection"]["facts"]["parkingAirport"] != "JFK"
    kinds = [item["kind"] for item in body["projection"]["tasks"]]
    assert kinds != ["parking"]
    events = client.get(f"{PREFIX}/sessions/{body['sessionId']}/events")
    assert events.status_code == 200
    assert "FALLBACK_DETERMINISTIC" in events.text
    assert "jfk" not in created_blob(events.text)


def test_events_are_agent_activity_not_wp07() -> None:
    client, _provider = _client()
    session_id = client.post(f"{PREFIX}/sessions", json={"objective": DEMO_A}).json()["sessionId"]
    events = client.get(f"{PREFIX}/sessions/{session_id}/events")
    assert events.status_code == 200
    assert events.headers["content-type"].startswith("text/event-stream")
    assert "OBJECTIVE_RECEIVED" in events.text
    assert "ProgressEventKind" not in events.text
    assert "STREAM_COMPLETED" not in events.text
    assert "scoreMicros" not in events.text


def test_create_app_includes_agent_router() -> None:
    application = create_app()
    application.state.aws_provider = OrchestratorProvider()
    client = TestClient(application)
    created = client.post(f"{PREFIX}/sessions", json={"objective": DEMO_A})
    assert created.status_code == 200
    health = client.get("/healthz")
    assert health.status_code == 200
    parking = client.post("/v1/simulations/airport-parking/intents", json=jfk_payload())
    assert parking.status_code == 200
    assert parking.json()["simulation"] is True


def test_new_york_trip_does_not_invent_jfk() -> None:
    client, _provider = _client()
    response = client.post(
        f"{PREFIX}/sessions", json={"objective": "travelling to New York for 10 days."}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    facts = body["projection"]["facts"]
    assert facts["destination"] == "New York"
    assert facts["parkingAirport"] != "JFK"
    assert "jfk" not in created_blob(body)
    parking = _tasks(body).get("parking")
    if parking is not None:
        assert parking["provenance"] != "explicit"
        assert parking["accepted"] is False


def test_new_york_parking_and_rental_stay_explicit_without_jfk() -> None:
    client, _provider = _client()
    objective = "travelling to New York for 10 days. need parking and rental car."
    response = client.post(f"{PREFIX}/sessions", json={"objective": objective})
    assert response.status_code == 200, response.text
    body = response.json()
    tasks = _tasks(body)
    assert tasks["parking"]["provenance"] == "explicit"
    assert tasks["rental"]["provenance"] == "explicit"
    assert body["projection"]["facts"]["destination"] == "New York"
    assert body["projection"]["facts"]["parkingAirport"] != "JFK"
    airport = ((body.get("domains") or {}).get("parking") or {}).get("fields", {}).get(
        "airportCode"
    ) or {}
    assert airport.get("value") != "JFK"


def test_same_session_parking_follow_up_becomes_explicit() -> None:
    client, provider = _client()
    created = client.post(
        f"{PREFIX}/sessions", json={"objective": "travelling to New York for 10 days."}
    )
    assert created.status_code == 200, created.text
    session_id = created.json()["sessionId"]
    before = _tasks(created.json()).get("parking")
    if before is not None:
        assert before["provenance"] != "explicit"
    refined = client.post(
        f"{PREFIX}/sessions/{session_id}/turns",
        json={"message": "I also need parking"},
    )
    assert refined.status_code == 200, refined.text
    body = refined.json()
    assert body["sessionId"] == session_id
    assert "I also need parking" in provider.plan_objectives[-1]
    parking = _tasks(body)["parking"]
    assert parking["provenance"] == "explicit"
    assert parking["accepted"] is True
    assert body["projection"]["facts"]["parkingAirport"] != "JFK"
    airport = ((body.get("domains") or {}).get("parking") or {}).get("fields", {}).get(
        "airportCode"
    ) or {}
    assert airport.get("value") != "JFK"


def test_confirm_mints_intake_id_on_prepared_parking_handoff() -> None:
    client, _provider = _client()
    created = client.post(f"{PREFIX}/sessions", json={"objective": DEMO_A}).json()
    session_id = created["sessionId"]
    confirmed = client.post(f"{PREFIX}/sessions/{session_id}/confirm", json={})
    assert confirmed.status_code == 200, confirmed.text
    fields = confirmed.json()["parkingHandoff"]["fields"]
    intake_id = fields["intakeId"]
    assert isinstance(intake_id, str) and intake_id.startswith("in_")
    assert "intentId" not in fields
    store = getattr(client.app.state, "intake_records", {})
    assert intake_id in store
    again = client.post(
        f"{PREFIX}/sessions/{session_id}/turns",
        json={"message": "Keep the same airport."},
    )
    assert again.status_code == 200, again.text
    assert again.json()["parkingHandoff"]["fields"]["intakeId"] == intake_id
    assert again.json()["parkingHandoff"]["fields"]["airportCode"] == "JFK"
