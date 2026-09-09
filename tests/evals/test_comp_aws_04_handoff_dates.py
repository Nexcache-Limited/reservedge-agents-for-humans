"""COMP-AWS-04: calendar/handoff consume canonical startDate/endDate directly."""

from __future__ import annotations

from collections.abc import Mapping

from fastapi.testclient import TestClient
from wp06_fakes import build_facade  # type: ignore[import-not-found]

from itaa_api.agent_session import PREFIX, build_agent_app
from itaa_aws_adapter.agent import compose_orchestrator
from itaa_aws_adapter.schemas import PlanAnswers
from itaa_aws_adapter.tools import ClosedTools

DEMO_B = (
    "I'm travelling from London to Edinburgh for a conference 14–19 October 2026 "
    "and I'll need a car when I land, somewhere near the venue."
)


class _Provider:
    def __init__(self) -> None:
        self.orch = compose_orchestrator(build_facade())

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


def test_session_facts_expose_iso_dates_without_browser_parsing() -> None:
    client = TestClient(build_agent_app(_Provider()))
    body = client.post(f"{PREFIX}/sessions", json={"objective": DEMO_B}).json()
    facts = body["projection"]["facts"]
    assert facts["startDate"] == "2026-10-14"
    assert facts["endDate"] == "2026-10-19"
    assert facts["hasExactDates"] is True
    assert "objective" not in body


def test_handoff_fields_copy_canonical_dates() -> None:
    client = TestClient(build_agent_app(_Provider()))
    created = client.post(f"{PREFIX}/sessions", json={"objective": DEMO_B}).json()
    confirmed = client.post(f"{PREFIX}/sessions/{created['sessionId']}/confirm", json={})
    assert confirmed.status_code == 200, confirmed.text
    fields = confirmed.json()["parkingHandoff"]["fields"]
    assert fields["startDate"] == "2026-10-14"
    assert fields["endDate"] == "2026-10-19"
    assert str(fields["start"]).startswith("2026-10-14")
    assert str(fields["end"]).startswith("2026-10-19")
    assert "intentId" not in fields
    assert "buyerToken" not in fields


def test_prepare_tool_returns_canonical_dates_from_answers_not_prose_parsing() -> None:
    tools = ClosedTools()
    result = tools.prepare_parking_requirement(
        {
            "planConfirmed": True,
            "objective": "I'm travelling to Edinburgh for a conference and need a car.",
            "answers": {
                "startDate": "2026-10-14",
                "endDate": "2026-10-19",
                "departureAirport": "LHR",
            },
        }
    )
    assert result["startDate"] == "2026-10-14"
    assert result["endDate"] == "2026-10-19"
    assert "14–19 October" not in str(result)
    assert "intentId" not in result
