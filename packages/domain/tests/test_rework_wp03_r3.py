from __future__ import annotations

from enum import StrEnum
from types import MappingProxyType

import pytest
from helpers import (
    at_minutes,
    draft_intent,
    intent_in_state,
    offer_in_state,
    request_at,
    transaction_in_state,
)
from test_rework_wp03_r2 import _canonical_event, _rebuild_offer

from itaa_domain import events as events_mod
from itaa_domain.errors import DomainInvariantError
from itaa_domain.events import (
    EVENT_SPECS,
    DomainEvent,
    EventSpec,
    EventType,
    FieldPresence,
    emit_domain_event,
)
from itaa_domain.offer import OfferAction, OfferState
from itaa_domain.purchase_intent import PurchaseIntent, PurchaseIntentState
from itaa_domain.transaction import Transaction, TransactionState
from itaa_domain.value_objects import Version


class FakeEventType(StrEnum):
    CONFIRMED = "purchase_intent.confirmed"


class FakeOfferState(StrEnum):
    ACCEPTED = "ACCEPTED"


class FakeIntentState(StrEnum):
    DRAFT = "DRAFT"


class FakeTxState(StrEnum):
    NOT_REQUESTED = "NOT_REQUESTED"


class FakeAction(StrEnum):
    CONFIRM = "confirm"
    BEGIN_DRAFT = "begin_draft"
    EXPIRE = "expire"


def _rebuild_intent(current: PurchaseIntent, **changes: object) -> PurchaseIntent:
    values = {
        "intent_id": current.intent_id,
        "requirement_id": current.requirement_id,
        "buyer_token": current.buyer_token,
        "state": current.state,
        "revision": current.revision,
        "created_at": current.created_at,
        "updated_at": current.updated_at,
        "expires_at": current.expires_at,
        "disclosure_payload_hash": current.disclosure_payload_hash,
        "dispatch_approval_id": current.dispatch_approval_id,
    }
    values.update(changes)
    return PurchaseIntent(**values)  # type: ignore[arg-type]


def _rebuild_transaction(current: Transaction, **changes: object) -> Transaction:
    values = {
        "state": current.state,
        "revision": current.revision,
        "created_at": current.created_at,
        "updated_at": current.updated_at,
        "acceptance": current.acceptance,
        "action": current.action,
        "amount": current.amount,
        "supplier_token": current.supplier_token,
        "decision_expires_at": current.decision_expires_at,
        "receipt": current.receipt,
    }
    values.update(changes)
    return Transaction(**values)  # type: ignore[arg-type]


def _confirmed_event_with(*, event_type: object) -> DomainEvent:
    base = _canonical_event(EventType.PURCHASE_INTENT_CONFIRMED)
    return DomainEvent(
        event_type=event_type,  # type: ignore[arg-type]
        resource_type=base.resource_type,
        resource_id=base.resource_id,
        resource_version=base.resource_version,
        occurred_at=base.occurred_at,
        actor_type=base.actor_type,
        actor_id=base.actor_id,
        action=base.action,
        reason_code=base.reason_code,
        correlation_id=base.correlation_id,
        target_state=base.target_state,
        intent_id=base.intent_id,
    )


def test_raw_event_type_string_is_rejected_at_construction() -> None:
    with pytest.raises(DomainInvariantError) as exc:
        _confirmed_event_with(event_type="purchase_intent.confirmed")
    assert "purchase_intent.confirmed" not in str(exc.value)
    event = _canonical_event(EventType.PURCHASE_INTENT_CONFIRMED)
    primitive = event.to_primitive()
    assert primitive["eventType"] == "purchase_intent.confirmed"


def test_unrelated_enum_with_same_event_type_value_is_rejected() -> None:
    with pytest.raises(DomainInvariantError) as exc:
        _confirmed_event_with(event_type=FakeEventType.CONFIRMED)
    assert "purchase_intent.confirmed" not in str(exc.value)


@pytest.mark.parametrize("event_type", [{}, [], object(), 12, "not-an-event"])
def test_unsupported_and_unhashable_event_types_raise_domain_error(event_type: object) -> None:
    with pytest.raises(DomainInvariantError) as exc:
        _confirmed_event_with(event_type=event_type)
    assert "not-an-event" not in str(exc.value)


def test_emit_domain_event_rejects_raw_event_type_without_keyerror() -> None:
    event = _canonical_event(EventType.PURCHASE_INTENT_CONFIRMED)
    with pytest.raises(DomainInvariantError) as exc:
        emit_domain_event(
            event_type="purchase_intent.confirmed",  # type: ignore[arg-type]
            resource_id=event.resource_id,
            resource_version=event.resource_version,
            occurred_at=event.occurred_at,
            actor_type=event.actor_type,
            actor_id=event.actor_id,
            reason_code=event.reason_code,
            correlation_id=event.correlation_id,
            intent_id=event.intent_id,
        )
    assert "purchase_intent.confirmed" not in str(exc.value)


def test_event_specs_are_exhaustive_and_immutable() -> None:
    assert type(EVENT_SPECS) is MappingProxyType
    assert set(EVENT_SPECS) == set(EventType)
    assert len(EVENT_SPECS) == 24
    original = EVENT_SPECS[EventType.PURCHASE_INTENT_CONFIRMED]
    mutated = EventSpec(
        resource_type=original.resource_type,
        action="authorize_simulated",
        target_state="FAILED",
        reason_codes=frozenset({"supplier_unavailable"}),
        offer_id=FieldPresence.FORBIDDEN,
        acceptance_id=FieldPresence.FORBIDDEN,
        payload_hash=FieldPresence.FORBIDDEN,
    )
    with pytest.raises(TypeError):
        EVENT_SPECS[EventType.PURCHASE_INTENT_CONFIRMED] = mutated  # type: ignore[index]
    with pytest.raises(TypeError):
        del EVENT_SPECS[EventType.PURCHASE_INTENT_CONFIRMED]  # type: ignore[attr-defined]
    with pytest.raises(AttributeError):
        EVENT_SPECS.update(  # type: ignore[attr-defined]
            {EventType.PURCHASE_INTENT_CONFIRMED: mutated}
        )
    with pytest.raises(AttributeError):
        EVENT_SPECS.clear()  # type: ignore[attr-defined]
    assert EVENT_SPECS[EventType.PURCHASE_INTENT_CONFIRMED] is original
    public_dicts = [
        name
        for name, value in vars(events_mod).items()
        if not name.startswith("_") and isinstance(value, dict)
    ]
    assert public_dicts == []


def test_raw_accepted_offer_without_acceptance_is_rejected() -> None:
    current = offer_in_state("ACCEPTED")
    with pytest.raises(DomainInvariantError) as exc:
        _rebuild_offer(current, state="ACCEPTED", acceptance_id=None)
    assert "ACCEPTED" not in str(exc.value)


def test_unsupported_purchase_intent_state_string_is_rejected() -> None:
    current = draft_intent()
    with pytest.raises(DomainInvariantError) as exc:
        _rebuild_intent(current, state="NOT_A_PURCHASE_INTENT_STATE")
    assert "NOT_A_PURCHASE_INTENT_STATE" not in str(exc.value)


@pytest.mark.parametrize(
    ("rebuild", "factory_state", "raw_state", "fake_state"),
    [
        (_rebuild_intent, "DRAFT", "DRAFT", FakeIntentState.DRAFT),
        (_rebuild_offer, "INVITED", "INVITED", FakeOfferState.ACCEPTED),
        (_rebuild_transaction, "NOT_REQUESTED", "NOT_REQUESTED", FakeTxState.NOT_REQUESTED),
    ],
)
def test_raw_and_unrelated_enum_states_fail_for_all_aggregates(
    rebuild,
    factory_state: str,
    raw_state: str,
    fake_state: StrEnum,
) -> None:
    if rebuild is _rebuild_intent:
        current = intent_in_state(factory_state)
    elif rebuild is _rebuild_offer:
        current = offer_in_state(factory_state)
    else:
        current = transaction_in_state(factory_state)
    snapshot = current
    with pytest.raises(DomainInvariantError) as exc:
        rebuild(current, state=raw_state)
    assert raw_state not in str(exc.value)
    with pytest.raises(DomainInvariantError):
        rebuild(current, state=fake_state)
    assert current == snapshot


def test_generic_apply_rejects_raw_and_unrelated_actions() -> None:
    intent = draft_intent()
    intent_snapshot = intent
    request = request_at(at_minutes(1), intent.revision)
    with pytest.raises(DomainInvariantError) as exc:
        intent.apply("confirm", request)  # type: ignore[arg-type]
    assert "confirm" not in str(exc.value)
    with pytest.raises(DomainInvariantError):
        intent.apply(FakeAction.CONFIRM, request)  # type: ignore[arg-type]
    assert intent == intent_snapshot

    offer = offer_in_state("INVITED")
    offer_snapshot = offer
    offer_request = request_at(at_minutes(1), offer.revision)
    with pytest.raises(DomainInvariantError) as exc:
        offer.apply("begin_draft", offer_request)  # type: ignore[arg-type]
    assert "begin_draft" not in str(exc.value)
    with pytest.raises(DomainInvariantError):
        offer.apply(FakeAction.BEGIN_DRAFT, offer_request)  # type: ignore[arg-type]
    assert offer == offer_snapshot

    tx = transaction_in_state("APPROVAL_REQUIRED")
    tx_snapshot = tx
    tx_request = request_at(tx.updated_at, tx.revision)
    with pytest.raises(DomainInvariantError) as exc:
        tx.apply("expire", tx_request)  # type: ignore[arg-type]
    assert "expire" not in str(exc.value)
    with pytest.raises(DomainInvariantError):
        tx.apply(FakeAction.EXPIRE, tx_request)  # type: ignore[arg-type]
    assert tx == tx_snapshot
    assert tx.receipt is None


@pytest.mark.parametrize("state", list(PurchaseIntentState))
def test_valid_purchase_intent_snapshots_remain_reconstructible(state: PurchaseIntentState) -> None:
    current = intent_in_state(state.value)
    assert _rebuild_intent(current) == current


@pytest.mark.parametrize("state", list(OfferState))
def test_valid_offer_snapshots_remain_reconstructible(state: OfferState) -> None:
    current = offer_in_state(state.value)
    assert _rebuild_offer(current) == current


@pytest.mark.parametrize("state", list(TransactionState))
def test_valid_transaction_snapshots_remain_reconstructible(state: TransactionState) -> None:
    current = transaction_in_state(state.value)
    assert _rebuild_transaction(current) == current


def test_named_transitions_still_accept_typed_actions() -> None:
    result = draft_intent().confirm(request_at(at_minutes(1), Version.initial()))
    assert result.aggregate.state is PurchaseIntentState.CONFIRMED
    assert result.event.event_type is EventType.PURCHASE_INTENT_CONFIRMED
    invited = offer_in_state("INVITED")
    drafted = invited.begin_draft(request_at(at_minutes(1), invited.revision))
    assert drafted.aggregate.state is OfferState.DRAFT
    assert drafted.event.action == OfferAction.BEGIN_DRAFT.value
