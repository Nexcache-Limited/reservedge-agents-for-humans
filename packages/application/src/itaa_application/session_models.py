"""Immutable golden-path session and buyer-safe DTOs. No HTTP types."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType

from itaa_application.offer_boundary import MappedOffer
from itaa_application.ranking_decision import DecisionRecord
from itaa_application.solicitation_service import CollectionResult
from itaa_domain.acceptance import Acceptance
from itaa_domain.identifiers import IntentId
from itaa_domain.purchase_intent import PurchaseIntent
from itaa_domain.requirement import Requirement
from itaa_domain.transaction import Transaction
from itaa_domain.value_objects import require_utc
from itaa_policy.idempotency import ResultRef


class BuyerSessionState(StrEnum):
    AWAITING_REQUIREMENT_CONFIRMATION = "AWAITING_REQUIREMENT_CONFIRMATION"
    AWAITING_DISPATCH_APPROVAL = "AWAITING_DISPATCH_APPROVAL"
    OFFERS_RANKED = "OFFERS_RANKED"
    ACCEPTANCE_RECORDED = "ACCEPTANCE_RECORDED"
    TRANSACTION_AUTHORIZED_SIMULATED = "TRANSACTION_AUTHORIZED_SIMULATED"
    CANCELLED = "CANCELLED"
    SUPERSEDED = "SUPERSEDED"


class MarketSourceType(StrEnum):
    SYNTHETIC_LOCAL_FIXTURE = "synthetic_local_fixture"


class MarketLabel(StrEnum):
    SIMULATION = "simulation"
    LOCAL_FIXTURE = "local-fixture"


@dataclass(frozen=True, slots=True)
class MarketEvidenceItem:
    source_type: MarketSourceType
    source_ref: str
    observed_at: datetime
    label: MarketLabel

    def __post_init__(self) -> None:
        object.__setattr__(self, "observed_at", require_utc(self.observed_at, "observed_at"))

    def to_primitive(self) -> dict[str, str]:
        from itaa_domain.value_objects import format_utc

        return {
            "sourceType": self.source_type.value,
            "sourceRef": self.source_ref,
            "observedAt": format_utc(self.observed_at),
            "label": self.label.value,
        }


@dataclass(frozen=True, slots=True)
class SupplierOutcomeView:
    supplier_token: str
    kind: str
    reason: str | None


def fit_for_rank(rank: int) -> str:
    """Qualitative fit from ordinal rank. Never derived from score_micros."""
    if rank == 1:
        return "strong"
    if rank == 2:
        return "good"
    return "fair"


@dataclass(frozen=True, slots=True)
class RankedOfferView:
    offer_id: str
    supplier_token: str
    version: int
    rank: int
    score_micros: int
    total_minor: int
    currency: str
    recommended: bool
    simulation: bool
    source_type: str = "supplier_private_quote"
    offer_class: str = "standard"
    issued_at: str = ""
    valid_from: str = ""
    valid_until: str = ""
    terms_hash: str = ""
    tax_minor: int = 0
    fees_minor: int = 0
    deposit_minor: int | None = None
    pay_later_minor: int | None = None
    fit: str = "fair"
    validity: str = "valid"
    inventory: str = "not_held"
    transaction_result: str = "simulated"
    completeness: str = "complete"
    evidence: tuple[tuple[str, str], ...] = ()
    schema_version: str = "1.0"
    superseded_by: str | None = None
    withdrawn: bool | None = None

    def to_buyer_offer(self) -> dict[str, object]:
        price: dict[str, object] = {
            "totalMinor": self.total_minor,
            "taxMinor": self.tax_minor,
            "feesMinor": self.fees_minor,
            "currency": self.currency,
        }
        if self.deposit_minor is not None:
            price["depositMinor"] = self.deposit_minor
        if self.pay_later_minor is not None:
            price["payLaterMinor"] = self.pay_later_minor
        payload: dict[str, object] = {
            "schemaVersion": self.schema_version,
            "offerId": self.offer_id,
            "supplierToken": self.supplier_token,
            "version": self.version,
            "sourceType": self.source_type,
            "offerClass": self.offer_class,
            "issuedAt": self.issued_at,
            "validFrom": self.valid_from,
            "validUntil": self.valid_until,
            "price": price,
            "fit": self.fit,
            "simulation": True,
            "validity": self.validity,
            "inventory": "not_held",
            "transactionResult": self.transaction_result,
            "completeness": self.completeness,
            "evidence": [{"type": kind, "ref": ref} for kind, ref in self.evidence],
            "rank": self.rank,
            "recommended": self.recommended,
            "termsHash": self.terms_hash,
        }
        if self.superseded_by is not None:
            payload["supersededBy"] = self.superseded_by
        if self.withdrawn is not None:
            payload["withdrawn"] = self.withdrawn
        return payload


@dataclass(frozen=True, slots=True)
class DownsideView:
    dimension: str
    delta: int
    versus_offer_id: str | None


@dataclass(frozen=True, slots=True)
class AcceptanceView:
    acceptance_id: str
    offer_id: str
    offer_version: int
    status: str


@dataclass(frozen=True, slots=True)
class TransactionView:
    authorization_id: str
    acceptance_id: str
    action: str
    mode: str
    amount_minor: int
    currency: str
    result_ref: str | None


@dataclass(frozen=True, slots=True)
class BuyerSnapshot:
    environment: str
    simulation: bool
    intent_id: str
    state: BuyerSessionState
    airport: str
    category: str
    created_at: str
    updated_at: str
    expires_at: str
    market_evidence: tuple[MarketEvidenceItem, ...]
    supplier_outcomes: tuple[SupplierOutcomeView, ...]
    offers: tuple[RankedOfferView, ...]
    recommended_offer_id: str | None
    downside: DownsideView | None
    acceptance: AcceptanceView | None
    transaction: TransactionView | None
    replaces_intent_id: str | None = None
    replaced_by_intent_id: str | None = None
    saved: bool = False
    saved_at: str | None = None
    window_start: str | None = None
    window_end: str | None = None

    def to_primitive(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "environment": self.environment,
            "simulation": self.simulation,
            "intentId": self.intent_id,
            "state": self.state.value,
            "airport": self.airport,
            "category": self.category,
            "createdAt": self.created_at,
            "updatedAt": self.updated_at,
            "expiresAt": self.expires_at,
            "marketEvidence": [item.to_primitive() for item in self.market_evidence],
            "supplierOutcomes": [
                {
                    "supplierToken": item.supplier_token,
                    "kind": item.kind,
                    "reason": item.reason,
                }
                for item in self.supplier_outcomes
            ],
            "offers": [item.to_buyer_offer() for item in self.offers],
            "recommendedOfferId": self.recommended_offer_id,
            "downside": None
            if self.downside is None
            else {
                "dimension": self.downside.dimension,
                "delta": self.downside.delta,
                "versusOfferId": self.downside.versus_offer_id,
            },
            "acceptance": None
            if self.acceptance is None
            else {
                "acceptanceId": self.acceptance.acceptance_id,
                "offerId": self.acceptance.offer_id,
                "offerVersion": self.acceptance.offer_version,
                "status": self.acceptance.status,
            },
            "transaction": None
            if self.transaction is None
            else {
                "authorizationId": self.transaction.authorization_id,
                "acceptanceId": self.transaction.acceptance_id,
                "action": self.transaction.action,
                "mode": self.transaction.mode,
                "amountMinor": self.transaction.amount_minor,
                "currency": self.transaction.currency,
                "resultRef": self.transaction.result_ref,
            },
        }
        if self.replaces_intent_id is not None:
            payload["replacesIntentId"] = self.replaces_intent_id
        if self.replaced_by_intent_id is not None:
            payload["replacedByIntentId"] = self.replaced_by_intent_id
        if self.saved:
            payload["saved"] = True
            if self.saved_at is not None:
                payload["savedAt"] = self.saved_at
        if self.window_start is not None:
            payload["windowStart"] = self.window_start
        if self.window_end is not None:
            payload["windowEnd"] = self.window_end
        return payload


@dataclass(frozen=True, slots=True)
class GovernanceCommand:
    actor_id: str
    owner_id: str
    approval_id: str
    correlation_id: str
    issued_at: datetime
    expires_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "issued_at", require_utc(self.issued_at, "issued_at"))
        object.__setattr__(self, "expires_at", require_utc(self.expires_at, "expires_at"))


@dataclass(frozen=True, slots=True)
class AcceptCommand(GovernanceCommand):
    offer_id: str
    offer_version: int


@dataclass(frozen=True, slots=True)
class AuthorizeCommand(GovernanceCommand):
    acceptance_id: str
    amount_minor: int
    currency: str
    supplier_token: str
    action: str
    mode: str
    idempotency_key: str


@dataclass(frozen=True, slots=True)
class ActivityEntry:
    occurred_at: datetime
    label: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "occurred_at", require_utc(self.occurred_at, "occurred_at"))


@dataclass(frozen=True, slots=True)
class ReplaceResult:
    previous: BuyerSnapshot
    draft: BuyerSnapshot

    def to_primitive(self) -> dict[str, object]:
        return {
            "previous": self.previous.to_primitive(),
            "draft": self.draft.to_primitive(),
        }


@dataclass(frozen=True, slots=True)
class GoldenPathSession:
    purchase_intent: PurchaseIntent
    requirement: Requirement
    intent_payload: MappingProxyType[str, object]
    state: BuyerSessionState
    market_evidence: tuple[MarketEvidenceItem, ...] = ()
    collection: CollectionResult | None = None
    mapped_offers: tuple[MappedOffer, ...] = ()
    decision: DecisionRecord | None = None
    acceptance: Acceptance | None = None
    transaction: Transaction | None = None
    authorization_result_ref: ResultRef | None = None
    used_approval_ids: frozenset[str] = field(default_factory=frozenset)
    portfolio_id: str | None = None
    replaces_intent_id: str | None = None
    replaced_by_intent_id: str | None = None
    saved: bool = False
    saved_at: datetime | None = None
    activity: tuple[ActivityEntry, ...] = ()

    @property
    def intent_id(self) -> IntentId:
        return self.purchase_intent.intent_id
