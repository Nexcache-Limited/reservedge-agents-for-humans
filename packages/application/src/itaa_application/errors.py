"""Application errors. Messages never include raw payloads or identity text."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ApplicationError(Exception):
    field: str
    code: str

    def __str__(self) -> str:
        return f"{self.field}: {self.code}"
