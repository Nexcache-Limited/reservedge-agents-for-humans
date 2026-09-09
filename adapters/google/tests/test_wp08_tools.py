from __future__ import annotations

from wp04_helpers import A1_ID, A2_ID, A3_ID, A4_ID
from wp06_fakes import (
    accept_command,
    authorize_command,
    build_facade,
    governance,
    intent_id,
    jfk_payload,
)
from wp08_helpers import PARKDIRECT

from itaa_application.errors import ApplicationError
from itaa_domain.value_objects import format_utc
from itaa_google_adapter.tools import FacadeTools


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


def test_tools_validate_opaque_ids() -> None:
    tools = FacadeTools(build_facade())
    try:
        tools.get_buyer_snapshot({"intentId": "not-an-id"})
    except ApplicationError as exc:
        assert exc.field == "intent_id"
        assert exc.code == "invalid_opaque_syntax"
    else:
        raise AssertionError("expected closed identifier error")


def test_cross_supplier_token_fails_closed() -> None:
    facade = build_facade()
    facade.create_purchase_intent(jfk_payload())
    facade.confirm_requirement(intent_id(), governance(A1_ID))
    dispatched = facade.approve_and_dispatch(intent_id(), governance(A2_ID))
    accepted = facade.accept_recommended_or_selected_offer(
        intent_id(), accept_command(dispatched.recommended_offer_id or "")
    )
    assert accepted.acceptance is not None
    winner = next(item for item in dispatched.offers if item.recommended)
    tools = FacadeTools(facade)
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
            "supplierToken": PARKDIRECT,
            "action": command.action,
            "mode": "SIMULATED",
            "idempotencyKey": command.idempotency_key,
            "approvalId": command.approval_id,
        },
    )
    try:
        tools.authorize_simulated_transaction(payload)
    except ApplicationError as exc:
        assert exc.field == "supplierToken"
        assert exc.code == "isolation_denied"
    else:
        raise AssertionError("expected isolation failure")


def test_live_mode_transaction_is_forbidden() -> None:
    facade = build_facade()
    facade.create_purchase_intent(jfk_payload())
    facade.confirm_requirement(intent_id(), governance(A1_ID))
    dispatched = facade.approve_and_dispatch(intent_id(), governance(A2_ID))
    accepted = facade.accept_recommended_or_selected_offer(
        intent_id(), accept_command(dispatched.recommended_offer_id or "")
    )
    assert accepted.acceptance is not None
    winner = next(item for item in dispatched.offers if item.recommended)
    tools = FacadeTools(facade)
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
            "approvalId": command.approval_id,
        },
    )
    try:
        tools.authorize_simulated_transaction(payload)
    except ApplicationError as exc:
        assert exc.field == "mode"
        assert exc.code == "mode_forbidden"
    else:
        raise AssertionError("expected mode_forbidden")


def test_retries_do_not_double_apply_authorization() -> None:
    facade = build_facade()
    facade.create_purchase_intent(jfk_payload())
    facade.confirm_requirement(intent_id(), governance(A1_ID))
    dispatched = facade.approve_and_dispatch(intent_id(), governance(A2_ID))
    accepted = facade.accept_recommended_or_selected_offer(
        intent_id(), accept_command(dispatched.recommended_offer_id or "")
    )
    assert accepted.acceptance is not None
    winner = next(item for item in dispatched.offers if item.recommended)
    tools = FacadeTools(facade)
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
            "mode": "SIMULATED",
            "idempotencyKey": command.idempotency_key,
            "approvalId": command.approval_id,
        },
    )
    first = tools.authorize_simulated_transaction(payload)
    second = tools.authorize_simulated_transaction(payload)
    assert first["transaction"] == second["transaction"]
    assert first["state"] == "TRANSACTION_AUTHORIZED_SIMULATED"


def test_extraction_never_auto_confirms() -> None:
    facade = build_facade()
    tools = FacadeTools(facade)
    created = tools.create_purchase_intent(jfk_payload())
    assert created["state"] == "AWAITING_REQUIREMENT_CONFIRMATION"
    snapshot = tools.get_buyer_snapshot({"intentId": created["intentId"]})
    assert snapshot["state"] == "AWAITING_REQUIREMENT_CONFIRMATION"


def test_tools_preserve_a1_a2_and_locked_ranking() -> None:
    tools = FacadeTools(build_facade())
    created = tools.create_purchase_intent(jfk_payload())
    assert created["state"] == "AWAITING_REQUIREMENT_CONFIRMATION"
    confirmed = tools.confirm_requirement(_governance_payload(A1_ID))
    assert confirmed["state"] == "AWAITING_DISPATCH_APPROVAL"
    dispatched = tools.approve_and_dispatch(_governance_payload(A2_ID))
    offers = dispatched["offers"]
    by_id = {item["offerId"]: item for item in offers}
    assert by_id["of_01k2m3n4p5q6r7s8t9v0w1x2a2"]["rank"] == 1
    assert by_id["of_01k2m3n4p5q6r7s8t9v0w1x2a2"]["price"]["totalMinor"] == 14800
    assert by_id["of_01k2m3n4p5q6r7s8t9v0w1x2a1"]["rank"] == 2
    assert by_id["of_01k2m3n4p5q6r7s8t9v0w1x2a1"]["price"]["totalMinor"] == 11900
    assert by_id["of_01k2m3n4p5q6r7s8t9v0w1x2a3"]["rank"] == 3
    assert by_id["of_01k2m3n4p5q6r7s8t9v0w1x2a3"]["price"]["totalMinor"] == 16900
    for item in offers:
        assert "scoreMicros" not in item
        assert "termsHash" in item
    assert dispatched["downside"]["delta"] == 2900
    accepted = tools.accept_offer(
        _governance_payload(
            A3_ID,
            {
                "offerId": dispatched["recommendedOfferId"],
                "offerVersion": 1,
            },
        )
    )
    assert accepted["state"] == "ACCEPTANCE_RECORDED"
