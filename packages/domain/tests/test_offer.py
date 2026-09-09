from __future__ import annotations

from dataclasses import replace

import pytest
from helpers import (
    ACCEPTANCE_CREATED_AT,
    COUNTER_OFFER_ID,
    DECLINE_REASON,
    OFFER_ID_SKY,
    OFFER_VALID_UNTIL,
    REJECT_REASON,
    make_acceptance,
    offer_in_state,
    parkdirect_terms,
    request_at,
    resubmitted_terms,
)

from itaa_domain.errors import (
    DomainInvariantError,
    DuplicateActionError,
    InvalidTransitionError,
    OfferVersionMismatchError,
    VersionConflictError,
)
from itaa_domain.identifiers import IntentId
from itaa_domain.offer import (
    OFFER_TERMINAL,
    OFFER_TRANSITIONS,
    Offer,
    OfferAction,
    OfferState,
)
from itaa_domain.protocol import TransitionRequest, TransitionResult
from itaa_domain.value_objects import Version

OFFER_CASES = [(state, action) for state in OfferState for action in OfferAction]


def _invoke(
    current: Offer,
    action: OfferAction,
    request: TransitionRequest,
) -> TransitionResult[Offer]:
    if action is OfferAction.BEGIN_DRAFT:
        return current.begin_draft(request)
    if action is OfferAction.SUBMIT:
        return current.submit(request, parkdirect_terms())
    if action is OfferAction.VALIDATE:
        return current.validate(request)
    if action is OfferAction.REJECT:
        return current.reject(request, REJECT_REASON)
    if action is OfferAction.COUNTER:
        return current.counter(request, COUNTER_OFFER_ID, current.offer_version)
    if action is OfferAction.RESUBMIT:
        return current.resubmit(request, resubmitted_terms(), current.offer_version.next())
    if action is OfferAction.MARK_ELIGIBLE:
        return current.mark_eligible(request)
    if action is OfferAction.RECOMMEND:
        return current.recommend(request)
    if action is OfferAction.ACCEPT:
        return current.accept(request, make_acceptance(offer=current))
    if action is OfferAction.DECLINE:
        return current.decline(request, DECLINE_REASON)
    if action is OfferAction.EXPIRE:
        return current.expire(request)
    raise AssertionError(action)


def _occurred_at(current: Offer, action: OfferAction):
    if action is OfferAction.EXPIRE:
        deadline = current.terms.validity.end if current.terms is not None else OFFER_VALID_UNTIL
        return max(current.updated_at, deadline)
    if action is OfferAction.ACCEPT:
        return max(current.updated_at, ACCEPTANCE_CREATED_AT)
    return current.updated_at


@pytest.mark.parametrize(("state", "action"), OFFER_CASES)
def test_offer_state_action_matrix(state: OfferState, action: OfferAction) -> None:
    current = offer_in_state(state.value)
    original = current
    commercial = current.offer_version
    request = request_at(_occurred_at(current, action), current.revision)
    allowed = (state, action) in OFFER_TRANSITIONS
    if allowed:
        result = _invoke(current, action, request)
        target = OFFER_TRANSITIONS[(state, action)]
        assert result.aggregate.state is target
        assert result.aggregate.revision == current.revision.next()
        assert result.event.resource_version == result.aggregate.revision.value
        assert result.event.simulation is True
        if action is OfferAction.RESUBMIT:
            assert result.aggregate.offer_version == commercial.next()
        else:
            assert result.aggregate.offer_version == commercial
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
        assert state in OFFER_TERMINAL


def test_offer_matrix_covers_every_pair() -> None:
    assert len(OFFER_CASES) == len(OfferState) * len(OfferAction)
    assert len(OFFER_CASES) == 121


def test_offer_version_conflict_and_wrong_acceptance() -> None:
    current = offer_in_state("ELIGIBLE")
    snapshot = current
    with pytest.raises(VersionConflictError):
        current.recommend(request_at(current.updated_at, Version(1)))
    assert current == snapshot
    wrong_id = make_acceptance(offer_id=OFFER_ID_SKY)
    with pytest.raises(DomainInvariantError) as exc:
        current.accept(request_at(ACCEPTANCE_CREATED_AT, current.revision), wrong_id)
    assert exc.value.field == "offer_id"
    assert current == snapshot
    wrong_intent = make_acceptance(offer=current)
    object.__setattr__(wrong_intent, "intent_id", IntentId("pi_01k2m3n4p5q6r7s8t9v0w1x2y9"))
    with pytest.raises(DomainInvariantError) as intent_exc:
        current.accept(request_at(ACCEPTANCE_CREATED_AT, current.revision), wrong_intent)
    assert intent_exc.value.field == "intent_id"
    assert current == snapshot
    wrong_version = make_acceptance(offer=current)
    object.__setattr__(wrong_version, "offer_version", Version(2))
    with pytest.raises(OfferVersionMismatchError):
        current.accept(request_at(ACCEPTANCE_CREATED_AT, current.revision), wrong_version)
    assert current == snapshot


def test_offer_premature_expire_and_terminal_repeat() -> None:
    current = offer_in_state("VALIDATED")
    snapshot = current
    with pytest.raises(DomainInvariantError) as exc:
        current.expire(request_at(current.updated_at, current.revision))
    assert exc.value.field == "valid_until"
    assert current == snapshot
    accepted = offer_in_state("ACCEPTED")
    with pytest.raises(DuplicateActionError):
        accepted.accept(
            request_at(max(accepted.updated_at, ACCEPTANCE_CREATED_AT), accepted.revision),
            make_acceptance(offer=accepted),
        )
    assert accepted.state is OfferState.ACCEPTED


def test_offer_counter_parent_mismatch_and_resubmit_version() -> None:
    current = offer_in_state("SUBMITTED")
    snapshot = current
    with pytest.raises(OfferVersionMismatchError):
        current.counter(
            request_at(current.updated_at, current.revision),
            COUNTER_OFFER_ID,
            Version(2),
        )
    assert current == snapshot
    countered = current.counter(
        request_at(current.updated_at, current.revision),
        COUNTER_OFFER_ID,
        current.offer_version,
    ).aggregate
    with pytest.raises(OfferVersionMismatchError):
        countered.resubmit(
            request_at(countered.updated_at, countered.revision),
            resubmitted_terms(),
            Version(3),
        )
    result = countered.resubmit(
        request_at(countered.updated_at, countered.revision),
        resubmitted_terms(),
        Version(2),
    )
    assert result.aggregate.offer_version.value == 2
    assert result.aggregate.revision == countered.revision.next()
    assert countered.offer_version.value == 1


def test_offer_rejects_false_simulation_and_bad_totals() -> None:
    with pytest.raises(DomainInvariantError) as exc:
        replace(parkdirect_terms(), simulation=False)
    assert exc.value.field == "simulation"
    with pytest.raises(DomainInvariantError) as exc:
        parkdirect_terms().price.__class__(
            parkdirect_terms().price.subtotal,
            parkdirect_terms().price.fees,
            parkdirect_terms().price.tax,
            parkdirect_terms().price.subtotal,
        )
    assert exc.value.field == "total_minor"
    with pytest.raises(DomainInvariantError) as exc:
        replace(parkdirect_terms(), evidence=())
    assert exc.value.field == "evidence"
