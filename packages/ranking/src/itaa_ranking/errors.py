"""Framework-neutral ranking errors. Messages never include raw payloads."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RankingError(Exception):
    field: str
    code: str

    def __str__(self) -> str:
        return f"{self.field}: {self.code}"
