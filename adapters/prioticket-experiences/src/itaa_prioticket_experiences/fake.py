"""Deterministic labelled fake experience search. Never hotel or JFK parking fixtures."""

from __future__ import annotations

from datetime import UTC, datetime

from itaa_application.external_search_port import (
    ExperienceOffer,
    ExperienceSearchPage,
    ExperienceSearchResult,
    ExternalSearchFailure,
    ExternalSearchQuery,
    SearchFailureCode,
    SearchProvenance,
    failure_message,
)
from itaa_prioticket_experiences.normalize import PROVIDER_ID

# title, category, location, minutes, amount_minor, currency
_CITY_OFFERS: dict[str, tuple[tuple[str, str, str, int, int, str], ...]] = {
    "milan": (
        (
            "Duomo rooftop and museum entry",
            "Museum",
            "Milan, Italy",
            120,
            4_500,
            "EUR",
        ),
        (
            "Navigli evening walking tour",
            "Tour",
            "Milan, Italy",
            90,
            3_200,
            "EUR",
        ),
        (
            "Family-friendly Leonardo science visit",
            "Attraction",
            "Milan, Italy",
            150,
            2_800,
            "EUR",
        ),
    ),
    "london": (
        (
            "Tower of London timed entry",
            "Attraction",
            "London, United Kingdom",
            180,
            6_400,
            "GBP",
        ),
        (
            "West End evening theatre",
            "Event",
            "London, United Kingdom",
            150,
            8_900,
            "GBP",
        ),
        (
            "Thames sightseeing cruise",
            "Cruise",
            "London, United Kingdom",
            60,
            2_400,
            "GBP",
        ),
    ),
    "new york": (
        (
            "Metropolitan Museum timed ticket",
            "Museum",
            "New York, United States",
            180,
            3_000,
            "USD",
        ),
        (
            "Evening Statue of Liberty cruise",
            "Cruise",
            "New York, United States",
            90,
            4_800,
            "USD",
        ),
    ),
    "edinburgh": (
        (
            "Edinburgh Castle timed entry",
            "Attraction",
            "Edinburgh, United Kingdom",
            120,
            3_600,
            "GBP",
        ),
        (
            "Old Town evening ghost tour",
            "Tour",
            "Edinburgh, United Kingdom",
            75,
            2_200,
            "GBP",
        ),
    ),
}


def _slug(value: str) -> str:
    return " ".join(value.strip().lower().split())


def _matches_prefs(title: str, category: str, prefs: tuple[str, ...]) -> bool:
    if not prefs:
        return True
    blob = f"{title} {category}".lower()
    for pref in prefs:
        token = pref.strip().lower()
        if token == "evening" and "evening" in blob:
            return True
        if token == "museum" and "museum" in blob:
            return True
        if token == "tour" and "tour" in blob:
            return True
        if token == "family-friendly" and "family" in blob:
            return True
        if token == "city-centre" and ("centre" in blob or "center" in blob or "city" in blob):
            return True
    return any(token.strip().lower() in blob for token in prefs)


class FakeExperienceSearchAdapter:
    """CI/default experience search. Provenance is always fake."""

    def search(self, query: ExternalSearchQuery) -> ExperienceSearchResult:
        if query.domain != "experience":
            return ExternalSearchFailure(
                code=SearchFailureCode.INVALID_QUERY,
                provider_id=PROVIDER_ID,
                source=SearchProvenance.FAKE,
                query=query,
                buyer_safe_message=failure_message(
                    SearchFailureCode.INVALID_QUERY, domain="experience"
                ),
            )
        destination = query.destination.value.strip()
        if not destination:
            return ExternalSearchFailure(
                code=SearchFailureCode.INVALID_QUERY,
                provider_id=PROVIDER_ID,
                source=SearchProvenance.FAKE,
                query=query,
                buyer_safe_message=failure_message(
                    SearchFailureCode.INVALID_QUERY, domain="experience"
                ),
            )
        slug = _slug(destination)
        rows = _CITY_OFFERS.get(slug)
        if rows is None:
            rows = (
                (
                    f"City walking tour in {destination}",
                    "Tour",
                    destination,
                    90,
                    2_500,
                    "USD",
                ),
            )
        filtered = [item for item in rows if _matches_prefs(item[0], item[1], query.preferences)]
        if query.preferences and not filtered:
            filtered = list(rows)
        offers = tuple(
            ExperienceOffer(
                provider_id=PROVIDER_ID,
                source=SearchProvenance.FAKE,
                external_id=f"fake-{slug.replace(' ', '-')}-{index}",
                title=item[0],
                category=item[1],
                location=item[2],
                availability=(
                    f"available; {', '.join(query.preferences)}"
                    if query.preferences
                    else "available"
                ),
                currency=item[5],
                amount_minor=item[4],
                duration_minutes=item[3],
                cancellation="Cancellation allowed",
            )
            for index, item in enumerate(filtered, start=1)
        )
        return ExperienceSearchPage(
            provider_id=PROVIDER_ID,
            source=SearchProvenance.FAKE,
            fetched_at=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            query=query,
            offers=offers,
        )
