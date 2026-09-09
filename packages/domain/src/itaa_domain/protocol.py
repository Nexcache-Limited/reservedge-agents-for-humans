"""Shared transition protocol. Pure functions only."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import TypeVar

from itaa_domain.errors import (
    DomainInvariantError,
    DuplicateActionError,
    InvalidTransitionError,
    VersionConflictError,
)
from itaa_domain.events import DomainEvent
from itaa_domain.identifiers import CorrelationId
from itaa_domain.value_objects import ActorRef, Version, require_utc

S = TypeVar("S")
A = TypeVar("A", bound=StrEnum)


@dataclass(frozen=True, slots=True)
class TransitionRequest:
    expected_revision: Version
    occurred_at: datetime
    actor: ActorRef
    correlation_id: CorrelationId

    def __post_init__(self) -> None:
        require_utc(self.occurred_at, "occurred_at")


@dataclass(frozen=True, slots=True)
class TransitionResult[T]:
    aggregate: T
    event: DomainEvent


def assert_revision(
    actual: Version,
    expected: Version,
    resource_type: str,
    resource_id: str,
) -> None:
    if actual != expected:
        raise VersionConflictError(
            resource_type=resource_type,
            resource_id=resource_id,
            expected_revision=expected.value,
            actual_revision=actual.value,
        )


def assert_monotonic(updated_at: datetime, occurred_at: datetime) -> None:
    if require_utc(occurred_at, "occurred_at") < require_utc(updated_at, "updated_at"):
        raise DomainInvariantError("occurred_at", "must_not_move_backwards")


def permitted_actions(table: dict[tuple[S, A], S], state: S) -> tuple[str, ...]:
    return tuple(sorted({action.value for current, action in table if current == state}))


def require_action_reason(
    reason: object | None,
    expected_type: type[object] | None,
    *,
    action_code: str,
) -> str:
    if expected_type is None:
        if reason is not None:
            raise DomainInvariantError("reason_code", "must_be_absent")
        return action_code
    if reason is None:
        raise DomainInvariantError("reason_code", "required")
    if type(reason) is not expected_type:
        raise DomainInvariantError("reason_code", "must_match_action")
    value = getattr(reason, "value", None)
    if not isinstance(value, str):
        raise DomainInvariantError("reason_code", "must_match_action")
    return value


def reject_illegal(
    *,
    resource_type: str,
    resource_id: str,
    current_state: str,
    attempted_action: str,
    permitted: tuple[str, ...],
    terminal: bool,
    duplicate_actions: frozenset[str],
) -> None:
    if terminal and attempted_action in duplicate_actions:
        raise DuplicateActionError(
            resource_type=resource_type,
            resource_id=resource_id,
            action=attempted_action,
            current_state=current_state,
        )
    raise InvalidTransitionError(
        resource_type=resource_type,
        resource_id=resource_id,
        current_state=current_state,
        attempted_action=attempted_action,
        permitted_actions=permitted,
    )
