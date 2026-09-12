"""Deterministic labelled fake flight search. Never stay or parking fixtures."""

from __future__ import annotations

from datetime import UTC, datetime

from itaa_application.external_search_port import (
    ExternalSearchFailure,
    FlightOffer,
    FlightSearchPage,
    FlightSearchQuery,
    FlightSearchResult,
    FlightSegment,
    SearchFailureCode,
    SearchProvenance,
    failure_message,
)

PROVIDER_ID = "liteapi-flights"


class FakeFlightSearchAdapter:
    def search(self, query: FlightSearchQuery) -> FlightSearchResult:
        origin = query.origin.strip().upper()
        destination = query.destination.strip().upper()
        if not origin or not destination or not query.date:
            return ExternalSearchFailure(
                code=SearchFailureCode.INVALID_QUERY,
                provider_id=PROVIDER_ID,
                source=SearchProvenance.FAKE,
                buyer_safe_message=failure_message(
                    SearchFailureCode.INVALID_QUERY, domain="flight"
                ),
            )
        dep = f"{query.date}T09:15:00"
        arr = f"{query.date}T10:25:00"
        offers = (
            FlightOffer(
                provider_id=PROVIDER_ID,
                source=SearchProvenance.FAKE,
                external_id=f"fake-{origin}-{destination}-1",
                origin=origin,
                destination=destination,
                departure=dep,
                arrival=arr,
                airline="Nuitee Air",
                segments=(
                    FlightSegment(
                        origin=origin,
                        destination=destination,
                        departure=dep,
                        arrival=arr,
                        airline_code="ND",
                        airline_name="Nuitee Air",
                        flight_number="101",
                        duration_minutes=70,
                    ),
                ),
                stops=0,
                duration_minutes=70,
                cabin="economy",
                currency=query.currency or "GBP",
                amount_minor=4_850,
                baggage="included",
            ),
            FlightOffer(
                provider_id=PROVIDER_ID,
                source=SearchProvenance.FAKE,
                external_id=f"fake-{origin}-{destination}-2",
                origin=origin,
                destination=destination,
                departure=f"{query.date}T18:40:00",
                arrival=f"{query.date}T19:55:00",
                airline="Nuitee Air",
                segments=(
                    FlightSegment(
                        origin=origin,
                        destination=destination,
                        departure=f"{query.date}T18:40:00",
                        arrival=f"{query.date}T19:55:00",
                        airline_code="ND",
                        airline_name="Nuitee Air",
                        flight_number="202",
                        duration_minutes=75,
                    ),
                ),
                stops=0,
                duration_minutes=75,
                cabin="economy",
                currency=query.currency or "GBP",
                amount_minor=6_200,
                baggage="not included",
            ),
        )
        held: tuple[FlightOffer, ...] = offers
        if query.max_amount_minor is not None:
            held = tuple(
                item
                for item in offers
                if item.amount_minor and item.amount_minor <= query.max_amount_minor
            )
        if not held:
            return ExternalSearchFailure(
                code=SearchFailureCode.EMPTY,
                provider_id=PROVIDER_ID,
                source=SearchProvenance.FAKE,
                buyer_safe_message=failure_message(SearchFailureCode.EMPTY, domain="flight"),
            )
        return FlightSearchPage(
            provider_id=PROVIDER_ID,
            source=SearchProvenance.FAKE,
            fetched_at=datetime.now(tz=UTC).isoformat().replace("+00:00", "Z"),
            query=query,
            offers=held,
        )
