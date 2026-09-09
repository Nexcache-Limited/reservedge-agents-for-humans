"""Observability errors. Messages never include raw payloads."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ObservabilityError(Exception):
    field: str
    code: str

    def __str__(self) -> str:
        return f"{self.field}: {self.code}"


@dataclass(frozen=True, slots=True)
class AuditConflictError(Exception):
    field: str
    code: str = "conflict"

    def __str__(self) -> str:
        return f"{self.field}: {self.code}"
