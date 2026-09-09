from __future__ import annotations

import pytest
from wp04_helpers import A1_ID, A2_ID
from wp06_fakes import (
    accept_command,
    authorize_command,
    build_facade,
    governance,
    intent_id,
    jfk_payload,
)

from itaa_application.errors import ApplicationError
from itaa_application.session_models import BuyerSessionState


def test_jfk_intent_creates_local_session() -> None:
    facade = build_facade()
    snapshot = facade.create_purchase_intent(jfk_payload())
    assert snapshot.intent_id == intent_id().to_primitive()
    assert snapshot.state is BuyerSessionState.AWAITING_REQUIREMENT_CONFIRMATION
    assert snapshot.simulation is True
    assert snapshot.environment == "local_simulation"
    assert snapshot.airport == "JFK"
    assert snapshot.category == "airport_parking"
    assert snapshot.market_evidence


def test_fixture_jfk_dispatch_preserves_locked_scores() -> None:
    facade = build_facade()
    facade.create_purchase_intent(jfk_payload())
    facade.confirm_requirement(intent_id(), governance(A1_ID))
    snapshot = facade.approve_and_dispatch(intent_id(), governance(A2_ID))
    by_id = {item.offer_id: item for item in snapshot.offers}
    assert by_id["of_01k2m3n4p5q6r7s8t9v0w1x2a2"].score_micros == 671_000
    assert by_id["of_01k2m3n4p5q6r7s8t9v0w1x2a2"].rank == 1
    assert by_id["of_01k2m3n4p5q6r7s8t9v0w1x2a2"].recommended is True
    assert by_id["of_01k2m3n4p5q6r7s8t9v0w1x2a1"].score_micros == 660_000
    assert by_id["of_01k2m3n4p5q6r7s8t9v0w1x2a1"].rank == 2
    assert by_id["of_01k2m3n4p5q6r7s8t9v0w1x2a3"].score_micros == 535_000
    assert by_id["of_01k2m3n4p5q6r7s8t9v0w1x2a3"].rank == 3
    assert snapshot.downside is not None
    assert snapshot.downside.dimension == "total_minor"
    assert snapshot.downside.delta == 2900
    assert snapshot.recommended_offer_id == "of_01k2m3n4p5q6r7s8t9v0w1x2a2"
    assert len(snapshot.supplier_outcomes) == 3


def test_accept_and_simulated_authorize() -> None:
    facade = build_facade()
    facade.create_purchase_intent(jfk_payload())
    facade.confirm_requirement(intent_id(), governance(A1_ID))
    dispatched = facade.approve_and_dispatch(intent_id(), governance(A2_ID))
    accepted = facade.accept_recommended_or_selected_offer(
        intent_id(), accept_command(dispatched.recommended_offer_id or "")
    )
    assert accepted.state is BuyerSessionState.ACCEPTANCE_RECORDED
    assert accepted.acceptance is not None
    winner = next(item for item in dispatched.offers if item.recommended)
    authorized = facade.authorize_simulated_transaction(
        intent_id(),
        authorize_command(
            acceptance_id=accepted.acceptance.acceptance_id,
            amount_minor=winner.total_minor,
            supplier_token=winner.supplier_token,
        ),
    )
    assert authorized.state is BuyerSessionState.TRANSACTION_AUTHORIZED_SIMULATED
    assert authorized.transaction is not None
    assert authorized.transaction.mode == "SIMULATED"
    assert authorized.transaction.action == "reserve_parking"
    replayed = facade.authorize_simulated_transaction(
        intent_id(),
        authorize_command(
            acceptance_id=accepted.acceptance.acceptance_id,
            amount_minor=winner.total_minor,
            supplier_token=winner.supplier_token,
        ),
    )
    assert replayed.transaction is not None
    assert replayed.transaction.result_ref == authorized.transaction.result_ref


def test_create_rejects_malformed_accessibility_and_auth_mismatch() -> None:
    facade = build_facade()
    payload = jfk_payload()
    constraints = payload["constraints"]
    assert isinstance(constraints, dict)
    constraints["accessibility"] = "ev_charging"
    with pytest.raises(ApplicationError, match="accessibility: required"):
        facade.create_purchase_intent(payload)
    facade.create_purchase_intent(jfk_payload())
    facade.confirm_requirement(intent_id(), governance(A1_ID))
    dispatched = facade.approve_and_dispatch(intent_id(), governance(A2_ID))
    accepted = facade.accept_recommended_or_selected_offer(
        intent_id(), accept_command(dispatched.recommended_offer_id or "")
    )
    winner = next(item for item in dispatched.offers if item.recommended)
    assert accepted.acceptance is not None
    with pytest.raises(ApplicationError, match="amountMinor: mismatch"):
        facade.authorize_simulated_transaction(
            intent_id(),
            authorize_command(
                acceptance_id=accepted.acceptance.acceptance_id,
                amount_minor=winner.total_minor + 50,
                supplier_token=winner.supplier_token,
                idempotency_key="ik_01k2m3n4p5q6r7s8t9v0w1x2c2",
            ),
        )
