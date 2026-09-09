"""Parent Intent state derivation from accepted Booking Tasks."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from itaa_domain.booking_task_states import (
    ATTENTION_STATES,
    IN_PROGRESS_STATES,
    OFFER_READY_STATES,
    SIMULATION_TERMINAL_STATES,
    BookingTaskState,
)


class IntentState(StrEnum):
    DRAFT = "draft"
    CLARIFYING = "clarifying"
    PLANNING = "planning"
    DELETED = "deleted"
    ATTENTION = "attention"
    IN_PROGRESS = "in_progress"
    OFFERS_READY = "offers_ready"
    PARTIALLY_AUTHORIZED_SIMULATED = "partially_authorized_simulated"
    PARTIALLY_AUTHORIZED_LIVE = "partially_authorized_live"
    PARTIALLY_BOOKED = "partially_booked"
    COMPLETED_SIMULATED = "completed_simulated"
    COMPLETED = "completed"
    PAUSED = "paused"
    CANCELLED = "cancelled"
    FAILED = "failed"


class ParentLifecycle(StrEnum):
    DELETED = "deleted"
    PAUSED = "paused"
    CANCELLED = "cancelled"
    NONE = "none"


class TaskMembership(StrEnum):
    PROPOSED = "proposed"
    ACCEPTED = "accepted"


@dataclass(frozen=True, slots=True)
class TaskProjectionInput:
    membership: TaskMembership
    state: BookingTaskState


_LIVE_AUTH_STATES: frozenset[BookingTaskState] = frozenset(
    {
        BookingTaskState.AUTHORIZED_LIVE,
        BookingTaskState.BOOKING_PENDING,
    }
)
_LIVE_COMPLETION_TERMINAL: frozenset[BookingTaskState] = frozenset(
    {
        BookingTaskState.CONFIRMED_BOOKING,
        BookingTaskState.CANCELLED,
        BookingTaskState.FAILED,
        BookingTaskState.BOOKING_FAILED,
    }
)
_FAILED_OR_CANCELLED: frozenset[BookingTaskState] = frozenset(
    {
        BookingTaskState.FAILED,
        BookingTaskState.CANCELLED,
    }
)


def project_intent_state(
    *,
    overlay: ParentLifecycle,
    tasks: tuple[TaskProjectionInput, ...],
    clarifying: bool = False,
) -> IntentState:
    if overlay is ParentLifecycle.DELETED:
        return IntentState.DELETED
    if overlay is ParentLifecycle.PAUSED:
        return IntentState.PAUSED
    if overlay is ParentLifecycle.CANCELLED:
        return IntentState.CANCELLED

    accepted = tuple(item for item in tasks if item.membership is TaskMembership.ACCEPTED)
    if not accepted:
        if clarifying:
            return IntentState.CLARIFYING
        return IntentState.DRAFT

    states = tuple(item.state for item in accepted)
    present = frozenset(states)

    if all(state in _FAILED_OR_CANCELLED for state in states) and any(
        state is BookingTaskState.FAILED for state in states
    ):
        return IntentState.FAILED

    if all(state in _LIVE_COMPLETION_TERMINAL for state in states) and any(
        state is BookingTaskState.CONFIRMED_BOOKING for state in states
    ):
        return IntentState.COMPLETED

    if (
        all(state in SIMULATION_TERMINAL_STATES for state in states)
        and BookingTaskState.CONFIRMED_BOOKING not in present
        and present.isdisjoint(_LIVE_AUTH_STATES)
        and BookingTaskState.BOOKING_FAILED not in present
    ):
        return IntentState.COMPLETED_SIMULATED

    if any(state is BookingTaskState.CONFIRMED_BOOKING for state in states) and any(
        state not in _LIVE_COMPLETION_TERMINAL for state in states
    ):
        return IntentState.PARTIALLY_BOOKED

    if any(state in _LIVE_AUTH_STATES for state in states) and (
        BookingTaskState.CONFIRMED_BOOKING not in present
    ):
        return IntentState.PARTIALLY_AUTHORIZED_LIVE

    if (
        any(state is BookingTaskState.AUTHORIZED_SIMULATED for state in states)
        and any(state not in SIMULATION_TERMINAL_STATES for state in states)
        and present.isdisjoint(_LIVE_AUTH_STATES)
        and BookingTaskState.CONFIRMED_BOOKING not in present
    ):
        return IntentState.PARTIALLY_AUTHORIZED_SIMULATED

    if any(state in ATTENTION_STATES for state in states):
        return IntentState.ATTENTION

    if any(state in OFFER_READY_STATES for state in states):
        return IntentState.OFFERS_READY

    if any(
        state in IN_PROGRESS_STATES or state is BookingTaskState.OFFERS_EXPIRED for state in states
    ):
        return IntentState.IN_PROGRESS

    return IntentState.PLANNING
