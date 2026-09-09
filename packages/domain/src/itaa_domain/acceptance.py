"""Immutable Acceptance snapshot. No competing Offer lifecycle."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from itaa_domain.errors import DomainInvariantError
from itaa_domain.identifiers import AcceptanceId, ApprovalId, IntentId, OfferId
from itaa_domain.value_objects import (
    AcceptanceStatus,
    PayloadHash,
    Version,
    format_utc,
    require_utc,
)


@dataclass(frozen=True, slots=True)
class Acceptance:
    acceptance_id: AcceptanceId
    intent_id: IntentId
    offer_id: OfferId
    offer_version: Version
    accepted_terms_hash: PayloadHash
    buyer_approval_id: ApprovalId
    created_at: datetime
    expires_at: datetime
    status: AcceptanceStatus = AcceptanceStatus.RECORDED

    def __post_init__(self) -> None:
        created = require_utc(self.created_at, "created_at")
        expires = require_utc(self.expires_at, "expires_at")
        if expires <= created:
            raise DomainInvariantError("expires_at", "must_follow_created_at")
        if self.status is not AcceptanceStatus.RECORDED:
            raise DomainInvariantError("status", "unsupported")
        object.__setattr__(self, "created_at", created)
        object.__setattr__(self, "expires_at", expires)

    @classmethod
    def record(
        cls,
        *,
        acceptance_id: AcceptanceId,
        intent_id: IntentId,
        offer_id: OfferId,
        offer_version: Version,
        accepted_terms_hash: PayloadHash,
        buyer_approval_id: ApprovalId,
        created_at: datetime,
        expires_at: datetime,
    ) -> Acceptance:
        return cls(
            acceptance_id=acceptance_id,
            intent_id=intent_id,
            offer_id=offer_id,
            offer_version=offer_version,
            accepted_terms_hash=accepted_terms_hash,
            buyer_approval_id=buyer_approval_id,
            created_at=created_at,
            expires_at=expires_at,
        )

    def is_expired_at(self, instant: datetime) -> bool:
        return require_utc(instant, "instant") >= self.expires_at

    def to_primitive(self) -> dict[str, object]:
        return {
            "acceptanceId": self.acceptance_id.to_primitive(),
            "intentId": self.intent_id.to_primitive(),
            "offerId": self.offer_id.to_primitive(),
            "offerVersion": self.offer_version.to_primitive(),
            "acceptedTermsHash": self.accepted_terms_hash.to_primitive(),
            "buyerApprovalId": self.buyer_approval_id.to_primitive(),
            "createdAt": format_utc(self.created_at),
            "expiresAt": format_utc(self.expires_at),
            "status": self.status.value,
        }
