"""Attach a WP-04 canonical hash to an immutable ranking decision."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from itaa_domain.value_objects import PayloadHash
from itaa_policy.canonical import SEPARATOR_RANKING_DECISION, hash_canonical
from itaa_ranking.inputs import RankingNeed, RankingOffer, ReliabilityFact
from itaa_ranking.profile import DEFAULT_PROFILE, RankingProfile
from itaa_ranking.rank import RankingResult, rank_offers


@dataclass(frozen=True, slots=True)
class DecisionRecord:
    result: RankingResult
    fingerprint: PayloadHash


def decide(
    offers: tuple[RankingOffer, ...],
    need: RankingNeed,
    *,
    evaluated_at: datetime,
    reliability: tuple[ReliabilityFact, ...],
    profile: RankingProfile = DEFAULT_PROFILE,
) -> DecisionRecord:
    result = rank_offers(
        offers,
        need,
        evaluated_at=evaluated_at,
        reliability=reliability,
        profile=profile,
    )
    digest = hash_canonical(SEPARATOR_RANKING_DECISION, result.fingerprint_material())
    return DecisionRecord(result=result, fingerprint=digest)
