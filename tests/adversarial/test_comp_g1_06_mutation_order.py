"""COMP-G1-06 Phase 2: parent and ledger projection must not depend on iteration order."""

from __future__ import annotations

from itertools import permutations

from itaa_application.cost_ledger_projection import (
    LedgerOfferInput,
    LedgerTaskInput,
    project_cost_ledger,
)
from itaa_domain.booking_task_states import BookingTaskState
from itaa_domain.intent_states import (
    IntentState,
    ParentLifecycle,
    TaskMembership,
    TaskProjectionInput,
    project_intent_state,
)


def test_shuffled_accepted_tasks_do_not_change_parent_state() -> None:
    tasks = (
        TaskProjectionInput(
            membership=TaskMembership.ACCEPTED, state=BookingTaskState.AUTHORIZED_SIMULATED
        ),
        TaskProjectionInput(
            membership=TaskMembership.ACCEPTED, state=BookingTaskState.OFFERS_READY
        ),
        TaskProjectionInput(membership=TaskMembership.PROPOSED, state=BookingTaskState.A1_REVIEW),
    )
    expected = project_intent_state(overlay=ParentLifecycle.NONE, tasks=tasks)
    assert expected is IntentState.PARTIALLY_AUTHORIZED_SIMULATED
    for order in permutations(tasks):
        assert project_intent_state(overlay=ParentLifecycle.NONE, tasks=order) is expected


def test_shuffled_ledger_inputs_do_not_change_rows_or_currencies() -> None:
    usd = LedgerTaskInput(
        task_id="bt_01k2m3n4p5q6r7s8t9v0w1x2p4",
        state=BookingTaskState.AUTHORIZED_SIMULATED,
        offers=(
            LedgerOfferInput(
                total_minor=16900,
                tax_minor=3400,
                fees_minor=0,
                currency="USD",
                validity="valid",
                selected=True,
                authorized=True,
            ),
            LedgerOfferInput(
                total_minor=2100,
                tax_minor=0,
                fees_minor=0,
                currency="USD",
                validity="expired",
            ),
        ),
    )
    gbp = LedgerTaskInput(
        task_id="bt_01k2m3n4p5q6r7s8t9v0w1x2p5",
        state=BookingTaskState.A3_REVIEW,
        offers=(
            LedgerOfferInput(
                total_minor=8900,
                tax_minor=800,
                fees_minor=0,
                currency="GBP",
                validity="valid",
                selected=True,
            ),
        ),
    )
    left = project_cost_ledger(
        "oi_01k2m3n4p5q6r7s8t9v0w1x2p1",
        "ld_01k2m3n4p5q6r7s8t9v0w1x2p3",
        (usd, gbp),
        simulation=True,
    )
    right = project_cost_ledger(
        "oi_01k2m3n4p5q6r7s8t9v0w1x2p1",
        "ld_01k2m3n4p5q6r7s8t9v0w1x2p3",
        (gbp, usd),
        simulation=True,
    )
    assert left["rows"] == right["rows"]
    assert left["currencies"] == right["currencies"] == ["GBP", "USD"]
    assert "fx" not in left
    assert "totalMinor" not in left
    assert "combinedMinor" not in left
    assert "scoreMicros" not in left
