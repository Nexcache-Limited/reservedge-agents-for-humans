"""Structured contract validation failures."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ContractViolation:
    schema_key: str
    source: str
    path: str
    keyword: str
    message: str

    def render(self) -> str:
        return f"{self.source} [{self.schema_key}] {self.path}: {self.keyword}: {self.message}"
