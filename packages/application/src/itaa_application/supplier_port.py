"""Cloud-neutral supplier solicitation port. No authorization, I/O, or wall clock."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Protocol

from itaa_application.errors import ApplicationError
from itaa_application.freeze import freeze_payload
from itaa_domain.identifiers import CorrelationId, OfferId, SignatureHandle, SupplierToken
from itaa_domain.value_objects import require_utc
from itaa_policy.envelopes import SupplierEnvelope
from itaa_policy.isolation import SupplierInvitationToken


class TerminalKind(StrEnum):
    OFFER = "OFFER"
    DECLINED = "DECLINED"
    INVALID = "INVALID"
    TIMED_OUT = "TIMED_OUT"
    FAILED = "FAILED"
    DENIED = "DENIED"
    LATE = "LATE"


class ClosedReason(StrEnum):
    UNSUPPORTED_AIRPORT = "unsupported_airport"
    UNSUPPORTED_CATEGORY = "unsupported_category"
    UNSUPPORTED_VEHICLE = "unsupported_vehicle"
    UNSUPPORTED_SERVICE = "unsupported_service"
    INSUFFICIENT_CAPACITY = "insufficient_capacity"
    PRICE_FLOOR = "price_floor"
    DISCOUNT_CAP = "discount_cap"
    ACQUISITION_CAP = "acquisition_cap"
    ADD_ON_MARGIN = "add_on_margin"
    CANCELLATION_PAIR = "cancellation_pair"
    VALIDITY_WINDOW = "validity_window"
    RESPONSE_DEADLINE = "response_deadline"
    MALFORMED = "malformed"
    TIMEOUT = "timeout"
    FAILED = "failed"
    DISPATCH_DENIED = "dispatch_denied"
    DUPLICATE = "duplicate"
    LATE = "late"
    WRONG_CHANNEL = "wrong_channel"


SUPPLIER_ORIGINATED_KINDS: frozenset[TerminalKind] = frozenset(
    {TerminalKind.OFFER, TerminalKind.DECLINED}
)
BUYER_OWNED_KINDS: frozenset[TerminalKind] = frozenset(
    {
        TerminalKind.INVALID,
        TerminalKind.TIMED_OUT,
        TerminalKind.FAILED,
        TerminalKind.DENIED,
        TerminalKind.LATE,
    }
)
SUPPLIER_DECLINE_REASONS: frozenset[ClosedReason] = frozenset(
    {
        ClosedReason.UNSUPPORTED_AIRPORT,
        ClosedReason.UNSUPPORTED_CATEGORY,
        ClosedReason.UNSUPPORTED_VEHICLE,
        ClosedReason.UNSUPPORTED_SERVICE,
        ClosedReason.INSUFFICIENT_CAPACITY,
        ClosedReason.PRICE_FLOOR,
        ClosedReason.DISCOUNT_CAP,
        ClosedReason.ACQUISITION_CAP,
        ClosedReason.ADD_ON_MARGIN,
        ClosedReason.CANCELLATION_PAIR,
        ClosedReason.VALIDITY_WINDOW,
        ClosedReason.RESPONSE_DEADLINE,
    }
)
BUYER_OWNED_REASONS: frozenset[ClosedReason] = frozenset(
    {
        ClosedReason.MALFORMED,
        ClosedReason.TIMEOUT,
        ClosedReason.FAILED,
        ClosedReason.DISPATCH_DENIED,
        ClosedReason.DUPLICATE,
        ClosedReason.LATE,
        ClosedReason.WRONG_CHANNEL,
    }
)


def validity_duration_in_bounds(
    start: datetime,
    end: datetime,
    *,
    minimum_seconds: int,
    maximum_seconds: int,
) -> bool:
    """Compare an inclusive validity window without truncating fractional seconds."""
    duration = end - start
    return timedelta(seconds=minimum_seconds) <= duration <= timedelta(seconds=maximum_seconds)


class Clock(Protocol):
    def now(self) -> datetime:
        """Return a validated UTC instant. Tests inject this; production never sleeps."""
        ...


class FrozenClock:
    """Deterministic UTC clock. Advance only from tests."""

    def __init__(self, instant: datetime) -> None:
        self._instant = require_utc(instant, "now")

    def now(self) -> datetime:
        return self._instant

    def set(self, instant: datetime) -> None:
        self._instant = require_utc(instant, "now")

    def advance(self, delta: timedelta) -> None:
        self._instant = require_utc(self._instant + delta, "now")


class WallClock:
    """Process wall clock. Local demo mints from this instead of a frozen August epoch."""

    def now(self) -> datetime:
        return require_utc(datetime.now(UTC).replace(microsecond=0), "now")


@dataclass(frozen=True, slots=True)
class SupplierAttempt:
    envelope: SupplierEnvelope
    occurred_at: datetime
    deadline: datetime
    invitation: SupplierInvitationToken
    offer_id: OfferId
    signature: SignatureHandle
    correlation_id: CorrelationId

    def __post_init__(self) -> None:
        object.__setattr__(self, "occurred_at", require_utc(self.occurred_at, "occurred_at"))
        object.__setattr__(self, "deadline", require_utc(self.deadline, "deadline"))
        if type(self.invitation) is not SupplierInvitationToken:
            raise ApplicationError("invitation", "required")
        if self.invitation != self.envelope.assignment.invitation:
            raise ApplicationError("invitation", "wrong_channel")


@dataclass(frozen=True, slots=True)
class SupplierTerminal:
    kind: TerminalKind
    supplier_token: SupplierToken
    correlation_id: CorrelationId
    invitation: SupplierInvitationToken
    completed_at: datetime
    reason: ClosedReason | None = None
    payload: Mapping[str, object] | None = None

    def __post_init__(self) -> None:
        if type(self.kind) is not TerminalKind:
            raise ApplicationError("kind", "invalid_enum")
        if type(self.supplier_token) is not SupplierToken:
            raise ApplicationError("supplier_token", "invalid_opaque_syntax")
        if type(self.correlation_id) is not CorrelationId:
            raise ApplicationError("correlation_id", "invalid_opaque_syntax")
        if type(self.invitation) is not SupplierInvitationToken:
            raise ApplicationError("invitation", "required")
        object.__setattr__(self, "completed_at", require_utc(self.completed_at, "completed_at"))
        if self.reason is not None and type(self.reason) is not ClosedReason:
            raise ApplicationError("reason", "invalid_enum")
        if self.kind is TerminalKind.OFFER:
            if self.payload is None or self.reason is not None:
                raise ApplicationError("payload", "offer_required")
            frozen = freeze_payload(self.payload)
            if not isinstance(frozen, Mapping):
                raise ApplicationError("payload", "must_be_object")
            object.__setattr__(self, "payload", frozen)
            return
        if self.kind is not TerminalKind.DECLINED:
            raise ApplicationError("kind", "invalid_enum")
        if self.payload is not None:
            raise ApplicationError("payload", "must_be_absent")
        if self.reason is None:
            raise ApplicationError("reason", "required")
        if self.reason not in SUPPLIER_DECLINE_REASONS:
            raise ApplicationError("reason", "invalid_enum")


class SupplierPort(Protocol):
    def attempt(self, request: SupplierAttempt) -> SupplierTerminal:
        """Return one closed terminal result. Must not perform A2 authorization."""
        ...
