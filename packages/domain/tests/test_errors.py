from __future__ import annotations

from helpers import draft_intent, invited_offer, make_requirement, request_at

from itaa_domain.errors import (
    DomainInvariantError,
    DuplicateActionError,
    ExpiredResourceError,
    InvalidTransitionError,
    OfferVersionMismatchError,
    VersionConflictError,
)
from itaa_domain.offer import OfferAction
from itaa_domain.purchase_intent import PurchaseIntentAction
from itaa_domain.value_objects import Version


def test_error_messages_are_framework_neutral_and_payload_free() -> None:
    messages = [
        str(DomainInvariantError("amount_minor", "out_of_range")),
        str(
            InvalidTransitionError(
                "purchase_intent",
                "pi_01k2m3n4p5q6r7s8t9v0w1x2y3",
                "DRAFT",
                "dispatch",
                ("confirm", "cancel"),
            )
        ),
        str(VersionConflictError("offer", "of_01k2m3n4p5q6r7s8t9v0w1x2a1", 2, 1)),
        str(
            ExpiredResourceError(
                "acceptance",
                "ac_01k2m3n4p5q6r7s8t9v0w1x2d1",
                "2026-08-21T18:00:00Z",
            )
        ),
        str(
            DuplicateActionError(
                "transaction",
                "ac_01k2m3n4p5q6r7s8t9v0w1x2d1",
                "authorize_simulated",
                "AUTHORIZED_SIMULATED",
            )
        ),
        str(OfferVersionMismatchError("of_01k2m3n4p5q6r7s8t9v0w1x2a1", 1, 2)),
    ]
    for message in messages:
        assert "http" not in message.lower()
        assert "@" not in message
        assert "prompt" not in message
        assert "itinerary" not in message


def test_aggregate_primitives_and_apply_helpers() -> None:
    requirement = make_requirement()
    assert requirement.to_primitive()["airportCode"] == "JFK"
    intent = draft_intent()
    confirmed = intent.apply(
        PurchaseIntentAction.CONFIRM,
        request_at(intent.updated_at, intent.revision),
    )
    assert confirmed.aggregate.to_primitive()["state"] == "CONFIRMED"
    offer = invited_offer()
    drafted = offer.apply(OfferAction.BEGIN_DRAFT, request_at(offer.updated_at, Version.initial()))
    assert drafted.aggregate.to_primitive()["state"] == "DRAFT"
    assert drafted.aggregate.to_primitive()["offerVersion"] == 1
