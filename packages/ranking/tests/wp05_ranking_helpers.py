from __future__ import annotations

from datetime import UTC, datetime

from itaa_domain.identifiers import OfferId, SupplierToken
from itaa_domain.value_objects import (
    AddOn,
    CancellationTerm,
    CoveredPreference,
    EvidenceRef,
    EvidenceType,
    LotType,
    RefundTerm,
    SimulatedAvailability,
    Version,
)
from itaa_ranking.inputs import RankingNeed, RankingOffer, ReliabilityFact
from itaa_ranking.profile import DEFAULT_PROFILE
from itaa_ranking.rank import rank_offers

EVALUATED_AT = datetime(2026, 8, 20, 16, 0, tzinfo=UTC)
VALID_FROM = EVALUATED_AT
VALID_UNTIL = datetime(2026, 8, 21, 16, 0, tzinfo=UTC)

PARKDIRECT = SupplierToken("sp_01k2m3n4p5q6r7s8t9v0w1x2b1")
SKYSHIELD = SupplierToken("sp_01k2m3n4p5q6r7s8t9v0w1x2b2")
TERMINALFLEX = SupplierToken("sp_01k2m3n4p5q6r7s8t9v0w1x2b3")
PARKDIRECT_OFFER = OfferId("of_01k2m3n4p5q6r7s8t9v0w1x2a1")
SKYSHIELD_OFFER = OfferId("of_01k2m3n4p5q6r7s8t9v0w1x2a2")
TERMINALFLEX_OFFER = OfferId("of_01k2m3n4p5q6r7s8t9v0w1x2a3")


def _need() -> RankingNeed:
    return RankingNeed(
        covered=CoveredPreference.PREFERRED,
        representable_add_ons=frozenset({AddOn.EV_CHARGING}),
        shuttle_max_minutes=20,
    )


def _reliability() -> tuple[ReliabilityFact, ...]:
    return (
        ReliabilityFact(
            PARKDIRECT,
            700_000,
            EvidenceRef("registry.parkdirect.reliability.v1"),
            "synthetic.v1",
        ),
        ReliabilityFact(
            SKYSHIELD,
            950_000,
            EvidenceRef("registry.skyshield.reliability.v1"),
            "synthetic.v1",
        ),
        ReliabilityFact(
            TERMINALFLEX,
            850_000,
            EvidenceRef("registry.terminalflex.reliability.v1"),
            "synthetic.v1",
        ),
    )


def parkdirect_offer() -> RankingOffer:
    return RankingOffer(
        offer_id=PARKDIRECT_OFFER,
        supplier_token=PARKDIRECT,
        version=Version(1),
        total_minor=11900,
        currency="USD",
        shuttle_minutes=15,
        distance_metres=2400,
        lot_type=LotType.UNCOVERED,
        add_ons=frozenset(),
        cancellation=CancellationTerm.FREE_UNTIL_24H,
        refund=RefundTerm.ORIGINAL_METHOD,
        valid_from=VALID_FROM,
        valid_until=VALID_UNTIL,
        evidence_types=frozenset({EvidenceType.SUPPLIER_POLICY}),
        availability=SimulatedAvailability.CONFIRMED_SIMULATED,
    )


def skyshield_offer() -> RankingOffer:
    return RankingOffer(
        offer_id=SKYSHIELD_OFFER,
        supplier_token=SKYSHIELD,
        version=Version(1),
        total_minor=14800,
        currency="USD",
        shuttle_minutes=8,
        distance_metres=2900,
        lot_type=LotType.COVERED,
        add_ons=frozenset({AddOn.EV_CHARGING}),
        cancellation=CancellationTerm.FREE_UNTIL_24H,
        refund=RefundTerm.ORIGINAL_METHOD,
        valid_from=VALID_FROM,
        valid_until=VALID_UNTIL,
        evidence_types=frozenset({EvidenceType.SUPPLIER_POLICY}),
        availability=SimulatedAvailability.CONFIRMED_SIMULATED,
    )


def terminalflex_offer() -> RankingOffer:
    return RankingOffer(
        offer_id=TERMINALFLEX_OFFER,
        supplier_token=TERMINALFLEX,
        version=Version(1),
        total_minor=16900,
        currency="USD",
        shuttle_minutes=5,
        distance_metres=900,
        lot_type=LotType.GARAGE,
        add_ons=frozenset({AddOn.INDOOR_WALKWAY}),
        cancellation=CancellationTerm.FREE_UNTIL_48H,
        refund=RefundTerm.ORIGINAL_METHOD,
        valid_from=VALID_FROM,
        valid_until=VALID_UNTIL,
        evidence_types=frozenset({EvidenceType.SUPPLIER_POLICY}),
        availability=SimulatedAvailability.LIMITED_SIMULATED,
    )


def golden_offers() -> tuple[RankingOffer, RankingOffer, RankingOffer]:
    return (parkdirect_offer(), skyshield_offer(), terminalflex_offer())


def rank_golden(order: tuple[RankingOffer, ...] | None = None):
    offers = golden_offers() if order is None else order
    return rank_offers(
        offers,
        _need(),
        evaluated_at=EVALUATED_AT,
        reliability=_reliability(),
        profile=DEFAULT_PROFILE,
    )
