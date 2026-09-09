"""Provider-neutral progress events. Operational facts, not a domain state machine."""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol

from itaa_application.errors import ApplicationError
from itaa_domain.value_objects import format_utc, require_utc

PRIVACY_DENYLIST: frozenset[str] = frozenset(
    {
        "email",
        "buyerToken",
        "buyer_token",
        "prompt",
        "itinerary",
        "payment",
        "card",
        "totalMinor",
        "scoreMicros",
        "approvalId",
        "idempotencyKey",
        "signature",
        "password",
        "secret",
    }
)

GENERATION_PREFIX = "pg_"
_GENERATION_RE = re.compile(r"^pg_[0-9a-hjkmnp-tv-z]{26}$")


class ProgressEventKind(StrEnum):
    SOLICITATION_PREPARING = "SOLICITATION_PREPARING"
    SOLICITATION_DISPATCHED = "SOLICITATION_DISPATCHED"
    SUPPLIER_WAITING = "SUPPLIER_WAITING"
    SUPPLIER_OFFER_RECEIVED = "SUPPLIER_OFFER_RECEIVED"
    SUPPLIER_DECLINED = "SUPPLIER_DECLINED"
    SUPPLIER_TIMED_OUT = "SUPPLIER_TIMED_OUT"
    SUPPLIER_LATE = "SUPPLIER_LATE"
    SUPPLIER_INVALID = "SUPPLIER_INVALID"
    SUPPLIER_FAILED = "SUPPLIER_FAILED"
    VALIDATION_COMPLETED = "VALIDATION_COMPLETED"
    RANKING_COMPLETED = "RANKING_COMPLETED"
    RECOMMENDATION_READY = "RECOMMENDATION_READY"
    STREAM_COMPLETED = "STREAM_COMPLETED"


SUPPLIER_KINDS: frozenset[ProgressEventKind] = frozenset(
    {
        ProgressEventKind.SUPPLIER_WAITING,
        ProgressEventKind.SUPPLIER_OFFER_RECEIVED,
        ProgressEventKind.SUPPLIER_DECLINED,
        ProgressEventKind.SUPPLIER_TIMED_OUT,
        ProgressEventKind.SUPPLIER_LATE,
        ProgressEventKind.SUPPLIER_INVALID,
        ProgressEventKind.SUPPLIER_FAILED,
    }
)

CLOSED_STATUSES: frozenset[str] = frozenset(
    {
        "deadline",
        "malformed",
        "closed",
        "dispatch_denied",
        "complete",
        "unavailable",
    }
)

PUBLIC_KEYS: frozenset[str] = frozenset(
    {
        "intentId",
        "generationId",
        "kind",
        "sequence",
        "occurredAt",
        "simulation",
        "supplierToken",
        "status",
        "correlationId",
        "terminal",
    }
)


class ProgressSink(Protocol):
    def emit(
        self,
        *,
        intent_id: str,
        kind: ProgressEventKind,
        occurred_at: datetime,
        supplier_token: str | None = None,
        status: str | None = None,
        correlation_id: str | None = None,
        terminal: bool = False,
    ) -> ProgressEvent | None: ...


class ProgressBus(Protocol):
    def watch(self, intent_id: str, generation_id: str | None = None) -> str: ...

    def emit(
        self,
        *,
        intent_id: str,
        kind: ProgressEventKind,
        occurred_at: datetime,
        supplier_token: str | None = None,
        status: str | None = None,
        correlation_id: str | None = None,
        terminal: bool = False,
    ) -> ProgressEvent | None: ...

    def events_after(
        self,
        intent_id: str,
        last_sequence: int | None,
        generation_id: str | None = None,
    ) -> tuple[ProgressEvent, ...]: ...

    def subscribe(
        self,
        intent_id: str,
        last_sequence: int | None,
        generation_id: str | None = None,
    ) -> Iterator[ProgressEvent | None]: ...


@dataclass(frozen=True, slots=True)
class ProgressEvent:
    intent_id: str
    generation_id: str
    kind: ProgressEventKind
    sequence: int
    occurred_at: datetime
    simulation: bool
    supplier_token: str | None
    status: str | None
    correlation_id: str | None
    terminal: bool

    def to_public(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "intentId": self.intent_id,
            "generationId": self.generation_id,
            "kind": self.kind.value,
            "sequence": self.sequence,
            "occurredAt": format_utc(self.occurred_at),
            "simulation": self.simulation,
            "supplierToken": self.supplier_token,
            "status": self.status,
            "correlationId": self.correlation_id,
            "terminal": self.terminal,
        }
        assert set(payload) == PUBLIC_KEYS
        _reject_privacy(payload)
        return payload


class NullProgressSink:
    def watch(self, intent_id: str, generation_id: str | None = None) -> str:
        del intent_id, generation_id
        return ""

    def emit(
        self,
        *,
        intent_id: str,
        kind: ProgressEventKind,
        occurred_at: datetime,
        supplier_token: str | None = None,
        status: str | None = None,
        correlation_id: str | None = None,
        terminal: bool = False,
    ) -> ProgressEvent | None:
        del intent_id, kind, occurred_at, supplier_token, status, correlation_id, terminal
        return None

    def has_started(self, intent_id: str) -> bool:
        del intent_id
        return False

    def abandon_empty(self, intent_id: str) -> None:
        del intent_id


def validate_generation_id(generation_id: str) -> str:
    if not _GENERATION_RE.fullmatch(generation_id):
        raise ApplicationError("generationId", "schema_invalid")
    return generation_id


def validate_progress_fields(
    *,
    intent_id: str,
    generation_id: str,
    kind: ProgressEventKind,
    sequence: int,
    occurred_at: datetime,
    supplier_token: str | None,
    status: str | None,
    correlation_id: str | None,
    terminal: bool,
) -> None:
    if not isinstance(intent_id, str) or not intent_id.startswith("pi_"):
        raise ApplicationError("intentId", "schema_invalid")
    validate_generation_id(generation_id)
    if type(kind) is not ProgressEventKind:
        raise ApplicationError("kind", "schema_invalid")
    if type(sequence) is not int or sequence < 1:
        raise ApplicationError("sequence", "schema_invalid")
    require_utc(occurred_at, "occurredAt")
    if kind in SUPPLIER_KINDS:
        if not isinstance(supplier_token, str) or not supplier_token.startswith("sp_"):
            raise ApplicationError("supplierToken", "required")
    elif supplier_token is not None:
        raise ApplicationError("supplierToken", "forbidden")
    if status is not None and status not in CLOSED_STATUSES:
        raise ApplicationError("status", "schema_invalid")
    if correlation_id is not None and (
        not isinstance(correlation_id, str) or not correlation_id.startswith("cr_")
    ):
        raise ApplicationError("correlationId", "schema_invalid")
    if kind is ProgressEventKind.STREAM_COMPLETED:
        if not terminal:
            raise ApplicationError("terminal", "required")
        if status not in {"complete", "unavailable"}:
            raise ApplicationError("status", "schema_invalid")
    elif terminal:
        raise ApplicationError("terminal", "forbidden")


def _reject_privacy(payload: dict[str, object]) -> None:
    extra = set(payload) - PUBLIC_KEYS
    if extra:
        raise ApplicationError("payload", "schema_invalid")
    for key, value in payload.items():
        lowered = key.lower()
        if any(item.lower() == lowered for item in PRIVACY_DENYLIST):
            raise ApplicationError("payload", "schema_invalid")
        if isinstance(value, str) and "@" in value and "." in value:
            raise ApplicationError("payload", "schema_invalid")
