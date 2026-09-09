"""Canonical redaction-safe audit vocabulary."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from itaa_domain.errors import DomainInvariantError
from itaa_domain.events import EVENT_SPECS, DomainEvent, EventType, ResourceType
from itaa_domain.identifiers import (
    CROCKFORD_BODY,
    UNBOUND_TRANSACTION_ID,
    AcceptanceId,
    ActorId,
    ApprovalId,
    CorrelationId,
    IdempotencyKey,
    IntentId,
    OfferId,
    RequirementId,
    SignatureHandle,
)
from itaa_domain.value_objects import (
    ActorType,
    PayloadHash,
    Version,
    format_utc,
    require_exact_enum,
    require_utc,
)
from itaa_observability.errors import ObservabilityError

REDACTION_PROFILE = "itaa.redaction.v1"
POLICY_ID = "itaa.governance.v1"
POLICY_VERSION = "1.0"


class AuditAction(StrEnum):
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
    DISCLOSURE_ALLOW = "disclosure.allow"
    DISCLOSURE_DENY = "disclosure.deny"
    APPROVAL_ISSUE = "approval.issue"
    APPROVAL_ALLOW = "approval.allow"
    APPROVAL_DENY = "approval.deny"
    APPROVAL_REVOKE = "approval.revoke"
    ISOLATION_ALLOW = "isolation.allow"
    ISOLATION_DENY = "isolation.deny"
    IDEMPOTENCY_RESERVE = "idempotency.reserve"
    IDEMPOTENCY_REPLAY = "idempotency.replay"
    IDEMPOTENCY_CONFLICT = "idempotency.conflict"
    IDEMPOTENCY_COMPLETE = "idempotency.complete"
    IDEMPOTENCY_FAIL = "idempotency.fail"


class AuditDecisionResult(StrEnum):
    ALLOW = "allow"
    DENY = "deny"
    RECORD = "record"
    REPLAY = "replay"
    CONFLICT = "conflict"


class AuditResourceType(StrEnum):
    PURCHASE_INTENT = "purchase_intent"
    OFFER = "offer"
    TRANSACTION = "transaction"
    REQUIREMENT = "requirement"
    APPROVAL = "approval"
    IDEMPOTENCY = "idempotency"
    DISCLOSURE = "disclosure"
    ISOLATION = "isolation"


class AuditReason(StrEnum):
    CONFIRM = "confirm"
    CANCEL = "cancel"
    PREVIEW_DISCLOSURE = "preview_disclosure"
    APPROVE_DISPATCH = "approve_dispatch"
    DISPATCH = "dispatch"
    EXPIRE = "expire"
    CLOSE = "close"
    BEGIN_DRAFT = "begin_draft"
    SUBMIT = "submit"
    VALIDATE = "validate"
    REJECT = "reject"
    COUNTER = "counter"
    RESUBMIT = "resubmit"
    MARK_ELIGIBLE = "mark_eligible"
    RECOMMEND = "recommend"
    ACCEPT = "accept"
    DECLINE = "decline"
    REQUEST_FROM_ACCEPTANCE = "request_from_acceptance"
    REQUIRE_APPROVAL = "require_approval"
    AUTHORIZE_SIMULATED = "authorize_simulated"
    FAIL = "fail"
    BUYER_REVOKED = "buyer_revoked"
    BUYER_ABANDONED = "buyer_abandoned"
    OPERATOR_CANCELLED = "operator_cancelled"
    COMPLETED = "completed"
    SUPERSEDED = "superseded"
    INELIGIBLE = "ineligible"
    INVALID_TERMS = "invalid_terms"
    POLICY_REJECTED = "policy_rejected"
    UNAVAILABLE = "unavailable"
    BUYER_DECLINED = "buyer_declined"
    SUPERSEDED_BY_OTHER = "superseded_by_other"
    APPROVAL_WITHHELD = "approval_withheld"
    SUPPLIER_UNAVAILABLE = "supplier_unavailable"
    AUTHORIZATION_FAILED = "authorization_failed"
    SIMULATION_REJECTED = "simulation_rejected"
    ALLOWED = "allowed"
    MISSING = "missing"
    INACTIVE = "inactive"
    EXPIRED = "expired"
    NOT_YET_VALID = "not_yet_valid"
    ACTOR_MISMATCH = "actor_mismatch"
    OWNER_MISMATCH = "owner_mismatch"
    KIND_MISMATCH = "kind_mismatch"
    PURPOSE_MISMATCH = "purpose_mismatch"
    RESOURCE_MISMATCH = "resource_mismatch"
    VERSION_MISMATCH = "version_mismatch"
    HASH_MISMATCH = "hash_mismatch"
    RECIPIENT_COUNT_MISMATCH = "recipient_count_mismatch"
    DEADLINE_PASSED = "deadline_passed"
    APPROVAL_REUSED = "approval_reused"
    MODE_FORBIDDEN = "mode_forbidden"
    ACTION_MISMATCH = "action_mismatch"
    AMOUNT_MISMATCH = "amount_mismatch"
    CURRENCY_MISMATCH = "currency_mismatch"
    SUPPLIER_MISMATCH = "supplier_mismatch"
    UNKNOWN_KIND = "unknown_kind"
    PRINCIPAL_MISMATCH = "principal_mismatch"
    INVITATION_MISMATCH = "invitation_mismatch"
    SCOPE_MISMATCH = "scope_mismatch"
    CAPABILITY_DENIED = "capability_denied"
    UNKNOWN_CAPABILITY = "unknown_capability"
    UNREPRESENTABLE = "unrepresentable"
    WITHHELD_IDENTITY = "withheld_identity"
    WITHHELD_RAW_CONTENT = "withheld_raw_content"
    WITHHELD_ITINERARY = "withheld_itinerary"
    WITHHELD_PAYMENT = "withheld_payment"
    WITHHELD_PREFERENCES = "withheld_preferences"
    WITHHELD_BUDGET = "withheld_budget"
    WITHHELD_COMPETITOR = "withheld_competitor"
    WITHHELD_CREDENTIALS = "withheld_credentials"
    DENIED_UNKNOWN_FIELD = "denied_unknown_field"
    RESERVED = "reserved"
    IN_PROGRESS = "in_progress"
    REPLAYED = "replayed"
    REQUEST_MISMATCH = "request_mismatch"
    FAILED = "failed"
    EXPIRED_REPLACED = "expired_replaced"
    COMPLETION_MISMATCH = "completion_mismatch"


class ProviderLabel(StrEnum):
    UNSPECIFIED = "unspecified"
    LOCAL_REFERENCE = "local_reference"


@dataclass(frozen=True, slots=True)
class IsolationAuditRef:
    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str) or isinstance(self.value, bool):
            raise ObservabilityError("resource_id", "must_be_string")
        if not re.fullmatch("iv_" + CROCKFORD_BODY, self.value):
            raise ObservabilityError("resource_id", "invalid_opaque_syntax")

    def to_primitive(self) -> str:
        return self.value


class AuditEventId:
    def __init__(self, value: str) -> None:
        if not isinstance(value, str) or isinstance(value, bool):
            raise ObservabilityError("event_id", "must_be_string")
        if not re.fullmatch("ae_" + CROCKFORD_BODY, value):
            raise ObservabilityError("event_id", "invalid_opaque_syntax")
        self.value = value

    def to_primitive(self) -> str:
        return self.value


_EVENT_TYPE_TO_ACTION: dict[EventType, AuditAction] = {
    EventType.PURCHASE_INTENT_CONFIRMED: AuditAction.PURCHASE_INTENT_CONFIRMED,
    EventType.PURCHASE_INTENT_CANCELLED: AuditAction.PURCHASE_INTENT_CANCELLED,
    EventType.PURCHASE_INTENT_DISCLOSURE_PREVIEWED: (
        AuditAction.PURCHASE_INTENT_DISCLOSURE_PREVIEWED
    ),
    EventType.PURCHASE_INTENT_APPROVED: AuditAction.PURCHASE_INTENT_APPROVED,
    EventType.PURCHASE_INTENT_DISPATCHED: AuditAction.PURCHASE_INTENT_DISPATCHED,
    EventType.PURCHASE_INTENT_EXPIRED: AuditAction.PURCHASE_INTENT_EXPIRED,
    EventType.PURCHASE_INTENT_CLOSED: AuditAction.PURCHASE_INTENT_CLOSED,
    EventType.OFFER_DRAFT_BEGUN: AuditAction.OFFER_DRAFT_BEGUN,
    EventType.OFFER_SUBMITTED: AuditAction.OFFER_SUBMITTED,
    EventType.OFFER_VALIDATED: AuditAction.OFFER_VALIDATED,
    EventType.OFFER_REJECTED: AuditAction.OFFER_REJECTED,
    EventType.OFFER_COUNTERED: AuditAction.OFFER_COUNTERED,
    EventType.OFFER_RESUBMITTED: AuditAction.OFFER_RESUBMITTED,
    EventType.OFFER_MARKED_ELIGIBLE: AuditAction.OFFER_MARKED_ELIGIBLE,
    EventType.OFFER_RECOMMENDED: AuditAction.OFFER_RECOMMENDED,
    EventType.OFFER_ACCEPTED: AuditAction.OFFER_ACCEPTED,
    EventType.OFFER_DECLINED: AuditAction.OFFER_DECLINED,
    EventType.OFFER_EXPIRED: AuditAction.OFFER_EXPIRED,
    EventType.TRANSACTION_REQUESTED: AuditAction.TRANSACTION_REQUESTED,
    EventType.TRANSACTION_APPROVAL_REQUIRED: AuditAction.TRANSACTION_APPROVAL_REQUIRED,
    EventType.TRANSACTION_AUTHORIZED_SIMULATED: AuditAction.TRANSACTION_AUTHORIZED_SIMULATED,
    EventType.TRANSACTION_DECLINED: AuditAction.TRANSACTION_DECLINED,
    EventType.TRANSACTION_EXPIRED: AuditAction.TRANSACTION_EXPIRED,
    EventType.TRANSACTION_FAILED: AuditAction.TRANSACTION_FAILED,
}

_RESOURCE_MAP = {
    ResourceType.PURCHASE_INTENT: AuditResourceType.PURCHASE_INTENT,
    ResourceType.OFFER: AuditResourceType.OFFER,
    ResourceType.TRANSACTION: AuditResourceType.TRANSACTION,
}

_WITHHELD = frozenset(
    {
        AuditReason.WITHHELD_IDENTITY,
        AuditReason.WITHHELD_RAW_CONTENT,
        AuditReason.WITHHELD_ITINERARY,
        AuditReason.WITHHELD_PAYMENT,
        AuditReason.WITHHELD_PREFERENCES,
        AuditReason.WITHHELD_BUDGET,
        AuditReason.WITHHELD_COMPETITOR,
        AuditReason.WITHHELD_CREDENTIALS,
        AuditReason.DENIED_UNKNOWN_FIELD,
    }
)
_APPROVAL_DENY = frozenset(
    reason
    for reason in AuditReason
    if reason.value
    in {
        "missing",
        "inactive",
        "expired",
        "not_yet_valid",
        "actor_mismatch",
        "owner_mismatch",
        "kind_mismatch",
        "purpose_mismatch",
        "resource_mismatch",
        "version_mismatch",
        "hash_mismatch",
        "recipient_count_mismatch",
        "deadline_passed",
        "approval_reused",
        "mode_forbidden",
        "action_mismatch",
        "amount_mismatch",
        "currency_mismatch",
        "supplier_mismatch",
        "unknown_kind",
    }
)
_ISOLATION_DENY = frozenset(
    {
        AuditReason.PRINCIPAL_MISMATCH,
        AuditReason.INVITATION_MISMATCH,
        AuditReason.SCOPE_MISMATCH,
        AuditReason.CAPABILITY_DENIED,
        AuditReason.EXPIRED,
        AuditReason.NOT_YET_VALID,
        AuditReason.UNKNOWN_CAPABILITY,
        AuditReason.UNREPRESENTABLE,
    }
)
_GOVERNANCE_COMPAT: dict[AuditAction, tuple[AuditDecisionResult, frozenset[AuditReason]]] = {
    AuditAction.DISCLOSURE_ALLOW: (AuditDecisionResult.ALLOW, frozenset({AuditReason.ALLOWED})),
    AuditAction.DISCLOSURE_DENY: (AuditDecisionResult.DENY, _WITHHELD),
    AuditAction.APPROVAL_ISSUE: (AuditDecisionResult.RECORD, frozenset({AuditReason.ALLOWED})),
    AuditAction.APPROVAL_ALLOW: (AuditDecisionResult.ALLOW, frozenset({AuditReason.ALLOWED})),
    AuditAction.APPROVAL_DENY: (AuditDecisionResult.DENY, _APPROVAL_DENY),
    AuditAction.APPROVAL_REVOKE: (AuditDecisionResult.RECORD, frozenset({AuditReason.ALLOWED})),
    AuditAction.ISOLATION_ALLOW: (AuditDecisionResult.ALLOW, frozenset({AuditReason.ALLOWED})),
    AuditAction.ISOLATION_DENY: (AuditDecisionResult.DENY, _ISOLATION_DENY),
    AuditAction.IDEMPOTENCY_RESERVE: (
        AuditDecisionResult.ALLOW,
        frozenset({AuditReason.RESERVED, AuditReason.EXPIRED_REPLACED}),
    ),
    AuditAction.IDEMPOTENCY_REPLAY: (AuditDecisionResult.REPLAY, frozenset({AuditReason.REPLAYED})),
    AuditAction.IDEMPOTENCY_CONFLICT: (
        AuditDecisionResult.CONFLICT,
        frozenset({AuditReason.REQUEST_MISMATCH, AuditReason.COMPLETION_MISMATCH}),
    ),
    AuditAction.IDEMPOTENCY_COMPLETE: (
        AuditDecisionResult.ALLOW,
        frozenset({AuditReason.COMPLETED}),
    ),
    AuditAction.IDEMPOTENCY_FAIL: (AuditDecisionResult.RECORD, frozenset({AuditReason.FAILED})),
}


def _obs_enum(value: object, enum_cls: type[object], field: str) -> None:
    try:
        require_exact_enum(value, enum_cls, field)
    except DomainInvariantError as exc:
        raise ObservabilityError(exc.field, exc.code) from exc


def _obs_utc(value: object, field: str) -> datetime:
    try:
        return require_utc(value, field)
    except DomainInvariantError as exc:
        raise ObservabilityError(exc.field, exc.code) from exc


def _closed_reason(value: object) -> AuditReason:
    if type(value) is not AuditReason:
        raise ObservabilityError("reason_code", "must_be_closed")
    return value


def _domain_reason(code: str) -> AuditReason:
    try:
        return AuditReason(code)
    except ValueError as exc:
        raise ObservabilityError("reason_code", "must_be_closed") from exc


def _require_resource_id(resource_type: AuditResourceType, resource_id: object) -> str:
    if not isinstance(resource_id, str) or isinstance(resource_id, bool):
        raise ObservabilityError("resource_id", "must_be_string")
    try:
        if resource_type in {AuditResourceType.PURCHASE_INTENT, AuditResourceType.DISCLOSURE}:
            IntentId(resource_id)
        elif resource_type is AuditResourceType.OFFER:
            OfferId(resource_id)
        elif resource_type is AuditResourceType.TRANSACTION:
            if resource_id != UNBOUND_TRANSACTION_ID:
                AcceptanceId(resource_id)
        elif resource_type is AuditResourceType.REQUIREMENT:
            RequirementId(resource_id)
        elif resource_type is AuditResourceType.APPROVAL:
            ApprovalId(resource_id)
        elif resource_type is AuditResourceType.IDEMPOTENCY:
            IdempotencyKey(resource_id)
        elif resource_type is AuditResourceType.ISOLATION:
            IsolationAuditRef(resource_id)
        else:
            raise ObservabilityError("resource_type", "unsupported")
    except DomainInvariantError as exc:
        raise ObservabilityError("resource_id", "invalid_opaque_syntax") from exc
    return resource_id


def _assert_compatible(
    action: AuditAction,
    decision: AuditDecisionResult,
    reasons: tuple[AuditReason, ...],
) -> None:
    try:
        event_type = EventType(action.value)
    except ValueError:
        event_type = None
    if event_type is not None:
        if decision is not AuditDecisionResult.RECORD:
            raise ObservabilityError("decision", "incompatible")
        permitted = EVENT_SPECS[event_type].reason_codes
        for reason in reasons:
            if reason.value not in permitted:
                raise ObservabilityError("reason_code", "incompatible")
        return
    spec = _GOVERNANCE_COMPAT.get(action)
    if spec is None:
        raise ObservabilityError("action", "unsupported")
    expected_decision, permitted_reasons = spec
    if decision is not expected_decision:
        raise ObservabilityError("decision", "incompatible")
    for reason in reasons:
        if reason not in permitted_reasons:
            raise ObservabilityError("reason_code", "incompatible")


@dataclass(frozen=True, slots=True)
class AuditRecord:
    event_id: str
    occurred_at: datetime
    actor_type: ActorType
    actor_id: ActorId
    action: AuditAction
    resource_type: AuditResourceType
    resource_id: str
    resource_version: Version
    decision: AuditDecisionResult
    policy_id: str
    policy_version: str
    reason_codes: tuple[AuditReason, ...]
    correlation_id: CorrelationId
    redaction_profile: str
    event_hash: PayloadHash
    payload_hash: PayloadHash | None = None
    approval_id: ApprovalId | None = None
    provider_label: ProviderLabel | None = None
    simulation: bool | None = None
    previous_event_hash: PayloadHash | None = None
    signature_handle: SignatureHandle | None = None

    def __post_init__(self) -> None:
        AuditEventId(self.event_id)
        _obs_enum(self.actor_type, ActorType, "actor_type")
        _obs_enum(self.action, AuditAction, "action")
        _obs_enum(self.resource_type, AuditResourceType, "resource_type")
        _obs_enum(self.decision, AuditDecisionResult, "decision")
        if type(self.actor_id) is not ActorId:
            raise ObservabilityError("actor_id", "invalid_opaque_syntax")
        if type(self.correlation_id) is not CorrelationId:
            raise ObservabilityError("correlation_id", "invalid_opaque_syntax")
        if type(self.resource_version) is not Version:
            raise ObservabilityError("resource_version", "invalid_type")
        if type(self.event_hash) is not PayloadHash:
            raise ObservabilityError("event_hash", "invalid_type")
        if self.payload_hash is not None and type(self.payload_hash) is not PayloadHash:
            raise ObservabilityError("payload_hash", "invalid_type")
        if (
            self.previous_event_hash is not None
            and type(self.previous_event_hash) is not PayloadHash
        ):
            raise ObservabilityError("previous_event_hash", "invalid_type")
        if self.approval_id is not None and type(self.approval_id) is not ApprovalId:
            raise ObservabilityError("approval_id", "invalid_opaque_syntax")
        if self.signature_handle is not None and type(self.signature_handle) is not SignatureHandle:
            raise ObservabilityError("signature_handle", "invalid_opaque_syntax")
        object.__setattr__(self, "occurred_at", _obs_utc(self.occurred_at, "occurred_at"))
        object.__setattr__(
            self, "resource_id", _require_resource_id(self.resource_type, self.resource_id)
        )
        if self.policy_id != POLICY_ID or self.policy_version != POLICY_VERSION:
            raise ObservabilityError("policy_id", "unsupported")
        if self.redaction_profile != REDACTION_PROFILE:
            raise ObservabilityError("redaction_profile", "unsupported")
        if self.provider_label is not None:
            _obs_enum(self.provider_label, ProviderLabel, "provider_label")
        if self.simulation is not None and self.simulation is not True:
            raise ObservabilityError("simulation", "must_be_true_or_absent")
        if not self.reason_codes:
            raise ObservabilityError("reason_codes", "required")
        reasons = tuple(_closed_reason(item) for item in self.reason_codes)
        object.__setattr__(self, "reason_codes", reasons)
        _assert_compatible(self.action, self.decision, reasons)


def audit_hash_material(record: AuditRecord) -> dict[str, object]:
    payload: dict[str, object] = {
        "eventId": record.event_id,
        "occurredAt": format_utc(record.occurred_at),
        "actorType": record.actor_type.value,
        "actorId": record.actor_id.to_primitive(),
        "action": record.action.value,
        "resourceType": record.resource_type.value,
        "resourceId": record.resource_id,
        "resourceVersion": record.resource_version.to_primitive(),
        "decision": record.decision.value,
        "policyId": record.policy_id,
        "policyVersion": record.policy_version,
        "reasonCodes": [item.value for item in record.reason_codes],
        "correlationId": record.correlation_id.to_primitive(),
        "redactionProfile": record.redaction_profile,
    }
    optional: dict[str, object | None] = {
        "payloadHash": None if record.payload_hash is None else record.payload_hash.to_primitive(),
        "approvalId": None if record.approval_id is None else record.approval_id.to_primitive(),
        "providerLabel": None if record.provider_label is None else record.provider_label.value,
        "simulation": record.simulation,
        "previousEventHash": (
            None
            if record.previous_event_hash is None
            else record.previous_event_hash.to_primitive()
        ),
    }
    for key, value in optional.items():
        if value is not None:
            payload[key] = value
    return payload


def project_domain_event(
    event: DomainEvent,
    *,
    event_id: str,
    event_hash: PayloadHash,
    previous_event_hash: PayloadHash | None = None,
) -> AuditRecord:
    action = _EVENT_TYPE_TO_ACTION.get(event.event_type)
    if action is None:
        raise ObservabilityError("event_type", "unsupported")
    resource_type = _RESOURCE_MAP[event.resource_type]
    payload_hash = None if event.payload_hash is None else PayloadHash(event.payload_hash)
    approval_id = None if event.approval_id is None else ApprovalId(event.approval_id)
    return AuditRecord(
        event_id=event_id,
        occurred_at=event.occurred_at,
        actor_type=event.actor_type,
        actor_id=ActorId(event.actor_id),
        action=action,
        resource_type=resource_type,
        resource_id=event.resource_id,
        resource_version=Version(event.resource_version),
        decision=AuditDecisionResult.RECORD,
        policy_id=POLICY_ID,
        policy_version=POLICY_VERSION,
        reason_codes=(_domain_reason(event.reason_code),),
        correlation_id=CorrelationId(event.correlation_id),
        redaction_profile=REDACTION_PROFILE,
        event_hash=event_hash,
        payload_hash=payload_hash,
        approval_id=approval_id,
        simulation=event.simulation,
        previous_event_hash=previous_event_hash,
    )


def governance_record(
    *,
    event_id: str,
    occurred_at: datetime,
    actor_type: ActorType,
    actor_id: ActorId,
    action: AuditAction,
    resource_type: AuditResourceType,
    resource_id: str,
    resource_version: Version,
    decision: AuditDecisionResult,
    reason_codes: tuple[AuditReason, ...],
    correlation_id: CorrelationId,
    event_hash: PayloadHash,
    payload_hash: PayloadHash | None = None,
    approval_id: ApprovalId | None = None,
    simulation: bool | None = None,
    previous_event_hash: PayloadHash | None = None,
    provider_label: ProviderLabel | None = None,
) -> AuditRecord:
    return AuditRecord(
        event_id=event_id,
        occurred_at=occurred_at,
        actor_type=actor_type,
        actor_id=actor_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        resource_version=resource_version,
        decision=decision,
        policy_id=POLICY_ID,
        policy_version=POLICY_VERSION,
        reason_codes=reason_codes,
        correlation_id=correlation_id,
        redaction_profile=REDACTION_PROFILE,
        event_hash=event_hash,
        payload_hash=payload_hash,
        approval_id=approval_id,
        provider_label=provider_label,
        simulation=simulation,
        previous_event_hash=previous_event_hash,
    )


def record_as_mapping(record: AuditRecord) -> Mapping[str, object]:
    material = audit_hash_material(record)
    material["eventHash"] = record.event_hash.to_primitive()
    if record.signature_handle is not None:
        material["signatureHandle"] = record.signature_handle.to_primitive()
    return material
