"""Buyer-safe agent activity kinds. Not WP-07 ProgressEventKind."""

from __future__ import annotations

from typing import Literal

ActivityKind = Literal[
    "OBJECTIVE_RECEIVED",
    "CHECKING_MISSING",
    "CLARIFICATION_READY",
    "PLAN_UPDATING",
    "PLAN_READY",
    "PLAN_CONFIRMED",
    "PARKING_RESEARCHING",
    "OFFERS_COMPARING",
    "RECOMMENDATION_PREPARING",
    "AWAITING_HUMAN_APPROVAL",
    "FALLBACK_DETERMINISTIC",
    "FAILED_CLOSED",
]

ACTIVITY_COPY: dict[ActivityKind, str] = {
    "OBJECTIVE_RECEIVED": "Understanding your objective",
    "CHECKING_MISSING": "Checking what information is missing",
    "CLARIFICATION_READY": "Asking one question that blocks the plan",
    "PLAN_UPDATING": "Updating your plan",
    "PLAN_READY": "Preparing N tasks",
    "PLAN_CONFIRMED": "Plan confirmed",
    "PARKING_RESEARCHING": "Researching suppliers",
    "OFFERS_COMPARING": "Comparing eligible offers",
    "RECOMMENDATION_PREPARING": "Preparing recommendation",
    "AWAITING_HUMAN_APPROVAL": "Waiting for your approval",
    "FALLBACK_DETERMINISTIC": "Using the local planner (labelled)",
    "FAILED_CLOSED": "Could not complete this step",
}


def activity_event(kind: ActivityKind, *, task_count: int | None = None) -> dict[str, str]:
    copy = ACTIVITY_COPY[kind]
    if kind == "PLAN_READY" and task_count is not None:
        copy = f"Preparing {task_count} tasks"
    return {"kind": kind, "message": copy}
