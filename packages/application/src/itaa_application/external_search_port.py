"""Provider-neutral external research search port.

Capability routing decides *whether* to search. This port is how a configured
adapter fulfils one search. StayOffer and ExperienceOffer are domain-native
pages; do not reuse StayOffer for experiences. Adapters must not leak provider
JSON types into application or domain code. Failures stay typed; callers must
not substitute inventory from another domain.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal, Protocol

SearchDomain = Literal["stay", "experience", "flight"]
PlaceKind = Literal["city", "iata", "text"]
BookingAuthority = Literal["none"]


class SearchProvenance(StrEnum):
    FAKE = "fake"
    SANDBOX = "sandbox"
    LIVE = "live"


class SearchFailureCode(StrEnum):
    EMPTY = "empty"
    UNAVAILABLE = "unavailable"
    TIMEOUT = "timeout"
    INVALID_QUERY = "invalid_query"
    INVALID_RESPONSE = "invalid_response"
    UNAUTHORIZED = "unauthorized"


BUYER_LABELS: Mapping[SearchProvenance, str] = {
    SearchProvenance.FAKE: "Labelled fake hotel search",
    SearchProvenance.SANDBOX: "Sandbox hotel search",
    SearchProvenance.LIVE: "Live hotel search",
}

EXPERIENCE_BUYER_LABELS: Mapping[SearchProvenance, str] = {
    SearchProvenance.FAKE: "Labelled fake experience search",
    SearchProvenance.SANDBOX: "Sandbox experience search",
    SearchProvenance.LIVE: "Live experience search",
}

FAILURE_COPY: Mapping[SearchFailureCode, str] = {
    SearchFailureCode.EMPTY: "No hotel matches for those dates and destination.",
    SearchFailureCode.UNAVAILABLE: "Hotel search is unavailable right now.",
    SearchFailureCode.TIMEOUT: "Hotel search timed out. No simulated parking was substituted.",
    SearchFailureCode.INVALID_QUERY: "Hotel search needs a destination and stay dates.",
    SearchFailureCode.INVALID_RESPONSE: "Hotel search returned an unreadable result.",
    SearchFailureCode.UNAUTHORIZED: "Hotel search is not configured on the server.",
}

FLIGHT_BUYER_LABELS: Mapping[SearchProvenance, str] = {
    SearchProvenance.FAKE: "Labelled fake flight search",
    SearchProvenance.SANDBOX: "Sandbox flight search",
    SearchProvenance.LIVE: "Live flight search",
}

FLIGHT_FAILURE_COPY: Mapping[SearchFailureCode, str] = {
    SearchFailureCode.EMPTY: "No flight matches for that route and date.",
    SearchFailureCode.UNAVAILABLE: "Flight search is unavailable right now.",
    SearchFailureCode.TIMEOUT: (
        "Flight search timed out. No hotel or parking inventory was substituted."
    ),
    SearchFailureCode.INVALID_QUERY: "Flight search needs origin, destination, and a date.",
    SearchFailureCode.INVALID_RESPONSE: "Flight search returned an unreadable result.",
    SearchFailureCode.UNAUTHORIZED: "Flight search is not configured on the server.",
}

EXPERIENCE_FAILURE_COPY: Mapping[SearchFailureCode, str] = {
    SearchFailureCode.EMPTY: "No experience matches for that destination.",
    SearchFailureCode.UNAVAILABLE: "Experience search is unavailable right now.",
    SearchFailureCode.TIMEOUT: (
        "Experience search timed out. No hotel or parking inventory was substituted."
    ),
    SearchFailureCode.INVALID_QUERY: "Experience search needs a destination.",
    SearchFailureCode.INVALID_RESPONSE: "Experience search returned an unreadable result.",
    SearchFailureCode.UNAUTHORIZED: "Experience search is not configured on the server.",
}


@dataclass(frozen=True, slots=True)
class PlaceRef:
    kind: PlaceKind
    value: str


@dataclass(frozen=True, slots=True)
class ExternalSearchQuery:
    domain: SearchDomain
    destination: PlaceRef
    start: str
    end: str
    origin: PlaceRef | None = None
    guests: int | None = None
    rooms: int | None = None
    preferences: tuple[str, ...] = ()
    correlation_id: str = ""


@dataclass(frozen=True, slots=True)
class ExperienceOffer:
    provider_id: str
    source: SearchProvenance
    external_id: str
    title: str
    category: str
    location: str
    availability: str
    currency: str | None
    amount_minor: int | None
    duration_minutes: int | None
    cancellation: str | None
    booking_authority: BookingAuthority = "none"
    photo_url: str | None = None


@dataclass(frozen=True, slots=True)
class StayOffer:
    provider_id: str
    source: SearchProvenance
    external_id: str
    name: str
    locality: str
    check_in: str
    check_out: str
    currency: str | None
    amount_minor: int | None
    cancellation: str | None
    availability: str
    booking_authority: BookingAuthority = "none"
    photo_url: str | None = None
    rate_ref: str | None = None


@dataclass(frozen=True, slots=True)
class ExternalSearchPage:
    provider_id: str
    source: SearchProvenance
    fetched_at: str
    query: ExternalSearchQuery
    offers: tuple[StayOffer, ...]
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ExperienceSearchPage:
    provider_id: str
    source: SearchProvenance
    fetched_at: str
    query: ExternalSearchQuery
    offers: tuple[ExperienceOffer, ...]
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class FlightSearchQuery:
    origin: str
    destination: str
    date: str
    return_date: str | None = None
    adults: int = 1
    currency: str = "GBP"
    country: str = "GB"
    cabin: str | None = None
    max_amount_minor: int | None = None
    correlation_id: str = ""


@dataclass(frozen=True, slots=True)
class FlightSegment:
    origin: str
    destination: str
    departure: str
    arrival: str
    airline_code: str
    airline_name: str
    flight_number: str
    duration_minutes: int | None = None


@dataclass(frozen=True, slots=True)
class FlightOffer:
    provider_id: str
    source: SearchProvenance
    external_id: str
    origin: str
    destination: str
    departure: str
    arrival: str
    airline: str
    segments: tuple[FlightSegment, ...]
    stops: int
    duration_minutes: int | None
    cabin: str | None
    currency: str | None
    amount_minor: int | None
    baggage: str | None
    booking_authority: BookingAuthority = "none"


@dataclass(frozen=True, slots=True)
class FlightSearchPage:
    provider_id: str
    source: SearchProvenance
    fetched_at: str
    query: FlightSearchQuery
    offers: tuple[FlightOffer, ...]
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ExternalSearchFailure:
    code: SearchFailureCode
    provider_id: str
    source: SearchProvenance
    query: ExternalSearchQuery | None = None
    buyer_safe_message: str = ""


ExternalSearchResult = ExternalSearchPage | ExternalSearchFailure
ExperienceSearchResult = ExperienceSearchPage | ExternalSearchFailure
FlightSearchResult = FlightSearchPage | ExternalSearchFailure
SearchResult = ExternalSearchPage | ExperienceSearchPage | FlightSearchPage | ExternalSearchFailure


class ExternalSearchPort(Protocol):
    def search(self, query: ExternalSearchQuery) -> ExternalSearchResult:
        """Return a buyer-safe page or a typed failure. Never parking fixtures."""


class ExperienceSearchPort(Protocol):
    def search(self, query: ExternalSearchQuery) -> ExperienceSearchResult:
        """Return a buyer-safe experience page or a typed failure. Never stay fixtures."""


class FlightSearchPort(Protocol):
    def search(self, query: FlightSearchQuery) -> FlightSearchResult:
        """Return a buyer-safe flight page or a typed failure. Never stay fixtures."""


def buyer_label(source: SearchProvenance, domain: SearchDomain = "stay") -> str:
    if domain == "experience":
        return EXPERIENCE_BUYER_LABELS[source]
    if domain == "flight":
        return FLIGHT_BUYER_LABELS[source]
    return BUYER_LABELS[source]


def failure_message(
    code: SearchFailureCode,
    explicit: str = "",
    domain: SearchDomain = "stay",
) -> str:
    if explicit.strip():
        return explicit.strip()
    if domain == "experience":
        return EXPERIENCE_FAILURE_COPY[code]
    if domain == "flight":
        return FLIGHT_FAILURE_COPY[code]
    return FAILURE_COPY[code]


def public_query(query: ExternalSearchQuery | None) -> dict[str, object] | None:
    if query is None:
        return None
    payload: dict[str, object] = {
        "domain": query.domain,
        "destination": {"kind": query.destination.kind, "value": query.destination.value},
        "checkIn": query.start,
        "checkOut": query.end,
    }
    if query.origin is not None:
        payload["origin"] = {"kind": query.origin.kind, "value": query.origin.value}
    if query.guests is not None:
        payload["guests"] = query.guests
    if query.rooms is not None:
        payload["rooms"] = query.rooms
    if query.preferences:
        payload["preferences"] = list(query.preferences)
    return payload


def public_offer(offer: StayOffer) -> dict[str, object]:
    price: dict[str, object] = {}
    if offer.currency:
        price["currency"] = offer.currency
    if offer.amount_minor is not None:
        price["amountMinor"] = offer.amount_minor
    payload: dict[str, object] = {
        "id": offer.external_id,
        "name": offer.name,
        "locality": offer.locality,
        "checkIn": offer.check_in,
        "checkOut": offer.check_out,
        "price": price,
        "cancellation": offer.cancellation,
        "availability": offer.availability,
        "bookingAuthority": offer.booking_authority,
    }
    if offer.photo_url:
        payload["photoUrl"] = offer.photo_url
    if offer.rate_ref:
        payload["rateRef"] = offer.rate_ref
    return payload


def public_search_result(result: ExternalSearchResult) -> dict[str, object]:
    """Buyer-visible stay payload. No provider JSON, credentials, or parking fixtures."""

    domain: SearchDomain = "stay"
    if result.query is not None:
        domain = result.query.domain
    if isinstance(result, ExternalSearchFailure):
        return {
            "status": result.code.value,
            "label": buyer_label(result.source, domain),
            "providerId": result.provider_id,
            "source": result.source.value,
            "query": public_query(result.query),
            "offers": [],
            "buyerSafeMessage": failure_message(result.code, result.buyer_safe_message, domain),
            "bookingAuthority": "none",
        }
    offers: Sequence[StayOffer] = result.offers
    return {
        "status": "ok",
        "label": buyer_label(result.source, domain),
        "providerId": result.provider_id,
        "source": result.source.value,
        "fetchedAt": result.fetched_at,
        "query": public_query(result.query),
        "offers": [public_offer(item) for item in offers],
        "warnings": list(result.warnings),
        "buyerSafeMessage": (
            f"{buyer_label(result.source, domain)}: {len(offers)} "
            f"{'property' if len(offers) == 1 else 'properties'}. Not a booking."
        ),
        "bookingAuthority": "none",
    }


def public_experience_offer(offer: ExperienceOffer) -> dict[str, object]:
    price: dict[str, object] = {}
    if offer.currency:
        price["currency"] = offer.currency
    if offer.amount_minor is not None:
        price["amountMinor"] = offer.amount_minor
    payload: dict[str, object] = {
        "id": offer.external_id,
        "title": offer.title,
        "category": offer.category,
        "location": offer.location,
        "availability": offer.availability,
        "price": price,
        "durationMinutes": offer.duration_minutes,
        "cancellation": offer.cancellation,
        "bookingAuthority": offer.booking_authority,
    }
    if offer.photo_url:
        payload["photoUrl"] = offer.photo_url
    return payload


def public_experience_search_result(result: ExperienceSearchResult) -> dict[str, object]:
    """Buyer-visible experience payload. No provider JSON or stay/parking fixtures."""

    domain: SearchDomain = "experience"
    if isinstance(result, ExternalSearchFailure):
        return {
            "status": result.code.value,
            "label": buyer_label(result.source, domain),
            "providerId": result.provider_id,
            "source": result.source.value,
            "query": public_query(result.query),
            "offers": [],
            "buyerSafeMessage": failure_message(result.code, result.buyer_safe_message, domain),
            "bookingAuthority": "none",
        }
    offers: Sequence[ExperienceOffer] = result.offers
    return {
        "status": "ok",
        "label": buyer_label(result.source, domain),
        "providerId": result.provider_id,
        "source": result.source.value,
        "fetchedAt": result.fetched_at,
        "query": public_query(result.query),
        "offers": [public_experience_offer(item) for item in offers],
        "warnings": list(result.warnings),
        "buyerSafeMessage": (
            f"{buyer_label(result.source, domain)}: {len(offers)} "
            f"{'experience' if len(offers) == 1 else 'experiences'}. Not a booking."
        ),
        "bookingAuthority": "none",
    }


def public_flight_query(query: FlightSearchQuery | None) -> dict[str, object] | None:
    if query is None:
        return None
    payload: dict[str, object] = {
        "domain": "flight",
        "origin": query.origin,
        "destination": query.destination,
        "date": query.date,
        "adults": query.adults,
        "currency": query.currency,
    }
    if query.return_date:
        payload["returnDate"] = query.return_date
    if query.cabin:
        payload["cabin"] = query.cabin
    return payload


def public_flight_offer(offer: FlightOffer) -> dict[str, object]:
    price: dict[str, object] = {}
    if offer.currency:
        price["currency"] = offer.currency
    if offer.amount_minor is not None:
        price["amountMinor"] = offer.amount_minor
    return {
        "id": offer.external_id,
        "origin": offer.origin,
        "destination": offer.destination,
        "departure": offer.departure,
        "arrival": offer.arrival,
        "airline": offer.airline,
        "stops": offer.stops,
        "durationMinutes": offer.duration_minutes,
        "cabin": offer.cabin,
        "baggage": offer.baggage,
        "price": price,
        "segments": [
            {
                "origin": item.origin,
                "destination": item.destination,
                "departure": item.departure,
                "arrival": item.arrival,
                "airlineCode": item.airline_code,
                "airlineName": item.airline_name,
                "flightNumber": item.flight_number,
                "durationMinutes": item.duration_minutes,
            }
            for item in offer.segments
        ],
        "bookingAuthority": offer.booking_authority,
    }


def public_flight_search_result(result: FlightSearchResult) -> dict[str, object]:
    """Buyer-visible flight payload. No provider JSON, stay fixtures, or payment claims."""

    domain: SearchDomain = "flight"
    if isinstance(result, ExternalSearchFailure):
        return {
            "status": result.code.value,
            "label": buyer_label(result.source, domain),
            "providerId": result.provider_id,
            "source": result.source.value,
            "query": None,
            "offers": [],
            "buyerSafeMessage": failure_message(result.code, result.buyer_safe_message, domain),
            "bookingAuthority": "none",
        }
    return {
        "status": "ok",
        "label": buyer_label(result.source, domain),
        "providerId": result.provider_id,
        "source": result.source.value,
        "fetchedAt": result.fetched_at,
        "query": public_flight_query(result.query),
        "offers": [public_flight_offer(item) for item in result.offers],
        "warnings": list(result.warnings),
        "buyerSafeMessage": (
            f"{len(result.offers)} sandbox flight "
            f"{'option' if len(result.offers) == 1 else 'options'}. Not a ticket."
        ),
        "bookingAuthority": "none",
    }
