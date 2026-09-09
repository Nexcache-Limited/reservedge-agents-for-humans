"""Pure integer scoring, eligibility, ranking, and explanation facts."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime

from itaa_domain.identifiers import OfferId
from itaa_domain.value_objects import (
    AddOn,
    CoveredPreference,
    EvidenceType,
    LotType,
    RefundTerm,
    SimulatedAvailability,
    format_utc,
    require_utc,
)
from itaa_ranking.errors import RankingError
from itaa_ranking.inputs import RankingNeed, RankingOffer, ReliabilityFact
from itaa_ranking.profile import (
    CANCELLATION_MICROS,
    COMPONENT_ORDER,
    CONFIG_VERSION,
    DEFAULT_PROFILE,
    FIT_GOOD_COVERAGE,
    FIT_GOOD_SCORE,
    FIT_STRONG_COVERAGE,
    FIT_STRONG_SCORE,
    MISSING_COMPONENT_PENALTY,
    PENALTY_VERSION,
    SCORE_SCALE,
    TIE_BREAK_VERSION,
    RankingProfile,
    half_up,
    invert_min_max,
    weighted_contribution,
)
from itaa_ranking.vocab import (
    DownsideDimension,
    DownsideUnit,
    ExclusionCode,
    ExclusionField,
    FitLabel,
    GapCode,
    PenaltyKind,
    RecencyStatus,
    ScoreComponent,
)

EVIDENCE_CLASSES: tuple[EvidenceType, ...] = (
    EvidenceType.SUPPLIER_POLICY,
    EvidenceType.RATE_CARD,
    EvidenceType.LOT_RULES,
    EvidenceType.AVAILABILITY_SNAPSHOT,
)
COVERED_LOTS = frozenset({LotType.COVERED, LotType.GARAGE})
UNCOVERED_LOTS = frozenset({LotType.UNCOVERED, LotType.SURFACE})


@dataclass(frozen=True, slots=True)
class ComponentBreakdown:
    name: ScoreComponent
    micros: int | None
    weight_micros: int
    contribution_micros: int
    missing: bool


@dataclass(frozen=True, slots=True)
class PenaltyItem:
    kind: PenaltyKind
    component: ScoreComponent
    micros: int


@dataclass(frozen=True, slots=True)
class Exclusion:
    offer_id: OfferId | None
    field: ExclusionField
    code: ExclusionCode


@dataclass(frozen=True, slots=True)
class RankedOffer:
    offer_id: OfferId
    version: int
    rank: int
    score_micros: int
    components: tuple[ComponentBreakdown, ...]
    penalties: tuple[PenaltyItem, ...]
    penalty_micros: int
    evidence_coverage_micros: int
    remaining_validity_seconds: int
    total_minor: int
    shuttle_minutes: int
    distance_metres: int
    drivers: tuple[ScoreComponent, ...]
    fit: FitLabel


@dataclass(frozen=True, slots=True)
class MaterialDownside:
    versus_offer_id: OfferId
    dimension: DownsideDimension
    unit: DownsideUnit
    delta: int


@dataclass(frozen=True, slots=True)
class SnapshotNeed:
    covered: str
    representable_add_ons: tuple[str, ...]
    shuttle_max_minutes: int | None


@dataclass(frozen=True, slots=True)
class SnapshotOffer:
    offer_id: str
    supplier_token: str
    version: int
    total_minor: int
    currency: str
    shuttle_minutes: int
    distance_metres: int
    lot_type: str
    add_ons: tuple[str, ...]
    cancellation: str
    refund: str
    valid_from: str
    valid_until: str
    evidence_types: tuple[str, ...]
    availability: str
    simulation: bool


@dataclass(frozen=True, slots=True)
class SnapshotReliability:
    supplier_token: str
    score_micros: int
    evidence_ref: str
    registry_version: str
    observed_at: str | None


@dataclass(frozen=True, slots=True)
class SnapshotExclusion:
    offer_id: str | None
    field: str
    code: str


@dataclass(frozen=True, slots=True)
class DecisionInputSnapshot:
    profile_id: str
    profile_version: str
    weight_version: str
    config_version: str
    penalty_version: str
    tie_break_version: str
    reason: str
    evidence_ref: str
    weights: tuple[tuple[str, int], ...]
    weight_bound: int
    evaluated_at: str
    need: SnapshotNeed
    reliability: tuple[SnapshotReliability, ...]
    offers: tuple[SnapshotOffer, ...]
    exclusions: tuple[SnapshotExclusion, ...]

    def to_primitive(self) -> dict[str, object]:
        return {
            "profileId": self.profile_id,
            "profileVersion": self.profile_version,
            "weightVersion": self.weight_version,
            "configVersion": self.config_version,
            "penaltyVersion": self.penalty_version,
            "tieBreakVersion": self.tie_break_version,
            "reason": self.reason,
            "evidenceRef": self.evidence_ref,
            "weights": {name: value for name, value in self.weights},
            "weightBound": self.weight_bound,
            "evaluatedAt": self.evaluated_at,
            "need": {
                "covered": self.need.covered,
                "representableAddOns": list(self.need.representable_add_ons),
                "shuttleMaxMinutes": self.need.shuttle_max_minutes,
            },
            "reliability": [
                {
                    "supplierToken": item.supplier_token,
                    "scoreMicros": item.score_micros,
                    "evidenceRef": item.evidence_ref,
                    "registryVersion": item.registry_version,
                    "observedAt": item.observed_at,
                }
                for item in self.reliability
            ],
            "offers": [
                {
                    "offerId": item.offer_id,
                    "supplierToken": item.supplier_token,
                    "version": item.version,
                    "totalMinor": item.total_minor,
                    "currency": item.currency,
                    "shuttleMinutes": item.shuttle_minutes,
                    "distanceMetres": item.distance_metres,
                    "lotType": item.lot_type,
                    "addOns": list(item.add_ons),
                    "cancellation": item.cancellation,
                    "refund": item.refund,
                    "validFrom": item.valid_from,
                    "validUntil": item.valid_until,
                    "evidenceTypes": list(item.evidence_types),
                    "availability": item.availability,
                    "simulation": item.simulation,
                }
                for item in self.offers
            ],
            "exclusions": [
                {
                    "offerId": item.offer_id,
                    "field": item.field,
                    "code": item.code,
                }
                for item in self.exclusions
            ],
        }


@dataclass(frozen=True, slots=True)
class RankingResult:
    profile_id: str
    profile_version: str
    weight_version: str
    evaluated_at: datetime
    ranked: tuple[RankedOffer, ...]
    exclusions: tuple[Exclusion, ...]
    recommended_offer_id: OfferId | None
    recommended_version: int | None
    fit: FitLabel | None
    downside: MaterialDownside | None
    gaps: tuple[GapCode, ...]
    recency: RecencyStatus
    input_snapshot: DecisionInputSnapshot

    def fingerprint_material(self) -> dict[str, object]:
        return self.input_snapshot.to_primitive()


def evidence_coverage_micros(types: frozenset[EvidenceType]) -> int:
    present = len({item for item in types if item in EVIDENCE_CLASSES})
    return half_up(present * SCORE_SCALE, len(EVIDENCE_CLASSES))


def rank_offers(
    offers: tuple[RankingOffer, ...],
    need: RankingNeed,
    *,
    evaluated_at: datetime,
    reliability: tuple[ReliabilityFact, ...],
    profile: RankingProfile = DEFAULT_PROFILE,
) -> RankingResult:
    instant = require_utc(evaluated_at, "evaluated_at")
    if type(profile) is not RankingProfile:
        raise RankingError("profile", "invalid")
    _assert_unique_candidates(offers)
    registry = {item.supplier_token: item for item in reliability}
    if len(registry) != len(reliability):
        raise RankingError("reliability", "duplicate_supplier")
    eligible: list[RankingOffer] = []
    exclusions: list[Exclusion] = []
    for offer in offers:
        reason = _eligibility(offer, need, instant)
        if reason is None:
            eligible.append(offer)
        else:
            exclusions.append(Exclusion(offer.offer_id, reason[0], reason[1]))
    exclusions = sorted(
        exclusions,
        key=lambda row: (
            "" if row.offer_id is None else row.offer_id.to_primitive(),
            row.field.value,
            row.code.value,
        ),
    )
    snapshot = _input_snapshot(offers, need, reliability, profile, instant, exclusions)
    if not eligible:
        return RankingResult(
            profile_id=profile.profile_id,
            profile_version=profile.profile_version,
            weight_version=profile.weight_version,
            evaluated_at=instant,
            ranked=(),
            exclusions=tuple(exclusions),
            recommended_offer_id=None,
            recommended_version=None,
            fit=None,
            downside=None,
            gaps=(GapCode.NO_ELIGIBLE_OFFERS,),
            recency=_recency(registry.values()),
            input_snapshot=snapshot,
        )
    prices = [item.total_minor for item in eligible]
    shuttles = [item.shuttle_minutes for item in eligible]
    distances = [item.distance_metres for item in eligible]
    scored: list[RankedOffer] = []
    for offer in eligible:
        components, penalties = _score_offer(
            offer,
            need,
            profile,
            registry.get(offer.supplier_token),
            min(prices),
            max(prices),
            min(shuttles),
            max(shuttles),
            min(distances),
            max(distances),
        )
        penalty_total = sum(item.micros for item in penalties)
        contribution_total = sum(item.contribution_micros for item in components)
        score = contribution_total - penalty_total
        if score < 0:
            score = 0
        if score > SCORE_SCALE:
            score = SCORE_SCALE
        remaining = int((offer.valid_until - instant).total_seconds())
        coverage = evidence_coverage_micros(offer.evidence_types)
        scored.append(
            RankedOffer(
                offer_id=offer.offer_id,
                version=offer.version.to_primitive(),
                rank=0,
                score_micros=score,
                components=components,
                penalties=penalties,
                penalty_micros=penalty_total,
                evidence_coverage_micros=coverage,
                remaining_validity_seconds=remaining,
                total_minor=offer.total_minor,
                shuttle_minutes=offer.shuttle_minutes,
                distance_metres=offer.distance_metres,
                drivers=_drivers(components),
                fit=_fit(score, coverage, penalty_total),
            )
        )
    ordered = sorted(scored, key=_tie_key)
    ranked = tuple(
        RankedOffer(
            offer_id=item.offer_id,
            version=item.version,
            rank=index,
            score_micros=item.score_micros,
            components=item.components,
            penalties=item.penalties,
            penalty_micros=item.penalty_micros,
            evidence_coverage_micros=item.evidence_coverage_micros,
            remaining_validity_seconds=item.remaining_validity_seconds,
            total_minor=item.total_minor,
            shuttle_minutes=item.shuttle_minutes,
            distance_metres=item.distance_metres,
            drivers=item.drivers,
            fit=item.fit,
        )
        for index, item in enumerate(ordered, start=1)
    )
    winner = ranked[0]
    gaps = tuple(
        GapCode.RELIABILITY_TRUST
        for component in winner.components
        if component.missing and component.name is ScoreComponent.RELIABILITY_TRUST
    )
    return RankingResult(
        profile_id=profile.profile_id,
        profile_version=profile.profile_version,
        weight_version=profile.weight_version,
        evaluated_at=instant,
        ranked=ranked,
        exclusions=tuple(exclusions),
        recommended_offer_id=winner.offer_id,
        recommended_version=winner.version,
        fit=winner.fit,
        downside=_downside(winner, ranked[1:]),
        gaps=gaps,
        recency=_recency(registry.values()),
        input_snapshot=snapshot,
    )


def _assert_unique_candidates(offers: tuple[RankingOffer, ...]) -> None:
    offer_ids = [item.offer_id.to_primitive() for item in offers]
    if len(set(offer_ids)) != len(offer_ids):
        raise RankingError("offer_id", "duplicate")
    versions = [(item.offer_id.to_primitive(), item.version.to_primitive()) for item in offers]
    if len(set(versions)) != len(versions):
        raise RankingError("offer_version", "duplicate")
    suppliers = [item.supplier_token.to_primitive() for item in offers]
    if len(set(suppliers)) != len(suppliers):
        raise RankingError("supplier_token", "duplicate")


def _eligibility(
    offer: RankingOffer, need: RankingNeed, evaluated_at: datetime
) -> tuple[ExclusionField, ExclusionCode] | None:
    if offer.simulation is not True:
        return (ExclusionField.SIMULATION, ExclusionCode.MUST_BE_TRUE)
    if offer.availability is SimulatedAvailability.UNAVAILABLE_SIMULATED:
        return (ExclusionField.AVAILABILITY, ExclusionCode.UNAVAILABLE)
    if evaluated_at < offer.valid_from:
        return (ExclusionField.VALID_FROM, ExclusionCode.NOT_YET_VALID)
    if evaluated_at >= offer.valid_until:
        return (ExclusionField.VALID_UNTIL, ExclusionCode.EXPIRED)
    if need.covered is CoveredPreference.REQUIRED and offer.lot_type in UNCOVERED_LOTS:
        return (ExclusionField.COVERAGE, ExclusionCode.REQUIRED)
    if need.shuttle_max_minutes is not None and offer.shuttle_minutes > need.shuttle_max_minutes:
        return (ExclusionField.SHUTTLE_MINUTES, ExclusionCode.EXCEEDS_MAXIMUM)
    return None


def _score_offer(
    offer: RankingOffer,
    need: RankingNeed,
    profile: RankingProfile,
    reliability: ReliabilityFact | None,
    min_price: int,
    max_price: int,
    min_shuttle: int,
    max_shuttle: int,
    min_distance: int,
    max_distance: int,
) -> tuple[tuple[ComponentBreakdown, ...], tuple[PenaltyItem, ...]]:
    price = invert_min_max(offer.total_minor, min_price, max_price)
    shuttle = invert_min_max(offer.shuttle_minutes, min_shuttle, max_shuttle)
    distance = invert_min_max(offer.distance_metres, min_distance, max_distance)
    cancellation = CANCELLATION_MICROS[offer.cancellation.value]
    if offer.refund is RefundTerm.NONE and cancellation > 0:
        cancellation = 0
    coverage = _coverage_micros(need.covered, offer.lot_type)
    add_on = _add_on_micros(need.representable_add_ons, offer.add_ons)
    reliability_missing = reliability is None
    reliability_value = 0 if reliability is None else reliability.score_micros
    raw: dict[ScoreComponent, tuple[int, bool]] = {
        ScoreComponent.PRICE_VALUE: (price, False),
        ScoreComponent.RELIABILITY_TRUST: (reliability_value, reliability_missing),
        ScoreComponent.CANCELLATION_FLEXIBILITY: (cancellation, False),
        ScoreComponent.SHUTTLE_CONVENIENCE: (shuttle, False),
        ScoreComponent.DISTANCE_VALUE: (distance, False),
        ScoreComponent.COVERAGE_FIT: (coverage, False),
        ScoreComponent.ADD_ON_FIT: (add_on, False),
    }
    penalties: list[PenaltyItem] = []
    rows: list[ComponentBreakdown] = []
    for name in COMPONENT_ORDER:
        micros, missing = raw[name]
        if missing:
            penalties.append(
                PenaltyItem(PenaltyKind.MISSING_COMPONENT, name, MISSING_COMPONENT_PENALTY)
            )
            contribution = 0
            stored: int | None = None
        else:
            stored = micros
            contribution = weighted_contribution(micros, profile.weight(name))
        rows.append(
            ComponentBreakdown(
                name=name,
                micros=stored,
                weight_micros=profile.weight(name),
                contribution_micros=contribution,
                missing=missing,
            )
        )
    return tuple(rows), tuple(penalties)


def _coverage_micros(preference: CoveredPreference, lot: LotType) -> int:
    if preference is CoveredPreference.NONE:
        return SCORE_SCALE
    if lot in COVERED_LOTS:
        return SCORE_SCALE
    return 0


def _add_on_micros(requested: frozenset[AddOn], offered: frozenset[AddOn]) -> int:
    if not requested:
        return SCORE_SCALE
    matched = len(requested & offered)
    return half_up(matched * SCORE_SCALE, len(requested))


def _drivers(components: tuple[ComponentBreakdown, ...]) -> tuple[ScoreComponent, ...]:
    positive = [item for item in components if item.contribution_micros > 0]
    ordered = sorted(positive, key=lambda item: (-item.contribution_micros, item.name.value))
    return tuple(item.name for item in ordered[:3])


def _fit(score: int, coverage: int, penalty: int) -> FitLabel:
    if penalty == 0 and score >= FIT_STRONG_SCORE and coverage >= FIT_STRONG_COVERAGE:
        return FitLabel.STRONG
    if score >= FIT_GOOD_SCORE and coverage >= FIT_GOOD_COVERAGE:
        return FitLabel.GOOD
    return FitLabel.FAIR


def _tie_key(item: RankedOffer) -> tuple[object, ...]:
    return (
        -item.score_micros,
        -item.evidence_coverage_micros,
        -item.remaining_validity_seconds,
        item.total_minor,
        item.offer_id.to_primitive(),
    )


def _component_micros(offer: RankedOffer, name: ScoreComponent) -> int:
    for item in offer.components:
        if item.name is name:
            return 0 if item.micros is None else item.micros
    return 0


def _downside(winner: RankedOffer, others: tuple[RankedOffer, ...]) -> MaterialDownside | None:
    if not others:
        return None
    competitor = min(others, key=_tie_key)
    if winner.total_minor > competitor.total_minor:
        return MaterialDownside(
            versus_offer_id=competitor.offer_id,
            dimension=DownsideDimension.TOTAL_MINOR,
            unit=DownsideUnit.MINOR_CURRENCY,
            delta=winner.total_minor - competitor.total_minor,
        )
    if winner.shuttle_minutes > competitor.shuttle_minutes:
        return MaterialDownside(
            versus_offer_id=competitor.offer_id,
            dimension=DownsideDimension.SHUTTLE_MINUTES,
            unit=DownsideUnit.MINUTES,
            delta=winner.shuttle_minutes - competitor.shuttle_minutes,
        )
    if winner.distance_metres > competitor.distance_metres:
        return MaterialDownside(
            versus_offer_id=competitor.offer_id,
            dimension=DownsideDimension.DISTANCE_METRES,
            unit=DownsideUnit.METRES,
            delta=winner.distance_metres - competitor.distance_metres,
        )
    coverage_delta = _component_micros(competitor, ScoreComponent.COVERAGE_FIT) - _component_micros(
        winner, ScoreComponent.COVERAGE_FIT
    )
    if coverage_delta > 0:
        return MaterialDownside(
            versus_offer_id=competitor.offer_id,
            dimension=DownsideDimension.COVERAGE_FIT,
            unit=DownsideUnit.SCORE_MICROS,
            delta=coverage_delta,
        )
    add_on_delta = _component_micros(competitor, ScoreComponent.ADD_ON_FIT) - _component_micros(
        winner, ScoreComponent.ADD_ON_FIT
    )
    if add_on_delta > 0:
        return MaterialDownside(
            versus_offer_id=competitor.offer_id,
            dimension=DownsideDimension.ADD_ON_FIT,
            unit=DownsideUnit.SCORE_MICROS,
            delta=add_on_delta,
        )
    cancellation_delta = _component_micros(
        competitor, ScoreComponent.CANCELLATION_FLEXIBILITY
    ) - _component_micros(winner, ScoreComponent.CANCELLATION_FLEXIBILITY)
    if cancellation_delta > 0:
        return MaterialDownside(
            versus_offer_id=competitor.offer_id,
            dimension=DownsideDimension.CANCELLATION,
            unit=DownsideUnit.SCORE_MICROS,
            delta=cancellation_delta,
        )
    return None


def _recency(facts: Iterable[ReliabilityFact]) -> RecencyStatus:
    observed = [item.observed_at for item in facts if item.observed_at is not None]
    if not observed:
        return RecencyStatus.UNAVAILABLE
    return RecencyStatus.OBSERVED


def _input_snapshot(
    offers: tuple[RankingOffer, ...],
    need: RankingNeed,
    reliability: tuple[ReliabilityFact, ...],
    profile: RankingProfile,
    evaluated_at: datetime,
    exclusions: list[Exclusion],
) -> DecisionInputSnapshot:
    offer_rows = []
    for offer in sorted(offers, key=lambda item: item.offer_id.to_primitive()):
        offer_rows.append(
            SnapshotOffer(
                offer_id=offer.offer_id.to_primitive(),
                supplier_token=offer.supplier_token.to_primitive(),
                version=offer.version.to_primitive(),
                total_minor=offer.total_minor,
                currency=offer.currency,
                shuttle_minutes=offer.shuttle_minutes,
                distance_metres=offer.distance_metres,
                lot_type=offer.lot_type.value,
                add_ons=tuple(sorted(item.value for item in offer.add_ons)),
                cancellation=offer.cancellation.value,
                refund=offer.refund.value,
                valid_from=format_utc(offer.valid_from),
                valid_until=format_utc(offer.valid_until),
                evidence_types=tuple(sorted(item.value for item in offer.evidence_types)),
                availability=offer.availability.value,
                simulation=True,
            )
        )
    reliability_rows = []
    for fact in sorted(reliability, key=lambda item: item.supplier_token.to_primitive()):
        reliability_rows.append(
            SnapshotReliability(
                supplier_token=fact.supplier_token.to_primitive(),
                score_micros=fact.score_micros,
                evidence_ref=fact.evidence_ref.to_primitive(),
                registry_version=fact.registry_version,
                observed_at=None if fact.observed_at is None else format_utc(fact.observed_at),
            )
        )
    return DecisionInputSnapshot(
        profile_id=profile.profile_id,
        profile_version=profile.profile_version,
        weight_version=profile.weight_version,
        config_version=CONFIG_VERSION,
        penalty_version=PENALTY_VERSION,
        tie_break_version=TIE_BREAK_VERSION,
        reason=profile.reason.value,
        evidence_ref=profile.evidence_ref.to_primitive(),
        weights=tuple(
            (component.value, profile.weight(component)) for component in COMPONENT_ORDER
        ),
        weight_bound=500_000,
        evaluated_at=format_utc(evaluated_at),
        need=SnapshotNeed(
            covered=need.covered.value,
            representable_add_ons=tuple(sorted(item.value for item in need.representable_add_ons)),
            shuttle_max_minutes=need.shuttle_max_minutes,
        ),
        reliability=tuple(reliability_rows),
        offers=tuple(offer_rows),
        exclusions=tuple(
            SnapshotExclusion(
                offer_id=None if item.offer_id is None else item.offer_id.to_primitive(),
                field=item.field.value,
                code=item.code.value,
            )
            for item in exclusions
        ),
    )
