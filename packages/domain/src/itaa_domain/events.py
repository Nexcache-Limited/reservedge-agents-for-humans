"""Typed, redaction-safe domain events. No event IDs or clocks are generated here."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType
from typing import Any

from itaa_domain.errors import DomainInvariantError
from itaa_domain.identifiers import (
    UNBOUND_TRANSACTION_ID,
    AcceptanceId,
    ActorId,
    ApprovalId,
    AuthorizationId,
    CorrelationId,
    CounterOfferId,
    IdempotencyKey,
    IntentId,
    OfferId,
)
from itaa_domain.value_objects import (
    ActorType,
    CancellationReason,
    ClosureReason,
    DeclineReason,
    PayloadHash,
    RejectionReason,
    TransactionDeclineReason,
    TransactionFailureReason,
    Version,
    format_utc,
    require_exact_enum,
    require_utc,
)

# Closed codes are listed here to avoid import cycles with aggregate modules.
# Tests assert this set equals the union of action/reason enums.
CLOSED_ACTION_CODES: frozenset[str] = frozenset(
    {
        "confirm",
        "cancel",
        "preview_disclosure",
        "approve_dispatch",
        "dispatch",
        "expire",
        "close",
        "begin_draft",
        "submit",
        "validate",
        "reject",
        "counter",
        "resubmit",
        "mark_eligible",
        "recommend",
        "accept",
        "decline",
        "request_from_acceptance",
        "require_approval",
        "authorize_simulated",
        "fail",
    }
)
CLOSED_REASON_CODES: frozenset[str] = CLOSED_ACTION_CODES | {
    "buyer_revoked",
    "buyer_abandoned",
    "operator_cancelled",
    "completed",
    "superseded",
    "ineligible",
    "invalid_terms",
    "policy_rejected",
    "unavailable",
    "buyer_declined",
    "superseded_by_other",
    "approval_withheld",
    "supplier_unavailable",
    "authorization_failed",
    "simulation_rejected",
}
CLOSED_TARGET_STATES: frozenset[str] = frozenset(
    {
        "DRAFT",
        "CONFIRMED",
        "DISCLOSURE_PREVIEWED",
        "APPROVED",
        "DISPATCHED",
        "CLOSED",
        "CANCELLED",
        "EXPIRED",
        "INVITED",
        "SUBMITTED",
        "COUNTERED",
        "VALIDATED",
        "ELIGIBLE",
        "RECOMMENDED",
        "REJECTED",
        "ACCEPTED",
        "DECLINED",
        "NOT_REQUESTED",
        "ACCEPTANCE_PENDING",
        "APPROVAL_REQUIRED",
        "AUTHORIZED_SIMULATED",
        "FAILED",
    }
)


class EventType(StrEnum):
    PURCHASE_INTENT_CONFIRMED = "purchase_intent.confirmed"
    PURCHASE_INTENT_CANCELLED = "purchase_intent.cancelled"
    PURCHASE_INTENT_DISCLOSURE_PREVIEWED = "purchase_intent.disclosure_previewed"
    PURCHASE_INTENT_APPROVED = "purchase_intent.approved"
    PURCHASE_INTENT_DISPATCHED = "purchase_intent.dispatched"
    PURCHASE_INTENT_EXPIRED = "purchase_intent.expired"
    PURCHASE_INTENT_CLOSED = "purchase_intent.closed"
    OFFER_DRAFT_BEGUN = "offer.draft_begun"
    OFFER_SUBMITTED = "offer.submitted"
    OFFER_VALIDATED = "offer.validated"
    OFFER_REJECTED = "offer.rejected"
    OFFER_COUNTERED = "offer.countered"
    OFFER_RESUBMITTED = "offer.resubmitted"
    OFFER_MARKED_ELIGIBLE = "offer.marked_eligible"
    OFFER_RECOMMENDED = "offer.recommended"
    OFFER_ACCEPTED = "offer.accepted"
    OFFER_DECLINED = "offer.declined"
    OFFER_EXPIRED = "offer.expired"
    TRANSACTION_REQUESTED = "transaction.requested"
    TRANSACTION_APPROVAL_REQUIRED = "transaction.approval_required"
    TRANSACTION_AUTHORIZED_SIMULATED = "transaction.authorized_simulated"
    TRANSACTION_DECLINED = "transaction.declined"
    TRANSACTION_EXPIRED = "transaction.expired"
    TRANSACTION_FAILED = "transaction.failed"


class ResourceType(StrEnum):
    PURCHASE_INTENT = "purchase_intent"
    OFFER = "offer"
    TRANSACTION = "transaction"


class FieldPresence(StrEnum):
    REQUIRED = "required"
    OPTIONAL = "optional"
    FORBIDDEN = "forbidden"


@dataclass(frozen=True, slots=True)
class EventSpec:
    resource_type: ResourceType
    action: str
    target_state: str
    reason_codes: frozenset[str]
    offer_id: FieldPresence
    acceptance_id: FieldPresence
    payload_hash: FieldPresence


def _codes(enum_cls: type[StrEnum]) -> frozenset[str]:
    return frozenset(item.value for item in enum_cls)


def _fixed(action: str) -> frozenset[str]:
    return frozenset({action})


def _spec(
    resource_type: ResourceType,
    action: str,
    target_state: str,
    reason_codes: frozenset[str],
    *,
    offer_id: FieldPresence,
    acceptance_id: FieldPresence,
    payload_hash: FieldPresence,
) -> EventSpec:
    return EventSpec(
        resource_type=resource_type,
        action=action,
        target_state=target_state,
        reason_codes=reason_codes,
        offer_id=offer_id,
        acceptance_id=acceptance_id,
        payload_hash=payload_hash,
    )


_PI = ResourceType.PURCHASE_INTENT
_OFFER = ResourceType.OFFER
_TX = ResourceType.TRANSACTION
_F = FieldPresence.FORBIDDEN
_R = FieldPresence.REQUIRED
_O = FieldPresence.OPTIONAL

EVENT_SPECS: Mapping[EventType, EventSpec] = MappingProxyType(
    {
        EventType.PURCHASE_INTENT_CONFIRMED: _spec(
            _PI,
            "confirm",
            "CONFIRMED",
            _fixed("confirm"),
            offer_id=_F,
            acceptance_id=_F,
            payload_hash=_F,
        ),
        EventType.PURCHASE_INTENT_CANCELLED: _spec(
            _PI,
            "cancel",
            "CANCELLED",
            _codes(CancellationReason),
            offer_id=_F,
            acceptance_id=_F,
            payload_hash=_O,
        ),
        EventType.PURCHASE_INTENT_DISCLOSURE_PREVIEWED: _spec(
            _PI,
            "preview_disclosure",
            "DISCLOSURE_PREVIEWED",
            _fixed("preview_disclosure"),
            offer_id=_F,
            acceptance_id=_F,
            payload_hash=_R,
        ),
        EventType.PURCHASE_INTENT_APPROVED: _spec(
            _PI,
            "approve_dispatch",
            "APPROVED",
            _fixed("approve_dispatch"),
            offer_id=_F,
            acceptance_id=_F,
            payload_hash=_R,
        ),
        EventType.PURCHASE_INTENT_DISPATCHED: _spec(
            _PI,
            "dispatch",
            "DISPATCHED",
            _fixed("dispatch"),
            offer_id=_F,
            acceptance_id=_F,
            payload_hash=_R,
        ),
        EventType.PURCHASE_INTENT_EXPIRED: _spec(
            _PI,
            "expire",
            "EXPIRED",
            _fixed("expire"),
            offer_id=_F,
            acceptance_id=_F,
            payload_hash=_R,
        ),
        EventType.PURCHASE_INTENT_CLOSED: _spec(
            _PI,
            "close",
            "CLOSED",
            _codes(ClosureReason),
            offer_id=_F,
            acceptance_id=_F,
            payload_hash=_R,
        ),
        EventType.OFFER_DRAFT_BEGUN: _spec(
            _OFFER,
            "begin_draft",
            "DRAFT",
            _fixed("begin_draft"),
            offer_id=_R,
            acceptance_id=_F,
            payload_hash=_F,
        ),
        EventType.OFFER_SUBMITTED: _spec(
            _OFFER,
            "submit",
            "SUBMITTED",
            _fixed("submit"),
            offer_id=_R,
            acceptance_id=_F,
            payload_hash=_F,
        ),
        EventType.OFFER_VALIDATED: _spec(
            _OFFER,
            "validate",
            "VALIDATED",
            _fixed("validate"),
            offer_id=_R,
            acceptance_id=_F,
            payload_hash=_F,
        ),
        EventType.OFFER_REJECTED: _spec(
            _OFFER,
            "reject",
            "REJECTED",
            _codes(RejectionReason),
            offer_id=_R,
            acceptance_id=_F,
            payload_hash=_F,
        ),
        EventType.OFFER_COUNTERED: _spec(
            _OFFER,
            "counter",
            "COUNTERED",
            _fixed("counter"),
            offer_id=_R,
            acceptance_id=_F,
            payload_hash=_F,
        ),
        EventType.OFFER_RESUBMITTED: _spec(
            _OFFER,
            "resubmit",
            "SUBMITTED",
            _fixed("resubmit"),
            offer_id=_R,
            acceptance_id=_F,
            payload_hash=_F,
        ),
        EventType.OFFER_MARKED_ELIGIBLE: _spec(
            _OFFER,
            "mark_eligible",
            "ELIGIBLE",
            _fixed("mark_eligible"),
            offer_id=_R,
            acceptance_id=_F,
            payload_hash=_F,
        ),
        EventType.OFFER_RECOMMENDED: _spec(
            _OFFER,
            "recommend",
            "RECOMMENDED",
            _fixed("recommend"),
            offer_id=_R,
            acceptance_id=_F,
            payload_hash=_F,
        ),
        EventType.OFFER_ACCEPTED: _spec(
            _OFFER,
            "accept",
            "ACCEPTED",
            _fixed("accept"),
            offer_id=_R,
            acceptance_id=_R,
            payload_hash=_F,
        ),
        EventType.OFFER_DECLINED: _spec(
            _OFFER,
            "decline",
            "DECLINED",
            _codes(DeclineReason),
            offer_id=_R,
            acceptance_id=_F,
            payload_hash=_F,
        ),
        EventType.OFFER_EXPIRED: _spec(
            _OFFER,
            "expire",
            "EXPIRED",
            _fixed("expire"),
            offer_id=_R,
            acceptance_id=_F,
            payload_hash=_F,
        ),
        EventType.TRANSACTION_REQUESTED: _spec(
            _TX,
            "request_from_acceptance",
            "ACCEPTANCE_PENDING",
            _fixed("request_from_acceptance"),
            offer_id=_R,
            acceptance_id=_R,
            payload_hash=_F,
        ),
        EventType.TRANSACTION_APPROVAL_REQUIRED: _spec(
            _TX,
            "require_approval",
            "APPROVAL_REQUIRED",
            _fixed("require_approval"),
            offer_id=_R,
            acceptance_id=_R,
            payload_hash=_F,
        ),
        EventType.TRANSACTION_AUTHORIZED_SIMULATED: _spec(
            _TX,
            "authorize_simulated",
            "AUTHORIZED_SIMULATED",
            _fixed("authorize_simulated"),
            offer_id=_R,
            acceptance_id=_R,
            payload_hash=_F,
        ),
        EventType.TRANSACTION_DECLINED: _spec(
            _TX,
            "decline",
            "DECLINED",
            _codes(TransactionDeclineReason),
            offer_id=_R,
            acceptance_id=_R,
            payload_hash=_F,
        ),
        EventType.TRANSACTION_EXPIRED: _spec(
            _TX,
            "expire",
            "EXPIRED",
            _fixed("expire"),
            offer_id=_R,
            acceptance_id=_R,
            payload_hash=_F,
        ),
        EventType.TRANSACTION_FAILED: _spec(
            _TX,
            "fail",
            "FAILED",
            _codes(TransactionFailureReason),
            offer_id=_R,
            acceptance_id=_R,
            payload_hash=_F,
        ),
    }
)

assert set(EVENT_SPECS) == set(EventType)


def _require_id(constructor: type[object], value: object, field: str) -> None:
    try:
        constructor(value)  # type: ignore[call-arg]
    except DomainInvariantError:
        raise DomainInvariantError(field, "invalid_opaque_syntax") from None


def _check_presence(value: object, policy: FieldPresence, field: str) -> None:
    if policy is FieldPresence.REQUIRED and value is None:
        raise DomainInvariantError(field, "required")
    if policy is FieldPresence.FORBIDDEN and value is not None:
        raise DomainInvariantError(field, "must_be_absent")


def emit_domain_event(
    *,
    event_type: EventType,
    resource_id: str,
    resource_version: int,
    occurred_at: datetime,
    actor_type: ActorType,
    actor_id: str,
    reason_code: str,
    correlation_id: str,
    intent_id: str | None = None,
    offer_id: str | None = None,
    acceptance_id: str | None = None,
    counter_offer_id: str | None = None,
    approval_id: str | None = None,
    authorization_id: str | None = None,
    idempotency_key: str | None = None,
    payload_hash: str | None = None,
    offer_version: int | None = None,
    simulation: bool | None = None,
) -> DomainEvent:
    require_exact_enum(event_type, EventType, "event_type")
    spec = EVENT_SPECS.get(event_type)
    if spec is None:
        raise DomainInvariantError("event_type", "unsupported")
    return DomainEvent(
        event_type=event_type,
        resource_type=spec.resource_type,
        resource_id=resource_id,
        resource_version=resource_version,
        occurred_at=occurred_at,
        actor_type=actor_type,
        actor_id=actor_id,
        action=spec.action,
        reason_code=reason_code,
        correlation_id=correlation_id,
        target_state=spec.target_state,
        intent_id=intent_id,
        offer_id=offer_id,
        acceptance_id=acceptance_id,
        counter_offer_id=counter_offer_id,
        approval_id=approval_id,
        authorization_id=authorization_id,
        idempotency_key=idempotency_key,
        payload_hash=payload_hash,
        offer_version=offer_version,
        simulation=simulation,
    )


@dataclass(frozen=True, slots=True)
class DomainEvent:
    event_type: EventType
    resource_type: ResourceType
    resource_id: str
    resource_version: int
    occurred_at: datetime
    actor_type: ActorType
    actor_id: str
    action: str
    reason_code: str
    correlation_id: str
    target_state: str
    intent_id: str | None = None
    offer_id: str | None = None
    acceptance_id: str | None = None
    counter_offer_id: str | None = None
    approval_id: str | None = None
    authorization_id: str | None = None
    idempotency_key: str | None = None
    payload_hash: str | None = None
    offer_version: int | None = None
    simulation: bool | None = None

    def __post_init__(self) -> None:
        require_exact_enum(self.event_type, EventType, "event_type")
        require_exact_enum(self.resource_type, ResourceType, "resource_type")
        require_exact_enum(self.actor_type, ActorType, "actor_type")
        require_utc(self.occurred_at, "occurred_at")
        Version(self.resource_version)
        spec = EVENT_SPECS.get(self.event_type)
        if spec is None:
            raise DomainInvariantError("event_type", "unsupported")
        if self.resource_type is not spec.resource_type:
            raise DomainInvariantError("resource_type", "event_type_mismatch")
        if self.action != spec.action:
            raise DomainInvariantError("action", "event_type_mismatch")
        if self.target_state != spec.target_state:
            raise DomainInvariantError("target_state", "event_type_mismatch")
        if self.reason_code not in spec.reason_codes:
            raise DomainInvariantError("reason_code", "event_type_mismatch")
        _check_presence(self.offer_id, spec.offer_id, "offer_id")
        _check_presence(self.acceptance_id, spec.acceptance_id, "acceptance_id")
        _check_presence(self.payload_hash, spec.payload_hash, "payload_hash")
        if self.action not in CLOSED_ACTION_CODES:
            raise DomainInvariantError("action", "must_be_closed")
        if self.reason_code not in CLOSED_REASON_CODES:
            raise DomainInvariantError("reason_code", "must_be_closed")
        if self.target_state not in CLOSED_TARGET_STATES:
            raise DomainInvariantError("target_state", "must_be_closed")
        _require_id(ActorId, self.actor_id, "actor_id")
        _require_id(CorrelationId, self.correlation_id, "correlation_id")
        self._validate_resource_id()
        if self.intent_id is not None:
            _require_id(IntentId, self.intent_id, "intent_id")
        if self.offer_id is not None:
            _require_id(OfferId, self.offer_id, "offer_id")
        if self.acceptance_id is not None:
            _require_id(AcceptanceId, self.acceptance_id, "acceptance_id")
        if self.counter_offer_id is not None:
            _require_id(CounterOfferId, self.counter_offer_id, "counter_offer_id")
        if self.approval_id is not None:
            _require_id(ApprovalId, self.approval_id, "approval_id")
        if self.authorization_id is not None:
            _require_id(AuthorizationId, self.authorization_id, "authorization_id")
        if self.idempotency_key is not None:
            _require_id(IdempotencyKey, self.idempotency_key, "idempotency_key")
        if self.payload_hash is not None:
            PayloadHash(self.payload_hash)
        if self.offer_version is not None:
            Version(self.offer_version)
        if self.simulation is not None and self.simulation is not True:
            raise DomainInvariantError("simulation", "must_be_true")

    def _validate_resource_id(self) -> None:
        if self.resource_type is ResourceType.PURCHASE_INTENT:
            _require_id(IntentId, self.resource_id, "resource_id")
            return
        if self.resource_type is ResourceType.OFFER:
            _require_id(OfferId, self.resource_id, "resource_id")
            return
        if self.resource_id != UNBOUND_TRANSACTION_ID:
            _require_id(AcceptanceId, self.resource_id, "resource_id")

    def to_primitive(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "eventType": self.event_type.value,
            "resourceType": self.resource_type.value,
            "resourceId": self.resource_id,
            "resourceVersion": self.resource_version,
            "occurredAt": format_utc(self.occurred_at),
            "actorType": self.actor_type.value,
            "actorId": self.actor_id,
            "action": self.action,
            "reasonCode": self.reason_code,
            "correlationId": self.correlation_id,
            "targetState": self.target_state,
        }
        optional = {
            "intentId": self.intent_id,
            "offerId": self.offer_id,
            "acceptanceId": self.acceptance_id,
            "counterOfferId": self.counter_offer_id,
            "approvalId": self.approval_id,
            "authorizationId": self.authorization_id,
            "idempotencyKey": self.idempotency_key,
            "payloadHash": self.payload_hash,
            "offerVersion": self.offer_version,
            "simulation": self.simulation,
        }
        for key, value in optional.items():
            if value is not None:
                payload[key] = value
        return payload
