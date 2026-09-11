"""LiteAPI/Nuitee sandbox stay search. Failures stay visible; no parking fallback."""

from __future__ import annotations

import os
from collections.abc import Mapping
from datetime import UTC, datetime

import httpx

from itaa_application.external_search_port import (
    ExternalSearchFailure,
    ExternalSearchPage,
    ExternalSearchQuery,
    ExternalSearchResult,
    SearchFailureCode,
    SearchProvenance,
    failure_message,
)
from itaa_liteapi_hotels.gazetteer import guest_nationality, lookup_city
from itaa_liteapi_hotels.normalize import PROVIDER_ID, normalize_offers

RATES_PATH = "/v3.0/hotels/rates"
PREBOOK_PATH = "/v3.0/rates/prebook"
BOOK_PATH = "/v3.0/rates/book"
DEFAULT_BASE_URL = "https://api.liteapi.travel"
DEFAULT_BOOK_BASE_URL = "https://book.liteapi.travel"
DEFAULT_TIMEOUT_MS = 18_000
MAX_TIMEOUT_MS = 20_000
MIN_TIMEOUT_MS = 3_000
SANDBOX_HOLDER = {
    "firstName": "Reservedge",
    "lastName": "Sandbox",
    "email": "sandbox.guest@example.invalid",
}


def stay_search_mode(raw: str | None = None) -> str:
    text = os.environ.get("ITAA_STAY_SEARCH_MODE", "fake") if raw is None else raw
    mode = text.strip().lower()
    return mode if mode in {"fake", "sandbox"} else "fake"


def liteapi_timeout_ms(raw: str | None = None) -> int:
    text = os.environ.get("ITAA_LITEAPI_TIMEOUT_MS", "") if raw is None else raw
    if text is None or not str(text).strip():
        return DEFAULT_TIMEOUT_MS
    try:
        value = int(str(text).strip())
    except ValueError:
        return DEFAULT_TIMEOUT_MS
    return max(MIN_TIMEOUT_MS, min(value, MAX_TIMEOUT_MS))


def liteapi_api_key(raw: str | None = None) -> str:
    text = os.environ.get("ITAA_LITEAPI_API_KEY", "") if raw is None else raw
    return "" if text is None else str(text).strip()


def provenance_for_key(api_key: str) -> SearchProvenance:
    if api_key.startswith("live_"):
        return SearchProvenance.LIVE
    return SearchProvenance.SANDBOX


def rates_request_body(query: ExternalSearchQuery) -> dict[str, object]:
    city, country, currency = lookup_city(query.destination.value)
    origin = query.origin.value if query.origin is not None else ""
    occupancy: dict[str, object] = {
        "adults": query.guests if query.guests and query.guests > 0 else 2
    }
    body: dict[str, object] = {
        "checkin": query.start,
        "checkout": query.end,
        "currency": currency,
        "guestNationality": guest_nationality(origin, country),
        "occupancies": [occupancy],
        "limit": 6,
        "timeout": max(4, min(liteapi_timeout_ms() // 1000, 16)),
        "includeHotelData": True,
        "maxRatesPerHotel": 1,
    }
    if country:
        body["countryCode"] = country
        body["cityName"] = city
    else:
        body["aiSearch"] = f"hotels in {query.destination.value}"
    if query.rooms and query.rooms > 1:
        occupancy["rooms"] = query.rooms
    return body


class LiteApiStaySearchAdapter:
    def __init__(
        self,
        *,
        api_key: str,
        timeout_ms: int | None = None,
        transport: httpx.BaseTransport | None = None,
        base_url: str = DEFAULT_BASE_URL,
        book_base_url: str = DEFAULT_BOOK_BASE_URL,
    ) -> None:
        self._api_key = api_key.strip()
        self._timeout_ms = liteapi_timeout_ms(None if timeout_ms is None else str(timeout_ms))
        self._transport = transport
        self._base_url = base_url.rstrip("/")
        self._book_base_url = book_base_url.rstrip("/")
        self.last_request_body: dict[str, object] | None = None
        self.last_prebook_body: dict[str, object] | None = None
        self.last_book_body: dict[str, object] | None = None

    @classmethod
    def from_env(cls) -> LiteApiStaySearchAdapter:
        return cls(api_key=liteapi_api_key(), timeout_ms=liteapi_timeout_ms())

    def search(self, query: ExternalSearchQuery) -> ExternalSearchResult:
        source = provenance_for_key(self._api_key)
        if (
            query.domain != "stay"
            or not query.destination.value.strip()
            or not query.start
            or not query.end
            or query.start > query.end
        ):
            return ExternalSearchFailure(
                code=SearchFailureCode.INVALID_QUERY,
                provider_id=PROVIDER_ID,
                source=source,
                query=query,
                buyer_safe_message=failure_message(SearchFailureCode.INVALID_QUERY),
            )
        if not self._api_key:
            return ExternalSearchFailure(
                code=SearchFailureCode.UNAUTHORIZED,
                provider_id=PROVIDER_ID,
                source=source,
                query=query,
                buyer_safe_message=failure_message(SearchFailureCode.UNAUTHORIZED),
            )
        body = rates_request_body(query)
        self.last_request_body = dict(body)
        timeout_s = self._timeout_ms / 1000.0
        headers = {
            "X-API-Key": self._api_key,
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        try:
            with httpx.Client(
                base_url=self._base_url,
                timeout=timeout_s,
                transport=self._transport,
            ) as client:
                response = client.post(RATES_PATH, json=body, headers=headers)
        except httpx.TimeoutException:
            return ExternalSearchFailure(
                code=SearchFailureCode.TIMEOUT,
                provider_id=PROVIDER_ID,
                source=source,
                query=query,
                buyer_safe_message=failure_message(SearchFailureCode.TIMEOUT),
            )
        except httpx.HTTPError:
            return ExternalSearchFailure(
                code=SearchFailureCode.UNAVAILABLE,
                provider_id=PROVIDER_ID,
                source=source,
                query=query,
                buyer_safe_message=failure_message(SearchFailureCode.UNAVAILABLE),
            )
        return self._result_from_response(query, source, response)

    def _result_from_response(
        self,
        query: ExternalSearchQuery,
        source: SearchProvenance,
        response: httpx.Response,
    ) -> ExternalSearchResult:
        if response.status_code in {401, 403}:
            return ExternalSearchFailure(
                code=SearchFailureCode.UNAUTHORIZED,
                provider_id=PROVIDER_ID,
                source=source,
                query=query,
                buyer_safe_message=(
                    "Hotel search credentials were rejected. No simulated parking was substituted."
                ),
            )
        if response.status_code in {408, 504}:
            return ExternalSearchFailure(
                code=SearchFailureCode.TIMEOUT,
                provider_id=PROVIDER_ID,
                source=source,
                query=query,
                buyer_safe_message=failure_message(SearchFailureCode.TIMEOUT),
            )
        if response.status_code >= 400:
            return ExternalSearchFailure(
                code=SearchFailureCode.UNAVAILABLE,
                provider_id=PROVIDER_ID,
                source=source,
                query=query,
                buyer_safe_message=failure_message(SearchFailureCode.UNAVAILABLE),
            )
        try:
            payload = response.json()
        except ValueError:
            return ExternalSearchFailure(
                code=SearchFailureCode.INVALID_RESPONSE,
                provider_id=PROVIDER_ID,
                source=source,
                query=query,
                buyer_safe_message=failure_message(SearchFailureCode.INVALID_RESPONSE),
            )
        if not isinstance(payload, Mapping):
            return ExternalSearchFailure(
                code=SearchFailureCode.INVALID_RESPONSE,
                provider_id=PROVIDER_ID,
                source=source,
                query=query,
                buyer_safe_message=failure_message(SearchFailureCode.INVALID_RESPONSE),
            )
        offers = normalize_offers(payload, query, source)
        if not offers:
            data = payload.get("data")
            if data in (None, [], {}):
                return ExternalSearchFailure(
                    code=SearchFailureCode.EMPTY,
                    provider_id=PROVIDER_ID,
                    source=source,
                    query=query,
                    buyer_safe_message=failure_message(SearchFailureCode.EMPTY),
                )
            return ExternalSearchFailure(
                code=SearchFailureCode.INVALID_RESPONSE,
                provider_id=PROVIDER_ID,
                source=source,
                query=query,
                buyer_safe_message=failure_message(SearchFailureCode.INVALID_RESPONSE),
            )
        return ExternalSearchPage(
            provider_id=PROVIDER_ID,
            source=source,
            fetched_at=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            query=query,
            offers=offers,
        )

    def book_sandbox(self, rate_ref: str) -> dict[str, object]:
        source = provenance_for_key(self._api_key)
        if source is SearchProvenance.LIVE:
            return {
                "status": "unavailable",
                "phase": "stopped",
                "source": source.value,
                "simulatedPayment": False,
                "bookingId": "",
                "buyerSafeMessage": (
                    "Live hotel booking is off. Sandbox holds only. No charge was attempted."
                ),
            }
        token = rate_ref.strip()
        if not token or not self._api_key:
            return {
                "status": "invalid_query",
                "phase": "stopped",
                "source": source.value,
                "simulatedPayment": True,
                "bookingId": "",
                "buyerSafeMessage": "That stay rate cannot be held in the sandbox.",
            }
        headers = {
            "X-API-Key": self._api_key,
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        timeout_s = self._timeout_ms / 1000.0
        prebook_body = {"offerId": token, "usePaymentSdk": False}
        self.last_prebook_body = dict(prebook_body)
        try:
            with httpx.Client(
                base_url=self._book_base_url,
                timeout=timeout_s,
                transport=self._transport,
            ) as client:
                prebook = client.post(PREBOOK_PATH, json=prebook_body, headers=headers)
                prebook_id = _prebook_id(prebook)
                if not prebook_id:
                    return _book_failure(source, "Could not create a sandbox hold. No charge.")
                book_body = {
                    "prebookId": prebook_id,
                    "holder": dict(SANDBOX_HOLDER),
                    "payment": {"method": "ACC_CREDIT_CARD"},
                    "guests": [
                        {
                            "occupancyNumber": 1,
                            "firstName": SANDBOX_HOLDER["firstName"],
                            "lastName": SANDBOX_HOLDER["lastName"],
                            "email": SANDBOX_HOLDER["email"],
                        }
                    ],
                }
                self.last_book_body = dict(book_body)
                booked = client.post(BOOK_PATH, json=book_body, headers=headers)
        except httpx.TimeoutException:
            return _book_failure(source, "Sandbox hold timed out. No charge.")
        except httpx.HTTPError:
            return _book_failure(source, "Sandbox hold is unavailable. No charge.")
        booking_id = _booking_id(booked)
        if not booking_id:
            return _book_failure(source, "Sandbox book did not confirm. No charge.")
        return {
            "status": "ok",
            "phase": "sandbox_booked",
            "source": source.value,
            "simulatedPayment": True,
            "bookingId": booking_id,
            "buyerSafeMessage": (
                "Sandbox booking created with simulated payment. No charge. Stopped after book."
            ),
        }


def _mapping(response: httpx.Response) -> Mapping[str, object]:
    try:
        payload = response.json()
    except ValueError:
        return {}
    return payload if isinstance(payload, Mapping) else {}


def _prebook_id(response: httpx.Response) -> str:
    if response.status_code >= 400:
        return ""
    payload = _mapping(response)
    data = payload.get("data")
    blob = data if isinstance(data, Mapping) else payload
    token = blob.get("prebookId")
    return token.strip() if isinstance(token, str) else ""


def _booking_id(response: httpx.Response) -> str:
    if response.status_code >= 400:
        return ""
    payload = _mapping(response)
    data = payload.get("data")
    blob = data if isinstance(data, Mapping) else payload
    for key in ("bookingId", "hotelConfirmationCode", "confirmationId", "id"):
        token = blob.get(key)
        if isinstance(token, str) and token.strip():
            return token.strip()[:80]
    status = blob.get("status")
    if isinstance(status, str) and status.strip().upper() == "CONFIRMED":
        return "sandbox-confirmed"
    return ""


def _book_failure(source: SearchProvenance, message: str) -> dict[str, object]:
    return {
        "status": "unavailable",
        "phase": "stopped",
        "source": source.value,
        "simulatedPayment": True,
        "bookingId": "",
        "buyerSafeMessage": message,
    }
