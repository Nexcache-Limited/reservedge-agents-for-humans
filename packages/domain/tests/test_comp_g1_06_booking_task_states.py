from __future__ import annotations

import pytest

from itaa_domain.booking_task_states import (
    ATTENTION_STATES,
    IN_PROGRESS_STATES,
    LIVE_ONLY_STATES,
    OFFER_READY_STATES,
    SIMULATION_FORBIDDEN_STATES,
    SIMULATION_TERMINAL_STATES,
    BookingTaskAction,
    BookingTaskState,
    apply_booking_task_transition,
)
from itaa_domain.errors import InvalidTransitionError

CONTRACT_STATES = {
    "proposed",
    "missing_details",
    "a1_review",
    "a1_blocked",
    "public_research",
    "a2_required",
    "researching",
    "supplier_timeout",
    "no_offer",
    "offers_ready",
    "offers_expiring",
    "offers_expired",
    "superseded",
    "a3_review",
    "a3_ineligible",
    "a4_required",
    "a4_failed",
    "authorized_simulated",
    "authorized_live",
    "booking_pending",
    "confirmed_booking",
    "booking_failed",
    "paused",
    "cancelled",
    "failed",
    "offline_readonly",
}


def test_booking_task_state_has_every_contract_value() -> None:
    assert {item.value for item in BookingTaskState} == CONTRACT_STATES
    assert len(CONTRACT_STATES) == 26
    assert len(BookingTaskState) == len(CONTRACT_STATES)


def test_published_state_sets() -> None:
    assert SIMULATION_FORBIDDEN_STATES == LIVE_ONLY_STATES
    assert {item.value for item in LIVE_ONLY_STATES} == {
        "authorized_live",
        "booking_pending",
        "confirmed_booking",
        "booking_failed",
    }
    assert {item.value for item in ATTENTION_STATES} == {
        "missing_details",
        "a1_review",
        "a1_blocked",
        "a2_required",
        "a3_review",
        "a3_ineligible",
        "a4_required",
        "a4_failed",
    }
    assert {item.value for item in OFFER_READY_STATES} == {"offers_ready", "offers_expiring"}
    assert {item.value for item in IN_PROGRESS_STATES} == {
        "public_research",
        "researching",
        "supplier_timeout",
        "no_offer",
        "superseded",
    }
    assert {item.value for item in SIMULATION_TERMINAL_STATES} == {
        "authorized_simulated",
        "cancelled",
        "failed",
    }


def test_simulation_happy_path_never_becomes_a_booking() -> None:
    state = BookingTaskState.PROPOSED
    state = apply_booking_task_transition(
        state, BookingTaskAction.ACCEPT_A1_REVIEW, simulation=True
    )
    state = apply_booking_task_transition(state, BookingTaskAction.CONFIRM_A1, simulation=True)
    state = apply_booking_task_transition(state, BookingTaskAction.APPROVE_A2, simulation=True)
    state = apply_booking_task_transition(state, BookingTaskAction.RECEIVE_OFFERS, simulation=True)
    state = apply_booking_task_transition(state, BookingTaskAction.SELECT_OFFER, simulation=True)
    state = apply_booking_task_transition(state, BookingTaskAction.BIND_A3, simulation=True)
    assert state is BookingTaskState.A4_REQUIRED
    authorized = apply_booking_task_transition(
        state, BookingTaskAction.AUTHORIZE_SIMULATED, simulation=True
    )
    assert authorized is BookingTaskState.AUTHORIZED_SIMULATED
    assert authorized is not BookingTaskState.CONFIRMED_BOOKING
    assert authorized not in LIVE_ONLY_STATES


def test_a4_failed_is_distinct_from_booking_failed_and_can_retry() -> None:
    failed = apply_booking_task_transition(
        BookingTaskState.A4_REQUIRED, BookingTaskAction.FAIL_A4, simulation=True
    )
    assert failed is BookingTaskState.A4_FAILED
    assert failed is not BookingTaskState.BOOKING_FAILED
    retried = apply_booking_task_transition(failed, BookingTaskAction.RETRY_A4, simulation=True)
    assert retried is BookingTaskState.A4_REQUIRED


@pytest.mark.parametrize(
    ("current", "action"),
    [
        (BookingTaskState.A4_REQUIRED, BookingTaskAction.AUTHORIZE_LIVE),
        (BookingTaskState.AUTHORIZED_LIVE, BookingTaskAction.START_BOOKING),
        (BookingTaskState.BOOKING_PENDING, BookingTaskAction.CONFIRM_BOOKING),
        (BookingTaskState.BOOKING_PENDING, BookingTaskAction.FAIL_BOOKING),
    ],
)
def test_simulation_rejects_live_only_destinations(
    current: BookingTaskState, action: BookingTaskAction
) -> None:
    with pytest.raises(InvalidTransitionError) as caught:
        apply_booking_task_transition(current, action, simulation=True)
    assert caught.value.current_state == current.value
    assert caught.value.attempted_action == action.value
    live = apply_booking_task_transition(current, action, simulation=False)
    assert live in LIVE_ONLY_STATES


def test_illegal_simulation_transition_raises() -> None:
    with pytest.raises(InvalidTransitionError):
        apply_booking_task_transition(
            BookingTaskState.PROPOSED, BookingTaskAction.AUTHORIZE_SIMULATED, simulation=True
        )
    with pytest.raises(InvalidTransitionError):
        apply_booking_task_transition(
            BookingTaskState.OFFERS_EXPIRED, BookingTaskAction.SELECT_OFFER, simulation=True
        )


def test_expired_and_superseded_cannot_select() -> None:
    ineligible = apply_booking_task_transition(
        BookingTaskState.OFFERS_EXPIRED, BookingTaskAction.MARK_A3_INELIGIBLE, simulation=True
    )
    assert ineligible is BookingTaskState.A3_INELIGIBLE
    with pytest.raises(InvalidTransitionError):
        apply_booking_task_transition(
            BookingTaskState.A3_INELIGIBLE, BookingTaskAction.BIND_A3, simulation=True
        )


def test_live_states_exist_for_parent_fixtures() -> None:
    assert BookingTaskState.CONFIRMED_BOOKING.value == "confirmed_booking"
    assert BookingTaskState.AUTHORIZED_LIVE in LIVE_ONLY_STATES
