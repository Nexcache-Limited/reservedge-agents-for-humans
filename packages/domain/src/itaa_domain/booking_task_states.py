"""Booking Task states and the simulation-safe transition graph."""

from __future__ import annotations

from enum import StrEnum

from itaa_domain.errors import InvalidTransitionError
from itaa_domain.protocol import permitted_actions


class BookingTaskState(StrEnum):
    PROPOSED = "proposed"
    MISSING_DETAILS = "missing_details"
    A1_REVIEW = "a1_review"
    A1_BLOCKED = "a1_blocked"
    PUBLIC_RESEARCH = "public_research"
    A2_REQUIRED = "a2_required"
    RESEARCHING = "researching"
    SUPPLIER_TIMEOUT = "supplier_timeout"
    NO_OFFER = "no_offer"
    OFFERS_READY = "offers_ready"
    OFFERS_EXPIRING = "offers_expiring"
    OFFERS_EXPIRED = "offers_expired"
    SUPERSEDED = "superseded"
    A3_REVIEW = "a3_review"
    A3_INELIGIBLE = "a3_ineligible"
    A4_REQUIRED = "a4_required"
    A4_FAILED = "a4_failed"
    AUTHORIZED_SIMULATED = "authorized_simulated"
    AUTHORIZED_LIVE = "authorized_live"
    BOOKING_PENDING = "booking_pending"
    CONFIRMED_BOOKING = "confirmed_booking"
    BOOKING_FAILED = "booking_failed"
    PAUSED = "paused"
    CANCELLED = "cancelled"
    FAILED = "failed"
    OFFLINE_READONLY = "offline_readonly"


class BookingTaskAction(StrEnum):
    ACCEPT_MISSING_DETAILS = "accept_missing_details"
    ACCEPT_A1_REVIEW = "accept_a1_review"
    PROVIDE_DETAILS = "provide_details"
    CONFIRM_A1 = "confirm_a1"
    BLOCK_A1 = "block_a1"
    APPROVE_A2 = "approve_a2"
    START_PUBLIC_RESEARCH = "start_public_research"
    RECEIVE_OFFERS = "receive_offers"
    TIMEOUT_SUPPLIERS = "timeout_suppliers"
    RECORD_NO_OFFER = "record_no_offer"
    MARK_EXPIRING = "mark_expiring"
    EXPIRE_OFFERS = "expire_offers"
    SELECT_OFFER = "select_offer"
    BIND_A3 = "bind_a3"
    MARK_A3_INELIGIBLE = "mark_a3_ineligible"
    FAIL_A4 = "fail_a4"
    AUTHORIZE_SIMULATED = "authorize_simulated"
    RETRY_A4 = "retry_a4"
    AUTHORIZE_LIVE = "authorize_live"
    START_BOOKING = "start_booking"
    CONFIRM_BOOKING = "confirm_booking"
    FAIL_BOOKING = "fail_booking"
    CANCEL = "cancel"
    FAIL = "fail"
    PAUSE = "pause"
    SUPERSEDE = "supersede"
    MARK_OFFLINE = "mark_offline"


LIVE_ONLY_STATES: frozenset[BookingTaskState] = frozenset(
    {
        BookingTaskState.AUTHORIZED_LIVE,
        BookingTaskState.BOOKING_PENDING,
        BookingTaskState.CONFIRMED_BOOKING,
        BookingTaskState.BOOKING_FAILED,
    }
)
SIMULATION_FORBIDDEN_STATES: frozenset[BookingTaskState] = LIVE_ONLY_STATES

ATTENTION_STATES: frozenset[BookingTaskState] = frozenset(
    {
        BookingTaskState.MISSING_DETAILS,
        BookingTaskState.A1_REVIEW,
        BookingTaskState.A1_BLOCKED,
        BookingTaskState.A2_REQUIRED,
        BookingTaskState.A3_REVIEW,
        BookingTaskState.A3_INELIGIBLE,
        BookingTaskState.A4_REQUIRED,
        BookingTaskState.A4_FAILED,
    }
)
OFFER_READY_STATES: frozenset[BookingTaskState] = frozenset(
    {
        BookingTaskState.OFFERS_READY,
        BookingTaskState.OFFERS_EXPIRING,
    }
)
IN_PROGRESS_STATES: frozenset[BookingTaskState] = frozenset(
    {
        BookingTaskState.PUBLIC_RESEARCH,
        BookingTaskState.RESEARCHING,
        BookingTaskState.SUPPLIER_TIMEOUT,
        BookingTaskState.NO_OFFER,
        BookingTaskState.SUPERSEDED,
    }
)
SIMULATION_TERMINAL_STATES: frozenset[BookingTaskState] = frozenset(
    {
        BookingTaskState.AUTHORIZED_SIMULATED,
        BookingTaskState.CANCELLED,
        BookingTaskState.FAILED,
    }
)

BOOKING_TASK_TRANSITIONS: dict[tuple[BookingTaskState, BookingTaskAction], BookingTaskState] = {
    (BookingTaskState.PROPOSED, BookingTaskAction.ACCEPT_MISSING_DETAILS): (
        BookingTaskState.MISSING_DETAILS
    ),
    (BookingTaskState.PROPOSED, BookingTaskAction.ACCEPT_A1_REVIEW): BookingTaskState.A1_REVIEW,
    (BookingTaskState.MISSING_DETAILS, BookingTaskAction.PROVIDE_DETAILS): (
        BookingTaskState.A1_REVIEW
    ),
    (BookingTaskState.A1_REVIEW, BookingTaskAction.CONFIRM_A1): BookingTaskState.A2_REQUIRED,
    (BookingTaskState.A1_REVIEW, BookingTaskAction.BLOCK_A1): BookingTaskState.A1_BLOCKED,
    (BookingTaskState.A1_BLOCKED, BookingTaskAction.PROVIDE_DETAILS): BookingTaskState.A1_REVIEW,
    (BookingTaskState.A1_REVIEW, BookingTaskAction.START_PUBLIC_RESEARCH): (
        BookingTaskState.PUBLIC_RESEARCH
    ),
    (BookingTaskState.A2_REQUIRED, BookingTaskAction.APPROVE_A2): BookingTaskState.RESEARCHING,
    (BookingTaskState.A2_REQUIRED, BookingTaskAction.START_PUBLIC_RESEARCH): (
        BookingTaskState.PUBLIC_RESEARCH
    ),
    (BookingTaskState.RESEARCHING, BookingTaskAction.RECEIVE_OFFERS): BookingTaskState.OFFERS_READY,
    (BookingTaskState.RESEARCHING, BookingTaskAction.TIMEOUT_SUPPLIERS): (
        BookingTaskState.SUPPLIER_TIMEOUT
    ),
    (BookingTaskState.RESEARCHING, BookingTaskAction.RECORD_NO_OFFER): BookingTaskState.NO_OFFER,
    (BookingTaskState.OFFERS_READY, BookingTaskAction.MARK_EXPIRING): (
        BookingTaskState.OFFERS_EXPIRING
    ),
    (BookingTaskState.OFFERS_READY, BookingTaskAction.EXPIRE_OFFERS): (
        BookingTaskState.OFFERS_EXPIRED
    ),
    (BookingTaskState.OFFERS_EXPIRING, BookingTaskAction.EXPIRE_OFFERS): (
        BookingTaskState.OFFERS_EXPIRED
    ),
    (BookingTaskState.OFFERS_READY, BookingTaskAction.SELECT_OFFER): BookingTaskState.A3_REVIEW,
    (BookingTaskState.OFFERS_EXPIRING, BookingTaskAction.SELECT_OFFER): BookingTaskState.A3_REVIEW,
    (BookingTaskState.OFFERS_EXPIRED, BookingTaskAction.MARK_A3_INELIGIBLE): (
        BookingTaskState.A3_INELIGIBLE
    ),
    (BookingTaskState.SUPERSEDED, BookingTaskAction.MARK_A3_INELIGIBLE): (
        BookingTaskState.A3_INELIGIBLE
    ),
    (BookingTaskState.A3_REVIEW, BookingTaskAction.BIND_A3): BookingTaskState.A4_REQUIRED,
    (BookingTaskState.A4_REQUIRED, BookingTaskAction.FAIL_A4): BookingTaskState.A4_FAILED,
    (BookingTaskState.A4_REQUIRED, BookingTaskAction.AUTHORIZE_SIMULATED): (
        BookingTaskState.AUTHORIZED_SIMULATED
    ),
    (BookingTaskState.A4_FAILED, BookingTaskAction.RETRY_A4): BookingTaskState.A4_REQUIRED,
    (BookingTaskState.A4_REQUIRED, BookingTaskAction.AUTHORIZE_LIVE): (
        BookingTaskState.AUTHORIZED_LIVE
    ),
    (BookingTaskState.AUTHORIZED_LIVE, BookingTaskAction.START_BOOKING): (
        BookingTaskState.BOOKING_PENDING
    ),
    (BookingTaskState.BOOKING_PENDING, BookingTaskAction.CONFIRM_BOOKING): (
        BookingTaskState.CONFIRMED_BOOKING
    ),
    (BookingTaskState.BOOKING_PENDING, BookingTaskAction.FAIL_BOOKING): (
        BookingTaskState.BOOKING_FAILED
    ),
    (BookingTaskState.A1_REVIEW, BookingTaskAction.CANCEL): BookingTaskState.CANCELLED,
    (BookingTaskState.A2_REQUIRED, BookingTaskAction.CANCEL): BookingTaskState.CANCELLED,
    (BookingTaskState.OFFERS_READY, BookingTaskAction.CANCEL): BookingTaskState.CANCELLED,
    (BookingTaskState.A3_REVIEW, BookingTaskAction.CANCEL): BookingTaskState.CANCELLED,
    (BookingTaskState.A4_REQUIRED, BookingTaskAction.CANCEL): BookingTaskState.CANCELLED,
    (BookingTaskState.RESEARCHING, BookingTaskAction.FAIL): BookingTaskState.FAILED,
    (BookingTaskState.A4_REQUIRED, BookingTaskAction.FAIL): BookingTaskState.FAILED,
    (BookingTaskState.OFFERS_READY, BookingTaskAction.PAUSE): BookingTaskState.PAUSED,
    (BookingTaskState.A2_REQUIRED, BookingTaskAction.PAUSE): BookingTaskState.PAUSED,
    (BookingTaskState.OFFERS_READY, BookingTaskAction.SUPERSEDE): BookingTaskState.SUPERSEDED,
    (BookingTaskState.A3_REVIEW, BookingTaskAction.SUPERSEDE): BookingTaskState.SUPERSEDED,
    (BookingTaskState.A4_REQUIRED, BookingTaskAction.SUPERSEDE): BookingTaskState.SUPERSEDED,
    (BookingTaskState.OFFERS_READY, BookingTaskAction.MARK_OFFLINE): (
        BookingTaskState.OFFLINE_READONLY
    ),
}


def apply_booking_task_transition(
    current: BookingTaskState,
    action: BookingTaskAction,
    *,
    simulation: bool,
) -> BookingTaskState:
    destination = BOOKING_TASK_TRANSITIONS.get((current, action))
    permitted = permitted_actions(BOOKING_TASK_TRANSITIONS, current)
    if simulation:
        permitted = tuple(
            name
            for name in permitted
            if BOOKING_TASK_TRANSITIONS[(current, BookingTaskAction(name))]
            not in SIMULATION_FORBIDDEN_STATES
        )
    if destination is None:
        raise InvalidTransitionError(
            resource_type="booking_task",
            resource_id="",
            current_state=current.value,
            attempted_action=action.value,
            permitted_actions=permitted,
        )
    if simulation and destination in SIMULATION_FORBIDDEN_STATES:
        raise InvalidTransitionError(
            resource_type="booking_task",
            resource_id="",
            current_state=current.value,
            attempted_action=action.value,
            permitted_actions=permitted,
        )
    return destination
