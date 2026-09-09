"""Fixture: imports that domain code may use."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


@dataclass(frozen=True)
class ExampleValue:
    code: str


class ExampleState(Enum):
    DRAFT = "draft"
