from __future__ import annotations

from dataclasses import replace

import pytest
from wp05_ranking_helpers import (
    EVALUATED_AT,
    PARKDIRECT_OFFER,
    SKYSHIELD_OFFER,
    _need,
    _reliability,
    parkdirect_offer,
    rank_golden,
    skyshield_offer,
)

from itaa_domain.value_objects import (
    AddOn,
    CancellationTerm,
    CoveredPreference,
    LotType,
    RefundTerm,
)
from itaa_ranking.errors import RankingError
from itaa_ranking.profile import half_up, invert_min_max
from itaa_ranking.rank import rank_offers
from itaa_ranking.vocab import DownsideDimension, DownsideUnit, ScoreComponent


def _rank(winner, runner):
    return rank_offers(
        (winner, runner),
        _need(),
        evaluated_at=EVALUATED_AT,
        reliability=_reliability(),
    )


def test_coverage_only_downside_uses_score_micros() -> None:
    winner = replace(parkdirect_offer(), lot_type=LotType.UNCOVERED)
    runner = replace(
        skyshield_offer(),
        total_minor=20_000,
        shuttle_minutes=winner.shuttle_minutes,
        distance_metres=winner.distance_metres,
        add_ons=frozenset(),
        cancellation=CancellationTerm.FREE_UNTIL_24H,
        lot_type=LotType.COVERED,
    )
    result = _rank(winner, runner)
    assert result.recommended_offer_id == PARKDIRECT_OFFER
    assert result.downside is not None
    assert result.downside.versus_offer_id == SKYSHIELD_OFFER
    assert result.downside.dimension is DownsideDimension.COVERAGE_FIT
    assert result.downside.unit is DownsideUnit.SCORE_MICROS
    assert result.downside.delta > 0


def test_add_on_only_downside_uses_score_micros() -> None:
    winner = replace(parkdirect_offer(), lot_type=LotType.COVERED, add_ons=frozenset())
    runner = replace(
        skyshield_offer(),
        total_minor=20_000,
        shuttle_minutes=winner.shuttle_minutes,
        distance_metres=winner.distance_metres,
        lot_type=LotType.COVERED,
        add_ons=frozenset({AddOn.EV_CHARGING}),
        cancellation=CancellationTerm.FREE_UNTIL_24H,
    )
    result = _rank(winner, runner)
    assert result.recommended_offer_id == PARKDIRECT_OFFER
    assert result.downside is not None
    assert result.downside.dimension is DownsideDimension.ADD_ON_FIT
    assert result.downside.unit is DownsideUnit.SCORE_MICROS
    assert result.downside.delta > 0


def test_cancellation_only_downside_uses_score_micros() -> None:
    winner = replace(
        parkdirect_offer(),
        lot_type=LotType.COVERED,
        add_ons=frozenset({AddOn.EV_CHARGING}),
        cancellation=CancellationTerm.NON_REFUNDABLE,
        refund=RefundTerm.NONE,
    )
    runner = replace(
        skyshield_offer(),
        total_minor=20_000,
        shuttle_minutes=winner.shuttle_minutes,
        distance_metres=winner.distance_metres,
        lot_type=LotType.COVERED,
        add_ons=frozenset({AddOn.EV_CHARGING}),
        cancellation=CancellationTerm.FREE_UNTIL_24H,
        refund=RefundTerm.ORIGINAL_METHOD,
    )
    result = _rank(winner, runner)
    assert result.recommended_offer_id == PARKDIRECT_OFFER
    assert result.downside is not None
    assert result.downside.dimension is DownsideDimension.CANCELLATION
    assert result.downside.unit is DownsideUnit.SCORE_MICROS
    assert result.downside.delta > 0


def test_winner_not_worse_on_any_dimension_has_no_downside() -> None:
    worse = replace(
        parkdirect_offer(),
        offer_id=SKYSHIELD_OFFER,
        supplier_token=skyshield_offer().supplier_token,
        total_minor=20_000,
        shuttle_minutes=20,
        distance_metres=5000,
    )
    result = _rank(parkdirect_offer(), worse)
    assert result.recommended_offer_id == PARKDIRECT_OFFER
    assert result.downside is None


def test_shuttle_and_distance_downsides_follow_precedence() -> None:
    winner = replace(
        parkdirect_offer(),
        lot_type=LotType.COVERED,
        add_ons=frozenset({AddOn.EV_CHARGING}),
        shuttle_minutes=18,
        distance_metres=1000,
        total_minor=5_000,
    )
    runner = replace(
        skyshield_offer(),
        lot_type=LotType.COVERED,
        add_ons=frozenset({AddOn.EV_CHARGING}),
        shuttle_minutes=8,
        distance_metres=1000,
        total_minor=20_000,
    )
    shuttle = _rank(winner, runner)
    assert shuttle.recommended_offer_id == PARKDIRECT_OFFER
    assert shuttle.downside is not None
    assert shuttle.downside.dimension is DownsideDimension.SHUTTLE_MINUTES
    assert shuttle.downside.unit is DownsideUnit.MINUTES
    distance_winner = replace(winner, shuttle_minutes=8, distance_metres=4000)
    distance_runner = replace(runner, shuttle_minutes=8, distance_metres=1000)
    distance = _rank(distance_winner, distance_runner)
    assert distance.recommended_offer_id == PARKDIRECT_OFFER
    assert distance.downside is not None
    assert distance.downside.dimension is DownsideDimension.DISTANCE_METRES
    assert distance.downside.unit is DownsideUnit.METRES


def test_golden_downside_remains_usd_29() -> None:
    result = rank_golden()
    assert [item.score_micros for item in result.ranked] == [671_000, 660_000, 535_000]
    assert result.downside is not None
    assert result.downside.versus_offer_id == parkdirect_offer().offer_id
    assert result.downside.dimension is DownsideDimension.TOTAL_MINOR
    assert result.downside.delta == 2900
    sky = result.ranked[0]
    contributions = {item.name: item.contribution_micros for item in sky.components}
    assert contributions[ScoreComponent.RELIABILITY_TRUST] == 190_000


def test_ranking_guardrails_and_remaining_dimensions() -> None:
    with pytest.raises(RankingError, match="profile: invalid"):
        rank_offers(
            (parkdirect_offer(),),
            _need(),
            evaluated_at=EVALUATED_AT,
            reliability=_reliability(),
            profile=object(),  # type: ignore[arg-type]
        )
    with pytest.raises(RankingError, match="reliability: duplicate_supplier"):
        rank_offers(
            (parkdirect_offer(),),
            _need(),
            evaluated_at=EVALUATED_AT,
            reliability=(_reliability()[0], _reliability()[0]),
        )
    with pytest.raises(RankingError, match="must_be_positive"):
        half_up(1, 0)
    with pytest.raises(RankingError, match="must_be_non_negative"):
        half_up(-1, 2)
    with pytest.raises(RankingError, match="range: invalid"):
        invert_min_max(1, 5, 1)
    with pytest.raises(RankingError, match="out_of_cohort"):
        invert_min_max(9, 0, 1)
    assert invert_min_max(3, 3, 3) == 1_000_000
    over = rank_offers(
        (parkdirect_offer(),),
        replace(_need(), shuttle_max_minutes=1),
        evaluated_at=EVALUATED_AT,
        reliability=_reliability(),
    )
    assert over.ranked == ()
    none_need = replace(_need(), covered=CoveredPreference.NONE)
    none = rank_offers(
        (parkdirect_offer(), skyshield_offer()),
        none_need,
        evaluated_at=EVALUATED_AT,
        reliability=_reliability(),
    )
    coverage = {
        item.offer_id: next(
            row.micros for row in item.components if row.name is ScoreComponent.COVERAGE_FIT
        )
        for item in none.ranked
    }
    assert set(coverage.values()) == {1_000_000}
    refunded = rank_offers(
        (replace(parkdirect_offer(), refund=RefundTerm.NONE),),
        _need(),
        evaluated_at=EVALUATED_AT,
        reliability=_reliability(),
    )
    cancellation = next(
        row
        for row in refunded.ranked[0].components
        if row.name is ScoreComponent.CANCELLATION_FLEXIBILITY
    )
    assert cancellation.micros == 0
