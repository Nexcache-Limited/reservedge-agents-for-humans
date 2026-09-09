"""COMP-G1-04: DISPATCHED may cancel with BUYER_REVOKED before simulated authorization."""

from __future__ import annotations

from helpers import CANCEL_REASON, at_minutes, intent_in_state, request_at

from itaa_domain.errors import DuplicateActionError, InvalidTransitionError
from itaa_domain.events import EventType
from itaa_domain.purchase_intent import (
    PURCHASE_INTENT_TRANSITIONS,
    PurchaseIntentAction,
    PurchaseIntentState,
)
from itaa_domain.value_objects import CancellationReason, ClosureReason


def test_dispatched_cancel_is_the_authorized_transition() -> None:
    assert (
        PURCHASE_INTENT_TRANSITIONS[(PurchaseIntentState.DISPATCHED, PurchaseIntentAction.CANCEL)]
        is PurchaseIntentState.CANCELLED
    )


def test_dispatched_cancel_uses_existing_buyer_revoked_reason() -> None:
    current = intent_in_state(PurchaseIntentState.DISPATCHED.value)
    result = current.cancel(request_at(at_minutes(5), current.revision), CANCEL_REASON)
    assert result.aggregate.state is PurchaseIntentState.CANCELLED
    assert result.event.event_type is EventType.PURCHASE_INTENT_CANCELLED
    assert result.event.reason_code == CancellationReason.BUYER_REVOKED.value
    assert result.event.payload_hash is None or str(result.event.payload_hash).startswith("sha256:")


def test_dispatched_close_superseded_remains_available() -> None:
    current = intent_in_state(PurchaseIntentState.DISPATCHED.value)
    result = current.close(request_at(at_minutes(5), current.revision), ClosureReason.SUPERSEDED)
    assert result.aggregate.state is PurchaseIntentState.CLOSED
    assert result.event.event_type is EventType.PURCHASE_INTENT_CLOSED
    assert result.event.reason_code == ClosureReason.SUPERSEDED.value


def test_cancelled_cannot_dispatch_or_close() -> None:
    current = intent_in_state(PurchaseIntentState.DISPATCHED.value)
    cancelled = current.cancel(request_at(at_minutes(5), current.revision), CANCEL_REASON).aggregate
    for action in (PurchaseIntentAction.DISPATCH, PurchaseIntentAction.CLOSE):
        try:
            cancelled.apply(action, request_at(at_minutes(6), cancelled.revision))
        except (InvalidTransitionError, DuplicateActionError):
            continue
        raise AssertionError(action)
