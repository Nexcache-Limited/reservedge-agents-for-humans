"""Opaque typed identifiers. The domain never generates these values."""

from __future__ import annotations

import re
from dataclasses import dataclass

from itaa_domain.errors import DomainInvariantError

CROCKFORD_BODY = r"[0-9a-hjkmnp-tv-z]{26}"
_PREFIXED = {
    "rq_": "requirement_id",
    "pi_": "intent_id",
    "oi_": "orchestration_intent_id",
    "bt_": "booking_task_id",
    "pl_": "plan_id",
    "ld_": "ledger_id",
    "bs_": "buyer_token",
    "of_": "offer_id",
    "sp_": "supplier_token",
    "co_": "counter_offer_id",
    "ac_": "acceptance_id",
    "ta_": "authorization_id",
    "ap_": "approval_id",
    "ik_": "idempotency_key",
    "sg_": "signature_handle",
    "ar_": "actor_id",
    "cr_": "correlation_id",
}


def _validate(prefix: str, value: object) -> str:
    field = _PREFIXED[prefix]
    if not isinstance(value, str) or isinstance(value, bool):
        raise DomainInvariantError(field, "must_be_string")
    if not re.fullmatch(prefix + CROCKFORD_BODY, value):
        raise DomainInvariantError(field, "invalid_opaque_syntax")
    return value


UNBOUND_TRANSACTION_ID = "transaction:unbound"


@dataclass(frozen=True, slots=True)
class RequirementId:
    value: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", _validate("rq_", self.value))

    def to_primitive(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class IntentId:
    value: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", _validate("pi_", self.value))

    def to_primitive(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class OrchestrationIntentId:
    value: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", _validate("oi_", self.value))

    def to_primitive(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class BookingTaskId:
    value: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", _validate("bt_", self.value))

    def to_primitive(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class PlanId:
    value: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", _validate("pl_", self.value))

    def to_primitive(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class LedgerId:
    value: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", _validate("ld_", self.value))

    def to_primitive(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class BuyerToken:
    value: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", _validate("bs_", self.value))

    def to_primitive(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class OfferId:
    value: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", _validate("of_", self.value))

    def to_primitive(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class SupplierToken:
    value: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", _validate("sp_", self.value))

    def to_primitive(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class CounterOfferId:
    value: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", _validate("co_", self.value))

    def to_primitive(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class AcceptanceId:
    value: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", _validate("ac_", self.value))

    def to_primitive(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class AuthorizationId:
    value: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", _validate("ta_", self.value))

    def to_primitive(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class ApprovalId:
    value: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", _validate("ap_", self.value))

    def to_primitive(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class IdempotencyKey:
    value: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", _validate("ik_", self.value))

    def to_primitive(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class SignatureHandle:
    value: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", _validate("sg_", self.value))

    def to_primitive(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class ActorId:
    value: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", _validate("ar_", self.value))

    def to_primitive(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class CorrelationId:
    value: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", _validate("cr_", self.value))

    def to_primitive(self) -> str:
        return self.value
