"""Canonical local-demo suppliers for the locked JFK golden path.

These ports emit the accepted contract-fixture offer attributes (price,
lot, shuttle, add-ons, terms). Ranking remains authoritative: scores are
not hard-coded. Each ``canonical_golden_ports()`` call returns isolated
capacity so one demonstration cannot exhaust another.

MVP limitation: trusted buyer-side policy specs are loaded from the same
checked-in contract fixture JSON at import time. That file is a static
attestation source for the local demo, not a policy database. Live offer
payloads are untrusted candidates and must never become trusted values.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from types import MappingProxyType

from itaa_application.errors import ApplicationError
from itaa_application.policy_evaluation import (
    PolicyProfile,
    TrustedEvidence,
    TrustedPolicyEvaluation,
    required_simulator_checks,
)
from itaa_application.supplier_port import (
    ClosedReason,
    SupplierAttempt,
    SupplierPort,
    SupplierTerminal,
    TerminalKind,
)
from itaa_contracts_generated.offer import Offer as ContractOffer
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
    format_utc,
)
from itaa_supplier_simulator.policy import PARKDIRECT, SKYSHIELD, TERMINALFLEX

_REPO = Path(__file__).resolve().parents[4]
_FIXTURES = _REPO / "packages" / "contracts" / "fixtures" / "valid"
_OFFER_FILES = {
    PARKDIRECT.supplier_token: "offer-parkdirect.json",
    SKYSHIELD.supplier_token: "offer-skyshield.json",
    TERMINALFLEX.supplier_token: "offer-terminalflex.json",
}
_POLICIES = {
    PARKDIRECT.supplier_token: PARKDIRECT,
    SKYSHIELD.supplier_token: SKYSHIELD,
    TERMINALFLEX.supplier_token: TERMINALFLEX,
}
DEMO_CAPACITY = 8
VALIDITY = timedelta(hours=24)
MIN_VALIDITY_SECONDS = 15 * 60
MAX_VALIDITY_SECONDS = 48 * 60 * 60


def _require_int(value: object, field: str) -> int:
    if type(value) is not int or isinstance(value, bool):
        raise ApplicationError(field, "must_be_integer")
    return value


def _require_money(value: object, field: str) -> int:
    amount = _require_int(value, field)
    if amount < 0 or amount > JS_SAFE_MAX:
        raise ApplicationError(field, "out_of_range")
    return amount


def _require_mapping(value: object, field: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ApplicationError(field, "required")
    return value


@dataclass(frozen=True, slots=True)
class CanonicalTrustedSpec:
    """Import-time trusted attestation for one canonical supplier."""

    supplier_token: SupplierToken
    airports: frozenset[str]
    vehicles: frozenset[str]
    lot_types: frozenset[LotType]
    add_ons: frozenset[AddOn]
    allowed_availability: frozenset[SimulatedAvailability]
    evidence: tuple[TrustedEvidence, ...]
    floor_minor_per_day: int
    billable_days: int
    fees_minor: int
    tax_minor: int
    add_on_price_minor: int
    allowed_cancellations: frozenset[CancellationTerm]
    allowed_refunds: frozenset[RefundTerm]
    min_validity_seconds: int
    max_validity_seconds: int

    def __post_init__(self) -> None:
        if type(self.supplier_token) is not SupplierToken:
            raise ApplicationError("supplier_token", "invalid_opaque_syntax")
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
        for row in evidence:
            if type(row) is not TrustedEvidence:
                raise ApplicationError("evidence", "invalid")
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
        object.__setattr__(self, "airports", airports)
        object.__setattr__(self, "vehicles", vehicles)
        object.__setattr__(self, "lot_types", lots)
        object.__setattr__(self, "add_ons", add_ons)
        object.__setattr__(self, "allowed_availability", availability)
        object.__setattr__(self, "evidence", evidence)
        object.__setattr__(self, "allowed_cancellations", cancellations)
        object.__setattr__(self, "allowed_refunds", refunds)
        object.__setattr__(
            self,
            "floor_minor_per_day",
            _require_money(self.floor_minor_per_day, "floor_minor_per_day"),
        )
        object.__setattr__(self, "billable_days", _require_int(self.billable_days, "billable_days"))
        if self.billable_days < 1:
            raise ApplicationError("billable_days", "must_be_positive")
        object.__setattr__(self, "fees_minor", _require_money(self.fees_minor, "fees_minor"))
        object.__setattr__(self, "tax_minor", _require_money(self.tax_minor, "tax_minor"))
        object.__setattr__(
            self,
            "add_on_price_minor",
            _require_money(self.add_on_price_minor, "add_on_price_minor"),
        )
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


def canonical_golden_ports() -> dict[SupplierToken, SupplierPort]:
    return {token: CanonicalGoldenSupplier(token, _load_template(token)) for token in _OFFER_FILES}


def canonical_trusted_specs() -> Mapping[SupplierToken, CanonicalTrustedSpec]:
    """Return the import-time trusted table. Never derived from a live offer."""
    return _TRUSTED_SPECS


def trusted_canonical_evaluation(
    spec: CanonicalTrustedSpec, scoped_intent_id: IntentId
) -> TrustedPolicyEvaluation:
    return TrustedPolicyEvaluation(
        profile=PolicyProfile.CONTRACT_FIXTURE_V1,
        policy_version="contract_fixture_v1",
        supplier_token=spec.supplier_token,
        scoped_intent_id=scoped_intent_id,
        airports=spec.airports,
        vehicles=spec.vehicles,
        lot_types=spec.lot_types,
        add_ons=spec.add_ons,
        allowed_availability=spec.allowed_availability,
        evidence=spec.evidence,
        floor_minor_per_day=spec.floor_minor_per_day,
        billable_days=spec.billable_days,
        max_discount_micros=1_000_000,
        allowed_cancellations=spec.allowed_cancellations,
        allowed_refunds=spec.allowed_refunds,
        min_validity_seconds=spec.min_validity_seconds,
        max_validity_seconds=spec.max_validity_seconds,
        fees_minor=spec.fees_minor,
        tax_minor=spec.tax_minor,
        add_on_price_minor=spec.add_on_price_minor,
        simulator_only=required_simulator_checks(spec.add_ons),
    )


def _load_template(token: SupplierToken) -> dict[str, object]:
    path = _FIXTURES / _OFFER_FILES[token]
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ApplicationError("offer", "invalid")
    return payload


def _spec_from_fixture(token: SupplierToken) -> CanonicalTrustedSpec:
    payload = _load_template(token)
    seeded = _POLICIES[token]
    service = _require_mapping(payload.get("service"), "service")
    price = _require_mapping(payload.get("price"), "price")
    terms = _require_mapping(payload.get("terms"), "terms")
    evidence_raw = payload.get("evidence")
    if not isinstance(evidence_raw, list):
        raise ApplicationError("evidence", "required")
    raw_add_ons = service.get("addOns", [])
    if not isinstance(raw_add_ons, list):
        raise ApplicationError("addOns", "required")
    add_ons = frozenset(AddOn(str(item)) for item in raw_add_ons)
    evidence = tuple(
        TrustedEvidence(EvidenceType(str(item["type"])), EvidenceRef(str(item["ref"])))
        for item in evidence_raw
        if isinstance(item, dict)
    )
    return CanonicalTrustedSpec(
        supplier_token=token,
        airports=seeded.airports,
        vehicles=seeded.vehicles,
        lot_types=frozenset({LotType(str(service["lotType"]))}),
        add_ons=add_ons,
        allowed_availability=frozenset({SimulatedAvailability(str(service["availability"]))}),
        evidence=evidence,
        floor_minor_per_day=_require_money(price.get("subtotalMinor"), "subtotalMinor"),
        billable_days=1,
        fees_minor=_require_money(price.get("feesMinor"), "feesMinor"),
        tax_minor=_require_money(price.get("taxMinor"), "taxMinor"),
        add_on_price_minor=0,
        allowed_cancellations=frozenset({CancellationTerm(str(terms["cancellation"]))}),
        allowed_refunds=frozenset({RefundTerm(str(terms["refund"]))}),
        min_validity_seconds=MIN_VALIDITY_SECONDS,
        max_validity_seconds=MAX_VALIDITY_SECONDS,
    )


_TRUSTED_SPECS: MappingProxyType[SupplierToken, CanonicalTrustedSpec] = MappingProxyType(
    {token: _spec_from_fixture(token) for token in _OFFER_FILES}
)


class CanonicalGoldenSupplier(SupplierPort):
    """Isolated supplier that returns the canonical JFK offer envelope."""

    def __init__(self, token: SupplierToken, template: dict[str, object]) -> None:
        self._token = token
        self._template = template
        self._policy = _POLICIES[token]
        self._remaining = DEMO_CAPACITY

    @property
    def remaining_capacity(self) -> int:
        return self._remaining

    def restore_capacity(self, remaining: int) -> None:
        if type(remaining) is not int or isinstance(remaining, bool):
            raise ApplicationError("remaining_capacity", "must_be_integer")
        if remaining < 0 or remaining > DEMO_CAPACITY:
            raise ApplicationError("remaining_capacity", "out_of_range")
        self._remaining = remaining

    def attempt(self, request: SupplierAttempt) -> SupplierTerminal:
        token = request.envelope.assignment.supplier_token
        if token != self._token:
            raise ApplicationError("supplier_token", "mismatch")
        reason = self._decline(request)
        if reason is not None:
            return SupplierTerminal(
                TerminalKind.DECLINED,
                token,
                request.correlation_id,
                request.invitation,
                request.occurred_at,
                reason,
            )
        offer = deepcopy(self._template)
        offer["intentId"] = request.envelope.assignment.scoped_intent_id.to_primitive()
        offer["offerId"] = request.offer_id.to_primitive()
        offer["signature"] = request.signature.to_primitive()
        offer["supplierToken"] = token.to_primitive()
        offer["validFrom"] = format_utc(request.occurred_at)
        offer["validUntil"] = format_utc(request.occurred_at + VALIDITY)
        ContractOffer.model_validate(offer)
        self._remaining -= 1
        return SupplierTerminal(
            TerminalKind.OFFER,
            token,
            request.correlation_id,
            request.invitation,
            request.occurred_at,
            payload=offer,
        )

    def _decline(self, request: SupplierAttempt) -> ClosedReason | None:
        payload = request.envelope.payload_dict()
        policy = self._policy
        if payload.get("category") != "airport_parking":
            return ClosedReason.UNSUPPORTED_CATEGORY
        location = payload.get("location")
        airport = location.get("airportCode") if isinstance(location, dict) else None
        if airport not in policy.airports:
            return ClosedReason.UNSUPPORTED_AIRPORT
        requirements = payload.get("requirements")
        vehicle = requirements.get("vehicleClass") if isinstance(requirements, dict) else None
        if vehicle not in policy.vehicles:
            return ClosedReason.UNSUPPORTED_VEHICLE
        if self._remaining < 1:
            return ClosedReason.INSUFFICIENT_CAPACITY
        if request.occurred_at >= request.deadline:
            return ClosedReason.RESPONSE_DEADLINE
        window = payload.get("serviceWindow")
        if not isinstance(window, dict):
            return ClosedReason.UNSUPPORTED_SERVICE
        return None
