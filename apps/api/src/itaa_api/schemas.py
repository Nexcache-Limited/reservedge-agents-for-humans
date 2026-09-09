"""HTTP command models that do not duplicate the five canonical contracts."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class GovernanceBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    actorId: str = Field(pattern="^ar_[0-9a-hjkmnp-tv-z]{26}$")
    ownerId: str = Field(pattern="^ar_[0-9a-hjkmnp-tv-z]{26}$")
    approvalId: str = Field(pattern="^ap_[0-9a-hjkmnp-tv-z]{26}$")
    correlationId: str = Field(pattern="^cr_[0-9a-hjkmnp-tv-z]{26}$")
    issuedAt: str
    expiresAt: str


class AcceptanceBody(GovernanceBody):
    offerId: str = Field(pattern="^of_[0-9a-hjkmnp-tv-z]{26}$")
    offerVersion: int = Field(ge=1)


class AuthorizationBody(GovernanceBody):
    acceptanceId: str = Field(pattern="^ac_[0-9a-hjkmnp-tv-z]{26}$")
    amountMinor: int = Field(ge=0)
    currency: str = Field(pattern="^[A-Z]{3}$")
    supplierToken: str = Field(pattern="^sp_[0-9a-hjkmnp-tv-z]{26}$")
    action: str
    mode: str
    idempotencyKey: str = Field(pattern="^ik_[0-9a-hjkmnp-tv-z]{26}$")


class ClosedError(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str
    field: str | None
    correlationId: str


class ErrorEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")
    error: ClosedError


class LivenessResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["ok"]
    environment: Literal["local_simulation"]


class ReadinessResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["ready"]
    environment: Literal["local_simulation"]
    durability: Literal["unsupported"]


_UTC_TIMESTAMP = r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\.[0-9]{1,9})?Z$"
_OFFER_ID = r"^of_[0-9a-hjkmnp-tv-z]{26}$"
_JS_SAFE_MAX = 9007199254740991


class BuyerOfferPrice(BaseModel):
    model_config = ConfigDict(extra="forbid")
    totalMinor: int = Field(ge=0, le=_JS_SAFE_MAX)
    taxMinor: int = Field(ge=0, le=_JS_SAFE_MAX)
    feesMinor: int = Field(ge=0, le=_JS_SAFE_MAX)
    currency: str = Field(pattern="^[A-Z]{3}$")
    depositMinor: int | None = Field(default=None, ge=0, le=_JS_SAFE_MAX)
    payLaterMinor: int | None = Field(default=None, ge=0, le=_JS_SAFE_MAX)


class BuyerOfferEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["supplier_policy", "rate_card", "lot_rules", "availability_snapshot"]
    ref: str = Field(pattern=r"^[a-z][a-z0-9_.:-]{2,80}$")


class BuyerOffer(BaseModel):
    """Buyer commercial projection. Ranking micros are internal-only."""

    model_config = ConfigDict(extra="forbid")
    schemaVersion: Literal["1.0"]
    offerId: str = Field(pattern=_OFFER_ID)
    supplierToken: str = Field(pattern=r"^sp_[0-9a-hjkmnp-tv-z]{26}$")
    version: int = Field(ge=1, le=_JS_SAFE_MAX)
    sourceType: Literal["aggregator_rate", "public_market_reference", "supplier_private_quote"]
    offerClass: Literal["standard", "curated"]
    issuedAt: str = Field(pattern=_UTC_TIMESTAMP)
    validFrom: str = Field(pattern=_UTC_TIMESTAMP)
    validUntil: str = Field(pattern=_UTC_TIMESTAMP)
    termsHash: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    price: BuyerOfferPrice
    fit: Literal["strong", "good", "fair"]
    simulation: Literal[True]
    validity: Literal["valid", "expiring", "expired", "superseded"]
    inventory: Literal["not_held", "subject_to_availability", "held_until"]
    transactionResult: Literal[
        "simulated",
        "authorized_simulated",
        "authorized_live",
        "booking_pending",
        "confirmed_booking",
        "booking_failed",
        "failed",
        "cancelled",
    ]
    completeness: Literal["complete", "incomplete"]
    evidence: list[BuyerOfferEvidence] = Field(min_length=1)
    supersededBy: str | None = Field(default=None, pattern=_OFFER_ID)
    withdrawn: bool | None = None
    rank: int | None = Field(default=None, ge=1, le=_JS_SAFE_MAX)
    recommended: bool | None = None
    inventoryHeldUntil: str | None = Field(default=None, pattern=_UTC_TIMESTAMP)

    @model_validator(mode="after")
    def _simulation_inventory(self) -> BuyerOffer:
        if self.simulation is True:
            if self.inventory != "not_held":
                raise ValueError("inventory must be not_held in simulation")
            if self.inventoryHeldUntil is not None:
                raise ValueError("inventoryHeldUntil must be absent in simulation")
        return self


class BuyerSessionSnapshot(BaseModel):
    """Buyer-safe snapshot. Offer items use the BuyerOffer commercial projection."""

    model_config = ConfigDict(extra="allow")
    offers: list[BuyerOffer] = Field(default_factory=list)


_ORCHESTRATION_INTENT_ID = r"^oi_[0-9a-hjkmnp-tv-z]{26}$"
_BOOKING_TASK_ID = r"^bt_[0-9a-hjkmnp-tv-z]{26}$"
_PLAN_ID = r"^pl_[0-9a-hjkmnp-tv-z]{26}$"
_LEDGER_ID = r"^ld_[0-9a-hjkmnp-tv-z]{26}$"
_PURCHASE_INTENT_ID = r"^pi_[0-9a-hjkmnp-tv-z]{26}$"


class OrchestrationIntent(BaseModel):
    """Buyer-owned parent Intent. Restart yields unknown_resource."""

    model_config = ConfigDict(extra="forbid")
    schemaVersion: Literal["1.0"]
    intentId: str = Field(pattern=_ORCHESTRATION_INTENT_ID)
    state: Literal[
        "draft",
        "clarifying",
        "planning",
        "deleted",
        "attention",
        "in_progress",
        "offers_ready",
        "partially_authorized_simulated",
        "partially_authorized_live",
        "partially_booked",
        "completed_simulated",
        "completed",
        "paused",
        "cancelled",
        "failed",
    ]
    objective: str = Field(min_length=1, max_length=4000)
    createdAt: str = Field(pattern=_UTC_TIMESTAMP)
    updatedAt: str = Field(pattern=_UTC_TIMESTAMP)
    simulation: Literal[True]
    durability: Literal["unsupported"]
    conversationId: str | None = Field(default=None, min_length=1, max_length=128)
    planId: str | None = Field(default=None, pattern=_PLAN_ID)
    ledgerId: str | None = Field(default=None, pattern=_LEDGER_ID)


class IntentPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schemaVersion: Literal["1.0"]
    planId: str = Field(pattern=_PLAN_ID)
    intentId: str = Field(pattern=_ORCHESTRATION_INTENT_ID)
    taskIds: list[str] = Field(default_factory=list)
    combinedRecommendationsEligible: bool | None = None


class CostLedgerRow(BaseModel):
    model_config = ConfigDict(extra="forbid")
    taskId: str = Field(pattern=_BOOKING_TASK_ID)
    currency: str = Field(pattern="^[A-Z]{3}$")
    confirmedBookingMinor: int = Field(ge=0, le=_JS_SAFE_MAX)
    authorizedSimulatedMinor: int = Field(ge=0, le=_JS_SAFE_MAX)
    authorizedLiveMinor: int = Field(ge=0, le=_JS_SAFE_MAX)
    bookingPendingMinor: int = Field(ge=0, le=_JS_SAFE_MAX)
    selectedNotAuthorizedMinor: int = Field(ge=0, le=_JS_SAFE_MAX)
    estimatedMinor: int = Field(ge=0, le=_JS_SAFE_MAX)
    expiredExcludedMinor: int = Field(ge=0, le=_JS_SAFE_MAX)
    taxesFeesMinor: int = Field(ge=0, le=_JS_SAFE_MAX)
    depositsHoldsMinor: int = Field(ge=0, le=_JS_SAFE_MAX)
    payableNowMinor: int = Field(ge=0, le=_JS_SAFE_MAX)
    payableLaterMinor: int = Field(ge=0, le=_JS_SAFE_MAX)


class CostLedger(BaseModel):
    """Deterministic per-task buckets. Restart yields unknown_resource."""

    model_config = ConfigDict(extra="forbid")
    schemaVersion: Literal["1.0"]
    ledgerId: str = Field(pattern=_LEDGER_ID)
    intentId: str = Field(pattern=_ORCHESTRATION_INTENT_ID)
    simulation: Literal[True]
    rows: list[CostLedgerRow]
    currencies: list[str]


class BookingTask(BaseModel):
    """Per-domain task. Must not embed conversation, siblings, or preferences."""

    model_config = ConfigDict(extra="forbid")
    schemaVersion: Literal["1.0"]
    taskId: str = Field(pattern=_BOOKING_TASK_ID)
    intentId: str = Field(pattern=_ORCHESTRATION_INTENT_ID)
    domain: Literal["parking", "rental", "ents"]
    state: Literal[
        "proposed",
        "missing_details",
        "a1_review",
        "a1_blocked",
        "public_research",
        "a2_required",
        "researching",
        "supplier_timeout",
        "no_offer",
        "offers_ready",
        "offers_expiring",
        "offers_expired",
        "superseded",
        "a3_review",
        "a3_ineligible",
        "a4_required",
        "a4_failed",
        "authorized_simulated",
        "authorized_live",
        "booking_pending",
        "confirmed_booking",
        "booking_failed",
        "paused",
        "cancelled",
        "failed",
        "offline_readonly",
    ]
    simulation: Literal[True]
    requirementVersion: int | None = Field(default=None, ge=1)
    purchaseIntentId: str | None = Field(default=None, pattern=_PURCHASE_INTENT_ID)
    validity: Literal["valid", "expiring", "expired", "superseded"] | None = None
    inventory: Literal["not_held", "subject_to_availability", "held_until"] | None = None
    transactionResult: (
        Literal[
            "simulated",
            "authorized_simulated",
            "authorized_live",
            "booking_pending",
            "confirmed_booking",
            "booking_failed",
            "failed",
            "cancelled",
        ]
        | None
    ) = None
