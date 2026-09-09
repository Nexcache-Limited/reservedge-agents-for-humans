"""Synthetic buyer-side local market evidence. No network or provider SDK."""

from __future__ import annotations

from itaa_application.session_models import (
    GoldenPathSession,
    MarketEvidenceItem,
    MarketLabel,
    MarketSourceType,
)
from itaa_application.supplier_port import Clock


class SyntheticMarketEvidence:
    """Deterministic checked-in local evidence. Never fetched."""

    def collect(self, session: GoldenPathSession, clock: Clock) -> tuple[MarketEvidenceItem, ...]:
        observed = clock.now()
        airport = session.requirement.airport.to_primitive().lower()
        return (
            MarketEvidenceItem(
                source_type=MarketSourceType.SYNTHETIC_LOCAL_FIXTURE,
                source_ref=f"market.{airport}.normal_options.v1",
                observed_at=observed,
                label=MarketLabel.LOCAL_FIXTURE,
            ),
            MarketEvidenceItem(
                source_type=MarketSourceType.SYNTHETIC_LOCAL_FIXTURE,
                source_ref=f"market.{airport}.covered_band.v1",
                observed_at=observed,
                label=MarketLabel.SIMULATION,
            ),
            MarketEvidenceItem(
                source_type=MarketSourceType.SYNTHETIC_LOCAL_FIXTURE,
                source_ref=f"market.{airport}.uncovered_band.v1",
                observed_at=observed,
                label=MarketLabel.SIMULATION,
            ),
        )
