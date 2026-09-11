from __future__ import annotations

import pytest
from wp04_helpers import A1_ID, A2_ID, A3_ID, A4_ID
from wp06_fakes import (
    accept_command,
    authorize_command,
    build_facade,
    governance,
    intent_id,
    jfk_payload,
)

from itaa_application.errors import ApplicationError
from itaa_aws_adapter.agent import compose_orchestrator
from itaa_aws_adapter.tools import CLOSED_TOOLS, EXECUTE_TOOLS, PLAN_TOOLS, ClosedTools
from itaa_domain.value_objects import format_utc

DEMO_A = (
    "I'm flying from JFK on September 3 at 1 PM and returning September 8 at 10 PM. "
    "I have a standard EV, prefer covered parking, and don't want a shuttle longer than 20 minutes."
)


def _governance_payload(
    approval: object, extra: dict[str, object] | None = None
) -> dict[str, object]:
    command = governance(approval)
    payload: dict[str, object] = {
        "intentId": intent_id().to_primitive(),
        "actorId": command.actor_id,
        "ownerId": command.owner_id,
        "approvalId": command.approval_id,
        "correlationId": command.correlation_id,
        "issuedAt": format_utc(command.issued_at),
        "expiresAt": format_utc(command.expires_at),
    }
    if extra:
        payload.update(extra)
    return payload


def _dispatched_session() -> tuple[object, object]:
    facade = build_facade()
    facade.create_purchase_intent(jfk_payload())
    facade.confirm_requirement(intent_id(), governance(A1_ID))
    dispatched = facade.approve_and_dispatch(intent_id(), governance(A2_ID))
    return facade, dispatched


def test_unknown_tool_fails_closed() -> None:
    agent = compose_orchestrator()
    with pytest.raises(ApplicationError, match="tool: closed"):
        agent.execute_turn("rank_offers", {})


def test_plan_tools_rejected_on_execute_turn() -> None:
    agent = compose_orchestrator()
    for name in PLAN_TOOLS:
        with pytest.raises(ApplicationError, match="tool: closed"):
            agent.execute_turn(name, {"objective": "hi"})


def test_mutating_tools_rejected_on_plan_call() -> None:
    tools = ClosedTools(build_facade())
    with pytest.raises(ApplicationError, match="tool: closed"):
        tools.call("solicit_parking_offers", _governance_payload(A2_ID), turn="plan")


def test_mutating_execute_requires_grant() -> None:
    agent = compose_orchestrator(build_facade())
    with pytest.raises(ApplicationError, match="approvalId: required"):
        agent.execute_turn(
            "solicit_parking_offers",
            {"intentId": intent_id().to_primitive()},
        )


def test_prepare_parking_requires_plan_confirmation() -> None:
    agent = compose_orchestrator()
    with pytest.raises(ApplicationError, match="plan: illegal_state"):
        agent.execute_turn(
            "prepare_parking_requirement",
            {"objective": "Airport parking at JFK", "planConfirmed": False},
        )


def test_prepare_parking_does_not_mint_ids() -> None:
    agent = compose_orchestrator()
    result = agent.execute_turn(
        "prepare_parking_requirement",
        {"objective": DEMO_A, "planConfirmed": True},
    )
    assert result.get("airportCode") == "JFK"
    assert result.get("startDate") == "2026-09-03"
    assert result.get("endDate") == "2026-09-08"
    assert result.get("vehicleClass") == "standard"
    assert result.get("covered") == "preferred"
    assert result.get("shuttleMaxMinutes") == 20
    assert "intentId" not in result
    assert "buyerToken" not in result
    assert "approvalId" not in result


def test_authorize_rejects_non_simulated_mode() -> None:
    facade, dispatched = _dispatched_session()
    accepted = facade.accept_recommended_or_selected_offer(
        intent_id(), accept_command(dispatched.recommended_offer_id or "")
    )
    assert accepted.acceptance is not None
    winner = next(item for item in dispatched.offers if item.recommended)
    agent = compose_orchestrator(facade)
    command = authorize_command(
        acceptance_id=accepted.acceptance.acceptance_id,
        amount_minor=winner.total_minor,
        supplier_token=winner.supplier_token,
    )
    payload = _governance_payload(
        A4_ID,
        {
            "acceptanceId": command.acceptance_id,
            "amountMinor": command.amount_minor,
            "currency": command.currency,
            "supplierToken": command.supplier_token,
            "action": command.action,
            "mode": "LIVE",
            "idempotencyKey": command.idempotency_key,
        },
    )
    with pytest.raises(ApplicationError, match="mode: mode_forbidden"):
        agent.execute_turn("authorize_simulated_transaction", payload)


def test_explain_cannot_change_scores() -> None:
    facade, dispatched = _dispatched_session()
    agent = compose_orchestrator(facade)
    explained = agent.execute_turn(
        "explain_ranked_offers",
        {"intentId": intent_id().to_primitive()},
    )
    assert explained["scoreMicros"] == [item.score_micros for item in dispatched.offers]
    assert explained["totalMinor"] == [item.total_minor for item in dispatched.offers]
    assert explained["recommendedOfferId"] == dispatched.recommended_offer_id
    assert explained["grounded"] is True
    assert 671000 in explained["scoreMicros"]
    assert "999999" not in explained["explanation"]
    snapshot = agent.execute_turn(
        "get_buyer_snapshot",
        {"intentId": intent_id().to_primitive()},
    )
    for item in snapshot["offers"]:
        assert "scoreMicros" not in item


def test_accept_requires_a3_grant() -> None:
    facade, dispatched = _dispatched_session()
    agent = compose_orchestrator(facade)
    with pytest.raises(ApplicationError, match="approvalId: required"):
        agent.execute_turn(
            "accept_offer",
            {
                "intentId": intent_id().to_primitive(),
                "offerId": dispatched.recommended_offer_id,
                "offerVersion": 1,
            },
        )
    accepted = agent.execute_turn(
        "accept_offer",
        _governance_payload(
            A3_ID,
            {"offerId": dispatched.recommended_offer_id or "", "offerVersion": 1},
        ),
    )
    assert accepted["state"] == "ACCEPTANCE_RECORDED"


def test_closed_allowlist_matches_freeze() -> None:
    assert PLAN_TOOLS == ("get_supported_capabilities", "project_plan_from_facts")
    assert EXECUTE_TOOLS == (
        "prepare_parking_requirement",
        "search_stay_offers",
        "search_experience_offers",
        "book_stay_sandbox",
        "get_buyer_snapshot",
        "solicit_parking_offers",
        "explain_ranked_offers",
        "accept_offer",
        "authorize_simulated_transaction",
    )
    assert CLOSED_TOOLS == PLAN_TOOLS + EXECUTE_TOOLS
    assert "rank_offers" not in CLOSED_TOOLS
    assert "create_purchase_intent" not in CLOSED_TOOLS
