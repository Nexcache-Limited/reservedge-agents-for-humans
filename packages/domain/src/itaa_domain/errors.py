"""Framework-neutral domain errors. Messages never include raw payloads."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DomainInvariantError(Exception):
    field: str
    code: str

    def __str__(self) -> str:
        return f"{self.field}: {self.code}"


@dataclass(frozen=True, slots=True)
class InvalidTransitionError(Exception):
    resource_type: str
    resource_id: str
    current_state: str
    attempted_action: str
    permitted_actions: tuple[str, ...]

    def __str__(self) -> str:
        return (
            f"{self.resource_type} {self.current_state} cannot {self.attempted_action}; "
            f"permitted={list(self.permitted_actions)}"
        )


@dataclass(frozen=True, slots=True)
class VersionConflictError(Exception):
    resource_type: str
    resource_id: str
    expected_revision: int
    actual_revision: int

    def __str__(self) -> str:
        return f"{self.resource_type} revision conflict"


@dataclass(frozen=True, slots=True)
class ExpiredResourceError(Exception):
    resource_type: str
    resource_id: str
    expired_at: str

    def __str__(self) -> str:
        return f"{self.resource_type} expired"


@dataclass(frozen=True, slots=True)
class DuplicateActionError(Exception):
    resource_type: str
    resource_id: str
    action: str
    current_state: str

    def __str__(self) -> str:
        return f"{self.resource_type} duplicate {self.action}"


@dataclass(frozen=True, slots=True)
class OfferVersionMismatchError(Exception):
    offer_id: str
    expected_version: int
    actual_version: int

    def __str__(self) -> str:
        return "offer version mismatch"
