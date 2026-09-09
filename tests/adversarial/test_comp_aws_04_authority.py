"""COMP-AWS-04: model cannot skip A1–A4; mutations need grants; unknown tools fail closed."""

from __future__ import annotations

from collections.abc import Mapping

import pytest
from fastapi.testclient import TestClient
from wp04_helpers import A2_ID  # type: ignore[import-not-found]
from wp06_fakes import (  # type: ignore[import-not-found]
    build_facade,
    governance,
    intent_id,
    jfk_payload,
)

from itaa_api.agent_session import PREFIX, build_agent_app
from itaa_application.errors import ApplicationError
from itaa_aws_adapter.agent import compose_orchestrator
from itaa_aws_adapter.schemas import PlanAnswers
from itaa_aws_adapter.tools import PLAN_TOOLS, ClosedTools

DEMO_A = (
    "I'm flying from JFK on September 3 at 1 PM and returning September 8 at 10 PM. "
    "I have a standard EV, prefer covered parking, and don't want a shuttle longer than 20 minutes."
)


class _Provider:
    def __init__(self) -> None:
        self.facade = build_facade()
        self.orch = compose_orchestrator(self.facade)
        self.execute_tools: list[str] = []

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
        self.execute_tools.append(tool)
        inner = payload.get("payload")
        result = self.orch.execute_turn(tool, inner if isinstance(inner, dict) else {})
        return {"tool": tool, "result": result}


def test_confirm_only_prepares_parking_and_does_not_mint_intent() -> None:
    provider = _Provider()
    client = TestClient(build_agent_app(provider))
    session_id = client.post(f"{PREFIX}/sessions", json={"objective": DEMO_A}).json()["sessionId"]
    confirmed = client.post(f"{PREFIX}/sessions/{session_id}/confirm", json={})
    assert confirmed.status_code == 200, confirmed.text
    assert provider.execute_tools == ["prepare_parking_requirement"]
    assert confirmed.json()["confirmed"] is True
    with pytest.raises(ApplicationError):
        provider.facade.get_buyer_snapshot(intent_id())
    assert confirmed.json()["pendingAuthorizations"] == []


def test_mutating_execute_before_confirm_is_closed() -> None:
    client = TestClient(build_agent_app(_Provider()))
    session_id = client.post(f"{PREFIX}/sessions", json={"objective": DEMO_A}).json()["sessionId"]
    response = client.post(
        f"{PREFIX}/sessions/{session_id}/turns",
        json={
            "tool": "solicit_parking_offers",
            "payload": {"intentId": intent_id().to_primitive()},
        },
    )
    assert response.status_code in {400, 409, 500}
    assert response.json()["error"]["field"] in {"plan", "tool", "approvalId"}


def test_unknown_tool_fails_closed() -> None:
    agent = compose_orchestrator()
    with pytest.raises(ApplicationError, match="tool: closed"):
        agent.execute_turn("rank_offers", {})


def test_plan_turn_cannot_call_mutation_tools() -> None:
    tools = ClosedTools(build_facade())
    with pytest.raises(ApplicationError, match="tool: closed"):
        tools.call(
            "solicit_parking_offers",
            {"intentId": intent_id().to_primitive()},
            turn="plan",
        )
    agent = compose_orchestrator()
    for name in PLAN_TOOLS:
        with pytest.raises(ApplicationError, match="tool: closed"):
            agent.execute_turn(name, {"objective": DEMO_A})


def test_execute_mutations_require_explicit_authorization() -> None:
    facade = build_facade()
    facade.create_purchase_intent(jfk_payload())
    agent = compose_orchestrator(facade)
    with pytest.raises(ApplicationError, match="approvalId: required"):
        agent.execute_turn(
            "solicit_parking_offers",
            {"intentId": intent_id().to_primitive()},
        )
    command = governance(A2_ID)
    with pytest.raises(ApplicationError):
        agent.execute_turn(
            "solicit_parking_offers",
            {
                "intentId": intent_id().to_primitive(),
                "actorId": command.actor_id,
                "ownerId": command.owner_id,
                "approvalId": command.approval_id,
                "correlationId": command.correlation_id,
                "issuedAt": command.issued_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "expiresAt": command.expires_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
            },
        )
