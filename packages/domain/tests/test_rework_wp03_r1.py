from __future__ import annotations

from datetime import timedelta

import pytest
from helpers import (
    ACCEPTANCE_CREATED_AT,
    AUTHORIZATION_ID,
    COUNTER_OFFER_ID,
    DECISION_EXPIRES_AT,
    IDEMPOTENCY_KEY,
    INTENT_EXPIRES_AT,
    OFFER_VALID_UNTIL,
    RECEIPT_SIGNATURE,
    SUPPLIER_TOKEN,
    USER_APPROVAL_ID,
    at_minutes,
    draft_intent,
    intent_in_state,
    invited_offer,
    make_acceptance,
    offer_in_state,
    parkdirect_terms,
    request_at,
    transaction_in_state,
    usd,
)

from itaa_domain.errors import DomainInvariantError, ExpiredResourceError
from itaa_domain.events import CLOSED_REASON_CODES, DomainEvent, EventType, ResourceType
from itaa_domain.identifiers import CorrelationId
from itaa_domain.offer import Offer, OfferState
from itaa_domain.purchase_intent import PurchaseIntentAction
from itaa_domain.transaction import Transaction, TransactionState
from itaa_domain.value_objects import ActorRef, ActorType, AuthorizationAction, Version


def test_incomplete_approval_required_transaction_is_rejected() -> None:
    with pytest.raises(DomainInvariantError):
        Transaction(
            state=TransactionState.APPROVAL_REQUIRED,
            revision=Version(2),
            created_at=at_minutes(0),
            updated_at=at_minutes(60),
        )


@pytest.mark.parametrize(
    "state",
    [
        TransactionState.NOT_REQUESTED,
        TransactionState.ACCEPTANCE_PENDING,
        TransactionState.APPROVAL_REQUIRED,
        TransactionState.AUTHORIZED_SIMULATED,
        TransactionState.DECLINED,
        TransactionState.EXPIRED,
        TransactionState.FAILED,
    ],
)
def test_valid_transaction_state_snapshots_are_reconstructible(state: TransactionState) -> None:
    current = transaction_in_state(state.value)
    rebuilt = Transaction(
        state=current.state,
        revision=current.revision,
        created_at=current.created_at,
        updated_at=current.updated_at,
        acceptance=current.acceptance,
        action=current.action,
        amount=current.amount,
        supplier_token=current.supplier_token,
        decision_expires_at=current.decision_expires_at,
        receipt=current.receipt,
    )
    assert rebuilt == current


def test_countered_offer_requires_matching_counter_metadata() -> None:
    current = offer_in_state("SUBMITTED")
    with pytest.raises(DomainInvariantError):
        Offer(
            offer_id=current.offer_id,
            intent_id=current.intent_id,
            supplier_token=current.supplier_token,
            state=OfferState.COUNTERED,
            revision=Version(4),
            offer_version=current.offer_version,
            created_at=current.created_at,
            updated_at=current.updated_at,
            terms=current.terms,
        )
    invited = invited_offer()
    with pytest.raises(DomainInvariantError):
        Offer(
            offer_id=invited.offer_id,
            intent_id=invited.intent_id,
            supplier_token=invited.supplier_token,
            state=OfferState.INVITED,
            revision=invited.revision,
            offer_version=invited.offer_version,
            created_at=invited.created_at,
            updated_at=invited.updated_at,
            latest_counter_offer_id=COUNTER_OFFER_ID,
            countered_parent_version=Version.initial(),
        )
    accepted = offer_in_state("ACCEPTED")
    assert accepted.acceptance_id is not None
    with pytest.raises(DomainInvariantError):
        Offer(
            offer_id=accepted.offer_id,
            intent_id=accepted.intent_id,
            supplier_token=accepted.supplier_token,
            state=OfferState.ACCEPTED,
            revision=accepted.revision,
            offer_version=accepted.offer_version,
            created_at=accepted.created_at,
            updated_at=accepted.updated_at,
            terms=accepted.terms,
        )


def test_expired_intent_cannot_be_dispatched() -> None:
    current = intent_in_state("APPROVED")
    snapshot = current
    late = INTENT_EXPIRES_AT + timedelta(minutes=1)
    with pytest.raises(ExpiredResourceError):
        current.dispatch(request_at(late, current.revision))
    assert current == snapshot
    draft = draft_intent()
    with pytest.raises(ExpiredResourceError):
        draft.confirm(request_at(late, draft.revision))
    assert draft.state.value == "DRAFT"


def test_expired_offer_cannot_be_accepted_or_advanced() -> None:
    current = offer_in_state("ELIGIBLE")
    snapshot = current
    late = OFFER_VALID_UNTIL + timedelta(minutes=1)
    acceptance = make_acceptance(offer=current)
    with pytest.raises(ExpiredResourceError):
        current.accept(request_at(late, current.revision), acceptance)
    assert current == snapshot
    submitted = offer_in_state("SUBMITTED")
    with pytest.raises(ExpiredResourceError):
        submitted.validate(request_at(late, submitted.revision))
    with pytest.raises(ExpiredResourceError):
        invited_offer().begin_draft(request_at(at_minutes(1), Version.initial())).aggregate.submit(
            request_at(late, Version(2)),
            parkdirect_terms(),
        )
    future_acceptance = make_acceptance(offer=current)
    with pytest.raises(ExpiredResourceError):
        current.accept(
            request_at(ACCEPTANCE_CREATED_AT - timedelta(minutes=1), current.revision),
            future_acceptance,
        )


def test_authorization_after_decision_deadline_fails() -> None:
    current = transaction_in_state("APPROVAL_REQUIRED")
    snapshot = current
    late = DECISION_EXPIRES_AT + timedelta(minutes=1)
    with pytest.raises(ExpiredResourceError):
        current.authorize_simulated(
            request_at(late, current.revision),
            authorization_id=AUTHORIZATION_ID,
            user_approval_id=USER_APPROVAL_ID,
            idempotency_key=IDEMPOTENCY_KEY,
            signature=RECEIPT_SIGNATURE,
            expires_at=late + timedelta(hours=1),
        )
    assert current == snapshot
    with pytest.raises(ExpiredResourceError):
        current.authorize_simulated(
            request_at(DECISION_EXPIRES_AT, current.revision),
            authorization_id=AUTHORIZATION_ID,
            user_approval_id=USER_APPROVAL_ID,
            idempotency_key=IDEMPOTENCY_KEY,
            signature=RECEIPT_SIGNATURE,
            expires_at=DECISION_EXPIRES_AT + timedelta(hours=1),
        )
    expired = current.expire(request_at(DECISION_EXPIRES_AT, current.revision))
    assert expired.aggregate.state is TransactionState.EXPIRED
    pending = transaction_in_state("ACCEPTANCE_PENDING")
    with pytest.raises(DomainInvariantError):
        pending.require_approval(
            request_at(pending.updated_at, pending.revision),
            action=AuthorizationAction.RESERVE_PARKING,
            amount=usd(11900),
            supplier_token=SUPPLIER_TOKEN,
            decision_expires_at=pending.updated_at,
        )


def test_identity_like_event_values_are_rejected() -> None:
    intent = draft_intent()
    with pytest.raises(DomainInvariantError) as exc:
        ActorRef(ActorType.BUYER, "alice.smith")  # type: ignore[arg-type]
    assert "alice" not in str(exc.value)
    with pytest.raises(DomainInvariantError) as exc:
        CorrelationId("jfk.trip.alice")
    assert "jfk" not in str(exc.value)
    with pytest.raises(DomainInvariantError) as exc:
        intent.apply(
            PurchaseIntentAction.CANCEL,
            request_at(at_minutes(1), intent.revision),
            reason="customer_alice_smith_requested_cancel",  # type: ignore[arg-type]
        )
    assert "alice" not in str(exc.value)
    with pytest.raises(DomainInvariantError) as exc:
        DomainEvent(
            event_type=EventType.PURCHASE_INTENT_CANCELLED,
            resource_type=ResourceType.PURCHASE_INTENT,
            resource_id=intent.intent_id.to_primitive(),
            resource_version=2,
            occurred_at=at_minutes(1),
            actor_type=ActorType.BUYER,
            actor_id="alice.smith",
            action="cancel",
            reason_code="customer_alice_smith_requested_cancel",
            correlation_id="jfk.trip.alice",
            target_state="CANCELLED",
        )
    assert "alice" not in str(exc.value)
    assert "customer_alice" not in str(exc.value)


def test_closed_reason_codes_cover_all_enums() -> None:
    from itaa_domain.offer import OfferAction
    from itaa_domain.purchase_intent import PurchaseIntentAction
    from itaa_domain.transaction import TransactionAction
    from itaa_domain.value_objects import (
        CancellationReason,
        ClosureReason,
        DeclineReason,
        RejectionReason,
        TransactionDeclineReason,
        TransactionFailureReason,
    )

    expected = (
        {item.value for item in PurchaseIntentAction}
        | {item.value for item in OfferAction}
        | {item.value for item in TransactionAction}
        | {item.value for item in CancellationReason}
        | {item.value for item in ClosureReason}
        | {item.value for item in RejectionReason}
        | {item.value for item in DeclineReason}
        | {item.value for item in TransactionDeclineReason}
        | {item.value for item in TransactionFailureReason}
    )
    assert frozenset(expected) == CLOSED_REASON_CODES
