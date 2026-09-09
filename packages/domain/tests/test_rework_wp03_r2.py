from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from enum import StrEnum

import pytest
from helpers import (
    ACCEPTANCE_EXPIRES_AT,
    ACCEPTANCE_ID,
    ACTOR,
    CORRELATION,
    DECISION_EXPIRES_AT,
    INTENT_ID,
    OFFER_ID,
    OFFER_VALID_UNTIL,
    PAYLOAD_HASH,
    at_minutes,
    draft_intent,
    intent_in_state,
    offer_in_state,
    request_at,
    transaction_in_state,
)

from itaa_domain.errors import DomainInvariantError
from itaa_domain.events import EVENT_SPECS, DomainEvent, EventType, FieldPresence, ResourceType
from itaa_domain.offer import Offer, OfferAction, OfferState
from itaa_domain.purchase_intent import PurchaseIntentAction
from itaa_domain.transaction import Transaction, TransactionAction, TransactionState
from itaa_domain.value_objects import (
    ActorType,
    CancellationReason,
    ClosureReason,
    DeclineReason,
    RejectionReason,
    TransactionDeclineReason,
    TransactionFailureReason,
    Version,
)

MICROSECOND = timedelta(microseconds=1)


def _late_authorized(instant):
    current = transaction_in_state("AUTHORIZED_SIMULATED")
    assert current.receipt is not None
    receipt = replace(
        current.receipt,
        authorized_at=instant,
        expires_at=max(current.receipt.expires_at, instant + timedelta(hours=1)),
    )
    return replace(current, updated_at=instant, receipt=receipt)


def _rebuild_offer(current: Offer, **changes: object) -> Offer:
    values = {
        "offer_id": current.offer_id,
        "intent_id": current.intent_id,
        "supplier_token": current.supplier_token,
        "state": current.state,
        "revision": current.revision,
        "offer_version": current.offer_version,
        "created_at": current.created_at,
        "updated_at": current.updated_at,
        "simulation": current.simulation,
        "terms": current.terms,
        "latest_counter_offer_id": current.latest_counter_offer_id,
        "countered_parent_version": current.countered_parent_version,
        "acceptance_id": current.acceptance_id,
    }
    values.update(changes)
    return Offer(**values)  # type: ignore[arg-type]


def _canonical_event(event_type: EventType, **overrides: object) -> DomainEvent:
    spec = EVENT_SPECS[event_type]
    payload: dict[str, object] = {
        "event_type": event_type,
        "resource_type": spec.resource_type,
        "resource_version": 2,
        "occurred_at": at_minutes(1),
        "actor_type": ActorType.BUYER,
        "actor_id": ACTOR.actor_id.to_primitive(),
        "action": spec.action,
        "reason_code": sorted(spec.reason_codes)[0],
        "correlation_id": CORRELATION.to_primitive(),
        "target_state": spec.target_state,
        "intent_id": INTENT_ID.to_primitive(),
    }
    if spec.resource_type is ResourceType.PURCHASE_INTENT:
        payload["resource_id"] = INTENT_ID.to_primitive()
    elif spec.resource_type is ResourceType.OFFER:
        payload["resource_id"] = OFFER_ID.to_primitive()
        payload["simulation"] = True
    else:
        payload["resource_id"] = ACCEPTANCE_ID.to_primitive()
        payload["simulation"] = True
    if spec.offer_id is not FieldPresence.FORBIDDEN:
        payload["offer_id"] = OFFER_ID.to_primitive()
    if spec.acceptance_id is not FieldPresence.FORBIDDEN:
        payload["acceptance_id"] = ACCEPTANCE_ID.to_primitive()
    if spec.payload_hash is not FieldPresence.FORBIDDEN:
        payload["payload_hash"] = PAYLOAD_HASH.to_primitive()
    payload.update(overrides)
    return DomainEvent(**payload)  # type: ignore[arg-type]


def test_late_authorized_transaction_snapshot_is_rejected() -> None:
    with pytest.raises(DomainInvariantError):
        _late_authorized(DECISION_EXPIRES_AT)
    with pytest.raises(DomainInvariantError):
        _late_authorized(DECISION_EXPIRES_AT + timedelta(minutes=1))


def test_authorized_snapshot_after_acceptance_expiry_is_rejected() -> None:
    with pytest.raises(DomainInvariantError):
        _late_authorized(ACCEPTANCE_EXPIRES_AT)
    with pytest.raises(DomainInvariantError):
        _late_authorized(ACCEPTANCE_EXPIRES_AT + timedelta(minutes=1))


def test_expired_transaction_cannot_be_reconstructed_before_deadline() -> None:
    current = transaction_in_state("EXPIRED")
    assert current.decision_expires_at is not None
    with pytest.raises(DomainInvariantError):
        replace(current, updated_at=current.decision_expires_at - MICROSECOND)


def test_authorized_snapshot_one_microsecond_before_deadline_is_valid() -> None:
    rebuilt = _late_authorized(DECISION_EXPIRES_AT - MICROSECOND)
    assert rebuilt.state is TransactionState.AUTHORIZED_SIMULATED
    assert rebuilt.updated_at == DECISION_EXPIRES_AT - MICROSECOND


@pytest.mark.parametrize("state", list(TransactionState))
def test_valid_transaction_snapshots_remain_reconstructible(state: TransactionState) -> None:
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


def test_expired_accepted_offer_snapshot_is_rejected() -> None:
    current = offer_in_state("ACCEPTED")
    with pytest.raises(DomainInvariantError):
        _rebuild_offer(current, updated_at=OFFER_VALID_UNTIL)
    with pytest.raises(DomainInvariantError):
        _rebuild_offer(current, updated_at=OFFER_VALID_UNTIL + timedelta(minutes=1))


def test_expired_offer_cannot_be_reconstructed_before_validity_ends() -> None:
    current = offer_in_state("EXPIRED")
    with pytest.raises(DomainInvariantError):
        _rebuild_offer(current, updated_at=OFFER_VALID_UNTIL - MICROSECOND)


def test_accepted_offer_one_microsecond_before_validity_end_is_valid() -> None:
    current = offer_in_state("ACCEPTED")
    rebuilt = _rebuild_offer(current, updated_at=OFFER_VALID_UNTIL - MICROSECOND)
    assert rebuilt.state is OfferState.ACCEPTED


def test_rejected_and_declined_offers_may_be_reconstructed_after_validity() -> None:
    rejected = _rebuild_offer(
        offer_in_state("REJECTED"),
        updated_at=OFFER_VALID_UNTIL + timedelta(minutes=1),
    )
    declined = _rebuild_offer(
        offer_in_state("DECLINED"),
        updated_at=OFFER_VALID_UNTIL + timedelta(minutes=1),
    )
    assert rejected.state is OfferState.REJECTED
    assert declined.state is OfferState.DECLINED


@pytest.mark.parametrize("state", list(OfferState))
def test_valid_offer_snapshots_remain_reconstructible(state: OfferState) -> None:
    current = offer_in_state(state.value)
    assert _rebuild_offer(current) == current


def test_event_specs_cover_all_twenty_four_event_types() -> None:
    assert set(EVENT_SPECS) == set(EventType)
    assert len(EVENT_SPECS) == 24


@pytest.mark.parametrize("event_type", list(EventType))
def test_canonical_event_combination_is_accepted(event_type: EventType) -> None:
    event = _canonical_event(event_type)
    spec = EVENT_SPECS[event_type]
    assert event.event_type is event_type
    assert event.resource_type is spec.resource_type
    assert event.action == spec.action
    assert event.target_state == spec.target_state
    assert event.reason_code in spec.reason_codes


def _wrong_resource(spec_resource: ResourceType) -> ResourceType:
    if spec_resource is ResourceType.PURCHASE_INTENT:
        return ResourceType.OFFER
    return ResourceType.PURCHASE_INTENT


def _wrong_action(action: str) -> str:
    return "confirm" if action != "confirm" else "authorize_simulated"


def _wrong_target(target: str) -> str:
    return "FAILED" if target != "FAILED" else "CONFIRMED"


def _wrong_reason(reason_codes: frozenset[str]) -> str:
    for code in ("supplier_unavailable", "completed", "confirm"):
        if code not in reason_codes:
            return code
    raise AssertionError("no alternate closed reason")


@pytest.mark.parametrize("event_type", list(EventType))
@pytest.mark.parametrize(
    "dimension",
    ["resource_type", "action", "target_state", "reason_code", "reference_policy"],
)
def test_direct_event_construction_rejects_semantic_mismatch(
    event_type: EventType,
    dimension: str,
) -> None:
    spec = EVENT_SPECS[event_type]
    overrides: dict[str, object] = {}
    if dimension == "resource_type":
        overrides["resource_type"] = _wrong_resource(spec.resource_type)
    elif dimension == "action":
        overrides["action"] = _wrong_action(spec.action)
    elif dimension == "target_state":
        overrides["target_state"] = _wrong_target(spec.target_state)
    elif dimension == "reason_code":
        overrides["reason_code"] = _wrong_reason(spec.reason_codes)
    else:
        if spec.offer_id is FieldPresence.REQUIRED:
            overrides["offer_id"] = None
        elif spec.offer_id is FieldPresence.FORBIDDEN:
            overrides["offer_id"] = OFFER_ID.to_primitive()
        elif spec.acceptance_id is FieldPresence.REQUIRED:
            overrides["acceptance_id"] = None
        elif spec.acceptance_id is FieldPresence.FORBIDDEN:
            overrides["acceptance_id"] = ACCEPTANCE_ID.to_primitive()
        elif spec.payload_hash is FieldPresence.REQUIRED:
            overrides["payload_hash"] = None
        else:
            overrides["payload_hash"] = PAYLOAD_HASH.to_primitive()
    with pytest.raises(DomainInvariantError) as exc:
        _canonical_event(event_type, **overrides)
    assert "supplier_unavailable" not in str(exc.value)
    assert "completed" not in str(exc.value)


def test_semantically_inconsistent_purchase_intent_event_is_rejected() -> None:
    with pytest.raises(DomainInvariantError) as exc:
        _canonical_event(
            EventType.PURCHASE_INTENT_CONFIRMED,
            action="authorize_simulated",
            reason_code="supplier_unavailable",
            target_state="FAILED",
        )
    assert "supplier_unavailable" not in str(exc.value)


def test_cancel_rejects_closure_reason_on_generic_and_named_apis() -> None:
    draft = draft_intent()
    snapshot = draft
    request = request_at(at_minutes(1), draft.revision)
    with pytest.raises(DomainInvariantError):
        draft.apply(PurchaseIntentAction.CANCEL, request, reason=ClosureReason.COMPLETED)
    assert draft == snapshot
    with pytest.raises(DomainInvariantError):
        draft.cancel(request, ClosureReason.COMPLETED)  # type: ignore[arg-type]
    assert draft == snapshot


def test_close_rejects_cancellation_reason_on_generic_and_named_apis() -> None:
    dispatched = intent_in_state("DISPATCHED")
    snapshot = dispatched
    request = request_at(dispatched.updated_at, dispatched.revision)
    with pytest.raises(DomainInvariantError):
        dispatched.apply(
            PurchaseIntentAction.CLOSE,
            request,
            reason=CancellationReason.BUYER_REVOKED,
        )
    assert dispatched == snapshot
    with pytest.raises(DomainInvariantError):
        dispatched.close(request, CancellationReason.BUYER_REVOKED)  # type: ignore[arg-type]
    assert dispatched == snapshot


def test_offer_reject_and_decline_reject_cross_family_reasons() -> None:
    submitted = offer_in_state("SUBMITTED")
    snapshot = submitted
    request = request_at(submitted.updated_at, submitted.revision)
    with pytest.raises(DomainInvariantError):
        submitted.apply(OfferAction.REJECT, request, reason=DeclineReason.BUYER_DECLINED)
    with pytest.raises(DomainInvariantError):
        submitted.reject(request, DeclineReason.BUYER_DECLINED)  # type: ignore[arg-type]
    assert submitted == snapshot
    eligible = offer_in_state("ELIGIBLE")
    eligible_snapshot = eligible
    eligible_request = request_at(eligible.updated_at, eligible.revision)
    with pytest.raises(DomainInvariantError):
        eligible.apply(OfferAction.DECLINE, eligible_request, reason=RejectionReason.INELIGIBLE)
    with pytest.raises(DomainInvariantError):
        eligible.decline(eligible_request, RejectionReason.INELIGIBLE)  # type: ignore[arg-type]
    assert eligible == eligible_snapshot


def test_transaction_decline_and_fail_reject_cross_family_reasons() -> None:
    required = transaction_in_state("APPROVAL_REQUIRED")
    snapshot = required
    request = request_at(required.updated_at, required.revision)
    with pytest.raises(DomainInvariantError):
        required.apply(
            TransactionAction.DECLINE,
            request,
            reason=TransactionFailureReason.AUTHORIZATION_FAILED,
        )
    with pytest.raises(DomainInvariantError):
        required.decline(request, TransactionFailureReason.AUTHORIZATION_FAILED)  # type: ignore[arg-type]
    assert required == snapshot
    with pytest.raises(DomainInvariantError):
        required.apply(
            TransactionAction.FAIL,
            request,
            reason=TransactionDeclineReason.APPROVAL_WITHHELD,
        )
    with pytest.raises(DomainInvariantError):
        required.fail(request, TransactionDeclineReason.APPROVAL_WITHHELD)  # type: ignore[arg-type]
    assert required == snapshot


def test_fixed_action_reason_rejects_unrelated_enum_with_matching_string() -> None:
    class FakeConfirm(StrEnum):
        CONFIRM = "confirm"

    draft = draft_intent()
    snapshot = draft
    request = request_at(at_minutes(1), draft.revision)
    with pytest.raises(DomainInvariantError):
        draft.apply(PurchaseIntentAction.CONFIRM, request, reason=FakeConfirm.CONFIRM)  # type: ignore[arg-type]
    assert draft == snapshot
    result = draft.confirm(request)
    assert result.event.reason_code == "confirm"
    assert result.aggregate.revision == Version(2)
