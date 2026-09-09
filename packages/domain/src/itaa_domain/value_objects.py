"""Immutable value objects. No I/O, hashing, or system clock."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from functools import total_ordering

from itaa_domain.errors import DomainInvariantError
from itaa_domain.identifiers import ActorId

JS_SAFE_MAX: int = 9007199254740991
CURRENCY_PATTERN = re.compile(r"^[A-Z]{3}$")
AIRPORT_PATTERN = re.compile(r"^[A-Z]{3}$")
HASH_PATTERN = re.compile(r"^sha256:[a-f0-9]{64}$")
EVIDENCE_REF_PATTERN = re.compile(r"^[a-z][a-z0-9_.:-]{2,80}$")
UTC_TIMESTAMP_PATTERN = re.compile(
    r"^([0-9]{4})-([0-9]{2})-([0-9]{2})T([0-9]{2}):([0-9]{2}):([0-9]{2})(?:\.([0-9]{1,9}))?Z$"
)


def _require_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise DomainInvariantError(field, "must_be_integer")
    return value


def require_exact_enum(value: object, enum_cls: type[object], field: str) -> None:
    if type(value) is not enum_cls:
        raise DomainInvariantError(field, "invalid_enum")


def require_utc(value: object, field: str) -> datetime:
    if not isinstance(value, datetime):
        raise DomainInvariantError(field, "must_be_datetime")
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise DomainInvariantError(field, "must_be_utc")
    return value.astimezone(UTC)


def parse_utc(value: object, field: str) -> datetime:
    if isinstance(value, datetime):
        return require_utc(value, field)
    if not isinstance(value, str):
        raise DomainInvariantError(field, "must_be_utc_timestamp")
    match = UTC_TIMESTAMP_PATTERN.fullmatch(value)
    if match is None:
        raise DomainInvariantError(field, "invalid_utc_timestamp")
    year, month, day, hour, minute, second, fraction = match.groups()
    microsecond = 0
    if fraction:
        microsecond = int(fraction.ljust(6, "0")[:6])
    try:
        parsed = datetime(
            int(year),
            int(month),
            int(day),
            int(hour),
            int(minute),
            int(second),
            microsecond,
            tzinfo=UTC,
        )
    except ValueError as exc:
        raise DomainInvariantError(field, "invalid_utc_timestamp") from exc
    return parsed


def format_utc(value: datetime) -> str:
    utc = require_utc(value, "occurred_at")
    if utc.microsecond:
        fraction = f"{utc.microsecond:06d}".rstrip("0")
        return utc.strftime("%Y-%m-%dT%H:%M:%S") + "." + fraction + "Z"
    return utc.strftime("%Y-%m-%dT%H:%M:%SZ")


@total_ordering
@dataclass(frozen=True, slots=True)
class Money:
    amount_minor: int
    currency: str

    def __post_init__(self) -> None:
        amount = _require_int(self.amount_minor, "amount_minor")
        if amount < 0 or amount > JS_SAFE_MAX:
            raise DomainInvariantError("amount_minor", "out_of_range")
        if not isinstance(self.currency, str) or CURRENCY_PATTERN.fullmatch(self.currency) is None:
            raise DomainInvariantError("currency", "invalid_currency_code")
        object.__setattr__(self, "amount_minor", amount)

    def _same_currency(self, other: object, op: str) -> Money:
        if not isinstance(other, Money):
            raise DomainInvariantError("currency", f"{op}_requires_money")
        if self.currency != other.currency:
            raise DomainInvariantError("currency", "cross_currency_forbidden")
        return other

    def __add__(self, other: object) -> Money:
        matched = self._same_currency(other, "add")
        total = self.amount_minor + matched.amount_minor
        if total > JS_SAFE_MAX:
            raise DomainInvariantError("amount_minor", "overflow")
        return Money(total, self.currency)

    def __sub__(self, other: object) -> Money:
        matched = self._same_currency(other, "subtract")
        total = self.amount_minor - matched.amount_minor
        if total < 0:
            raise DomainInvariantError("amount_minor", "negative_result")
        return Money(total, self.currency)

    def __lt__(self, other: object) -> bool:
        matched = self._same_currency(other, "compare")
        return self.amount_minor < matched.amount_minor

    def to_primitive(self) -> dict[str, int | str]:
        return {"amountMinor": self.amount_minor, "currency": self.currency}


@dataclass(frozen=True, slots=True)
class TimeWindow:
    start: datetime
    end: datetime

    def __post_init__(self) -> None:
        start = require_utc(self.start, "start")
        end = require_utc(self.end, "end")
        if end <= start:
            raise DomainInvariantError("service_window", "end_must_follow_start")
        object.__setattr__(self, "start", start)
        object.__setattr__(self, "end", end)

    def contains(self, instant: datetime) -> bool:
        point = require_utc(instant, "instant")
        return self.start <= point < self.end

    def is_expired_at(self, instant: datetime) -> bool:
        point = require_utc(instant, "instant")
        return point >= self.end

    def duration(self) -> timedelta:
        return self.end - self.start

    def to_primitive(self) -> dict[str, str]:
        return {"start": format_utc(self.start), "end": format_utc(self.end)}

    @classmethod
    def from_primitives(cls, start: object, end: object) -> TimeWindow:
        return cls(parse_utc(start, "start"), parse_utc(end, "end"))


@dataclass(frozen=True, slots=True)
class Version:
    value: int

    def __post_init__(self) -> None:
        number = _require_int(self.value, "version")
        if number < 1 or number > JS_SAFE_MAX:
            raise DomainInvariantError("version", "out_of_range")
        object.__setattr__(self, "value", number)

    @classmethod
    def initial(cls) -> Version:
        return cls(1)

    def next(self) -> Version:
        if self.value >= JS_SAFE_MAX:
            raise DomainInvariantError("version", "overflow")
        return Version(self.value + 1)

    def to_primitive(self) -> int:
        return self.value


@dataclass(frozen=True, slots=True)
class PayloadHash:
    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str) or HASH_PATTERN.fullmatch(self.value) is None:
            raise DomainInvariantError("payload_hash", "invalid_sha256_shape")

    def to_primitive(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class AirportCode:
    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str) or AIRPORT_PATTERN.fullmatch(self.value) is None:
            raise DomainInvariantError("airport_code", "invalid_iata_code")

    def to_primitive(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class EvidenceRef:
    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str) or EVIDENCE_REF_PATTERN.fullmatch(self.value) is None:
            raise DomainInvariantError("evidence_ref", "invalid_evidence_ref")

    def to_primitive(self) -> str:
        return self.value


class ActorType(StrEnum):
    BUYER = "buyer"
    SUPPLIER = "supplier"
    SYSTEM = "system"
    OPERATOR = "operator"


@dataclass(frozen=True, slots=True)
class ActorRef:
    category: ActorType
    actor_id: ActorId

    def __post_init__(self) -> None:
        require_exact_enum(self.category, ActorType, "actor_type")
        if not isinstance(self.actor_id, ActorId):
            raise DomainInvariantError("actor_id", "invalid_opaque_syntax")

    def to_primitive(self) -> dict[str, str]:
        return {"actorType": self.category.value, "actorId": self.actor_id.to_primitive()}


class VehicleClass(StrEnum):
    STANDARD = "standard"
    COMPACT = "compact"
    SUV = "suv"
    OVERSIZED = "oversized"


class CoveredPreference(StrEnum):
    NONE = "none"
    PREFERRED = "preferred"
    REQUIRED = "required"


class AccessibilityNeed(StrEnum):
    STEP_FREE = "step_free"
    WHEELCHAIR = "wheelchair"
    EV_CHARGING = "ev_charging"


class LotType(StrEnum):
    COVERED = "covered"
    UNCOVERED = "uncovered"
    GARAGE = "garage"
    SURFACE = "surface"


class SimulatedAvailability(StrEnum):
    CONFIRMED_SIMULATED = "confirmed_simulated"
    LIMITED_SIMULATED = "limited_simulated"
    UNAVAILABLE_SIMULATED = "unavailable_simulated"


class AddOn(StrEnum):
    EV_CHARGING = "ev_charging"
    INDOOR_WALKWAY = "indoor_walkway"
    OVERSIZED_BAY = "oversized_bay"


class CancellationTerm(StrEnum):
    FREE_UNTIL_24H = "free_until_24h"
    FREE_UNTIL_48H = "free_until_48h"
    NON_REFUNDABLE = "non_refundable"


class RefundTerm(StrEnum):
    ORIGINAL_METHOD = "original_method"
    NONE = "none"


class EvidenceType(StrEnum):
    SUPPLIER_POLICY = "supplier_policy"
    RATE_CARD = "rate_card"
    LOT_RULES = "lot_rules"
    AVAILABILITY_SNAPSHOT = "availability_snapshot"


class AcceptanceStatus(StrEnum):
    RECORDED = "recorded"


class AuthorizationAction(StrEnum):
    RESERVE_PARKING = "reserve_parking"


class AuthorizationMode(StrEnum):
    SIMULATED = "SIMULATED"


class CancellationReason(StrEnum):
    BUYER_REVOKED = "buyer_revoked"
    BUYER_ABANDONED = "buyer_abandoned"
    OPERATOR_CANCELLED = "operator_cancelled"


class ClosureReason(StrEnum):
    COMPLETED = "completed"
    SUPERSEDED = "superseded"


class RejectionReason(StrEnum):
    INELIGIBLE = "ineligible"
    INVALID_TERMS = "invalid_terms"
    POLICY_REJECTED = "policy_rejected"
    UNAVAILABLE = "unavailable"


class DeclineReason(StrEnum):
    BUYER_DECLINED = "buyer_declined"
    SUPERSEDED_BY_OTHER = "superseded_by_other"


class TransactionDeclineReason(StrEnum):
    BUYER_DECLINED = "buyer_declined"
    APPROVAL_WITHHELD = "approval_withheld"


class TransactionFailureReason(StrEnum):
    SUPPLIER_UNAVAILABLE = "supplier_unavailable"
    AUTHORIZATION_FAILED = "authorization_failed"
    SIMULATION_REJECTED = "simulation_rejected"


def require_shuttle_minutes(value: object, field: str = "shuttle_minutes") -> int:
    minutes = _require_int(value, field)
    if minutes < 0 or minutes > 180:
        raise DomainInvariantError(field, "out_of_range")
    return minutes


def require_distance_metres(value: object) -> int:
    metres = _require_int(value, "distance_metres")
    if metres < 0 or metres > 100000:
        raise DomainInvariantError("distance_metres", "out_of_range")
    return metres
