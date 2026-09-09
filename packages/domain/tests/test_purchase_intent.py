from __future__ import annotations

import pytest
from helpers import (
    CANCEL_REASON,
    CLOSE_REASON,
    DISPATCH_APPROVAL_ID,
    INTENT_EXPIRES_AT,
    PAYLOAD_HASH,
    at_minutes,
    draft_intent,
    intent_in_state,
    request_at,
)

from itaa_domain.errors import (
    DomainInvariantError,
    DuplicateActionError,
    InvalidTransitionError,
    VersionConflictError,
)
from itaa_domain.protocol import TransitionRequest, TransitionResult
from itaa_domain.purchase_intent import (
    PURCHASE_INTENT_TERMINAL,
    PURCHASE_INTENT_TRANSITIONS,
    PurchaseIntent,
    PurchaseIntentAction,
    PurchaseIntentState,
)
from itaa_domain.value_objects import Version

PI_CASES = [(state, action) for state in PurchaseIntentState for action in PurchaseIntentAction]


def _invoke(
    current: PurchaseIntent,
    action: PurchaseIntentAction,
    request: TransitionRequest,
) -> TransitionResult[PurchaseIntent]:
    if action is PurchaseIntentAction.CONFIRM:
        return current.confirm(request)
    if action is PurchaseIntentAction.CANCEL:
        return current.cancel(request, CANCEL_REASON)
    if action is PurchaseIntentAction.PREVIEW_DISCLOSURE:
        return current.preview_disclosure(request, PAYLOAD_HASH)
    if action is PurchaseIntentAction.APPROVE_DISPATCH:
        return current.approve_dispatch(request, DISPATCH_APPROVAL_ID)
    if action is PurchaseIntentAction.DISPATCH:
        return current.dispatch(request)
    if action is PurchaseIntentAction.EXPIRE:
        return current.expire(request)
    if action is PurchaseIntentAction.CLOSE:
        return current.close(request, CLOSE_REASON)
    raise AssertionError(action)


def _occurred_at(current: PurchaseIntent, action: PurchaseIntentAction):
    if action is PurchaseIntentAction.EXPIRE:
        return max(current.updated_at, INTENT_EXPIRES_AT)
    return current.updated_at


@pytest.mark.parametrize(("state", "action"), PI_CASES)
def test_purchase_intent_state_action_matrix(
    state: PurchaseIntentState,
    action: PurchaseIntentAction,
) -> None:
    current = intent_in_state(state.value)
    original = current
    request = request_at(_occurred_at(current, action), current.revision)
    allowed = (state, action) in PURCHASE_INTENT_TRANSITIONS
    if allowed:
        result = _invoke(current, action, request)
        target = PURCHASE_INTENT_TRANSITIONS[(state, action)]
        assert result.aggregate is not current
        assert result.aggregate.state is target
        assert result.aggregate.revision == current.revision.next()
        assert result.event.resource_version == result.aggregate.revision.value
        assert result.event.action == action.value
        assert result.event.target_state == target.value
        assert result.event.correlation_id == request.correlation_id.to_primitive()
        assert result.event.actor_id == request.actor.actor_id.to_primitive()
        assert original == current
        return
    with pytest.raises((InvalidTransitionError, DuplicateActionError)) as exc:
        _invoke(current, action, request)
    assert current == original
    if isinstance(exc.value, InvalidTransitionError):
        assert exc.value.current_state == state.value
        assert exc.value.attempted_action == action.value
        assert tuple(exc.value.permitted_actions) == current.permitted_actions()
        assert exc.value.resource_type == "purchase_intent"
    if isinstance(exc.value, DuplicateActionError):
        assert state in PURCHASE_INTENT_TERMINAL


def test_purchase_intent_matrix_covers_every_pair() -> None:
    assert len(PI_CASES) == len(PurchaseIntentState) * len(PurchaseIntentAction)
    assert len(PI_CASES) == 56


def test_purchase_intent_version_conflict_does_not_mutate() -> None:
    current = draft_intent()
    snapshot = current
    with pytest.raises(VersionConflictError) as exc:
        current.confirm(request_at(at_minutes(1), Version(2)))
    assert current == snapshot
    assert exc.value.expected_revision == 2
    assert exc.value.actual_revision == 1


def test_purchase_intent_advanced_state_requires_hash_and_approval() -> None:
    base = intent_in_state("CONFIRMED")
    with pytest.raises(DomainInvariantError) as exc:
        PurchaseIntent(
            intent_id=base.intent_id,
            requirement_id=base.requirement_id,
            buyer_token=base.buyer_token,
            state=PurchaseIntentState.APPROVED,
            revision=base.revision,
            created_at=base.created_at,
            updated_at=base.updated_at,
            expires_at=base.expires_at,
        )
    assert exc.value.field in {"disclosure_payload_hash", "dispatch_approval_id"}


def test_purchase_intent_expire_before_deadline_fails() -> None:
    current = intent_in_state("APPROVED")
    snapshot = current
    with pytest.raises(DomainInvariantError) as exc:
        current.expire(request_at(current.updated_at, current.revision))
    assert exc.value.field == "expires_at"
    assert current == snapshot
    expired = intent_in_state("EXPIRED")
    with pytest.raises(DomainInvariantError) as reconstruction:
        PurchaseIntent(
            intent_id=expired.intent_id,
            requirement_id=expired.requirement_id,
            buyer_token=expired.buyer_token,
            state=PurchaseIntentState.EXPIRED,
            revision=expired.revision,
            created_at=expired.created_at,
            updated_at=expired.updated_at,
            expires_at=expired.expires_at,
        )
    assert reconstruction.value.field in {"disclosure_payload_hash", "dispatch_approval_id"}
    with pytest.raises(DomainInvariantError) as premature:
        PurchaseIntent(
            intent_id=expired.intent_id,
            requirement_id=expired.requirement_id,
            buyer_token=expired.buyer_token,
            state=PurchaseIntentState.EXPIRED,
            revision=expired.revision,
            created_at=expired.created_at,
            updated_at=expired.created_at,
            expires_at=expired.expires_at,
            disclosure_payload_hash=expired.disclosure_payload_hash,
            dispatch_approval_id=expired.dispatch_approval_id,
        )
    assert premature.value.field == "updated_at"


def test_purchase_intent_backwards_time_fails() -> None:
    current = intent_in_state("CONFIRMED")
    with pytest.raises(DomainInvariantError):
        current.preview_disclosure(request_at(at_minutes(0), current.revision), PAYLOAD_HASH)
