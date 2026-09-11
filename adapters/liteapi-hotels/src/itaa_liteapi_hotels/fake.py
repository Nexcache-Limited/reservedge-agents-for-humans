"""Deterministic labelled fake stay search. Never ParkDirect/SkyShield/JFK parking."""

from __future__ import annotations

from datetime import UTC, datetime

from itaa_application.external_search_port import (
    ExternalSearchFailure,
    ExternalSearchPage,
    ExternalSearchQuery,
    ExternalSearchResult,
    SearchFailureCode,
    SearchProvenance,
    StayOffer,
    failure_message,
)
from itaa_liteapi_hotels.normalize import PROVIDER_ID

_CITY_OFFERS: dict[str, tuple[tuple[str, str, str, int], ...]] = {
    "milan": (
        ("fake-milan-spadari", "Hotel Spadari al Duomo", "Milan, Italy", 24_000),
        ("fake-milan-viu", "Hotel Viu Milan", "Milan, Italy", 31_500),
        ("fake-milan-nh", "NH Collection Milano Porta Nuova", "Milan, Italy", 19_800),
    ),
    "london": (
        ("fake-london-savoy", "The Savoy", "London, United Kingdom", 42_000),
        ("fake-london-premier", "Premier Inn London City", "London, United Kingdom", 14_400),
        ("fake-london-citizenm", "citizenM London Bankside", "London, United Kingdom", 18_200),
    ),
    "new york": (
        ("fake-nyc-pod39", "Pod 39", "New York, United States", 22_000),
        ("fake-nyc-ace", "Ace Hotel New York", "New York, United States", 28_400),
    ),
    "edinburgh": (
        ("fake-edi-balmoral", "The Balmoral", "Edinburgh, United Kingdom", 33_000),
        ("fake-edi-motelone", "Motel One Edinburgh-Royal", "Edinburgh, United Kingdom", 12_600),
    ),
}


def _slug(value: str) -> str:
    return " ".join(value.strip().lower().split())


def _currency_for(slug: str) -> str:
    if slug in {"milan", "rome", "paris", "amsterdam", "dublin"}:
        return "EUR"
    if slug in {"london", "edinburgh", "manchester"}:
        return "GBP"
    return "USD"


class FakeStaySearchAdapter:
    """CI/default stay search. Provenance is always fake."""

    def search(self, query: ExternalSearchQuery) -> ExternalSearchResult:
        if query.domain != "stay":
            return ExternalSearchFailure(
                code=SearchFailureCode.INVALID_QUERY,
                provider_id=PROVIDER_ID,
                source=SearchProvenance.FAKE,
                query=query,
                buyer_safe_message=failure_message(SearchFailureCode.INVALID_QUERY),
            )
        destination = query.destination.value.strip()
        if not destination or not query.start or not query.end or query.start > query.end:
            return ExternalSearchFailure(
                code=SearchFailureCode.INVALID_QUERY,
                provider_id=PROVIDER_ID,
                source=SearchProvenance.FAKE,
                query=query,
                buyer_safe_message=failure_message(SearchFailureCode.INVALID_QUERY),
            )
        slug = _slug(destination)
        rows = _CITY_OFFERS.get(slug)
        if rows is None:
            rows = (
                (
                    f"fake-{slug.replace(' ', '-')}-centre",
                    f"City stay in {destination}",
                    destination,
                    15_000,
                ),
            )
        offers = tuple(
            StayOffer(
                provider_id=PROVIDER_ID,
                source=SearchProvenance.FAKE,
                external_id=item[0],
                name=item[1],
                locality=item[2],
                check_in=query.start,
                check_out=query.end,
                currency=_currency_for(slug),
                amount_minor=item[3],
                cancellation="Free cancellation until 24 hours before check-in",
                availability="available",
                rate_ref=f"fake-rate-{item[0]}",
            )
            for item in rows
        )
        return ExternalSearchPage(
            provider_id=PROVIDER_ID,
            source=SearchProvenance.FAKE,
            fetched_at=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            query=query,
            offers=offers,
        )

    def book_sandbox(self, rate_ref: str) -> dict[str, object]:
        token = rate_ref.strip()
        if not token.startswith("fake-rate-"):
            return {
                "status": "invalid_query",
                "phase": "stopped",
                "source": "fake",
                "simulatedPayment": True,
                "bookingId": "",
                "buyerSafeMessage": "That stay rate is no longer available for a sandbox hold.",
            }
        return {
            "status": "ok",
            "phase": "sandbox_booked",
            "source": "fake",
            "simulatedPayment": True,
            "bookingId": f"fake-bk-{token[-12:]}",
            "buyerSafeMessage": (
                "Labelled fake sandbox booking. Simulated payment. No charge. Stopped after book."
            ),
        }
