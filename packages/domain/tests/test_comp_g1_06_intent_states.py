from __future__ import annotations

from itertools import permutations

import pytest

from itaa_domain.booking_task_states import BookingTaskState
from itaa_domain.errors import DomainInvariantError
from itaa_domain.identifiers import (
    BookingTaskId,
    IntentId,
    LedgerId,
    OrchestrationIntentId,
    PlanId,
)
from itaa_domain.intent_states import (
    IntentState,
    ParentLifecycle,
    TaskMembership,
    TaskProjectionInput,
    project_intent_state,
)

BODY = "01k2m3n4p5q6r7s8t9v0w1x2y3"


def _accepted(*states: BookingTaskState) -> tuple[TaskProjectionInput, ...]:
    return tuple(TaskProjectionInput(TaskMembership.ACCEPTED, state) for state in states)


def _project(
    *states: BookingTaskState,
    overlay: ParentLifecycle = ParentLifecycle.NONE,
    clarifying: bool = False,
) -> IntentState:
    return project_intent_state(overlay=overlay, tasks=_accepted(*states), clarifying=clarifying)


def test_new_identifier_prefixes_and_intent_id_unchanged() -> None:
    assert IntentId("pi_" + BODY).to_primitive() == "pi_" + BODY
    assert OrchestrationIntentId("oi_" + BODY).to_primitive() == "oi_" + BODY
    assert BookingTaskId("bt_" + BODY).to_primitive() == "bt_" + BODY
    assert PlanId("pl_" + BODY).to_primitive() == "pl_" + BODY
    assert LedgerId("ld_" + BODY).to_primitive() == "ld_" + BODY
    with pytest.raises(DomainInvariantError) as caught:
        OrchestrationIntentId("pi_" + BODY)
    assert caught.value.field == "orchestration_intent_id"
    assert "oi_" not in str(caught.value) or caught.value.code == "invalid_opaque_syntax"


def test_intent_state_has_the_fifteen_contract_values() -> None:
    assert {item.value for item in IntentState} == {
        "draft",
        "clarifying",
        "planning",
        "deleted",
        "attention",
        "in_progress",
        "offers_ready",
        "partially_authorized_simulated",
        "partially_authorized_live",
        "partially_booked",
        "completed_simulated",
        "completed",
        "paused",
        "cancelled",
        "failed",
    }


@pytest.mark.parametrize(
    ("overlay", "expected"),
    [
        (ParentLifecycle.DELETED, IntentState.DELETED),
        (ParentLifecycle.PAUSED, IntentState.PAUSED),
        (ParentLifecycle.CANCELLED, IntentState.CANCELLED),
    ],
)
@pytest.mark.parametrize(
    "child",
    [
        BookingTaskState.A1_REVIEW,
        BookingTaskState.OFFERS_READY,
        BookingTaskState.AUTHORIZED_SIMULATED,
        BookingTaskState.CONFIRMED_BOOKING,
        BookingTaskState.FAILED,
    ],
)
def test_overlay_is_never_overwritten_by_children(
    overlay: ParentLifecycle, expected: IntentState, child: BookingTaskState
) -> None:
    assert _project(child, overlay=overlay) is expected
    assert (
        project_intent_state(
            overlay=overlay,
            tasks=(
                TaskProjectionInput(TaskMembership.PROPOSED, BookingTaskState.OFFERS_READY),
                TaskProjectionInput(TaskMembership.ACCEPTED, child),
            ),
        )
        is expected
    )


def test_proposed_tasks_are_ignored() -> None:
    proposed = TaskProjectionInput(TaskMembership.PROPOSED, BookingTaskState.OFFERS_READY)
    assert project_intent_state(overlay=ParentLifecycle.NONE, tasks=(proposed,)) is (
        IntentState.DRAFT
    )
    accepted = TaskProjectionInput(TaskMembership.ACCEPTED, BookingTaskState.A1_REVIEW)
    assert (
        project_intent_state(overlay=ParentLifecycle.NONE, tasks=(proposed, accepted))
        is IntentState.ATTENTION
    )


def test_empty_accepted_is_draft_unless_clarifying() -> None:
    assert project_intent_state(overlay=ParentLifecycle.NONE, tasks=()) is IntentState.DRAFT
    assert (
        project_intent_state(overlay=ParentLifecycle.NONE, tasks=(), clarifying=True)
        is IntentState.CLARIFYING
    )
    assert (
        project_intent_state(overlay=ParentLifecycle.NONE, tasks=(), clarifying=False)
        is IntentState.DRAFT
    )


def test_a4_only_is_completed_simulated_never_booking() -> None:
    assert _project(BookingTaskState.AUTHORIZED_SIMULATED) is IntentState.COMPLETED_SIMULATED
    assert _project(BookingTaskState.AUTHORIZED_SIMULATED) is not IntentState.COMPLETED
    assert _project(BookingTaskState.AUTHORIZED_SIMULATED) is not IntentState.PARTIALLY_BOOKED
    assert _project(BookingTaskState.AUTHORIZED_SIMULATED) is not (
        IntentState.PARTIALLY_AUTHORIZED_SIMULATED
    )


@pytest.mark.parametrize(
    ("states", "expected"),
    [
        ((BookingTaskState.FAILED,), IntentState.FAILED),
        ((BookingTaskState.FAILED, BookingTaskState.CANCELLED), IntentState.FAILED),
        ((BookingTaskState.CANCELLED, BookingTaskState.FAILED), IntentState.FAILED),
        (
            (BookingTaskState.CANCELLED, BookingTaskState.AUTHORIZED_SIMULATED),
            IntentState.COMPLETED_SIMULATED,
        ),
        ((BookingTaskState.CANCELLED,), IntentState.COMPLETED_SIMULATED),
        (
            (BookingTaskState.CONFIRMED_BOOKING, BookingTaskState.CANCELLED),
            IntentState.COMPLETED,
        ),
        ((BookingTaskState.CONFIRMED_BOOKING,), IntentState.COMPLETED),
        (
            (BookingTaskState.CONFIRMED_BOOKING, BookingTaskState.A1_REVIEW),
            IntentState.PARTIALLY_BOOKED,
        ),
        (
            (BookingTaskState.CONFIRMED_BOOKING, BookingTaskState.AUTHORIZED_LIVE),
            IntentState.PARTIALLY_BOOKED,
        ),
        ((BookingTaskState.AUTHORIZED_LIVE,), IntentState.PARTIALLY_AUTHORIZED_LIVE),
        (
            (BookingTaskState.BOOKING_PENDING, BookingTaskState.AUTHORIZED_SIMULATED),
            IntentState.PARTIALLY_AUTHORIZED_LIVE,
        ),
        (
            (BookingTaskState.AUTHORIZED_SIMULATED, BookingTaskState.A1_REVIEW),
            IntentState.PARTIALLY_AUTHORIZED_SIMULATED,
        ),
        (
            (BookingTaskState.AUTHORIZED_SIMULATED, BookingTaskState.OFFERS_READY),
            IntentState.PARTIALLY_AUTHORIZED_SIMULATED,
        ),
        ((BookingTaskState.A1_REVIEW,), IntentState.ATTENTION),
        ((BookingTaskState.A2_REQUIRED,), IntentState.ATTENTION),
        ((BookingTaskState.A4_REQUIRED,), IntentState.ATTENTION),
        ((BookingTaskState.A4_FAILED,), IntentState.ATTENTION),
        ((BookingTaskState.MISSING_DETAILS,), IntentState.ATTENTION),
        ((BookingTaskState.A3_REVIEW,), IntentState.ATTENTION),
        ((BookingTaskState.A3_INELIGIBLE,), IntentState.ATTENTION),
        ((BookingTaskState.OFFERS_READY,), IntentState.OFFERS_READY),
        ((BookingTaskState.OFFERS_EXPIRING,), IntentState.OFFERS_READY),
        (
            (BookingTaskState.OFFERS_READY, BookingTaskState.RESEARCHING),
            IntentState.OFFERS_READY,
        ),
        ((BookingTaskState.RESEARCHING,), IntentState.IN_PROGRESS),
        ((BookingTaskState.PUBLIC_RESEARCH,), IntentState.IN_PROGRESS),
        ((BookingTaskState.SUPPLIER_TIMEOUT,), IntentState.IN_PROGRESS),
        ((BookingTaskState.NO_OFFER,), IntentState.IN_PROGRESS),
        ((BookingTaskState.SUPERSEDED,), IntentState.IN_PROGRESS),
        ((BookingTaskState.OFFERS_EXPIRED,), IntentState.IN_PROGRESS),
        ((BookingTaskState.PAUSED,), IntentState.PLANNING),
        ((BookingTaskState.OFFLINE_READONLY,), IntentState.PLANNING),
    ],
)
def test_every_valid_parent_derivation(
    states: tuple[BookingTaskState, ...], expected: IntentState
) -> None:
    assert _project(*states) is expected


def test_shuffled_task_order_does_not_change_parent_state() -> None:
    mix = (
        BookingTaskState.AUTHORIZED_SIMULATED,
        BookingTaskState.A1_REVIEW,
        BookingTaskState.OFFERS_READY,
    )
    expected = IntentState.PARTIALLY_AUTHORIZED_SIMULATED
    for order in permutations(mix):
        assert _project(*order) is expected
    failed_mix = (BookingTaskState.FAILED, BookingTaskState.CANCELLED, BookingTaskState.FAILED)
    for order in set(permutations(failed_mix)):
        assert _project(*order) is IntentState.FAILED


def test_attention_does_not_outrank_partial_authorization() -> None:
    assert (
        _project(BookingTaskState.A4_REQUIRED, BookingTaskState.AUTHORIZED_SIMULATED)
        is IntentState.PARTIALLY_AUTHORIZED_SIMULATED
    )
