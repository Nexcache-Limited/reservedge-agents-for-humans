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


def test_dispatch_before_confirm_is_rejected() -> None:
    facade = build_facade()
    facade.create_purchase_intent(jfk_payload())
    with pytest.raises(ApplicationError, match="state: illegal_state"):
        facade.approve_and_dispatch(intent_id(), governance(A2_ID))
    assert (
        facade.get_buyer_snapshot(intent_id()).state
        is BuyerSessionState.AWAITING_REQUIREMENT_CONFIRMATION
    )


def test_accept_before_dispatch_is_rejected() -> None:
    facade = build_facade()
    facade.create_purchase_intent(jfk_payload())
    facade.confirm_requirement(intent_id(), governance(A1_ID))
    with pytest.raises(ApplicationError, match="state: illegal_state"):
        facade.accept_recommended_or_selected_offer(
            intent_id(), accept_command("of_01k2m3n4p5q6r7s8t9v0w1x2a2")
        )


def test_authorize_before_acceptance_is_rejected() -> None:
    facade = build_facade()
    facade.create_purchase_intent(jfk_payload())
    facade.confirm_requirement(intent_id(), governance(A1_ID))
    facade.approve_and_dispatch(intent_id(), governance(A2_ID))
    with pytest.raises(ApplicationError, match="state: illegal_state"):
        facade.authorize_simulated_transaction(
            intent_id(),
            authorize_command(
                acceptance_id="ac_01k2m3n4p5q6r7s8t9v0w1x2d1",
                amount_minor=14800,
                supplier_token="sp_01k2m3n4p5q6r7s8t9v0w1x2b2",
            ),
        )


def test_stale_and_foreign_offers_are_rejected() -> None:
    facade = build_facade()
    facade.create_purchase_intent(jfk_payload())
    facade.confirm_requirement(intent_id(), governance(A1_ID))
    facade.approve_and_dispatch(intent_id(), governance(A2_ID))
    with pytest.raises(ApplicationError, match="offerVersion: stale_version"):
        facade.accept_recommended_or_selected_offer(
            intent_id(), accept_command("of_01k2m3n4p5q6r7s8t9v0w1x2a2", version=9)
        )
    with pytest.raises(ApplicationError, match="offerId: ineligible"):
        facade.accept_recommended_or_selected_offer(
            intent_id(), accept_command("of_01k2m3n4p5q6r7s8t9v0w1x2a9")
        )
    with pytest.raises(ApplicationError, match="offer_id: invalid_opaque_syntax"):
        facade.accept_recommended_or_selected_offer(intent_id(), accept_command("not-an-offer"))
    with pytest.raises(ApplicationError, match="action: must_be_reserve_parking"):
        facade.authorize_simulated_transaction(
            intent_id(),
            authorize_command(
                acceptance_id="ac_01k2m3n4p5q6r7s8t9v0w1x2d1",
                amount_minor=14800,
                supplier_token="sp_01k2m3n4p5q6r7s8t9v0w1x2b2",
                action="charge_card",
            ),
        )
