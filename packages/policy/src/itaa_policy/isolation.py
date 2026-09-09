"""Supplier-specific invitation tokens, principals, and deny-by-default isolation."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from itaa_domain.identifiers import CROCKFORD_BODY, IntentId, SupplierToken
from itaa_domain.value_objects import require_exact_enum, require_utc
from itaa_policy.errors import PolicyError

_INVITATION_PREFIX = "iv_"


class SupplierCapability(StrEnum):
    INVITATION_READ = "invitation.read"
    OFFER_WRITE = "offer.write"
    COUNTEROFFER_WRITE = "counteroffer.write"


class IsolationReason(StrEnum):
    ALLOWED = "allowed"
    PRINCIPAL_MISMATCH = "principal_mismatch"
    INVITATION_MISMATCH = "invitation_mismatch"
    SCOPE_MISMATCH = "scope_mismatch"
    CAPABILITY_DENIED = "capability_denied"
    EXPIRED = "expired"
    NOT_YET_VALID = "not_yet_valid"
    UNKNOWN_CAPABILITY = "unknown_capability"
    UNREPRESENTABLE = "unrepresentable"


@dataclass(frozen=True, slots=True)
class SupplierInvitationToken:
    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str) or isinstance(self.value, bool):
            raise PolicyError("invitation_token", "must_be_string")
        if not re.fullmatch(_INVITATION_PREFIX + CROCKFORD_BODY, self.value):
            raise PolicyError("invitation_token", "invalid_opaque_syntax")

    def to_primitive(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class SupplierPrincipal:
    supplier_token: SupplierToken

    def __post_init__(self) -> None:
        if not isinstance(self.supplier_token, SupplierToken):
            raise PolicyError("supplier_token", "invalid_opaque_syntax")


@dataclass(frozen=True, slots=True)
class SupplierResourceScope:
    principal: SupplierPrincipal
    invitation: SupplierInvitationToken
    intent_id: IntentId
    capabilities: frozenset[SupplierCapability]
    valid_from: datetime
    valid_until: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.principal, SupplierPrincipal):
            raise PolicyError("principal", "invalid")
        if not isinstance(self.invitation, SupplierInvitationToken):
            raise PolicyError("invitation", "invalid_opaque_syntax")
        if not isinstance(self.intent_id, IntentId):
            raise PolicyError("intent_id", "invalid_opaque_syntax")
        start = require_utc(self.valid_from, "valid_from")
        end = require_utc(self.valid_until, "valid_until")
        if end <= start:
            raise PolicyError("valid_until", "must_follow_start")
        capabilities = frozenset(self.capabilities)
        if not capabilities:
            raise PolicyError("capabilities", "required")
        for item in capabilities:
            require_exact_enum(item, SupplierCapability, "capability")
        object.__setattr__(self, "capabilities", capabilities)
        object.__setattr__(self, "valid_from", start)
        object.__setattr__(self, "valid_until", end)


@dataclass(frozen=True, slots=True)
class IsolationDecision:
    allowed: bool
    reason: IsolationReason
    principal_ref: str
    invitation_ref: str
    intent_ref: str

    def __post_init__(self) -> None:
        require_exact_enum(self.reason, IsolationReason, "reason")
        if self.allowed is not (self.reason is IsolationReason.ALLOWED):
            raise PolicyError("allowed", "reason_mismatch")


def authorize_supplier(
    *,
    granted: SupplierResourceScope,
    principal: object,
    invitation: object,
    intent_id: object,
    capability: object,
    occurred_at: datetime,
) -> IsolationDecision:
    instant = require_utc(occurred_at, "occurred_at")
    refs = _safe_refs(granted)
    if type(capability) is not SupplierCapability:
        return IsolationDecision(False, IsolationReason.UNKNOWN_CAPABILITY, *refs)
    if type(principal) is not SupplierPrincipal:
        return IsolationDecision(False, IsolationReason.PRINCIPAL_MISMATCH, *refs)
    if type(invitation) is not SupplierInvitationToken:
        return IsolationDecision(False, IsolationReason.INVITATION_MISMATCH, *refs)
    if type(intent_id) is not IntentId:
        return IsolationDecision(False, IsolationReason.SCOPE_MISMATCH, *refs)
    if principal.supplier_token != granted.principal.supplier_token:
        return IsolationDecision(False, IsolationReason.PRINCIPAL_MISMATCH, *refs)
    if invitation != granted.invitation:
        return IsolationDecision(False, IsolationReason.INVITATION_MISMATCH, *refs)
    if intent_id != granted.intent_id:
        return IsolationDecision(False, IsolationReason.SCOPE_MISMATCH, *refs)
    if instant < granted.valid_from:
        return IsolationDecision(False, IsolationReason.NOT_YET_VALID, *refs)
    if instant >= granted.valid_until:
        return IsolationDecision(False, IsolationReason.EXPIRED, *refs)
    if capability not in granted.capabilities:
        return IsolationDecision(False, IsolationReason.CAPABILITY_DENIED, *refs)
    return IsolationDecision(True, IsolationReason.ALLOWED, *refs)


def deny_unrepresentable(granted: SupplierResourceScope) -> IsolationDecision:
    return IsolationDecision(False, IsolationReason.UNREPRESENTABLE, *_safe_refs(granted))


def _safe_refs(granted: SupplierResourceScope) -> tuple[str, str, str]:
    return (
        granted.principal.supplier_token.to_primitive(),
        granted.invitation.to_primitive(),
        granted.intent_id.to_primitive(),
    )
