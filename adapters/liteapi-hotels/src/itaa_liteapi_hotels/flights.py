"""LiteAPI/Nuitee sandbox flight search. Separate from stay types and booking."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

import httpx

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
from itaa_liteapi_hotels.adapter import (
    DEFAULT_BASE_URL,
    liteapi_api_key,
    liteapi_timeout_ms,
    provenance_for_key,
    stay_search_mode,
)

RATES_PATH = "/v3.0/flights/rates"
PROVIDER_ID = "liteapi-flights"
MAX_OFFERS = 6
DEFAULT_FLIGHT_TIMEOUT_MS = 30_000


def flight_search_mode(raw: str | None = None) -> str:
    return stay_search_mode(raw)


def flights_request_body(query: FlightSearchQuery) -> dict[str, object]:
    legs: list[dict[str, object]] = [
        {
            "origin": query.origin,
            "destination": query.destination,
            "date": query.date,
            "direction": "OUTBOUND",
        }
    ]
    if query.return_date:
        legs.append(
            {
                "origin": query.destination,
                "destination": query.origin,
                "date": query.return_date,
                "direction": "INBOUND",
            }
        )
    body: dict[str, object] = {
        "legs": legs,
        "adults": max(1, query.adults),
        "currency": query.currency or "GBP",
        "country": query.country or "GB",
    }
    if query.cabin:
        body["cabinClass"] = query.cabin
    return body


class LiteApiFlightSearchAdapter:
    def __init__(
        self,
        api_key: str,
        *,
        timeout_ms: int | None = None,
        base_url: str = DEFAULT_BASE_URL,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._api_key = api_key.strip()
        self._timeout_ms = timeout_ms or max(liteapi_timeout_ms(), DEFAULT_FLIGHT_TIMEOUT_MS)
        self._base_url = base_url
        self._transport = transport
        self.last_request_body: dict[str, object] | None = None

    @classmethod
    def from_env(cls) -> LiteApiFlightSearchAdapter:
        return cls(api_key=liteapi_api_key())

    def search(self, query: FlightSearchQuery) -> FlightSearchResult:
        source = provenance_for_key(self._api_key)
        if not query.origin.strip() or not query.destination.strip() or not query.date:
            return ExternalSearchFailure(
                code=SearchFailureCode.INVALID_QUERY,
                provider_id=PROVIDER_ID,
                source=source,
                buyer_safe_message=failure_message(
                    SearchFailureCode.INVALID_QUERY, domain="flight"
                ),
            )
        if not self._api_key:
            return ExternalSearchFailure(
                code=SearchFailureCode.UNAUTHORIZED,
                provider_id=PROVIDER_ID,
                source=source,
                buyer_safe_message=failure_message(SearchFailureCode.UNAUTHORIZED, domain="flight"),
            )
        body = flights_request_body(query)
        self.last_request_body = dict(body)
        headers = {
            "X-API-Key": self._api_key,
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        try:
            with httpx.Client(
                base_url=self._base_url,
                timeout=self._timeout_ms / 1000.0,
                transport=self._transport,
            ) as client:
                response = client.post(RATES_PATH, json=body, headers=headers)
        except httpx.TimeoutException:
            return ExternalSearchFailure(
                code=SearchFailureCode.TIMEOUT,
                provider_id=PROVIDER_ID,
                source=source,
                buyer_safe_message=failure_message(SearchFailureCode.TIMEOUT, domain="flight"),
            )
        except httpx.HTTPError:
            return ExternalSearchFailure(
                code=SearchFailureCode.UNAVAILABLE,
                provider_id=PROVIDER_ID,
                source=source,
                buyer_safe_message=failure_message(SearchFailureCode.UNAVAILABLE, domain="flight"),
            )
        if response.status_code in {401, 403}:
            return ExternalSearchFailure(
                code=SearchFailureCode.UNAUTHORIZED,
                provider_id=PROVIDER_ID,
                source=source,
                buyer_safe_message=failure_message(SearchFailureCode.UNAUTHORIZED, domain="flight"),
            )
        if response.status_code >= 500:
            return ExternalSearchFailure(
                code=SearchFailureCode.UNAVAILABLE,
                provider_id=PROVIDER_ID,
                source=source,
                buyer_safe_message=failure_message(SearchFailureCode.UNAVAILABLE, domain="flight"),
            )
        try:
            payload = response.json()
        except ValueError:
            return ExternalSearchFailure(
                code=SearchFailureCode.INVALID_RESPONSE,
                provider_id=PROVIDER_ID,
                source=source,
                buyer_safe_message=failure_message(
                    SearchFailureCode.INVALID_RESPONSE, domain="flight"
                ),
            )
        offers = _normalize_offers(payload, source=source)
        if query.max_amount_minor is not None:
            offers = tuple(
                item
                for item in offers
                if item.amount_minor is not None and item.amount_minor <= query.max_amount_minor
            )
        offers = offers[:MAX_OFFERS]
        if not offers:
            return ExternalSearchFailure(
                code=SearchFailureCode.EMPTY,
                provider_id=PROVIDER_ID,
                source=source,
                buyer_safe_message=failure_message(SearchFailureCode.EMPTY, domain="flight"),
            )
        return FlightSearchPage(
            provider_id=PROVIDER_ID,
            source=source,
            fetched_at=datetime.now(tz=UTC).isoformat().replace("+00:00", "Z"),
            query=query,
            offers=offers,
        )


def _normalize_offers(
    payload: Mapping[str, Any],
    *,
    source: SearchProvenance,
) -> tuple[FlightOffer, ...]:
    data = payload.get("data")
    batches = data if isinstance(data, list) else [data] if isinstance(data, dict) else []
    ranked: list[tuple[int, FlightOffer]] = []
    for batch in batches:
        if not isinstance(batch, dict):
            continue
        journeys = batch.get("journeys")
        if not isinstance(journeys, list):
            continue
        for journey in journeys:
            if not isinstance(journey, dict):
                continue
            offer = _from_journey(journey, source=source)
            if offer is None:
                continue
            price = offer.amount_minor if offer.amount_minor is not None else 10**9
            ranked.append((price, offer))
    ranked.sort(key=lambda item: (item[1].stops, item[0]))
    return tuple(item[1] for item in ranked)


def _from_journey(journey: Mapping[str, Any], *, source: SearchProvenance) -> FlightOffer | None:
    segs_raw = journey.get("segments")
    if not isinstance(segs_raw, list) or not segs_raw:
        return None
    segments: list[FlightSegment] = []
    for raw in segs_raw:
        if not isinstance(raw, dict):
            continue
        carrier_raw = raw.get("carrier")
        carrier = carrier_raw if isinstance(carrier_raw, dict) else {}
        flight_raw = raw.get("flight")
        flight = flight_raw if isinstance(flight_raw, dict) else {}
        duration_raw = raw.get("duration")
        duration = duration_raw if isinstance(duration_raw, dict) else {}
        minutes = duration.get("minutes") if isinstance(duration, dict) else None
        segments.append(
            FlightSegment(
                origin=str(raw.get("originCode") or ""),
                destination=str(raw.get("destinationCode") or ""),
                departure=str(raw.get("departureTime") or ""),
                arrival=str(raw.get("arrivalTime") or ""),
                airline_code=str(carrier.get("marketingCode") or ""),
                airline_name=str(carrier.get("marketingName") or ""),
                flight_number=str(flight.get("marketingNumber") or ""),
                duration_minutes=int(minutes) if isinstance(minutes, int) else None,
            )
        )
    if not segments:
        return None
    offers = journey.get("offers")
    first = offers[0] if isinstance(offers, list) and offers and isinstance(offers[0], dict) else {}
    amount, currency = _price(first)
    cabin = first.get("cabin") if isinstance(first, dict) else None
    baggage = _baggage(first)
    total_duration = journey.get("totalDuration")
    minutes = None
    if isinstance(total_duration, dict) and isinstance(total_duration.get("minutes"), int):
        minutes = int(total_duration["minutes"])
    origin = segments[0].origin
    destination = segments[-1].destination
    airline = segments[0].airline_name or segments[0].airline_code
    offer_id = str(first.get("offerId") or journey.get("journeyKey") or "")
    if not offer_id:
        return None
    return FlightOffer(
        provider_id=PROVIDER_ID,
        source=source,
        external_id=offer_id[:180],
        origin=origin,
        destination=destination,
        departure=segments[0].departure,
        arrival=segments[-1].arrival,
        airline=airline,
        segments=tuple(segments),
        stops=max(0, len(segments) - 1),
        duration_minutes=minutes,
        cabin=str(cabin) if cabin else None,
        currency=currency,
        amount_minor=amount,
        baggage=baggage,
    )


def _price(offer: Mapping[str, Any]) -> tuple[int | None, str | None]:
    pricing = offer.get("pricing") if isinstance(offer.get("pricing"), dict) else {}
    display = pricing.get("display") if isinstance(pricing, dict) else {}
    total = None
    currency = None
    if isinstance(display, dict):
        total = display.get("total")
        currency = display.get("currency") or display.get("currencyCode")
    if total is None and isinstance(pricing, dict):
        total = pricing.get("total")
        currency = currency or pricing.get("currency")
    if isinstance(total, bool) or total is None:
        return None, str(currency) if currency else None
    try:
        major = float(total)
    except (TypeError, ValueError):
        return None, str(currency) if currency else None
    return int(round(major * 100)), str(currency) if currency else "GBP"


def _baggage(offer: Mapping[str, Any]) -> str | None:
    baggage = offer.get("baggage")
    if isinstance(baggage, dict):
        included = baggage.get("included")
        if isinstance(included, bool):
            return "included" if included else "not included"
        if included:
            return str(included)
    return None
