"""COMP-G1-06 Phase 2: A4 is not a Booking; simulation never enters live states."""

from __future__ import annotations

import pytest

from itaa_application.cost_ledger_projection import (
    LedgerOfferInput,
    LedgerTaskInput,
    project_cost_ledger,
)
from itaa_domain.booking_task_states import (
    LIVE_ONLY_STATES,
    BookingTaskAction,
    BookingTaskState,
    apply_booking_task_transition,
)
from itaa_domain.errors import InvalidTransitionError
from itaa_domain.intent_states import (
    IntentState,
    ParentLifecycle,
    TaskMembership,
    TaskProjectionInput,
    project_intent_state,
)


def test_authorized_simulated_alone_is_completed_simulated_not_a_booking() -> None:
    parent = project_intent_state(
        overlay=ParentLifecycle.NONE,
        tasks=(
            TaskProjectionInput(
                membership=TaskMembership.ACCEPTED,
                state=BookingTaskState.AUTHORIZED_SIMULATED,
            ),
        ),
    )
    assert parent is IntentState.COMPLETED_SIMULATED
    assert parent.value != IntentState.PARTIALLY_BOOKED.value
    assert parent.value != IntentState.COMPLETED.value


def test_simulation_rejects_every_live_only_destination() -> None:
    assert BookingTaskState.AUTHORIZED_LIVE in LIVE_ONLY_STATES
    assert BookingTaskState.BOOKING_PENDING in LIVE_ONLY_STATES
    assert BookingTaskState.CONFIRMED_BOOKING in LIVE_ONLY_STATES
    assert BookingTaskState.BOOKING_FAILED in LIVE_ONLY_STATES
    for action in (
        BookingTaskAction.AUTHORIZE_LIVE,
        BookingTaskAction.START_BOOKING,
        BookingTaskAction.CONFIRM_BOOKING,
        BookingTaskAction.FAIL_BOOKING,
    ):
        current = BookingTaskState.A4_REQUIRED
        if action is BookingTaskAction.START_BOOKING:
            current = BookingTaskState.AUTHORIZED_LIVE
        if action in {BookingTaskAction.CONFIRM_BOOKING, BookingTaskAction.FAIL_BOOKING}:
            current = BookingTaskState.BOOKING_PENDING
        with pytest.raises(InvalidTransitionError):
            apply_booking_task_transition(current, action, simulation=True)


def test_a4_failed_is_distinct_from_booking_failed() -> None:
    failed_auth = apply_booking_task_transition(
        BookingTaskState.A4_REQUIRED, BookingTaskAction.FAIL_A4, simulation=True
    )
    assert failed_auth is BookingTaskState.A4_FAILED
    assert failed_auth.value != BookingTaskState.BOOKING_FAILED.value


def test_simulation_ledger_never_writes_confirmed_booking() -> None:
    ledger = project_cost_ledger(
        "oi_01k2m3n4p5q6r7s8t9v0w1x2p1",
        "ld_01k2m3n4p5q6r7s8t9v0w1x2p3",
        (
            LedgerTaskInput(
                task_id="bt_01k2m3n4p5q6r7s8t9v0w1x2p4",
                state=BookingTaskState.AUTHORIZED_SIMULATED,
                offers=(
                    LedgerOfferInput(
                        total_minor=14800,
                        tax_minor=1200,
                        fees_minor=300,
                        currency="USD",
                        validity="valid",
                        selected=True,
                        authorized=True,
                    ),
                ),
            ),
        ),
        simulation=True,
    )
    rows = ledger["rows"]
    assert isinstance(rows, list)
    row = rows[0]
    assert isinstance(row, dict)
    assert row["confirmedBookingMinor"] == 0
    assert row["authorizedLiveMinor"] == 0
    assert row["bookingPendingMinor"] == 0
    assert row["depositsHoldsMinor"] == 0
    assert row["payableNowMinor"] == 0
    assert row["payableLaterMinor"] == 0
    assert row["authorizedSimulatedMinor"] == 14800
    assert "scoreMicros" not in row
    assert "scoreMicros" not in ledger
