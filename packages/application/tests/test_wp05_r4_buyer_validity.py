from __future__ import annotations

from dataclasses import replace
from datetime import timedelta

import pytest
from wp04_helpers import OCCURRED_AT
from wp05_helpers import collected_offer, fixture_policy, scoped_fixture
from wp05_ranking_helpers import rank_golden

from itaa_application.errors import ApplicationError
from itaa_application.offer_boundary import accept_offer
from itaa_domain.offer import OfferState
from itaa_domain.value_objects import format_utc, parse_utc
from itaa_ranking.vocab import DownsideDimension


def _policy_with_window(binding, payload, *, minimum: int, maximum: int):
    return replace(
        fixture_policy(binding, payload),
        min_validity_seconds=minimum,
        max_validity_seconds=maximum,
    )


def _until(payload: dict[str, object], delta: timedelta) -> dict[str, object]:
    mutated = dict(payload)
    start = parse_utc(payload["validFrom"], "validFrom")
    mutated["validUntil"] = format_utc(start + delta)
    return mutated


def test_buyer_accepts_exact_minimum_and_maximum_duration() -> None:
    payload, binding = scoped_fixture("offer-parkdirect.json")
    policy = _policy_with_window(payload=payload, binding=binding, minimum=900, maximum=1800)
    exact_min = accept_offer(
        collected_offer(_until(payload, timedelta(seconds=900)), binding),
        policy,
        evaluated_at=OCCURRED_AT,
    )
    exact_max = accept_offer(
        collected_offer(_until(payload, timedelta(seconds=1800)), binding),
        policy,
        evaluated_at=OCCURRED_AT,
    )
    assert exact_min.offer.state is OfferState.ELIGIBLE
    assert exact_max.offer.state is OfferState.ELIGIBLE


def test_buyer_rejects_exact_duration_below_minimum() -> None:
    payload, binding = scoped_fixture("offer-parkdirect.json")
    policy = _policy_with_window(payload=payload, binding=binding, minimum=900, maximum=1800)
    with pytest.raises(ApplicationError, match="validity: out_of_range") as captured:
        accept_offer(
            collected_offer(
                _until(payload, timedelta(seconds=900) - timedelta(microseconds=1)),
                binding,
            ),
            policy,
            evaluated_at=OCCURRED_AT,
        )
    assert "900" not in str(captured.value)
    with pytest.raises(ApplicationError, match="validity: out_of_range"):
        accept_offer(
            collected_offer(_until(payload, timedelta(seconds=899)), binding),
            policy,
            evaluated_at=OCCURRED_AT,
        )


def test_buyer_rejects_exact_duration_above_maximum_without_truncation() -> None:
    payload, binding = scoped_fixture("offer-parkdirect.json")
    policy = _policy_with_window(payload=payload, binding=binding, minimum=900, maximum=1800)
    with pytest.raises(ApplicationError, match="validity: out_of_range"):
        accept_offer(
            collected_offer(
                _until(payload, timedelta(seconds=1800) + timedelta(microseconds=1)),
                binding,
            ),
            policy,
            evaluated_at=OCCURRED_AT,
        )
    with pytest.raises(ApplicationError, match="validity: out_of_range"):
        accept_offer(
            collected_offer(_until(payload, timedelta(seconds=1800, milliseconds=500)), binding),
            policy,
            evaluated_at=OCCURRED_AT,
        )


def test_golden_vector_scores_and_downside_are_unchanged() -> None:
    result = rank_golden()
    by_id = {item.offer_id.to_primitive(): item for item in result.ranked}
    assert by_id["of_01k2m3n4p5q6r7s8t9v0w1x2a2"].score_micros == 671_000
    assert by_id["of_01k2m3n4p5q6r7s8t9v0w1x2a1"].score_micros == 660_000
    assert by_id["of_01k2m3n4p5q6r7s8t9v0w1x2a3"].score_micros == 535_000
    assert result.downside is not None
    assert result.downside.dimension is DownsideDimension.TOTAL_MINOR
    assert result.downside.delta == 2900
