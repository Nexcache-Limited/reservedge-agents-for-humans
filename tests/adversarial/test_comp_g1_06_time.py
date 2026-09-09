"""COMP-G1-06 Phase 2: expiry cannot advance A3/A4; validity is not an inventory hold."""

from __future__ import annotations

import pytest

from itaa_application.cost_ledger_projection import (
    LedgerOfferInput,
    LedgerTaskInput,
    project_cost_ledger,
)
from itaa_domain.booking_task_states import (
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


def test_expired_and_superseded_tasks_cannot_select_or_authorize() -> None:
    expired = apply_booking_task_transition(
        BookingTaskState.OFFERS_READY, BookingTaskAction.EXPIRE_OFFERS, simulation=True
    )
    superseded = apply_booking_task_transition(
        BookingTaskState.OFFERS_READY, BookingTaskAction.SUPERSEDE, simulation=True
    )
    assert expired is BookingTaskState.OFFERS_EXPIRED
    assert superseded is BookingTaskState.SUPERSEDED
    with pytest.raises(InvalidTransitionError):
        apply_booking_task_transition(
            BookingTaskState.OFFERS_EXPIRED, BookingTaskAction.SELECT_OFFER, simulation=True
        )
    with pytest.raises(InvalidTransitionError):
        apply_booking_task_transition(
            BookingTaskState.SUPERSEDED, BookingTaskAction.SELECT_OFFER, simulation=True
        )
    assert (
        apply_booking_task_transition(
            BookingTaskState.OFFERS_EXPIRED,
            BookingTaskAction.MARK_A3_INELIGIBLE,
            simulation=True,
        )
        is BookingTaskState.A3_INELIGIBLE
    )
    assert (
        apply_booking_task_transition(
            BookingTaskState.SUPERSEDED, BookingTaskAction.MARK_A3_INELIGIBLE, simulation=True
        )
        is BookingTaskState.A3_INELIGIBLE
    )


def test_expired_amounts_belong_only_in_the_excluded_bucket() -> None:
    ledger = project_cost_ledger(
        "oi_01k2m3n4p5q6r7s8t9v0w1x2p1",
        "ld_01k2m3n4p5q6r7s8t9v0w1x2p3",
        (
            LedgerTaskInput(
                task_id="bt_01k2m3n4p5q6r7s8t9v0w1x2p4",
                state=BookingTaskState.OFFERS_READY,
                offers=(
                    LedgerOfferInput(
                        total_minor=14800,
                        tax_minor=1200,
                        fees_minor=300,
                        currency="USD",
                        validity="valid",
                        recommended=True,
                    ),
                    LedgerOfferInput(
                        total_minor=2100,
                        tax_minor=100,
                        fees_minor=0,
                        currency="USD",
                        validity="expired",
                    ),
                    LedgerOfferInput(
                        total_minor=900,
                        tax_minor=0,
                        fees_minor=0,
                        currency="USD",
                        validity="superseded",
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
    assert row["expiredExcludedMinor"] == 3000
    assert row["estimatedMinor"] == 14800
    assert row["authorizedSimulatedMinor"] == 0
    assert row["selectedNotAuthorizedMinor"] == 0
    assert row["confirmedBookingMinor"] == 0


def test_validity_never_implies_an_inventory_hold() -> None:
    parent = project_intent_state(
        overlay=ParentLifecycle.NONE,
        tasks=(
            TaskProjectionInput(
                membership=TaskMembership.ACCEPTED, state=BookingTaskState.OFFERS_EXPIRING
            ),
        ),
    )
    assert parent is IntentState.OFFERS_READY
    ledger = project_cost_ledger(
        "oi_01k2m3n4p5q6r7s8t9v0w1x2p1",
        "ld_01k2m3n4p5q6r7s8t9v0w1x2p3",
        (
            LedgerTaskInput(
                task_id="bt_01k2m3n4p5q6r7s8t9v0w1x2p4",
                state=BookingTaskState.OFFERS_EXPIRING,
                offers=(
                    LedgerOfferInput(
                        total_minor=14800,
                        tax_minor=1200,
                        fees_minor=300,
                        currency="USD",
                        validity="expiring",
                        recommended=True,
                    ),
                ),
            ),
        ),
        simulation=True,
    )
    hold_rows = ledger["rows"]
    assert isinstance(hold_rows, list)
    hold_row = hold_rows[0]
    assert isinstance(hold_row, dict)
    assert hold_row["depositsHoldsMinor"] == 0
    assert hold_row["payableNowMinor"] == 0
