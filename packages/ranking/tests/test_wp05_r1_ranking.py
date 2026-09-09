from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from types import MappingProxyType

import pytest
from wp05_ranking_helpers import (
    EVALUATED_AT,
    PARKDIRECT_OFFER,
    SKYSHIELD_OFFER,
    TERMINALFLEX,
    _need,
    _reliability,
    parkdirect_offer,
    rank_golden,
    skyshield_offer,
    terminalflex_offer,
)

from itaa_domain.value_objects import EvidenceRef, SimulatedAvailability, Version
from itaa_ranking.errors import RankingError
from itaa_ranking.inputs import RankingNeed, ReliabilityFact
from itaa_ranking.profile import (
    CANCELLATION_MICROS,
    DEFAULT_PROFILE,
    DEFAULT_WEIGHTS,
    SEEDED_RELIABILITY,
    RankingProfile,
)
from itaa_ranking.rank import rank_offers
from itaa_ranking.vocab import ProfileReason, ScoreComponent


def test_default_weights_and_profile_are_deeply_immutable() -> None:
    with pytest.raises(TypeError):
        DEFAULT_WEIGHTS["price_value"] = 0  # type: ignore[index]
    with pytest.raises(TypeError):
        DEFAULT_PROFILE.weights["price_value"] = 0  # type: ignore[index]
    with pytest.raises(TypeError):
        CANCELLATION_MICROS["free_until_24h"] = 0  # type: ignore[index]
    with pytest.raises(TypeError):
        SEEDED_RELIABILITY["sp_01k2m3n4p5q6r7s8t9v0w1x2b1"] = 0  # type: ignore[index]
    assert isinstance(DEFAULT_PROFILE.weights, MappingProxyType)
    source = dict(DEFAULT_WEIGHTS)
    profile = RankingProfile(
        profile_id="airport_parking_v1",
        profile_version="1.0",
        weight_version="1.0",
        weights=source,
        reason=ProfileReason.TEST_PROFILE,
        evidence_ref=EvidenceRef("ranking.alias"),
    )
    source["price_value"] = 0
    assert profile.weight(ScoreComponent.PRICE_VALUE) == 350_000
    mutated = replace(DEFAULT_PROFILE, reason=ProfileReason.TEST_PROFILE)
    assert DEFAULT_PROFILE.reason is ProfileReason.LOCKED_MVP_DEFAULT
    assert mutated.reason is ProfileReason.TEST_PROFILE
    assert rank_golden().ranked[0].score_micros == 671_000


def test_fingerprint_binds_reliability_provenance_and_need() -> None:
    baseline = rank_golden().fingerprint_material()
    provenance = (
        replace(
            _reliability()[0],
            registry_version="synthetic.v2",
            evidence_ref=EvidenceRef("registry.parkdirect.reliability.v2"),
        ),
        _reliability()[1],
        _reliability()[2],
    )
    changed_reliability = rank_offers(
        (parkdirect_offer(), skyshield_offer(), terminalflex_offer()),
        _need(),
        evaluated_at=EVALUATED_AT,
        reliability=provenance,
    )
    assert changed_reliability.ranked[0].score_micros == 671_000
    assert changed_reliability.fingerprint_material() != baseline
    observed = (
        replace(_reliability()[0], observed_at=EVALUATED_AT),
        _reliability()[1],
        _reliability()[2],
    )
    changed_observed = rank_offers(
        (parkdirect_offer(), skyshield_offer(), terminalflex_offer()),
        _need(),
        evaluated_at=EVALUATED_AT,
        reliability=observed,
    )
    assert changed_observed.fingerprint_material() != baseline
    wider = replace(_need(), shuttle_max_minutes=30)
    changed_need = rank_offers(
        (parkdirect_offer(), skyshield_offer(), terminalflex_offer()),
        wider,
        evaluated_at=EVALUATED_AT,
        reliability=_reliability(),
    )
    assert [item.score_micros for item in changed_need.ranked] == [
        item.score_micros for item in rank_golden().ranked
    ]
    assert changed_need.fingerprint_material() != baseline


def test_fingerprint_families_each_mutate() -> None:
    baseline = rank_golden().fingerprint_material()
    families = [
        rank_offers(
            (
                replace(parkdirect_offer(), total_minor=11899),
                skyshield_offer(),
                terminalflex_offer(),
            ),
            _need(),
            evaluated_at=EVALUATED_AT,
            reliability=_reliability(),
        ),
        rank_offers(
            (parkdirect_offer(), skyshield_offer(), terminalflex_offer()),
            replace(_need(), representable_add_ons=frozenset()),
            evaluated_at=EVALUATED_AT,
            reliability=_reliability(),
        ),
        rank_offers(
            (parkdirect_offer(), skyshield_offer(), terminalflex_offer()),
            _need(),
            evaluated_at=EVALUATED_AT + timedelta(seconds=1),
            reliability=_reliability(),
        ),
        rank_offers(
            (parkdirect_offer(), skyshield_offer(), terminalflex_offer()),
            _need(),
            evaluated_at=EVALUATED_AT,
            reliability=_reliability(),
            profile=RankingProfile(
                profile_id="airport_parking_v1",
                profile_version="1.0",
                weight_version="1.0",
                weights=dict(DEFAULT_WEIGHTS),
                reason=ProfileReason.TEST_PROFILE,
                evidence_ref=EvidenceRef("ranking.airport_parking_v1.weights"),
            ),
        ),
        rank_offers(
            (
                replace(
                    parkdirect_offer(),
                    valid_from=EVALUATED_AT - timedelta(hours=1),
                    valid_until=EVALUATED_AT,
                ),
                skyshield_offer(),
                terminalflex_offer(),
            ),
            _need(),
            evaluated_at=EVALUATED_AT,
            reliability=_reliability(),
        ),
    ]
    assert all(item.fingerprint_material() != baseline for item in families)


def test_duplicate_ids_versions_and_suppliers_fail_closed() -> None:
    with pytest.raises(RankingError, match="offer_id: duplicate"):
        rank_offers(
            (parkdirect_offer(), parkdirect_offer()),
            _need(),
            evaluated_at=EVALUATED_AT,
            reliability=_reliability(),
        )
    with pytest.raises(RankingError, match="supplier_token: duplicate"):
        rank_offers(
            (
                parkdirect_offer(),
                replace(parkdirect_offer(), offer_id=SKYSHIELD_OFFER, version=Version(2)),
            ),
            _need(),
            evaluated_at=EVALUATED_AT,
            reliability=_reliability(),
        )


def test_malformed_ranking_primitives_fail_closed() -> None:
    with pytest.raises(RankingError):
        replace(parkdirect_offer(), shuttle_minutes=-1)
    with pytest.raises(RankingError):
        replace(parkdirect_offer(), distance_metres=True)  # type: ignore[arg-type]
    with pytest.raises(RankingError):
        replace(parkdirect_offer(), total_minor=-1)
    with pytest.raises(RankingError):
        RankingNeed(_need().covered, frozenset(), shuttle_max_minutes=True)  # type: ignore[arg-type]
    with pytest.raises(RankingError):
        ReliabilityFact(
            TERMINALFLEX,
            True,  # type: ignore[arg-type]
            EvidenceRef("registry.terminalflex.reliability.v1"),
            "synthetic.v1",
        )


def test_ineligible_permutations_are_sorted_and_stable() -> None:
    unavailable = replace(
        skyshield_offer(), availability=SimulatedAvailability.UNAVAILABLE_SIMULATED
    )
    expired = replace(
        parkdirect_offer(),
        valid_from=EVALUATED_AT - timedelta(hours=1),
        valid_until=EVALUATED_AT,
    )
    first = rank_offers(
        (unavailable, expired),
        _need(),
        evaluated_at=EVALUATED_AT,
        reliability=_reliability(),
    )
    second = rank_offers(
        (expired, unavailable),
        _need(),
        evaluated_at=EVALUATED_AT,
        reliability=_reliability(),
    )
    assert first.fingerprint_material() == second.fingerprint_material()
    assert [item.offer_id for item in first.exclusions] == [
        item.offer_id for item in second.exclusions
    ]


def test_cheapest_winner_has_no_score_downside() -> None:
    worse = replace(
        parkdirect_offer(),
        offer_id=SKYSHIELD_OFFER,
        supplier_token=TERMINALFLEX,
        total_minor=20_000,
        shuttle_minutes=20,
        distance_metres=5000,
    )
    result = rank_offers(
        (parkdirect_offer(), worse),
        _need(),
        evaluated_at=EVALUATED_AT,
        reliability=_reliability(),
    )
    assert result.recommended_offer_id == PARKDIRECT_OFFER
    assert result.downside is None


def test_penalty_items_reconstruct_final_score() -> None:
    result = rank_offers(
        (skyshield_offer(),),
        _need(),
        evaluated_at=EVALUATED_AT,
        reliability=(),
    )
    row = result.ranked[0]
    contributions = sum(item.contribution_micros for item in row.components)
    penalties = sum(item.micros for item in row.penalties)
    assert row.score_micros == contributions - penalties
    assert row.penalty_micros == penalties
