"""Cloud-neutral deterministic ranking package. Domain types only."""

from __future__ import annotations

from itaa_domain import PACKAGE_NAME as DOMAIN_PACKAGE_NAME
from itaa_ranking.profile import DEFAULT_PROFILE, PROFILE_ID, SCORE_SCALE
from itaa_ranking.rank import rank_offers

PACKAGE_NAME = "itaa-ranking"
PACKAGE_ROLE = "cloud-neutral-ranking"
DOMAIN_DEPENDENCY = DOMAIN_PACKAGE_NAME

__all__ = [
    "DEFAULT_PROFILE",
    "DOMAIN_DEPENDENCY",
    "PACKAGE_NAME",
    "PACKAGE_ROLE",
    "PROFILE_ID",
    "SCORE_SCALE",
    "rank_offers",
]
