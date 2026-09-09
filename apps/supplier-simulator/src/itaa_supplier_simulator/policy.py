"""Versioned immutable simulated supplier policies. Not real inventory."""

from __future__ import annotations

from dataclasses import dataclass

from itaa_application.errors import ApplicationError
from itaa_application.policy_evaluation import (
    PolicyProfile,
    TrustedEvidence,
    TrustedPolicyEvaluation,
    required_simulator_checks,
)
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


def _require_int(value: object, field: str) -> int:
    if type(value) is not int or isinstance(value, bool):
        raise ApplicationError(field, "must_be_integer")
    return value


def _require_money(value: object, field: str) -> int:
    amount = _require_int(value, field)
    if amount < 0 or amount > JS_SAFE_MAX:
        raise ApplicationError(field, "out_of_range")
    return amount


def _require_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ApplicationError(field, "required")
    return value


@dataclass(frozen=True, slots=True)
class SimulatedPolicy:
    name: str
    version: str
    supplier_token: SupplierToken
    airports: frozenset[str]
    vehicles: frozenset[str]
    lot_type: LotType
    shuttle_minutes: int
    distance_metres: int
    add_ons: tuple[AddOn, ...]
    add_on_price_minor: int
    add_on_cost_minor: int
    list_minor_per_day: int
    floor_minor_per_day: int
    demand_micros: int
    discount_micros: int
    max_discount_micros: int
    acquisition_budget_minor: int
    fees_minor: int
    tax_minor: int
    capacity: int
    validity_seconds: int
    min_validity_seconds: int
    max_validity_seconds: int
    cancellation: CancellationTerm
    refund: RefundTerm
    availability: str
    policy_ref: str
    rate_ref: str
    lot_ref: str
    availability_ref: str

    def __post_init__(self) -> None:
        _require_text(self.name, "name")
        _require_text(self.version, "version")
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
        if type(self.lot_type) is not LotType:
            raise ApplicationError("lot_type", "invalid_enum")
        shuttle = _require_int(self.shuttle_minutes, "shuttle_minutes")
        if shuttle < 0 or shuttle > 180:
            raise ApplicationError("shuttle_minutes", "out_of_range")
        distance = _require_int(self.distance_metres, "distance_metres")
        if distance < 0 or distance > 100_000:
            raise ApplicationError("distance_metres", "out_of_range")
        add_ons = tuple(self.add_ons)
        if len(set(add_ons)) != len(add_ons):
            raise ApplicationError("add_ons", "duplicate")
        for item in add_ons:
            if type(item) is not AddOn:
                raise ApplicationError("add_ons", "invalid_enum")
        price = _require_money(self.add_on_price_minor, "add_on_price_minor")
        cost = _require_money(self.add_on_cost_minor, "add_on_cost_minor")
        if add_ons:
            if price <= cost:
                raise ApplicationError("add_on_margin", "non_positive")
        elif price != 0 or cost != 0:
            raise ApplicationError("add_ons", "price_without_item")
        listed = _require_money(self.list_minor_per_day, "list_minor_per_day")
        floor = _require_money(self.floor_minor_per_day, "floor_minor_per_day")
        if listed < floor:
            raise ApplicationError("list_minor_per_day", "below_floor")
        demand = _require_int(self.demand_micros, "demand_micros")
        if demand < 1 or demand > 10_000_000:
            raise ApplicationError("demand_micros", "out_of_range")
        max_discount = _require_int(self.max_discount_micros, "max_discount_micros")
        if max_discount < 0 or max_discount > 1_000_000:
            raise ApplicationError("max_discount_micros", "out_of_range")
        discount = _require_int(self.discount_micros, "discount_micros")
        if discount < 0 or discount > max_discount:
            raise ApplicationError("discount_micros", "out_of_range")
        _require_money(self.acquisition_budget_minor, "acquisition_budget_minor")
        _require_money(self.fees_minor, "fees_minor")
        _require_money(self.tax_minor, "tax_minor")
        capacity = _require_int(self.capacity, "capacity")
        if capacity < 0:
            raise ApplicationError("capacity", "out_of_range")
        minimum = _require_int(self.min_validity_seconds, "min_validity_seconds")
        maximum = _require_int(self.max_validity_seconds, "max_validity_seconds")
        validity = _require_int(self.validity_seconds, "validity_seconds")
        if minimum < 1 or maximum < minimum or validity < minimum or validity > maximum:
            raise ApplicationError("validity", "invalid")
        if type(self.cancellation) is not CancellationTerm:
            raise ApplicationError("cancellation", "invalid_enum")
        if type(self.refund) is not RefundTerm:
            raise ApplicationError("refund", "invalid_enum")
        if (
            self.cancellation is CancellationTerm.NON_REFUNDABLE
            and self.refund is not RefundTerm.NONE
        ):
            raise ApplicationError("refund", "invalid_pair")
        if (
            self.cancellation is not CancellationTerm.NON_REFUNDABLE
            and self.refund is RefundTerm.NONE
        ):
            raise ApplicationError("refund", "invalid_pair")
        try:
            SimulatedAvailability(self.availability)
        except ValueError:
            raise ApplicationError("availability", "invalid_enum") from None
        for field, raw in (
            ("policy_ref", self.policy_ref),
            ("rate_ref", self.rate_ref),
            ("lot_ref", self.lot_ref),
            ("availability_ref", self.availability_ref),
        ):
            try:
                EvidenceRef(_require_text(raw, field))
            except DomainInvariantError as exc:
                raise ApplicationError(exc.field, exc.code) from None
        object.__setattr__(self, "airports", airports)
        object.__setattr__(self, "vehicles", vehicles)
        object.__setattr__(self, "add_ons", add_ons)


def trusted_evaluation(
    policy: SimulatedPolicy, billable_days: int, scoped_intent_id: IntentId
) -> TrustedPolicyEvaluation:
    return TrustedPolicyEvaluation(
        profile=PolicyProfile.SIMULATOR_V1,
        policy_version=policy.version,
        supplier_token=policy.supplier_token,
        scoped_intent_id=scoped_intent_id,
        airports=policy.airports,
        vehicles=policy.vehicles,
        lot_types=frozenset({policy.lot_type}),
        add_ons=frozenset(policy.add_ons),
        allowed_availability=frozenset({SimulatedAvailability(policy.availability)}),
        evidence=(
            TrustedEvidence(EvidenceType.SUPPLIER_POLICY, EvidenceRef(policy.policy_ref)),
            TrustedEvidence(EvidenceType.RATE_CARD, EvidenceRef(policy.rate_ref)),
            TrustedEvidence(EvidenceType.LOT_RULES, EvidenceRef(policy.lot_ref)),
            TrustedEvidence(
                EvidenceType.AVAILABILITY_SNAPSHOT, EvidenceRef(policy.availability_ref)
            ),
        ),
        floor_minor_per_day=policy.floor_minor_per_day,
        billable_days=billable_days,
        max_discount_micros=policy.max_discount_micros,
        allowed_cancellations=frozenset({policy.cancellation}),
        allowed_refunds=frozenset({policy.refund}),
        min_validity_seconds=policy.min_validity_seconds,
        max_validity_seconds=policy.max_validity_seconds,
        fees_minor=policy.fees_minor,
        tax_minor=policy.tax_minor,
        add_on_price_minor=policy.add_on_price_minor,
        simulator_only=required_simulator_checks(frozenset(policy.add_ons)),
    )


SIMULATED_AIRPORTS = frozenset(
    {"JFK", "LGA", "EWR", "EDI", "MAN", "LHR", "LGW", "STN", "AMS", "CDG", "DUB", "GLA"}
)

PARKDIRECT = SimulatedPolicy(
    name="ParkDirect",
    version="sim.v1",
    supplier_token=SupplierToken("sp_01k2m3n4p5q6r7s8t9v0w1x2b1"),
    airports=SIMULATED_AIRPORTS,
    vehicles=frozenset({"standard", "compact"}),
    lot_type=LotType.UNCOVERED,
    shuttle_minutes=15,
    distance_metres=2400,
    add_ons=(),
    add_on_price_minor=0,
    add_on_cost_minor=0,
    list_minor_per_day=1900,
    floor_minor_per_day=1700,
    demand_micros=1_000_000,
    discount_micros=100_000,
    max_discount_micros=100_000,
    acquisition_budget_minor=2000,
    fees_minor=800,
    tax_minor=900,
    capacity=12,
    validity_seconds=20 * 60,
    min_validity_seconds=15 * 60,
    max_validity_seconds=30 * 60,
    cancellation=CancellationTerm.FREE_UNTIL_24H,
    refund=RefundTerm.ORIGINAL_METHOD,
    availability="confirmed_simulated",
    policy_ref="policy.parkdirect.v1",
    rate_ref="rate.parkdirect.v1",
    lot_ref="lot.parkdirect.v1",
    availability_ref="availability.parkdirect.v1",
)

SKYSHIELD = SimulatedPolicy(
    name="SkyShield",
    version="sim.v1",
    supplier_token=SupplierToken("sp_01k2m3n4p5q6r7s8t9v0w1x2b2"),
    airports=SIMULATED_AIRPORTS,
    vehicles=frozenset({"standard", "suv"}),
    lot_type=LotType.COVERED,
    shuttle_minutes=8,
    distance_metres=2900,
    add_ons=(AddOn.EV_CHARGING,),
    add_on_price_minor=1500,
    add_on_cost_minor=800,
    list_minor_per_day=3000,
    floor_minor_per_day=2800,
    demand_micros=1_000_000,
    discount_micros=50_000,
    max_discount_micros=80_000,
    acquisition_budget_minor=2500,
    fees_minor=1200,
    tax_minor=1500,
    capacity=8,
    validity_seconds=25 * 60,
    min_validity_seconds=15 * 60,
    max_validity_seconds=30 * 60,
    cancellation=CancellationTerm.FREE_UNTIL_24H,
    refund=RefundTerm.ORIGINAL_METHOD,
    availability="confirmed_simulated",
    policy_ref="policy.skyshield.v3",
    rate_ref="rate.skyshield.v3",
    lot_ref="lot.skyshield.v3",
    availability_ref="availability.skyshield.v3",
)

TERMINALFLEX = SimulatedPolicy(
    name="TerminalFlex",
    version="sim.v1",
    supplier_token=SupplierToken("sp_01k2m3n4p5q6r7s8t9v0w1x2b3"),
    airports=SIMULATED_AIRPORTS,
    vehicles=frozenset({"standard"}),
    lot_type=LotType.GARAGE,
    shuttle_minutes=5,
    distance_metres=900,
    add_ons=(AddOn.INDOOR_WALKWAY,),
    add_on_price_minor=2000,
    add_on_cost_minor=500,
    list_minor_per_day=2800,
    floor_minor_per_day=2400,
    demand_micros=1_000_000,
    discount_micros=0,
    max_discount_micros=50_000,
    acquisition_budget_minor=1500,
    fees_minor=1500,
    tax_minor=1600,
    capacity=3,
    validity_seconds=20 * 60,
    min_validity_seconds=20 * 60,
    max_validity_seconds=20 * 60,
    cancellation=CancellationTerm.FREE_UNTIL_48H,
    refund=RefundTerm.ORIGINAL_METHOD,
    availability="limited_simulated",
    policy_ref="policy.terminalflex.v2",
    rate_ref="rate.terminalflex.v2",
    lot_ref="lot.terminalflex.v2",
    availability_ref="availability.terminalflex.v2",
)

SEEDED = (PARKDIRECT, SKYSHIELD, TERMINALFLEX)
