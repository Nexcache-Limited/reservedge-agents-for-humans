from __future__ import annotations

from itaa_google_adapter.ports import RankingFacts, SafeOfferSummary

JFK_TEXT = (
    "Synthetic airport-parking request for JFK. "
    "Service window starts 2026-09-03T13:00:00Z and ends 2026-09-08T22:00:00Z. "
    "Vehicle class standard. Covered parking preferred. "
    "Shuttle maximum 20 minutes. Accessibility includes ev_charging. Currency USD."
)
CORRELATION = "cr_01k2m3n4p5q6r7s8t9v0w1x2k2"
SKYSHIELD = "sp_01k2m3n4p5q6r7s8t9v0w1x2b2"
PARKDIRECT = "sp_01k2m3n4p5q6r7s8t9v0w1x2b1"
TERMINALFLEX = "sp_01k2m3n4p5q6r7s8t9v0w1x2b3"
SKYSHIELD_OFFER = "of_01k2m3n4p5q6r7s8t9v0w1x2a2"
PARKDIRECT_OFFER = "of_01k2m3n4p5q6r7s8t9v0w1x2a1"
TERMINALFLEX_OFFER = "of_01k2m3n4p5q6r7s8t9v0w1x2a3"


def locked_ranking_facts() -> RankingFacts:
    return RankingFacts(
        winner_id=SKYSHIELD_OFFER,
        winner_display_name="SkyShield",
        offers=(
            SafeOfferSummary(
                SKYSHIELD,
                "SkyShield",
                SKYSHIELD_OFFER,
                1,
                671_000,
                14_800,
                "USD",
                True,
            ),
            SafeOfferSummary(
                PARKDIRECT,
                "ParkDirect",
                PARKDIRECT_OFFER,
                2,
                660_000,
                11_900,
                "USD",
                False,
            ),
            SafeOfferSummary(
                TERMINALFLEX,
                "TerminalFlex",
                TERMINALFLEX_OFFER,
                3,
                535_000,
                16_900,
                "USD",
                False,
            ),
        ),
        downside_delta=2_900,
        downside_dimension="total_minor",
        correlation_id=CORRELATION,
    )
