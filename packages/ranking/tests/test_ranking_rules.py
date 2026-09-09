from __future__ import annotations

from dataclasses import replace
from datetime import timedelta

import pytest
from wp05_ranking_helpers import (
    EVALUATED_AT,
    PARKDIRECT,
    PARKDIRECT_OFFER,
    SKYSHIELD,
    SKYSHIELD_OFFER,
    _need,
    _reliability,
    parkdirect_offer,
    rank_golden,
    skyshield_offer,
    terminalflex_offer,
)

from itaa_domain.value_objects import (
    CoveredPreference,
    EvidenceRef,
    EvidenceType,
    SimulatedAvailability,
)
from itaa_ranking.errors import RankingError
from itaa_ranking.inputs import ReliabilityFact
from itaa_ranking.profile import (
    DEFAULT_PROFILE,
    DEFAULT_WEIGHTS,
    SCORE_SCALE,
    RankingProfile,
    half_up,
    invert_min_max,
    weighted_contribution,
)
from itaa_ranking.rank import evidence_coverage_micros, rank_offers
from itaa_ranking.vocab import ExclusionCode, GapCode, ProfileReason, ScoreComponent


def test_equal_values_normalize_to_full_scale() -> None:
    assert invert_min_max(10, 10, 10) == SCORE_SCALE
    assert invert_min_max(5, 0, 10) == 500_000
    assert weighted_contribution(950_000, 200_000) == 190_000
    assert half_up(1 * SCORE_SCALE, 4) == 250_000


def test_single_offer_cohort_receives_full_lower_is_better_scores() -> None:
    result = rank_offers(
        (parkdirect_offer(),),
        _need(),
        evaluated_at=EVALUATED_AT,
        reliability=_reliability(),
    )
    assert len(result.ranked) == 1
    components = {item.name: item.micros for item in result.ranked[0].components}
    assert components[ScoreComponent.PRICE_VALUE] == SCORE_SCALE
    assert components[ScoreComponent.SHUTTLE_CONVENIENCE] == SCORE_SCALE
    assert components[ScoreComponent.DISTANCE_VALUE] == SCORE_SCALE
    assert result.recommended_offer_id == PARKDIRECT_OFFER


def test_invalid_weight_total_and_bounds_fail_closed() -> None:
    with pytest.raises(RankingError, match="must_sum_to_scale"):
        RankingProfile(
            profile_id="airport_parking_v1",
            profile_version="1.0",
            weight_version="1.0",
            weights={**DEFAULT_WEIGHTS, "add_on_fit": 41_000},
            reason=ProfileReason.TEST_PROFILE,
            evidence_ref=EvidenceRef("ranking.test"),
        )
    with pytest.raises(RankingError, match="out_of_bound"):
        RankingProfile(
            profile_id="airport_parking_v1",
            profile_version="1.0",
            weight_version="1.0",
            weights={**DEFAULT_WEIGHTS, "price_value": 501_000, "add_on_fit": 0},
            reason=ProfileReason.TEST_PROFILE,
            evidence_ref=EvidenceRef("ranking.test"),
        )
    with pytest.raises(RankingError, match="unsupported"):
        replace(DEFAULT_PROFILE, profile_id="other")


def test_missing_reliability_is_penalized_not_optimistic() -> None:
    with_fact = rank_offers(
        (skyshield_offer(),),
        _need(),
        evaluated_at=EVALUATED_AT,
        reliability=_reliability(),
    )
    without_fact = rank_offers(
        (skyshield_offer(),),
        _need(),
        evaluated_at=EVALUATED_AT,
        reliability=(),
    )
    row = without_fact.ranked[0]
    reliability = next(
        item for item in row.components if item.name is ScoreComponent.RELIABILITY_TRUST
    )
    assert reliability.missing is True
    assert reliability.contribution_micros == 0
    assert row.penalty_micros == 50_000
    assert row.score_micros == with_fact.ranked[0].score_micros - 190_000 - 50_000
    assert sum(item.micros for item in row.penalties) == row.penalty_micros


def test_required_uncovered_is_ineligible() -> None:
    need = replace(_need(), covered=CoveredPreference.REQUIRED)
    result = rank_offers(
        (parkdirect_offer(), skyshield_offer()),
        need,
        evaluated_at=EVALUATED_AT,
        reliability=_reliability(),
    )
    assert any(
        item.offer_id == PARKDIRECT_OFFER and item.code is ExclusionCode.REQUIRED
        for item in result.exclusions
    )
    assert result.recommended_offer_id == SKYSHIELD_OFFER


def test_unavailable_and_expired_cannot_be_recommended() -> None:
    unavailable = replace(
        skyshield_offer(), availability=SimulatedAvailability.UNAVAILABLE_SIMULATED
    )
    expired = replace(
        parkdirect_offer(),
        valid_from=EVALUATED_AT - timedelta(hours=1),
        valid_until=EVALUATED_AT,
    )
    result = rank_offers(
        (unavailable, expired),
        _need(),
        evaluated_at=EVALUATED_AT,
        reliability=_reliability(),
    )
    assert result.recommended_offer_id is None
    assert result.fit is None
    assert {item.code for item in result.exclusions} == {
        ExclusionCode.UNAVAILABLE,
        ExclusionCode.EXPIRED,
    }


def test_no_eligible_offers_returns_no_recommendation() -> None:
    expired = replace(
        parkdirect_offer(),
        valid_from=EVALUATED_AT - timedelta(hours=1),
        valid_until=EVALUATED_AT,
    )
    result = rank_offers(
        (expired,),
        _need(),
        evaluated_at=EVALUATED_AT,
        reliability=_reliability(),
    )
    assert result.ranked == ()
    assert result.recommended_offer_id is None
    assert GapCode.NO_ELIGIBLE_OFFERS in result.gaps


def _equal_reliability() -> tuple[ReliabilityFact, ...]:
    return (
        ReliabilityFact(
            PARKDIRECT,
            700_000,
            EvidenceRef("registry.parkdirect.reliability.v1"),
            "synthetic.v1",
        ),
        ReliabilityFact(
            SKYSHIELD,
            700_000,
            EvidenceRef("registry.skyshield.reliability.v1"),
            "synthetic.v1",
        ),
    )


def test_lexicographic_offer_id_breaks_remaining_ties() -> None:
    first = parkdirect_offer()
    second = replace(
        parkdirect_offer(),
        offer_id=SKYSHIELD_OFFER,
        supplier_token=SKYSHIELD,
    )
    result = rank_offers(
        (first, second),
        _need(),
        evaluated_at=EVALUATED_AT,
        reliability=_equal_reliability(),
    )
    assert [item.offer_id for item in result.ranked] == [PARKDIRECT_OFFER, SKYSHIELD_OFFER]
    assert result.ranked[0].score_micros == result.ranked[1].score_micros


def test_longer_validity_breaks_score_ties_before_price() -> None:
    shorter = parkdirect_offer()
    longer = replace(
        parkdirect_offer(),
        offer_id=SKYSHIELD_OFFER,
        supplier_token=SKYSHIELD,
        valid_until=EVALUATED_AT + timedelta(hours=36),
    )
    result = rank_offers(
        (shorter, longer),
        _need(),
        evaluated_at=EVALUATED_AT,
        reliability=_equal_reliability(),
    )
    assert result.recommended_offer_id == SKYSHIELD_OFFER
    assert result.ranked[0].remaining_validity_seconds > result.ranked[1].remaining_validity_seconds


def test_lower_total_breaks_ties_when_price_is_unweighted() -> None:
    profile = RankingProfile(
        profile_id="airport_parking_v1",
        profile_version="1.0",
        weight_version="1.0",
        weights={
            "price_value": 0,
            "reliability_trust": 200_000,
            "cancellation_flexibility": 500_000,
            "shuttle_convenience": 120_000,
            "distance_value": 80_000,
            "coverage_fit": 60_000,
            "add_on_fit": 40_000,
        },
        reason=ProfileReason.TEST_PROFILE,
        evidence_ref=EvidenceRef("ranking.test.tie"),
    )
    cheaper = replace(
        parkdirect_offer(),
        offer_id=SKYSHIELD_OFFER,
        supplier_token=SKYSHIELD,
        total_minor=10000,
    )
    result = rank_offers(
        (parkdirect_offer(), cheaper),
        _need(),
        evaluated_at=EVALUATED_AT,
        reliability=_equal_reliability(),
        profile=profile,
    )
    assert result.ranked[0].score_micros == result.ranked[1].score_micros
    assert result.recommended_offer_id == SKYSHIELD_OFFER


def test_fingerprint_changes_when_score_material_changes() -> None:
    baseline = rank_golden().fingerprint_material()
    mutated = replace(skyshield_offer(), total_minor=14700)
    changed = rank_offers(
        (parkdirect_offer(), mutated, terminalflex_offer()),
        _need(),
        evaluated_at=EVALUATED_AT,
        reliability=_reliability(),
    )
    assert changed.fingerprint_material() != baseline


def test_evidence_coverage_is_class_count_not_prose() -> None:
    assert evidence_coverage_micros(frozenset({EvidenceType.SUPPLIER_POLICY})) == 250_000
    assert (
        evidence_coverage_micros(
            frozenset(
                {
                    EvidenceType.SUPPLIER_POLICY,
                    EvidenceType.RATE_CARD,
                    EvidenceType.LOT_RULES,
                    EvidenceType.AVAILABILITY_SNAPSHOT,
                }
            )
        )
        == SCORE_SCALE
    )


def test_error_strings_do_not_echo_tokens() -> None:
    with pytest.raises(RankingError) as captured:
        replace(DEFAULT_PROFILE, profile_id="alice@example.com")
    assert "alice@" not in str(captured.value)
    assert "sp_" not in str(captured.value)
