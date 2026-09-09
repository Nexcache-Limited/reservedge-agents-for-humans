from __future__ import annotations

import pytest
from helpers import (
    AUTHORIZATION_ID,
    DECISION_EXPIRES_AT,
    IDEMPOTENCY_KEY,
    RECEIPT_EXPIRES_AT,
    RECEIPT_SIGNATURE,
    SUPPLIER_TOKEN,
    USER_APPROVAL_ID,
    idle_transaction,
    make_acceptance,
    offer_in_state,
    request_at,
    transaction_in_state,
    usd,
)

from itaa_domain.errors import (
    DomainInvariantError,
    DuplicateActionError,
    ExpiredResourceError,
    InvalidTransitionError,
    OfferVersionMismatchError,
    VersionConflictError,
)
from itaa_domain.identifiers import IntentId
from itaa_domain.protocol import TransitionRequest, TransitionResult
from itaa_domain.transaction import (
    TRANSACTION_TERMINAL,
    TRANSACTION_TRANSITIONS,
    AuthorizationReceipt,
    Transaction,
    TransactionAction,
    TransactionState,
)
from itaa_domain.value_objects import (
    AuthorizationAction,
    AuthorizationMode,
    TransactionDeclineReason,
    TransactionFailureReason,
    Version,
)

TX_CASES = [(state, action) for state in TransactionState for action in TransactionAction]


def _invoke(
    current: Transaction,
    action: TransactionAction,
    request: TransitionRequest,
) -> TransitionResult[Transaction]:
    offer = offer_in_state("ELIGIBLE")
    acceptance = current.acceptance or make_acceptance(offer=offer)
    if action is TransactionAction.REQUEST_FROM_ACCEPTANCE:
        return current.request_from_acceptance(request, acceptance, offer)
    if action is TransactionAction.REQUIRE_APPROVAL:
        return current.require_approval(
            request,
            action=AuthorizationAction.RESERVE_PARKING,
            amount=usd(11900),
            supplier_token=SUPPLIER_TOKEN,
            decision_expires_at=DECISION_EXPIRES_AT,
        )
    if action is TransactionAction.AUTHORIZE_SIMULATED:
        return current.authorize_simulated(
            request,
            authorization_id=AUTHORIZATION_ID,
            user_approval_id=USER_APPROVAL_ID,
            idempotency_key=IDEMPOTENCY_KEY,
            signature=RECEIPT_SIGNATURE,
            expires_at=RECEIPT_EXPIRES_AT,
        )
    if action is TransactionAction.DECLINE:
        return current.decline(request, TransactionDeclineReason.APPROVAL_WITHHELD)
    if action is TransactionAction.EXPIRE:
        return current.expire(request)
    if action is TransactionAction.FAIL:
        return current.fail(request, TransactionFailureReason.AUTHORIZATION_FAILED)
    raise AssertionError(action)


def _occurred_at(current: Transaction, action: TransactionAction):
    if action is TransactionAction.EXPIRE:
        deadline = current.decision_expires_at or DECISION_EXPIRES_AT
        return max(current.updated_at, deadline)
    return max(current.updated_at, current.updated_at)


@pytest.mark.parametrize(("state", "action"), TX_CASES)
def test_transaction_state_action_matrix(
    state: TransactionState,
    action: TransactionAction,
) -> None:
    current = transaction_in_state(state.value)
    original = current
    request = request_at(_occurred_at(current, action), current.revision)
    allowed = (state, action) in TRANSACTION_TRANSITIONS
    if allowed:
        result = _invoke(current, action, request)
        target = TRANSACTION_TRANSITIONS[(state, action)]
        assert result.aggregate.state is target
        assert result.aggregate.revision == current.revision.next()
        assert result.event.resource_version == result.aggregate.revision.value
        assert result.event.simulation is True
        if target is TransactionState.AUTHORIZED_SIMULATED:
            assert result.aggregate.receipt is not None
            assert result.aggregate.receipt.mode is AuthorizationMode.SIMULATED
            assert result.aggregate.receipt.action is AuthorizationAction.RESERVE_PARKING
        assert original == current
        return
    with pytest.raises((InvalidTransitionError, DuplicateActionError, DomainInvariantError)) as exc:
        _invoke(current, action, request)
    assert current == original
    if isinstance(exc.value, InvalidTransitionError):
        assert exc.value.current_state == state.value
        assert exc.value.attempted_action == action.value
        assert tuple(exc.value.permitted_actions) == current.permitted_actions()
    if isinstance(exc.value, DuplicateActionError):
        assert state in TRANSACTION_TERMINAL


def test_transaction_matrix_covers_every_pair() -> None:
    assert len(TX_CASES) == len(TransactionState) * len(TransactionAction)
    assert len(TX_CASES) == 42


def test_duplicate_authorization_does_not_emit_second_receipt() -> None:
    current = transaction_in_state("AUTHORIZED_SIMULATED")
    snapshot = current
    with pytest.raises(DuplicateActionError):
        current.authorize_simulated(
            request_at(current.updated_at, current.revision),
            authorization_id=AUTHORIZATION_ID,
            user_approval_id=USER_APPROVAL_ID,
            idempotency_key=IDEMPOTENCY_KEY,
            signature=RECEIPT_SIGNATURE,
            expires_at=RECEIPT_EXPIRES_AT,
        )
    assert current == snapshot
    assert current.receipt is not None


def test_transaction_version_conflict_and_wrong_offer_version() -> None:
    current = idle_transaction()
    with pytest.raises(VersionConflictError):
        current.request_from_acceptance(
            request_at(current.updated_at, Version(2)),
            make_acceptance(),
            offer_in_state("ELIGIBLE"),
        )
    offer = offer_in_state("ELIGIBLE")
    acceptance = make_acceptance(offer=offer)
    object.__setattr__(acceptance, "offer_version", Version(2))
    with pytest.raises(OfferVersionMismatchError):
        current.request_from_acceptance(
            request_at(current.updated_at, current.revision),
            acceptance,
            offer,
        )
    assert current.state is TransactionState.NOT_REQUESTED
    other_intent = make_acceptance(offer=offer)
    object.__setattr__(other_intent, "intent_id", IntentId("pi_01k2m3n4p5q6r7s8t9v0w1x2y9"))
    snapshot = current
    with pytest.raises(DomainInvariantError) as exc:
        current.request_from_acceptance(
            request_at(current.updated_at, current.revision),
            other_intent,
            offer,
        )
    assert exc.value.field == "intent_id"
    assert current == snapshot


def test_expired_acceptance_and_value_substitution_are_rejected() -> None:
    offer = offer_in_state("ELIGIBLE")
    acceptance = make_acceptance(offer=offer)
    current = idle_transaction()
    with pytest.raises(ExpiredResourceError):
        current.request_from_acceptance(
            request_at(acceptance.expires_at, current.revision),
            acceptance,
            offer,
        )
    pending = transaction_in_state("APPROVAL_REQUIRED")
    snapshot = pending
    with pytest.raises(DomainInvariantError) as exc:
        pending.apply(
            TransactionAction.AUTHORIZE_SIMULATED,
            request_at(pending.updated_at, pending.revision),
            authorization_id=AUTHORIZATION_ID,
            user_approval_id=USER_APPROVAL_ID,
            idempotency_key=IDEMPOTENCY_KEY,
            signature=RECEIPT_SIGNATURE,
            receipt_expires_at=RECEIPT_EXPIRES_AT,
            amount=usd(1),
        )
    assert exc.value.field == "amount"
    assert pending == snapshot
    with pytest.raises(DomainInvariantError) as exc:
        pending.expire(request_at(pending.updated_at, pending.revision))
    assert exc.value.field == "decision_expires_at"


def test_simulated_parking_authorization_only() -> None:
    with pytest.raises(ValueError):
        AuthorizationAction("charge_card")
    with pytest.raises(ValueError):
        AuthorizationMode("LIVE")
    with pytest.raises(ValueError):
        AuthorizationMode("real")
    receipt = transaction_in_state("AUTHORIZED_SIMULATED").receipt
    assert receipt is not None
    primitive = receipt.to_primitive()
    assert primitive["mode"] == "SIMULATED"
    assert primitive["action"] == "reserve_parking"
    assert "LIVE" not in str(primitive)
    assert AuthorizationReceipt is not None
