"""Mandatory trusted supplier-policy evaluation at the buyer-side Offer boundary."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from itaa_application.errors import ApplicationError
from itaa_domain.errors import DomainInvariantError
from itaa_domain.identifiers import IntentId, SupplierToken
from itaa_domain.value_objects import (
    JS_SAFE_MAX,
    AddOn,
    AirportCode,
    CancellationTerm,
    EvidenceRef,
    EvidenceType,
    LotType,
    RefundTerm,
    SimulatedAvailability,
)


class SimulatorOnlyCheck(StrEnum):
    REMAINING_CAPACITY = "remaining_capacity"
    DEMAND_FACTOR = "demand_factor"
    DISCOUNT_CAP = "discount_cap"
    ACQUISITION_BUDGET = "acquisition_budget"
    BUNDLE_MARGIN = "bundle_margin"


class PolicyProfile(StrEnum):
    SIMULATOR_V1 = "simulator_v1"
    CONTRACT_FIXTURE_V1 = "contract_fixture_v1"


def _require_int(value: object, field: str) -> int:
    if type(value) is not int or isinstance(value, bool):
        raise ApplicationError(field, "must_be_integer")
    return value


def _require_money(value: object, field: str) -> int:
    amount = _require_int(value, field)
    if amount < 0 or amount > JS_SAFE_MAX:
        raise ApplicationError(field, "out_of_range")
    return amount


def required_simulator_checks(add_ons: frozenset[AddOn]) -> frozenset[SimulatorOnlyCheck]:
    checks = {
        SimulatorOnlyCheck.REMAINING_CAPACITY,
        SimulatorOnlyCheck.DEMAND_FACTOR,
        SimulatorOnlyCheck.DISCOUNT_CAP,
        SimulatorOnlyCheck.ACQUISITION_BUDGET,
    }
    if add_ons:
        checks.add(SimulatorOnlyCheck.BUNDLE_MARGIN)
    return frozenset(checks)


@dataclass(frozen=True, slots=True)
class TrustedEvidence:
    evidence_type: EvidenceType
    ref: EvidenceRef

    def __post_init__(self) -> None:
        if type(self.evidence_type) is not EvidenceType:
            raise ApplicationError("evidence_type", "invalid_enum")
        if type(self.ref) is not EvidenceRef:
            raise ApplicationError("evidence_ref", "invalid")


@dataclass(frozen=True, slots=True)
class TrustedPolicyEvaluation:
    """Buyer-trusted policy attestation for one supplier solicitation."""

    profile: PolicyProfile
    policy_version: str
    supplier_token: SupplierToken
    scoped_intent_id: IntentId
    airports: frozenset[str]
    vehicles: frozenset[str]
    lot_types: frozenset[LotType]
    add_ons: frozenset[AddOn]
    allowed_availability: frozenset[SimulatedAvailability]
    evidence: tuple[TrustedEvidence, ...]
    floor_minor_per_day: int
    billable_days: int
    max_discount_micros: int
    allowed_cancellations: frozenset[CancellationTerm]
    allowed_refunds: frozenset[RefundTerm]
    min_validity_seconds: int
    max_validity_seconds: int
    fees_minor: int
    tax_minor: int
    add_on_price_minor: int
    simulator_only: frozenset[SimulatorOnlyCheck]

    def __post_init__(self) -> None:
        if type(self.profile) is not PolicyProfile:
            raise ApplicationError("profile", "invalid_enum")
        try:
            EvidenceRef(self.policy_version)
        except DomainInvariantError as exc:
            raise ApplicationError("policy_version", exc.code) from None
        if type(self.supplier_token) is not SupplierToken:
            raise ApplicationError("supplier_token", "invalid_opaque_syntax")
        if type(self.scoped_intent_id) is not IntentId:
            raise ApplicationError("scoped_intent_id", "invalid_opaque_syntax")
        airports = frozenset(self.airports)
        if not airports:
            raise ApplicationError("airports", "required")
        for code in airports:
            try:
                AirportCode(code)
            except DomainInvariantError as exc:
                raise ApplicationError(exc.field, exc.code) from None
        vehicles = frozenset(self.vehicles)
        if not vehicles:
            raise ApplicationError("vehicles", "required")
        for item in vehicles:
            if not isinstance(item, str) or not item:
                raise ApplicationError("vehicles", "invalid")
        lots = frozenset(self.lot_types)
        if not lots:
            raise ApplicationError("lot_types", "required")
        for item in lots:
            if type(item) is not LotType:
                raise ApplicationError("lot_types", "invalid_enum")
        add_ons = frozenset(self.add_ons)
        for item in add_ons:
            if type(item) is not AddOn:
                raise ApplicationError("add_ons", "invalid_enum")
        availability = frozenset(self.allowed_availability)
        if not availability:
            raise ApplicationError("allowed_availability", "required")
        for item in availability:
            if type(item) is not SimulatedAvailability:
                raise ApplicationError("allowed_availability", "invalid_enum")
        evidence = tuple(self.evidence)
        if not evidence:
            raise ApplicationError("evidence", "required")
        seen: set[str] = set()
        for row in evidence:
            if type(row) is not TrustedEvidence:
                raise ApplicationError("evidence", "invalid")
            key = f"{row.evidence_type.value}:{row.ref.to_primitive()}"
            if key in seen:
                raise ApplicationError("evidence", "duplicate")
            seen.add(key)
        cancellations = frozenset(self.allowed_cancellations)
        if not cancellations:
            raise ApplicationError("allowed_cancellations", "required")
        for item in cancellations:
            if type(item) is not CancellationTerm:
                raise ApplicationError("allowed_cancellations", "invalid_enum")
        refunds = frozenset(self.allowed_refunds)
        if not refunds:
            raise ApplicationError("allowed_refunds", "required")
        for item in refunds:
            if type(item) is not RefundTerm:
                raise ApplicationError("allowed_refunds", "invalid_enum")
        checks = frozenset(self.simulator_only)
        for item in checks:
            if type(item) is not SimulatorOnlyCheck:
                raise ApplicationError("simulator_only", "invalid_enum")
        required = required_simulator_checks(add_ons)
        if checks != required:
            raise ApplicationError("simulator_only", "incomplete")
        object.__setattr__(self, "airports", airports)
        object.__setattr__(self, "vehicles", vehicles)
        object.__setattr__(self, "lot_types", lots)
        object.__setattr__(self, "add_ons", add_ons)
        object.__setattr__(self, "allowed_availability", availability)
        object.__setattr__(self, "evidence", evidence)
        object.__setattr__(self, "allowed_cancellations", cancellations)
        object.__setattr__(self, "allowed_refunds", refunds)
        object.__setattr__(self, "simulator_only", checks)
        object.__setattr__(
            self,
            "floor_minor_per_day",
            _require_money(self.floor_minor_per_day, "floor_minor_per_day"),
        )
        object.__setattr__(self, "billable_days", _require_int(self.billable_days, "billable_days"))
        if self.billable_days < 1:
            raise ApplicationError("billable_days", "must_be_positive")
        object.__setattr__(
            self,
            "max_discount_micros",
            _require_int(self.max_discount_micros, "max_discount_micros"),
        )
        if self.max_discount_micros < 0 or self.max_discount_micros > 1_000_000:
            raise ApplicationError("max_discount_micros", "out_of_range")
        object.__setattr__(
            self,
            "min_validity_seconds",
            _require_int(self.min_validity_seconds, "min_validity_seconds"),
        )
        object.__setattr__(
            self,
            "max_validity_seconds",
            _require_int(self.max_validity_seconds, "max_validity_seconds"),
        )
        if self.min_validity_seconds < 1 or self.max_validity_seconds < self.min_validity_seconds:
            raise ApplicationError("validity", "invalid")
        object.__setattr__(self, "fees_minor", _require_money(self.fees_minor, "fees_minor"))
        object.__setattr__(self, "tax_minor", _require_money(self.tax_minor, "tax_minor"))
        object.__setattr__(
            self,
            "add_on_price_minor",
            _require_money(self.add_on_price_minor, "add_on_price_minor"),
        )
