"""COMP-AWS-04: confirm and A2/A4 replay stay idempotent."""

from __future__ import annotations

from collections.abc import Mapping

from fastapi.testclient import TestClient
from wp04_helpers import A1_ID, A2_ID  # type: ignore[import-not-found]
from wp06_fakes import (  # type: ignore[import-not-found]
    accept_command,
    authorize_command,
    build_facade,
    governance,
    intent_id,
    jfk_payload,
)

from itaa_api.agent_session import PREFIX, build_agent_app
from itaa_api.app import create_app
from itaa_application.compatibility import CompatibilityAdapter
from itaa_aws_adapter.agent import compose_orchestrator
from itaa_aws_adapter.schemas import PlanAnswers

DEMO_A = (
    "I'm flying from JFK on September 3 at 1 PM and returning September 8 at 10 PM. "
    "I have a standard EV, prefer covered parking, and don't want a shuttle longer than 20 minutes."
)


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


def test_confirm_is_idempotent_on_the_same_session() -> None:
    client = TestClient(build_agent_app(_Provider()))
    session_id = client.post(f"{PREFIX}/sessions", json={"objective": DEMO_A}).json()["sessionId"]
    first = client.post(f"{PREFIX}/sessions/{session_id}/confirm", json={})
    second = client.post(f"{PREFIX}/sessions/{session_id}/confirm", json={})
    assert first.status_code == second.status_code == 200
    assert first.json()["sessionId"] == second.json()["sessionId"] == session_id
    assert first.json()["confirmed"] is True
    assert second.json()["confirmed"] is True
    assert first.json()["parkingHandoff"] == second.json()["parkingHandoff"]


def test_a2_ranked_snapshot_reread_is_stable() -> None:
    facade = build_facade()
    facade.create_purchase_intent(jfk_payload())
    facade.confirm_requirement(intent_id(), governance(A1_ID))
    dispatched = facade.approve_and_dispatch(intent_id(), governance(A2_ID))
    first = facade.get_buyer_snapshot(intent_id())
    second = facade.get_buyer_snapshot(intent_id())
    assert dispatched.recommended_offer_id == first.recommended_offer_id
    assert first.recommended_offer_id == second.recommended_offer_id
    assert [item.offer_id for item in first.offers] == [item.offer_id for item in second.offers]
    assert first.to_primitive()["recommendedOfferId"] == second.to_primitive()["recommendedOfferId"]


def test_orchestration_wrap_replay_reuses_canonical_ids() -> None:
    facade = build_facade()
    facade.create_purchase_intent(jfk_payload())
    session = facade.lookup_session(intent_id())
    assert session is not None
    adapter = CompatibilityAdapter()
    first = adapter.wrap_purchase_intent(session)
    second = adapter.wrap_purchase_intent(session)
    assert first == second
    assert first is second


def test_orchestration_http_get_is_idempotent() -> None:
    client = TestClient(create_app(build_facade()))
    created = client.post("/v1/simulations/airport-parking/intents", json=jfk_payload())
    assert created.status_code == 200
    raw = created.json()["intentId"]
    first = client.get(f"/v1/orchestration/intents/{raw}")
    second = client.get(f"/v1/orchestration/intents/{raw}")
    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()


def test_a4_authorize_replay_reuses_result_ref() -> None:
    facade = build_facade()
    facade.create_purchase_intent(jfk_payload())
    facade.confirm_requirement(intent_id(), governance(A1_ID))
    dispatched = facade.approve_and_dispatch(intent_id(), governance(A2_ID))
    accepted = facade.accept_recommended_or_selected_offer(
        intent_id(), accept_command(dispatched.recommended_offer_id or "")
    )
    assert accepted.acceptance is not None
    winner = next(item for item in dispatched.offers if item.recommended)
    command = authorize_command(
        acceptance_id=accepted.acceptance.acceptance_id,
        amount_minor=winner.total_minor,
        supplier_token=winner.supplier_token,
    )
    first = facade.authorize_simulated_transaction(intent_id(), command)
    second = facade.authorize_simulated_transaction(intent_id(), command)
    assert first.transaction is not None
    assert second.transaction is not None
    assert first.transaction.result_ref == second.transaction.result_ref
