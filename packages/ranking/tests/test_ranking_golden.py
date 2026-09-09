from __future__ import annotations

from itertools import permutations

from wp05_ranking_helpers import (
    PARKDIRECT_OFFER,
    SKYSHIELD_OFFER,
    TERMINALFLEX_OFFER,
    golden_offers,
    rank_golden,
)

from itaa_ranking.rank import RecencyStatus
from itaa_ranking.vocab import DownsideDimension, ScoreComponent


def test_golden_vector_scores_order_drivers_and_downside() -> None:
    result = rank_golden()
    by_id = {item.offer_id: item for item in result.ranked}
    sky = by_id[SKYSHIELD_OFFER]
    park = by_id[PARKDIRECT_OFFER]
    flex = by_id[TERMINALFLEX_OFFER]
    assert sky.score_micros == 671_000
    assert park.score_micros == 660_000
    assert flex.score_micros == 535_000
    assert [item.offer_id for item in result.ranked] == [
        SKYSHIELD_OFFER,
        PARKDIRECT_OFFER,
        TERMINALFLEX_OFFER,
    ]
    assert result.recommended_offer_id == SKYSHIELD_OFFER
    assert sky.drivers == (
        ScoreComponent.RELIABILITY_TRUST,
        ScoreComponent.CANCELLATION_FLEXIBILITY,
        ScoreComponent.PRICE_VALUE,
    )
    contributions = {item.name: item.contribution_micros for item in sky.components}
    assert contributions[ScoreComponent.RELIABILITY_TRUST] == 190_000
    assert contributions[ScoreComponent.CANCELLATION_FLEXIBILITY] == 150_000
    assert contributions[ScoreComponent.PRICE_VALUE] == 147_000
    assert result.downside is not None
    assert result.downside.versus_offer_id == PARKDIRECT_OFFER
    assert result.downside.dimension is DownsideDimension.TOTAL_MINOR
    assert result.downside.delta == 2900
    assert sky.fit.value == "GOOD"
    assert result.recency is RecencyStatus.UNAVAILABLE
    assert park.penalty_micros == 0
    assert sky.penalty_micros == 0
    assert flex.penalty_micros == 0


def test_all_input_permutations_are_byte_identical() -> None:
    baseline = rank_golden().fingerprint_material()
    for order in permutations(golden_offers()):
        result = rank_golden(order)
        assert result.fingerprint_material() == baseline
        assert [item.offer_id for item in result.ranked] == [
            SKYSHIELD_OFFER,
            PARKDIRECT_OFFER,
            TERMINALFLEX_OFFER,
        ]


def test_one_thousand_repeated_runs_are_identical() -> None:
    first = rank_golden().fingerprint_material()
    for _ in range(1000):
        assert rank_golden().fingerprint_material() == first
