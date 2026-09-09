"""COMP-AWS-04: frozen demo plans, same-session refinement, labelled fallback."""

from __future__ import annotations

import re
from collections.abc import Mapping

from fastapi.testclient import TestClient
from wp06_fakes import build_facade  # type: ignore[import-not-found]

from itaa_api.agent_session import PREFIX, build_agent_app
from itaa_aws_adapter.agent import compose_orchestrator
from itaa_aws_adapter.fake import fake_plan_turn
from itaa_aws_adapter.projector import project_plan
from itaa_aws_adapter.schemas import PlanAnswers, SuggestedTask

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
MARKER = "MARKER_OBJECTIVE_DO_NOT_COPY_7f3a"
_OPAQUE_ID = re.compile(r"\b[a-z]{2}_[0-9a-hjkmnp-tv-z]{26}\b", re.I)


def _blob(raw: object) -> str:
    return _OPAQUE_ID.sub("", str(raw)).lower()


class _Provider:
    def __init__(self) -> None:
        self.facade = build_facade()
        self.orch = compose_orchestrator(self.facade)

    def plan_turn(self, payload: Mapping[str, object]) -> dict[str, object]:
        answers = PlanAnswers.model_validate(payload.get("answers") or {})
        model, projection, events = self.orch.plan_turn(str(payload["objective"]), answers)
        return {
            "planTurn": model.model_dump(mode="json"),
            "projection": projection.model_dump(mode="json"),
            "events": events,
        }

    def execute_turn(self, payload: Mapping[str, object]) -> dict[str, object]:
        tool = str(payload["tool"])
        inner = payload.get("payload")
        result = self.orch.execute_turn(tool, inner if isinstance(inner, dict) else {})
        return {"tool": tool, "result": result}


def _client() -> TestClient:
    return TestClient(build_agent_app(_Provider()))


def _tasks(body: dict[str, object]) -> dict[str, dict[str, object]]:
    projection = body["projection"]
    assert isinstance(projection, dict)
    tasks = projection["tasks"]
    assert isinstance(tasks, list)
    out: dict[str, dict[str, object]] = {}
    for item in tasks:
        assert isinstance(item, dict)
        kind = item.get("kind")
        if isinstance(kind, str):
            out[kind] = item
    return out


def test_demo_a_parking_led_and_not_a1() -> None:
    body = _client().post(f"{PREFIX}/sessions", json={"objective": DEMO_A}).json()
    parking = _tasks(body)["parking"]
    assert parking["provenance"] == "explicit"
    assert parking["support"] == "live_simulated"
    assert body["confirmed"] is False
    assert "hotel" not in _tasks(body) or _tasks(body)["hotel"]["provenance"] != "explicit"
    assert "671000" not in str(body)
    assert "intentId" not in str(body)


def test_demo_b_distinct_multitask_provenance() -> None:
    body = _client().post(f"{PREFIX}/sessions", json={"objective": DEMO_B}).json()
    by_kind = _tasks(body)
    assert by_kind["rental"]["provenance"] == "explicit"
    assert by_kind["parking"]["provenance"] == "inferred"
    assert by_kind["hotel"]["provenance"] == "proposed"
    assert body["projection"]["facts"]["startDate"] == "2026-10-14"
    assert body["projection"]["facts"]["endDate"] == "2026-10-19"


def test_demo_c_clarifies_then_same_session_answers_refine() -> None:
    client = _client()
    created = client.post(f"{PREFIX}/sessions", json={"objective": DEMO_C}).json()
    assert created["projection"]["phase"] == "clarify"
    session_id = created["sessionId"]
    refined = client.post(
        f"{PREFIX}/sessions/{session_id}/turns",
        json={
            "message": "The conference is in Edinburgh.",
            "answers": {
                "departureAirport": "LHR",
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
    assert facts["startDate"] == "2026-10-14"
    assert facts["endDate"] == "2026-10-19"
    assert facts["departureAirport"] == "LHR"
    assert facts["destination"] == "Edinburgh"
    assert "jfk" not in _blob(refined.text)


def test_generic_input_does_not_collapse_to_jfk() -> None:
    response = _client().post(f"{PREFIX}/sessions", json={"objective": GENERIC})
    assert response.status_code == 200
    assert "jfk" not in _blob(response.text)
    assert response.json()["projection"]["facts"]["parkingAirport"] != "JFK"


def test_model_cannot_upgrade_unearned_explicit() -> None:
    turn = fake_plan_turn(DEMO_A)
    turn.suggestedTasks.append(SuggestedTask(kind="hotel", provenance="explicit"))
    projection = project_plan(DEMO_A, PlanAnswers(), turn)
    assert all(task.kind != "hotel" or task.provenance != "explicit" for task in projection.tasks)


def test_labelled_fallback_is_explicit() -> None:
    class Fallback:
        def plan_turn(self, payload: Mapping[str, object]) -> dict[str, object]:
            del payload
            return {
                "planTurn": {
                    "understanding": "Local planner",
                    "facts": {"destination": "Manchester"},
                    "evidence": [],
                    "blockingQuestions": [],
                    "suggestedTasks": [],
                    "buyerSafeMessage": "Using the local planner (labelled)",
                    "fallback": True,
                },
                "projection": {
                    "facts": {"destination": "Manchester", "parkingAirport": "", "dates": ""},
                    "questions": [],
                    "tasks": [],
                    "phase": "forming",
                    "title": "Manchester",
                    "summary": "Labelled fallback",
                    "confirmedCount": 0,
                    "proposedCount": 0,
                },
                "events": [
                    {
                        "kind": "FALLBACK_DETERMINISTIC",
                        "message": "Using the local planner (labelled)",
                    }
                ],
            }

        def execute_turn(self, payload: Mapping[str, object]) -> dict[str, object]:
            del payload
            raise AssertionError("execute must not run during plan fallback")

    client = TestClient(build_agent_app(Fallback()))
    body = client.post(f"{PREFIX}/sessions", json={"objective": MARKER}).json()
    assert body["fallback"] is True
    assert "jfk" not in _blob(body)
    events = client.get(f"{PREFIX}/sessions/{body['sessionId']}/events")
    assert "Using the local planner (labelled)" in events.text
    assert "FALLBACK_DETERMINISTIC" in events.text
