"""Pure IntentPlan projection. Membership stays on PlanTaskInput."""

from __future__ import annotations

from dataclasses import dataclass

from itaa_domain.booking_task_states import OFFER_READY_STATES, BookingTaskState
from itaa_domain.intent_states import TaskMembership


@dataclass(frozen=True, slots=True)
class PlanTaskInput:
    task_id: str
    membership: TaskMembership
    state: BookingTaskState


def project_plan(
    intent_id: str,
    plan_id: str,
    tasks: tuple[PlanTaskInput, ...],
) -> dict[str, object]:
    accepted_offer_ready = sum(
        1
        for item in tasks
        if item.membership is TaskMembership.ACCEPTED and item.state in OFFER_READY_STATES
    )
    return {
        "schemaVersion": "1.0",
        "planId": plan_id,
        "intentId": intent_id,
        "taskIds": [item.task_id for item in tasks],
        "combinedRecommendationsEligible": accepted_offer_ready >= 2,
    }
