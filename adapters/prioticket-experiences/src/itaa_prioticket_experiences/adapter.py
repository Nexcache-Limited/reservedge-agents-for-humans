"""Prioticket Distributor sandbox experience search. Research only; no booking."""

from __future__ import annotations

import os
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

import httpx

from itaa_application.external_search_port import (
    ExperienceSearchPage,
    ExperienceSearchResult,
    ExternalSearchFailure,
    ExternalSearchQuery,
    SearchFailureCode,
    SearchProvenance,
    failure_message,
)
from itaa_prioticket_experiences.normalize import (
    PRODUCTS_SCOPE,
    PROVIDER_ID,
    match_destination_id,
    normalize_offers,
    secret_in_text,
)

DEFAULT_BASE_URL = "https://sandbox-distributor-api.prioticket.com/v3.8/distributor"
TOKEN_PATH = "/oauth2/token"
DESTINATIONS_PATH = "/products/destinations"
PRODUCTS_PATH = "/products"
DEFAULT_TIMEOUT_MS = 12_000
MAX_TIMEOUT_MS = 20_000
MIN_TIMEOUT_MS = 3_000


def experience_search_mode(raw: str | None = None) -> str:
    text = os.environ.get("ITAA_EXPERIENCE_SEARCH_MODE", "fake") if raw is None else raw
    mode = text.strip().lower()
    return mode if mode in {"fake", "sandbox"} else "fake"


def prioticket_timeout_ms(raw: str | None = None) -> int:
    text = os.environ.get("ITAA_PRIOTICKET_TIMEOUT_MS", "") if raw is None else raw
    if text is None or not str(text).strip():
        return DEFAULT_TIMEOUT_MS
    try:
        value = int(str(text).strip())
    except ValueError:
        return DEFAULT_TIMEOUT_MS
    return max(MIN_TIMEOUT_MS, min(value, MAX_TIMEOUT_MS))


def prioticket_client_id(raw: str | None = None) -> str:
    text = os.environ.get("ITAA_PRIOTICKET_CLIENT_ID", "") if raw is None else raw
    return "" if text is None else str(text).strip()


def prioticket_client_secret(raw: str | None = None) -> str:
    text = os.environ.get("ITAA_PRIOTICKET_CLIENT_SECRET", "") if raw is None else raw
    return "" if text is None else str(text).strip()


def prioticket_base_url(raw: str | None = None) -> str:
    text = os.environ.get("ITAA_PRIOTICKET_BASE_URL", "") if raw is None else raw
    value = DEFAULT_BASE_URL if text is None or not str(text).strip() else str(text).strip()
    return value.rstrip("/")


class PrioticketExperienceAdapter:
    def __init__(
        self,
        *,
        client_id: str,
        client_secret: str,
        timeout_ms: int | None = None,
        transport: httpx.BaseTransport | None = None,
        base_url: str | None = None,
    ) -> None:
        self._client_id = client_id.strip()
        self._client_secret = client_secret.strip()
        self._timeout_ms = prioticket_timeout_ms(None if timeout_ms is None else str(timeout_ms))
        self._transport = transport
        self._base_url = (base_url or prioticket_base_url()).rstrip("/")
        self._token = ""
        self._token_type = "Bearer"
        self.last_product_params: dict[str, object] | None = None

    @classmethod
    def from_env(cls) -> PrioticketExperienceAdapter:
        return cls(
            client_id=prioticket_client_id(),
            client_secret=prioticket_client_secret(),
            timeout_ms=prioticket_timeout_ms(),
            base_url=prioticket_base_url(),
        )

    def search(self, query: ExternalSearchQuery) -> ExperienceSearchResult:
        source = SearchProvenance.SANDBOX
        if query.domain != "experience" or not query.destination.value.strip():
            return ExternalSearchFailure(
                code=SearchFailureCode.INVALID_QUERY,
                provider_id=PROVIDER_ID,
                source=source,
                query=query,
                buyer_safe_message=failure_message(
                    SearchFailureCode.INVALID_QUERY, domain="experience"
                ),
            )
        if not self._client_id or not self._client_secret:
            return ExternalSearchFailure(
                code=SearchFailureCode.UNAUTHORIZED,
                provider_id=PROVIDER_ID,
                source=source,
                query=query,
                buyer_safe_message=failure_message(
                    SearchFailureCode.UNAUTHORIZED, domain="experience"
                ),
            )
        try:
            with httpx.Client(
                base_url=self._base_url,
                timeout=self._timeout_ms / 1000.0,
                transport=self._transport,
            ) as client:
                token = self._access_token(client, query)
                if isinstance(token, ExternalSearchFailure):
                    return token
                destination_id = self._destination_id(client, token, query.destination.value, query)
                if isinstance(destination_id, ExternalSearchFailure):
                    return destination_id
                payload = self._products(client, token, query, destination_id)
                if isinstance(payload, ExternalSearchFailure):
                    return payload
        except httpx.TimeoutException:
            return ExternalSearchFailure(
                code=SearchFailureCode.TIMEOUT,
                provider_id=PROVIDER_ID,
                source=source,
                query=query,
                buyer_safe_message=failure_message(SearchFailureCode.TIMEOUT, domain="experience"),
            )
        except httpx.HTTPError:
            return ExternalSearchFailure(
                code=SearchFailureCode.UNAVAILABLE,
                provider_id=PROVIDER_ID,
                source=source,
                query=query,
                buyer_safe_message=failure_message(
                    SearchFailureCode.UNAVAILABLE, domain="experience"
                ),
            )
        return self._page_from_payload(query, source, payload)

    def _access_token(
        self, client: httpx.Client, query: ExternalSearchQuery
    ) -> str | ExternalSearchFailure:
        if self._token:
            return self._token
        response = client.post(
            TOKEN_PATH,
            json={"grant_type": "client_credentials", "scope": PRODUCTS_SCOPE},
            auth=(self._client_id, self._client_secret),
            headers={"Accept": "application/json"},
        )
        failed = self._http_failure(response, SearchProvenance.SANDBOX, query)
        if failed is not None:
            return failed
        try:
            body = response.json()
        except ValueError:
            return self._typed_failure(SearchFailureCode.INVALID_RESPONSE, query=query)
        if not isinstance(body, Mapping):
            return self._typed_failure(SearchFailureCode.INVALID_RESPONSE, query=query)
        token = str(body.get("access_token") or "").strip()
        token_type = str(body.get("token_type") or "Bearer").strip() or "Bearer"
        if not token:
            return self._typed_failure(SearchFailureCode.UNAUTHORIZED, query=query)
        self._token = token
        self._token_type = token_type
        return token

    def _auth_header(self, token: str) -> dict[str, str]:
        return {
            "Authorization": f"{self._token_type} {token}",
            "Accept": "application/json",
        }

    def _destination_id(
        self,
        client: httpx.Client,
        token: str,
        city: str,
        query: ExternalSearchQuery,
    ) -> str | ExternalSearchFailure:
        response = client.get(
            DESTINATIONS_PATH,
            params={"items_per_page": 200, "page": 1},
            headers=self._auth_header(token),
        )
        failed = self._http_failure(response, SearchProvenance.SANDBOX, query)
        if failed is not None:
            return failed
        try:
            body = response.json()
        except ValueError:
            return self._typed_failure(SearchFailureCode.INVALID_RESPONSE, query=query)
        if not isinstance(body, Mapping):
            return self._typed_failure(SearchFailureCode.INVALID_RESPONSE, query=query)
        matched = match_destination_id(body, city)
        if matched:
            return matched
        return self._typed_failure(SearchFailureCode.EMPTY, query=query)

    def _products(
        self,
        client: httpx.Client,
        token: str,
        query: ExternalSearchQuery,
        destination_id: str,
    ) -> Mapping[str, Any] | ExternalSearchFailure:
        params: dict[str, str | int] = {"items_per_page": 6, "page": 1}
        if query.preferences:
            params["product_content"] = " ".join(query.preferences)
        if query.start:
            params["product_start_date"] = query.start
        if query.end:
            params["product_end_date"] = query.end
        self.last_product_params = dict(params)
        if destination_id:
            self.last_product_params["matched_destination_id"] = destination_id
        response = client.get(PRODUCTS_PATH, params=params, headers=self._auth_header(token))
        failed = self._http_failure(response, SearchProvenance.SANDBOX, query)
        if failed is not None:
            return failed
        try:
            body = response.json()
        except ValueError:
            return self._typed_failure(SearchFailureCode.INVALID_RESPONSE, query=query)
        if not isinstance(body, Mapping):
            return self._typed_failure(SearchFailureCode.INVALID_RESPONSE, query=query)
        return body

    def _page_from_payload(
        self,
        query: ExternalSearchQuery,
        source: SearchProvenance,
        payload: Mapping[str, Any],
    ) -> ExperienceSearchResult:
        offers = normalize_offers(payload, query, source)
        city = query.destination.value.strip().lower()
        if city:
            located = tuple(
                item
                for item in offers
                if city in item.location.lower() or city in item.title.lower()
            )
            offers = located
        if not offers:
            return ExternalSearchFailure(
                code=SearchFailureCode.EMPTY,
                provider_id=PROVIDER_ID,
                source=source,
                query=query,
                buyer_safe_message=failure_message(SearchFailureCode.EMPTY, domain="experience"),
            )
        encoded = str(payload).lower()
        if secret_in_text(encoded, self._client_id, self._client_secret, self._token):
            return ExternalSearchFailure(
                code=SearchFailureCode.INVALID_RESPONSE,
                provider_id=PROVIDER_ID,
                source=source,
                query=query,
                buyer_safe_message=failure_message(
                    SearchFailureCode.INVALID_RESPONSE, domain="experience"
                ),
            )
        return ExperienceSearchPage(
            provider_id=PROVIDER_ID,
            source=source,
            fetched_at=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            query=query,
            offers=offers,
        )

    def _http_failure(
        self,
        response: httpx.Response,
        source: SearchProvenance,
        query: ExternalSearchQuery,
    ) -> ExternalSearchFailure | None:
        if response.status_code in {401, 403}:
            self._token = ""
            return ExternalSearchFailure(
                code=SearchFailureCode.UNAUTHORIZED,
                provider_id=PROVIDER_ID,
                source=source,
                query=query,
                buyer_safe_message=(
                    "Experience search credentials were rejected. "
                    "No hotel or parking inventory was substituted."
                ),
            )
        if response.status_code in {408, 504}:
            return self._typed_failure(SearchFailureCode.TIMEOUT, query=query, source=source)
        if response.status_code >= 400:
            return self._typed_failure(SearchFailureCode.UNAVAILABLE, query=query, source=source)
        return None

    def _typed_failure(
        self,
        code: SearchFailureCode,
        *,
        query: ExternalSearchQuery | None = None,
        source: SearchProvenance = SearchProvenance.SANDBOX,
    ) -> ExternalSearchFailure:
        return ExternalSearchFailure(
            code=code,
            provider_id=PROVIDER_ID,
            source=source,
            query=query,
            buyer_safe_message=failure_message(code, domain="experience"),
        )
