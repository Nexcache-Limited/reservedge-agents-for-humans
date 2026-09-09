"""Versioned airport-parking ranking profile and integer weights."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final

from itaa_domain.value_objects import EvidenceRef
from itaa_ranking.errors import RankingError
from itaa_ranking.vocab import ProfileReason, ScoreComponent

SCORE_SCALE: Final[int] = 1_000_000
MISSING_COMPONENT_PENALTY: Final[int] = 50_000
COMPONENT_WEIGHT_BOUND: Final[int] = 500_000
PROFILE_ID: Final[str] = "airport_parking_v1"
PROFILE_VERSION: Final[str] = "1.0"
WEIGHT_VERSION: Final[str] = "1.0"
PENALTY_VERSION: Final[str] = "missing_component_v1"
TIE_BREAK_VERSION: Final[str] = "evidence_validity_total_id_v1"
CONFIG_VERSION: Final[str] = "1.0"

COMPONENT_ORDER: Final[tuple[ScoreComponent, ...]] = (
    ScoreComponent.PRICE_VALUE,
    ScoreComponent.RELIABILITY_TRUST,
    ScoreComponent.CANCELLATION_FLEXIBILITY,
    ScoreComponent.SHUTTLE_CONVENIENCE,
    ScoreComponent.DISTANCE_VALUE,
    ScoreComponent.COVERAGE_FIT,
    ScoreComponent.ADD_ON_FIT,
)

DEFAULT_WEIGHTS: Final[Mapping[str, int]] = MappingProxyType(
    {
        ScoreComponent.PRICE_VALUE.value: 350_000,
        ScoreComponent.RELIABILITY_TRUST.value: 200_000,
        ScoreComponent.CANCELLATION_FLEXIBILITY.value: 150_000,
        ScoreComponent.SHUTTLE_CONVENIENCE.value: 120_000,
        ScoreComponent.DISTANCE_VALUE.value: 80_000,
        ScoreComponent.COVERAGE_FIT.value: 60_000,
        ScoreComponent.ADD_ON_FIT.value: 40_000,
    }
)

CANCELLATION_MICROS: Final[Mapping[str, int]] = MappingProxyType(
    {
        "free_until_24h": SCORE_SCALE,
        "free_until_48h": 700_000,
        "non_refundable": 0,
    }
)

FIT_STRONG_SCORE: Final[int] = 800_000
FIT_STRONG_COVERAGE: Final[int] = 750_000
FIT_GOOD_SCORE: Final[int] = 650_000
FIT_GOOD_COVERAGE: Final[int] = 250_000

SEEDED_RELIABILITY: Final[Mapping[str, int]] = MappingProxyType(
    {
        "sp_01k2m3n4p5q6r7s8t9v0w1x2b1": 700_000,
        "sp_01k2m3n4p5q6r7s8t9v0w1x2b2": 950_000,
        "sp_01k2m3n4p5q6r7s8t9v0w1x2b3": 850_000,
    }
)


def half_up(numerator: int, denominator: int) -> int:
    if denominator <= 0:
        raise RankingError("denominator", "must_be_positive")
    if numerator < 0:
        raise RankingError("numerator", "must_be_non_negative")
    return (numerator + denominator // 2) // denominator


def weighted_contribution(component_micros: int, weight_micros: int) -> int:
    if component_micros < 0 or component_micros > SCORE_SCALE:
        raise RankingError("component_micros", "out_of_range")
    if weight_micros < 0 or weight_micros > COMPONENT_WEIGHT_BOUND:
        raise RankingError("weight_micros", "out_of_bound")
    return (component_micros * weight_micros + 500_000) // SCORE_SCALE


def invert_min_max(value: int, minimum: int, maximum: int) -> int:
    if minimum > maximum:
        raise RankingError("range", "invalid")
    if value < minimum or value > maximum:
        raise RankingError("value", "out_of_cohort")
    if minimum == maximum:
        return SCORE_SCALE
    return half_up((maximum - value) * SCORE_SCALE, maximum - minimum)


@dataclass(frozen=True, slots=True)
class RankingProfile:
    profile_id: str
    profile_version: str
    weight_version: str
    weights: Mapping[str, int]
    reason: ProfileReason
    evidence_ref: EvidenceRef

    def __post_init__(self) -> None:
        if self.profile_id != PROFILE_ID:
            raise RankingError("profile_id", "unsupported")
        if self.profile_version != PROFILE_VERSION:
            raise RankingError("profile_version", "unsupported")
        if self.weight_version != WEIGHT_VERSION:
            raise RankingError("weight_version", "unsupported")
        if type(self.reason) is not ProfileReason:
            raise RankingError("reason", "invalid_enum")
        if type(self.evidence_ref) is not EvidenceRef:
            raise RankingError("evidence_ref", "invalid")
        if not isinstance(self.weights, Mapping):
            raise RankingError("weights", "must_be_mapping")
        copied = {str(key): self.weights[key] for key in self.weights}
        expected = {item.value for item in COMPONENT_ORDER}
        if set(copied) != expected:
            raise RankingError("weights", "unknown_or_missing_component")
        total = 0
        ordered: dict[str, int] = {}
        for component in COMPONENT_ORDER:
            weight = copied[component.value]
            if type(weight) is not int or isinstance(weight, bool):
                raise RankingError(component.value, "must_be_integer")
            if weight < 0 or weight > COMPONENT_WEIGHT_BOUND:
                raise RankingError(component.value, "out_of_bound")
            ordered[component.value] = weight
            total += weight
        if total != SCORE_SCALE:
            raise RankingError("weights", "must_sum_to_scale")
        object.__setattr__(self, "weights", MappingProxyType(ordered))

    def weight(self, component: ScoreComponent | str) -> int:
        key = component.value if isinstance(component, ScoreComponent) else component
        return self.weights[key]


DEFAULT_PROFILE = RankingProfile(
    profile_id=PROFILE_ID,
    profile_version=PROFILE_VERSION,
    weight_version=WEIGHT_VERSION,
    weights=dict(DEFAULT_WEIGHTS),
    reason=ProfileReason.LOCKED_MVP_DEFAULT,
    evidence_ref=EvidenceRef("ranking.airport_parking_v1.weights"),
)
