"""Typed A1–A4 approval grants and exact validation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from itaa_domain.errors import DomainInvariantError
from itaa_domain.identifiers import (
    AcceptanceId,
    ActorId,
    ApprovalId,
    CorrelationId,
    IntentId,
    OfferId,
    RequirementId,
    SupplierToken,
)
from itaa_domain.value_objects import (
    ActorRef,
    ActorType,
    AuthorizationAction,
    AuthorizationMode,
    Money,
    PayloadHash,
    Version,
    require_exact_enum,
    require_utc,
)
from itaa_policy.disclosure import MAX_RECIPIENTS
from itaa_policy.errors import PolicyError


class ApprovalKind(StrEnum):
    REQUIREMENT_CONFIRMATION = "REQUIREMENT_CONFIRMATION"
    PURCHASE_INTENT_DISPATCH = "PURCHASE_INTENT_DISPATCH"
    OFFER_ACCEPTANCE = "OFFER_ACCEPTANCE"
    TRANSACTION_AUTHORIZATION = "TRANSACTION_AUTHORIZATION"


class ApprovalPurpose(StrEnum):
    REQUIREMENT_CONFIRMATION = "requirement_confirmation"
    PURCHASE_INTENT_DISPATCH = "purchase_intent_dispatch"
    OFFER_ACCEPTANCE = "offer_acceptance"
    TRANSACTION_AUTHORIZATION = "transaction_authorization"


class ApprovalStatus(StrEnum):
    ACTIVE = "active"
    REVOKED = "revoked"
    SUPERSEDED = "superseded"


class ApprovalResourceType(StrEnum):
    REQUIREMENT = "requirement"
    PURCHASE_INTENT = "purchase_intent"
    OFFER = "offer"
    TRANSACTION = "transaction"


class ApprovalDenyReason(StrEnum):
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


_KIND_PURPOSE = {
    ApprovalKind.REQUIREMENT_CONFIRMATION: ApprovalPurpose.REQUIREMENT_CONFIRMATION,
    ApprovalKind.PURCHASE_INTENT_DISPATCH: ApprovalPurpose.PURCHASE_INTENT_DISPATCH,
    ApprovalKind.OFFER_ACCEPTANCE: ApprovalPurpose.OFFER_ACCEPTANCE,
    ApprovalKind.TRANSACTION_AUTHORIZATION: ApprovalPurpose.TRANSACTION_AUTHORIZATION,
}
_KIND_RESOURCE = {
    ApprovalKind.REQUIREMENT_CONFIRMATION: ApprovalResourceType.REQUIREMENT,
    ApprovalKind.PURCHASE_INTENT_DISPATCH: ApprovalResourceType.PURCHASE_INTENT,
    ApprovalKind.OFFER_ACCEPTANCE: ApprovalResourceType.OFFER,
    ApprovalKind.TRANSACTION_AUTHORIZATION: ApprovalResourceType.TRANSACTION,
}


def _policy_enum(value: object, enum_cls: type[object], field: str) -> None:
    try:
        require_exact_enum(value, enum_cls, field)
    except DomainInvariantError as exc:
        raise PolicyError(exc.field, exc.code) from exc


def _policy_utc(value: object, field: str) -> datetime:
    try:
        return require_utc(value, field)
    except DomainInvariantError as exc:
        raise PolicyError(exc.field, exc.code) from exc


def _require_type(value: object, expected: type[object], field: str) -> None:
    if type(value) is not expected:
        raise PolicyError(field, "invalid_type")


def _require_money(amount: object, currency: object) -> Money:
    try:
        return Money(amount, currency)  # type: ignore[arg-type]
    except DomainInvariantError as exc:
        raise PolicyError(exc.field, exc.code) from exc


def _require_deadline(issued: datetime, expires: datetime, deadline: datetime, field: str) -> None:
    instant = _policy_utc(deadline, field)
    if not (issued < instant <= expires):
        raise PolicyError(field, "incoherent_window")


def _require_resource_id(resource_type: ApprovalResourceType, resource_id: object) -> str:
    if not isinstance(resource_id, str) or isinstance(resource_id, bool):
        raise PolicyError("resource_id", "must_be_string")
    try:
        if resource_type is ApprovalResourceType.REQUIREMENT:
            parsed: RequirementId | IntentId | OfferId | AcceptanceId = RequirementId(resource_id)
        elif resource_type is ApprovalResourceType.PURCHASE_INTENT:
            parsed = IntentId(resource_id)
        elif resource_type is ApprovalResourceType.OFFER:
            parsed = OfferId(resource_id)
        else:
            parsed = AcceptanceId(resource_id)
    except DomainInvariantError as exc:
        raise PolicyError("resource_id", "invalid_opaque_syntax") from exc
    return parsed.to_primitive()


def _require_optional_hash(value: object, field: str) -> None:
    if value is not None:
        _require_type(value, PayloadHash, field)


def _require_optional_version(value: object, field: str) -> None:
    if value is not None:
        _require_type(value, Version, field)


@dataclass(frozen=True, slots=True)
class ApprovalGrant:
    approval_id: ApprovalId
    kind: ApprovalKind
    purpose: ApprovalPurpose
    actor: ActorRef
    owner_id: ActorId
    resource_type: ApprovalResourceType
    resource_id: str
    resource_version: Version
    payload_hash: PayloadHash
    issued_at: datetime
    expires_at: datetime
    status: ApprovalStatus
    correlation_id: CorrelationId
    simulation: bool | None = None
    content_hash: PayloadHash | None = None
    manifest_hash: PayloadHash | None = None
    recipient_count: int | None = None
    solicitation_expires_at: datetime | None = None
    intent_id: IntentId | None = None
    offer_id: OfferId | None = None
    offer_version: Version | None = None
    terms_hash: PayloadHash | None = None
    offer_valid_until: datetime | None = None
    acceptance_id: AcceptanceId | None = None
    action: AuthorizationAction | None = None
    amount_minor: int | None = None
    currency: str | None = None
    supplier_token: SupplierToken | None = None
    mode: AuthorizationMode | None = None
    request_hash: PayloadHash | None = None
    decision_expires_at: datetime | None = None

    def __post_init__(self) -> None:
        _policy_enum(self.kind, ApprovalKind, "kind")
        _policy_enum(self.purpose, ApprovalPurpose, "purpose")
        _policy_enum(self.status, ApprovalStatus, "status")
        _policy_enum(self.resource_type, ApprovalResourceType, "resource_type")
        _require_type(self.approval_id, ApprovalId, "approval_id")
        _require_type(self.actor, ActorRef, "actor")
        if self.actor.category is not ActorType.BUYER:
            raise PolicyError("actor", "must_be_buyer")
        _require_type(self.owner_id, ActorId, "owner_id")
        if self.actor.actor_id != self.owner_id:
            raise PolicyError("owner_id", "must_match_actor")
        if _KIND_PURPOSE[self.kind] is not self.purpose:
            raise PolicyError("purpose", "kind_mismatch")
        if _KIND_RESOURCE[self.kind] is not self.resource_type:
            raise PolicyError("resource_type", "kind_mismatch")
        object.__setattr__(
            self, "resource_id", _require_resource_id(self.resource_type, self.resource_id)
        )
        _require_type(self.resource_version, Version, "resource_version")
        _require_type(self.payload_hash, PayloadHash, "payload_hash")
        _require_type(self.correlation_id, CorrelationId, "correlation_id")
        issued = _policy_utc(self.issued_at, "issued_at")
        expires = _policy_utc(self.expires_at, "expires_at")
        if expires <= issued:
            raise PolicyError("expires_at", "must_follow_issued")
        if self.status is not ApprovalStatus.ACTIVE:
            raise PolicyError("status", "must_be_active")
        object.__setattr__(self, "issued_at", issued)
        object.__setattr__(self, "expires_at", expires)
        _validate_kind_fields(self)


@dataclass(frozen=True, slots=True)
class ApprovalRevocation:
    revocation_id: ApprovalId
    target_id: ApprovalId
    occurred_at: datetime
    correlation_id: CorrelationId

    def __post_init__(self) -> None:
        _require_type(self.revocation_id, ApprovalId, "revocation_id")
        _require_type(self.target_id, ApprovalId, "target_id")
        if self.revocation_id == self.target_id:
            raise PolicyError("revocation_id", "must_be_distinct")
        _require_type(self.correlation_id, CorrelationId, "correlation_id")
        object.__setattr__(self, "occurred_at", _policy_utc(self.occurred_at, "occurred_at"))


def _validate_kind_fields(grant: ApprovalGrant) -> None:
    if grant.kind is ApprovalKind.REQUIREMENT_CONFIRMATION:
        _forbid_a2(grant)
        _forbid_a3(grant)
        _forbid_a4(grant)
        return
    if grant.kind is ApprovalKind.PURCHASE_INTENT_DISPATCH:
        _require_type(grant.content_hash, PayloadHash, "content_hash")
        _require_type(grant.manifest_hash, PayloadHash, "manifest_hash")
        if grant.payload_hash != grant.manifest_hash:
            raise PolicyError("payload_hash", "must_equal_manifest")
        if (
            not isinstance(grant.recipient_count, int)
            or isinstance(grant.recipient_count, bool)
            or grant.recipient_count < 1
            or grant.recipient_count > MAX_RECIPIENTS
        ):
            raise PolicyError("recipient_count", "out_of_range")
        if grant.solicitation_expires_at is None:
            raise PolicyError("solicitation_expires_at", "required")
        _require_deadline(
            grant.issued_at,
            grant.expires_at,
            grant.solicitation_expires_at,
            "solicitation_expires_at",
        )
        _forbid_a3(grant)
        _forbid_a4(grant)
        return
    if grant.kind is ApprovalKind.OFFER_ACCEPTANCE:
        _require_type(grant.intent_id, IntentId, "intent_id")
        _require_type(grant.offer_id, OfferId, "offer_id")
        _require_type(grant.offer_version, Version, "offer_version")
        assert grant.offer_id is not None
        if grant.offer_id.to_primitive() != grant.resource_id:
            raise PolicyError("offer_id", "resource_mismatch")
        _require_type(grant.terms_hash, PayloadHash, "terms_hash")
        if grant.payload_hash != grant.terms_hash:
            raise PolicyError("terms_hash", "required")
        if grant.offer_valid_until is None:
            raise PolicyError("offer_valid_until", "required")
        _require_deadline(
            grant.issued_at, grant.expires_at, grant.offer_valid_until, "offer_valid_until"
        )
        _forbid_a2(grant)
        _forbid_a4(grant)
        return
    if grant.simulation is not True or grant.mode is not AuthorizationMode.SIMULATED:
        raise PolicyError("mode", "must_be_simulated")
    _policy_enum(grant.action, AuthorizationAction, "action")
    if grant.action is not AuthorizationAction.RESERVE_PARKING:
        raise PolicyError("action", "must_be_reserve_parking")
    _require_type(grant.acceptance_id, AcceptanceId, "acceptance_id")
    _require_type(grant.request_hash, PayloadHash, "request_hash")
    _require_type(grant.supplier_token, SupplierToken, "supplier_token")
    assert grant.acceptance_id is not None
    if grant.acceptance_id.to_primitive() != grant.resource_id:
        raise PolicyError("resource_id", "must_equal_acceptance")
    if grant.payload_hash != grant.request_hash:
        raise PolicyError("request_hash", "mismatch")
    if grant.amount_minor is None or grant.currency is None or grant.decision_expires_at is None:
        raise PolicyError("amount_minor", "required")
    _require_money(grant.amount_minor, grant.currency)
    _require_deadline(
        grant.issued_at, grant.expires_at, grant.decision_expires_at, "decision_expires_at"
    )
    _forbid_a2(grant)
    _forbid_a3(grant)


def _forbid_a4_fields(
    *,
    acceptance_id: object,
    action: object,
    amount_minor: object,
    currency: object,
    supplier_token: object,
    mode: object,
    request_hash: object,
    decision_expires_at: object,
    simulation: object = None,
) -> None:
    if any(
        item is not None
        for item in (
            acceptance_id,
            action,
            amount_minor,
            currency,
            supplier_token,
            mode,
            request_hash,
            decision_expires_at,
        )
    ):
        raise PolicyError("a4_fields", "must_be_absent")
    if simulation is not None:
        raise PolicyError("simulation", "must_be_absent")


def _forbid_a2(grant: ApprovalGrant) -> None:
    if any(
        item is not None
        for item in (
            grant.content_hash,
            grant.manifest_hash,
            grant.recipient_count,
            grant.solicitation_expires_at,
        )
    ):
        raise PolicyError("a2_fields", "must_be_absent")


def _forbid_a3(grant: ApprovalGrant) -> None:
    if (
        any(
            item is not None
            for item in (
                grant.offer_id,
                grant.offer_version,
                grant.terms_hash,
                grant.offer_valid_until,
            )
        )
        and grant.kind is not ApprovalKind.OFFER_ACCEPTANCE
    ):
        raise PolicyError("a3_fields", "must_be_absent")
    if grant.kind is not ApprovalKind.OFFER_ACCEPTANCE and grant.intent_id is not None:
        raise PolicyError("intent_id", "must_be_absent")


def _forbid_a4(grant: ApprovalGrant) -> None:
    _forbid_a4_fields(
        acceptance_id=grant.acceptance_id,
        action=grant.action,
        amount_minor=grant.amount_minor,
        currency=grant.currency,
        supplier_token=grant.supplier_token,
        mode=grant.mode,
        request_hash=grant.request_hash,
        decision_expires_at=grant.decision_expires_at,
        simulation=grant.simulation,
    )


def _validate_request_kind_fields(request: ApprovalRequest) -> None:
    if request.kind is ApprovalKind.REQUIREMENT_CONFIRMATION:
        _forbid_a2_request(request)
        _forbid_a3_request(request)
        _forbid_a4_request(request)
        if request.prior_approval_ids:
            raise PolicyError("prior_approval_ids", "must_be_absent")
        return
    if request.kind is ApprovalKind.PURCHASE_INTENT_DISPATCH:
        _require_type(request.content_hash, PayloadHash, "content_hash")
        _require_type(request.manifest_hash, PayloadHash, "manifest_hash")
        if request.payload_hash != request.manifest_hash:
            raise PolicyError("payload_hash", "must_equal_manifest")
        if request.recipient_count is None:
            raise PolicyError("recipient_count", "required")
        if request.solicitation_expires_at is None:
            raise PolicyError("solicitation_expires_at", "required")
        _forbid_a3_request(request)
        _forbid_a4_request(request)
        if request.prior_approval_ids:
            raise PolicyError("prior_approval_ids", "must_be_absent")
        return
    if request.kind is ApprovalKind.OFFER_ACCEPTANCE:
        _require_type(request.intent_id, IntentId, "intent_id")
        _require_type(request.offer_id, OfferId, "offer_id")
        _require_type(request.offer_version, Version, "offer_version")
        assert request.offer_id is not None
        if request.offer_id.to_primitive() != request.resource_id:
            raise PolicyError("offer_id", "resource_mismatch")
        _require_type(request.terms_hash, PayloadHash, "terms_hash")
        if request.payload_hash != request.terms_hash:
            raise PolicyError("terms_hash", "required")
        if request.offer_valid_until is None:
            raise PolicyError("offer_valid_until", "required")
        _forbid_a2_request(request)
        _forbid_a4_request(request)
        if request.prior_approval_ids:
            raise PolicyError("prior_approval_ids", "must_be_absent")
        return
    if request.mode is not AuthorizationMode.SIMULATED:
        raise PolicyError("mode", "must_be_simulated")
    _policy_enum(request.action, AuthorizationAction, "action")
    if request.action is not AuthorizationAction.RESERVE_PARKING:
        raise PolicyError("action", "must_be_reserve_parking")
    _require_type(request.acceptance_id, AcceptanceId, "acceptance_id")
    _require_type(request.request_hash, PayloadHash, "request_hash")
    _require_type(request.supplier_token, SupplierToken, "supplier_token")
    assert request.acceptance_id is not None
    if request.acceptance_id.to_primitive() != request.resource_id:
        raise PolicyError("resource_id", "must_equal_acceptance")
    if request.payload_hash != request.request_hash:
        raise PolicyError("request_hash", "mismatch")
    if (
        request.amount_minor is None
        or request.currency is None
        or request.decision_expires_at is None
    ):
        raise PolicyError("amount_minor", "required")
    _require_money(request.amount_minor, request.currency)
    _forbid_a2_request(request)
    _forbid_a3_request(request)


def _forbid_a2_request(request: ApprovalRequest) -> None:
    if any(
        item is not None
        for item in (
            request.content_hash,
            request.manifest_hash,
            request.recipient_count,
            request.solicitation_expires_at,
        )
    ):
        raise PolicyError("a2_fields", "must_be_absent")


def _forbid_a3_request(request: ApprovalRequest) -> None:
    if any(
        item is not None
        for item in (
            request.offer_id,
            request.offer_version,
            request.terms_hash,
            request.offer_valid_until,
        )
    ):
        raise PolicyError("a3_fields", "must_be_absent")
    if request.intent_id is not None:
        raise PolicyError("intent_id", "must_be_absent")


def _forbid_a4_request(request: ApprovalRequest) -> None:
    _forbid_a4_fields(
        acceptance_id=request.acceptance_id,
        action=request.action,
        amount_minor=request.amount_minor,
        currency=request.currency,
        supplier_token=request.supplier_token,
        mode=request.mode,
        request_hash=request.request_hash,
        decision_expires_at=request.decision_expires_at,
    )


@dataclass(frozen=True, slots=True)
class ApprovalRequest:
    kind: ApprovalKind
    purpose: ApprovalPurpose
    actor: ActorRef
    owner_id: ActorId
    resource_type: ApprovalResourceType
    resource_id: str
    resource_version: Version
    payload_hash: PayloadHash
    occurred_at: datetime
    content_hash: PayloadHash | None = None
    manifest_hash: PayloadHash | None = None
    recipient_count: int | None = None
    solicitation_expires_at: datetime | None = None
    intent_id: IntentId | None = None
    offer_id: OfferId | None = None
    offer_version: Version | None = None
    terms_hash: PayloadHash | None = None
    offer_valid_until: datetime | None = None
    acceptance_id: AcceptanceId | None = None
    action: AuthorizationAction | None = None
    amount_minor: int | None = None
    currency: str | None = None
    supplier_token: SupplierToken | None = None
    mode: AuthorizationMode | None = None
    request_hash: PayloadHash | None = None
    decision_expires_at: datetime | None = None
    prior_approval_ids: frozenset[ApprovalId] = frozenset()

    def __post_init__(self) -> None:
        _policy_enum(self.kind, ApprovalKind, "kind")
        _policy_enum(self.purpose, ApprovalPurpose, "purpose")
        _policy_enum(self.resource_type, ApprovalResourceType, "resource_type")
        _require_type(self.actor, ActorRef, "actor")
        _require_type(self.owner_id, ActorId, "owner_id")
        object.__setattr__(
            self, "resource_id", _require_resource_id(self.resource_type, self.resource_id)
        )
        _require_type(self.resource_version, Version, "resource_version")
        _require_type(self.payload_hash, PayloadHash, "payload_hash")
        object.__setattr__(self, "occurred_at", _policy_utc(self.occurred_at, "occurred_at"))
        _require_optional_hash(self.content_hash, "content_hash")
        _require_optional_hash(self.manifest_hash, "manifest_hash")
        _require_optional_hash(self.terms_hash, "terms_hash")
        _require_optional_hash(self.request_hash, "request_hash")
        _require_optional_version(self.offer_version, "offer_version")
        if self.intent_id is not None:
            _require_type(self.intent_id, IntentId, "intent_id")
        if self.offer_id is not None:
            _require_type(self.offer_id, OfferId, "offer_id")
        if self.acceptance_id is not None:
            _require_type(self.acceptance_id, AcceptanceId, "acceptance_id")
        if self.supplier_token is not None:
            _require_type(self.supplier_token, SupplierToken, "supplier_token")
        if self.action is not None:
            _policy_enum(self.action, AuthorizationAction, "action")
        if self.mode is not None:
            _policy_enum(self.mode, AuthorizationMode, "mode")
        if self.amount_minor is not None or self.currency is not None:
            _require_money(self.amount_minor, self.currency)
        if self.solicitation_expires_at is not None:
            object.__setattr__(
                self,
                "solicitation_expires_at",
                _policy_utc(self.solicitation_expires_at, "solicitation_expires_at"),
            )
        if self.offer_valid_until is not None:
            object.__setattr__(
                self, "offer_valid_until", _policy_utc(self.offer_valid_until, "offer_valid_until")
            )
        if self.decision_expires_at is not None:
            object.__setattr__(
                self,
                "decision_expires_at",
                _policy_utc(self.decision_expires_at, "decision_expires_at"),
            )
        if self.recipient_count is not None and (
            not isinstance(self.recipient_count, int)
            or isinstance(self.recipient_count, bool)
            or self.recipient_count < 1
            or self.recipient_count > MAX_RECIPIENTS
        ):
            raise PolicyError("recipient_count", "out_of_range")
        if type(self.prior_approval_ids) is not frozenset:
            raise PolicyError("prior_approval_ids", "must_be_frozenset")
        for item in self.prior_approval_ids:
            _require_type(item, ApprovalId, "prior_approval_ids")
        if (
            self.kind is ApprovalKind.TRANSACTION_AUTHORIZATION
            and self.acceptance_id is not None
            and self.acceptance_id.to_primitive() != self.resource_id
        ):
            raise PolicyError("resource_id", "must_equal_acceptance")
        _validate_request_kind_fields(self)


@dataclass(frozen=True, slots=True)
class ApprovalDecision:
    allowed: bool
    reason: ApprovalDenyReason
    approval_id: ApprovalId | None
    kind: ApprovalKind | None

    def __post_init__(self) -> None:
        _policy_enum(self.reason, ApprovalDenyReason, "reason")
        if self.allowed is not (self.reason is ApprovalDenyReason.ALLOWED):
            raise PolicyError("allowed", "reason_mismatch")


def validate_approval(grant: ApprovalGrant | None, request: ApprovalRequest) -> ApprovalDecision:
    if type(request.kind) is not ApprovalKind:
        return ApprovalDecision(False, ApprovalDenyReason.UNKNOWN_KIND, None, None)
    if type(request.purpose) is not ApprovalPurpose:
        return ApprovalDecision(False, ApprovalDenyReason.PURPOSE_MISMATCH, None, request.kind)
    occurred = _policy_utc(request.occurred_at, "occurred_at")
    if grant is None:
        return ApprovalDecision(False, ApprovalDenyReason.MISSING, None, request.kind)
    if grant.status is not ApprovalStatus.ACTIVE:
        return ApprovalDecision(False, ApprovalDenyReason.INACTIVE, grant.approval_id, grant.kind)
    if occurred < grant.issued_at:
        return ApprovalDecision(
            False, ApprovalDenyReason.NOT_YET_VALID, grant.approval_id, grant.kind
        )
    if occurred >= grant.expires_at:
        return ApprovalDecision(False, ApprovalDenyReason.EXPIRED, grant.approval_id, grant.kind)
    if grant.kind is not request.kind:
        return ApprovalDecision(
            False, ApprovalDenyReason.KIND_MISMATCH, grant.approval_id, grant.kind
        )
    if grant.purpose is not request.purpose:
        return ApprovalDecision(
            False, ApprovalDenyReason.PURPOSE_MISMATCH, grant.approval_id, grant.kind
        )
    if grant.actor != request.actor:
        return ApprovalDecision(
            False, ApprovalDenyReason.ACTOR_MISMATCH, grant.approval_id, grant.kind
        )
    if grant.owner_id != request.owner_id:
        return ApprovalDecision(
            False, ApprovalDenyReason.OWNER_MISMATCH, grant.approval_id, grant.kind
        )
    if grant.resource_type is not request.resource_type or grant.resource_id != request.resource_id:
        return ApprovalDecision(
            False, ApprovalDenyReason.RESOURCE_MISMATCH, grant.approval_id, grant.kind
        )
    if grant.resource_version != request.resource_version:
        return ApprovalDecision(
            False, ApprovalDenyReason.VERSION_MISMATCH, grant.approval_id, grant.kind
        )
    if grant.payload_hash != request.payload_hash:
        return ApprovalDecision(
            False, ApprovalDenyReason.HASH_MISMATCH, grant.approval_id, grant.kind
        )
    extra = _validate_kind_request(grant, request, occurred)
    if extra is not ApprovalDenyReason.ALLOWED:
        return ApprovalDecision(False, extra, grant.approval_id, grant.kind)
    return ApprovalDecision(True, ApprovalDenyReason.ALLOWED, grant.approval_id, grant.kind)


def _validate_kind_request(
    grant: ApprovalGrant,
    request: ApprovalRequest,
    occurred: datetime,
) -> ApprovalDenyReason:
    if grant.kind is ApprovalKind.PURCHASE_INTENT_DISPATCH:
        if (
            grant.content_hash != request.content_hash
            or grant.manifest_hash != request.manifest_hash
        ):
            return ApprovalDenyReason.HASH_MISMATCH
        if grant.recipient_count != request.recipient_count:
            return ApprovalDenyReason.RECIPIENT_COUNT_MISMATCH
        if grant.solicitation_expires_at != request.solicitation_expires_at:
            return ApprovalDenyReason.HASH_MISMATCH
        deadline = grant.solicitation_expires_at
        if deadline is None or occurred >= deadline:
            return ApprovalDenyReason.DEADLINE_PASSED
        return ApprovalDenyReason.ALLOWED
    if grant.kind is ApprovalKind.OFFER_ACCEPTANCE:
        if grant.intent_id != request.intent_id or grant.offer_id != request.offer_id:
            return ApprovalDenyReason.RESOURCE_MISMATCH
        if grant.offer_version != request.offer_version:
            return ApprovalDenyReason.VERSION_MISMATCH
        if grant.terms_hash != request.terms_hash:
            return ApprovalDenyReason.HASH_MISMATCH
        if grant.offer_valid_until != request.offer_valid_until:
            return ApprovalDenyReason.HASH_MISMATCH
        deadline = grant.offer_valid_until
        if deadline is None or occurred >= deadline:
            return ApprovalDenyReason.DEADLINE_PASSED
        return ApprovalDenyReason.ALLOWED
    if grant.kind is ApprovalKind.TRANSACTION_AUTHORIZATION:
        if grant.approval_id in request.prior_approval_ids:
            return ApprovalDenyReason.APPROVAL_REUSED
        if (
            request.mode is not AuthorizationMode.SIMULATED
            or grant.mode is not AuthorizationMode.SIMULATED
        ):
            return ApprovalDenyReason.MODE_FORBIDDEN
        if (
            grant.action is not request.action
            or request.action is not AuthorizationAction.RESERVE_PARKING
        ):
            return ApprovalDenyReason.ACTION_MISMATCH
        try:
            grant_money = _require_money(grant.amount_minor, grant.currency)
            request_money = _require_money(request.amount_minor, request.currency)
        except PolicyError:
            return ApprovalDenyReason.AMOUNT_MISMATCH
        if grant_money.amount_minor != request_money.amount_minor:
            return ApprovalDenyReason.AMOUNT_MISMATCH
        if grant_money.currency != request_money.currency:
            return ApprovalDenyReason.CURRENCY_MISMATCH
        if grant.supplier_token != request.supplier_token:
            return ApprovalDenyReason.SUPPLIER_MISMATCH
        if (
            grant.acceptance_id != request.acceptance_id
            or grant.request_hash != request.request_hash
        ):
            return ApprovalDenyReason.HASH_MISMATCH
        if grant.decision_expires_at != request.decision_expires_at:
            return ApprovalDenyReason.HASH_MISMATCH
        deadline = grant.decision_expires_at
        if deadline is None or occurred >= deadline:
            return ApprovalDenyReason.DEADLINE_PASSED
        return ApprovalDenyReason.ALLOWED
    return ApprovalDenyReason.ALLOWED
