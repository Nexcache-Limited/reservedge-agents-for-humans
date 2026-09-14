from __future__ import annotations

import os

import httpx
import pytest

from itaa_application.external_search_port import (
    ExternalSearchFailure,
    ExternalSearchPage,
    ExternalSearchQuery,
    FlightSearchPage,
    FlightSearchQuery,
    PlaceRef,
    SearchFailureCode,
    SearchProvenance,
)
from itaa_liteapi_hotels.adapter import (
    LiteApiStaySearchAdapter,
    provider_timeout_s,
    rates_request_body,
)
from itaa_liteapi_hotels.compose import compose_flight_search_port, compose_stay_search_port
from itaa_liteapi_hotels.fake import FakeStaySearchAdapter
from itaa_liteapi_hotels.fake_flights import FakeFlightSearchAdapter
from itaa_liteapi_hotels.flights import LiteApiFlightSearchAdapter, flights_request_body
from itaa_liteapi_hotels.normalize import normalize_offers


def _query(city: str = "Milan") -> ExternalSearchQuery:
    return ExternalSearchQuery(
        domain="stay",
        destination=PlaceRef("city", city),
        start="2026-10-20",
        end="2026-10-30",
        origin=PlaceRef("city", "Mumbai"),
    )


def _key() -> str:
    return "sand_" + "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"


def test_milan_rates_request_uses_city_and_dates() -> None:
    body = rates_request_body(_query())
    assert body["cityName"] == "Milan"
    assert body["countryCode"] == "IT"
    assert body["checkin"] == "2026-10-20"
    assert body["checkout"] == "2026-10-30"
    assert body["currency"] == "EUR"
    assert body["guestNationality"] == "IN"
    assert body["occupancies"] == [{"adults": 2}]
    assert body["maxRatesPerHotel"] == 1
    assert body["limit"] == 4
    assert body["timeout"] == provider_timeout_s()
    assert "hotelIds" not in body


def test_heathrow_rates_request_uses_london_city_for_sandbox_catalog() -> None:
    body = rates_request_body(_query("Heathrow"))
    assert body["cityName"] == "London"
    assert body["countryCode"] == "GB"
    assert body["currency"] == "GBP"


def test_miami_rates_request_uses_us_city() -> None:
    body = rates_request_body(_query("Miami"))
    assert body["cityName"] == "Miami"
    assert body["countryCode"] == "US"
    assert body["currency"] == "USD"


def test_inverted_dates_are_invalid_query() -> None:
    query = ExternalSearchQuery(
        domain="stay",
        destination=PlaceRef("city", "Miami"),
        start="2026-10-20",
        end="2026-10-15",
    )
    result = FakeStaySearchAdapter().search(query)
    assert isinstance(result, ExternalSearchFailure)
    assert result.code is SearchFailureCode.INVALID_QUERY


def test_fake_mode_is_labelled_and_milan_specific() -> None:
    page = FakeStaySearchAdapter().search(_query())
    assert isinstance(page, ExternalSearchPage)
    assert page.source is SearchProvenance.FAKE
    names = " ".join(item.name for item in page.offers).lower()
    assert "milan" in names or any("milan" in item.locality.lower() for item in page.offers)
    assert all("jfk" not in item.name.lower() for item in page.offers)
    assert all("skyshield" not in item.name.lower() for item in page.offers)


def test_ci_default_compose_is_fake_without_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ITAA_STAY_SEARCH_MODE", raising=False)
    monkeypatch.delenv("ITAA_LITEAPI_API_KEY", raising=False)
    port = compose_stay_search_port()
    assert isinstance(port, FakeStaySearchAdapter)


def test_sandbox_compose_without_key_stays_credential_free(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ITAA_STAY_SEARCH_MODE", "sandbox")
    monkeypatch.delenv("ITAA_LITEAPI_API_KEY", raising=False)
    port = compose_stay_search_port()
    assert isinstance(port, FakeStaySearchAdapter)


def test_sandbox_without_key_is_unauthorized(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ITAA_STAY_SEARCH_MODE", "sandbox")
    monkeypatch.delenv("ITAA_LITEAPI_API_KEY", raising=False)
    result = LiteApiStaySearchAdapter.from_env().search(_query())
    assert isinstance(result, ExternalSearchFailure)
    assert result.code is SearchFailureCode.UNAUTHORIZED
    assert result.source is SearchProvenance.SANDBOX


def test_rejected_credentials_are_not_missing_config() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(401, json={"error": {"code": 401, "message": "unauthorized"}})

    adapter = LiteApiStaySearchAdapter(api_key=_key(), transport=httpx.MockTransport(handler))
    result = adapter.search(_query())
    assert isinstance(result, ExternalSearchFailure)
    assert result.code is SearchFailureCode.UNAUTHORIZED
    assert "not configured" not in result.buyer_safe_message.lower()
    assert "rejected" in result.buyer_safe_message.lower()
    assert "skyshield" not in result.buyer_safe_message.lower()


def test_dubai_origin_uses_ae_nationality_for_london_stay() -> None:
    body = rates_request_body(
        ExternalSearchQuery(
            domain="stay",
            destination=PlaceRef("city", "London"),
            start="2026-10-12T07:00:00",
            end="2026-10-16T22:00:00",
            origin=PlaceRef("city", "Dubai"),
        )
    )
    assert body["guestNationality"] == "AE"
    assert body["checkin"] == "2026-10-12"
    assert body["checkout"] == "2026-10-16"
    assert body["cityName"] == "London"
    assert body["countryCode"] == "GB"


def test_timeout_is_typed_not_parking(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        del request
        raise httpx.TimeoutException("slow")

    adapter = LiteApiStaySearchAdapter(api_key=_key(), transport=httpx.MockTransport(handler))
    result = adapter.search(_query())
    assert isinstance(result, ExternalSearchFailure)
    assert result.code is SearchFailureCode.TIMEOUT
    assert "skyshield" not in result.buyer_safe_message.lower()


def test_empty_result() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(200, json={"data": []})

    adapter = LiteApiStaySearchAdapter(api_key=_key(), transport=httpx.MockTransport(handler))
    result = adapter.search(_query())
    assert isinstance(result, ExternalSearchFailure)
    assert result.code is SearchFailureCode.EMPTY


def test_malformed_provider_result() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(200, json={"data": [{"hotel": {"id": "x"}}]})

    adapter = LiteApiStaySearchAdapter(api_key=_key(), transport=httpx.MockTransport(handler))
    result = adapter.search(_query())
    assert isinstance(result, ExternalSearchFailure)
    assert result.code is SearchFailureCode.INVALID_RESPONSE


def test_provider_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(503, json={"error": {"message": "down"}})

    adapter = LiteApiStaySearchAdapter(api_key=_key(), transport=httpx.MockTransport(handler))
    result = adapter.search(_query())
    assert isinstance(result, ExternalSearchFailure)
    assert result.code is SearchFailureCode.UNAVAILABLE
    assert "skyshield" not in result.buyer_safe_message.lower()
    assert "parkdirect" not in result.buyer_safe_message.lower()


def test_success_page_is_sandbox_labelled_milan() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers.get("X-API-Key") == _key()
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "hotel": {"id": "lp1", "name": "Hotel Viu Milan", "city": "Milan"},
                        "roomTypes": [
                            {
                                "rates": [
                                    {
                                        "retailRate": {
                                            "total": [{"amount": 198, "currency": "EUR"}]
                                        },
                                        "cancellationPolicies": [{"type": "FREE_CANCELLATION"}],
                                    }
                                ]
                            }
                        ],
                    }
                ]
            },
        )

    adapter = LiteApiStaySearchAdapter(api_key=_key(), transport=httpx.MockTransport(handler))
    result = adapter.search(_query())
    assert isinstance(result, ExternalSearchPage)
    assert result.source is SearchProvenance.SANDBOX
    assert result.offers[0].name == "Hotel Viu Milan"
    assert result.offers[0].booking_authority == "none"
    assert adapter.last_request_body is not None
    assert adapter.last_request_body["cityName"] == "Milan"


def test_no_silent_fake_fallback_on_sandbox_failure() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(500, json={})

    adapter = LiteApiStaySearchAdapter(api_key=_key(), transport=httpx.MockTransport(handler))
    result = adapter.search(_query())
    assert isinstance(result, ExternalSearchFailure)
    assert not isinstance(result, ExternalSearchPage)


def test_normalize_does_not_leak_room_types() -> None:
    payload = {
        "data": [
            {
                "hotel": {"id": "lp1", "name": "Hotel Viu Milan", "city": "Milan"},
                "roomTypes": [
                    {
                        "rates": [
                            {
                                "retailRate": {"total": [{"amount": 198, "currency": "EUR"}]},
                                "cancellationPolicies": [{"type": "FREE_CANCELLATION"}],
                            }
                        ]
                    }
                ],
            }
        ]
    }
    offers = normalize_offers(payload, _query(), SearchProvenance.SANDBOX)
    assert len(offers) == 1
    assert offers[0].name == "Hotel Viu Milan"
    assert offers[0].amount_minor == 19800
    assert offers[0].currency == "EUR"
    assert offers[0].booking_authority == "none"


def test_unknown_city_uses_ai_search_not_an_allowlist() -> None:
    body = rates_request_body(_query("Osaka"))
    assert body["aiSearch"] == "hotels in Osaka"
    assert "countryCode" not in body


def test_normalize_joins_sidecar_hotel_catalog() -> None:
    payload = {
        "data": [
            {
                "hotelId": "lp1c55f",
                "roomTypes": [
                    {
                        "offerId": "offer-lp1c55f",
                        "rates": [
                            {
                                "retailRate": {"total": [{"amount": 3423.25, "currency": "EUR"}]},
                                "cancellationPolicies": [{"type": "FREE_CANCELLATION"}],
                            }
                        ],
                    }
                ],
            }
        ],
        "hotels": [
            {
                "id": "lp1c55f",
                "name": "Hotel Viu Milan",
                "city_name": "Milan",
                "country_code": "IT",
                "address": "Via Piero da Pisa 9",
                "thumbnail": "https://cdn.example.invalid/viu.jpg",
            }
        ],
        "sandbox": True,
    }
    offers = normalize_offers(payload, _query(), SearchProvenance.SANDBOX)
    assert len(offers) == 1
    assert offers[0].name == "Hotel Viu Milan"
    assert offers[0].external_id == "lp1c55f"
    assert offers[0].locality == "Milan, IT"
    assert offers[0].amount_minor == 342325
    assert offers[0].booking_authority == "none"
    assert offers[0].photo_url == "https://cdn.example.invalid/viu.jpg"
    assert offers[0].rate_ref == "offer-lp1c55f"


def test_http_photo_is_dropped() -> None:
    payload = {
        "data": [
            {
                "hotel": {
                    "id": "lp1",
                    "name": "Hotel Viu Milan",
                    "city": "Milan",
                    "thumbnail": "http://insecure.example/x.jpg",
                },
                "roomTypes": [{"offerId": "offer-1", "rates": []}],
            }
        ]
    }
    offers = normalize_offers(payload, _query(), SearchProvenance.SANDBOX)
    assert offers[0].photo_url is None


def test_sandbox_book_prebooks_then_stops() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/rates/prebook"):
            return httpx.Response(200, json={"data": {"prebookId": "pb-1"}})
        if request.url.path.endswith("/rates/book"):
            return httpx.Response(200, json={"data": {"bookingId": "bk-1", "status": "CONFIRMED"}})
        return httpx.Response(500, json={})

    adapter = LiteApiStaySearchAdapter(
        api_key=_key(),
        transport=httpx.MockTransport(handler),
        book_base_url="https://book.liteapi.travel",
    )
    result = adapter.book_sandbox("offer-1")
    assert result["status"] == "ok"
    assert result["phase"] == "sandbox_booked"
    assert result["bookingId"] == "bk-1"
    assert result["simulatedPayment"] is True
    assert adapter.last_prebook_body == {"offerId": "offer-1", "usePaymentSdk": False}
    assert adapter.last_book_body is not None
    assert adapter.last_book_body["payment"] == {"method": "ACC_CREDIT_CARD"}
    assert (
        "charge" in str(result["buyerSafeMessage"]).lower()
        or "no charge" in str(result["buyerSafeMessage"]).lower()
    )


def test_live_key_does_not_book() -> None:
    adapter = LiteApiStaySearchAdapter(api_key="live_" + "a" * 36)
    result = adapter.book_sandbox("offer-1")
    assert result["status"] == "unavailable"
    assert result["simulatedPayment"] is False
    assert result["bookingId"] == ""


@pytest.mark.skipif(os.environ.get("ITAA_LITEAPI_LIVE_TEST") != "1", reason="opt-in sandbox UAT")
def test_opt_in_live_sandbox_milan() -> None:
    adapter = LiteApiStaySearchAdapter.from_env()
    result = adapter.search(_query())
    assert (
        not isinstance(result, ExternalSearchFailure)
        or result.code is not SearchFailureCode.UNAUTHORIZED
    )


def _flight_query() -> FlightSearchQuery:
    return FlightSearchQuery(origin="MAN", destination="LHR", date="2026-10-25")


def test_flights_request_body_uses_legs() -> None:
    body = flights_request_body(_flight_query())
    assert body["legs"] == [
        {
            "origin": "MAN",
            "destination": "LHR",
            "date": "2026-10-25",
            "direction": "OUTBOUND",
        }
    ]
    assert body["adults"] == 1
    assert body["currency"] == "GBP"


def test_ci_default_flight_compose_is_fake(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ITAA_STAY_SEARCH_MODE", raising=False)
    monkeypatch.delenv("ITAA_LITEAPI_API_KEY", raising=False)
    port = compose_flight_search_port()
    assert isinstance(port, FakeFlightSearchAdapter)


def test_fake_flight_search_is_labelled_and_not_stay() -> None:
    page = FakeFlightSearchAdapter().search(_flight_query())
    assert isinstance(page, FlightSearchPage)
    assert page.source is SearchProvenance.FAKE
    assert len(page.offers) == 2
    assert page.offers[0].origin == "MAN"
    assert page.offers[0].destination == "LHR"
    blob = str(page).lower()
    assert "spadari" not in blob
    assert "skyshield" not in blob


def test_sandbox_flight_success_page() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/v3.0/flights/rates")
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "journeys": [
                            {
                                "journeyKey": "j1",
                                "totalDuration": {"minutes": 70},
                                "segments": [
                                    {
                                        "originCode": "MAN",
                                        "destinationCode": "LHR",
                                        "departureTime": "2026-10-25T09:15:00",
                                        "arrivalTime": "2026-10-25T10:25:00",
                                        "carrier": {
                                            "marketingCode": "BA",
                                            "marketingName": "British Airways",
                                        },
                                        "flight": {"marketingNumber": "1391"},
                                        "duration": {"minutes": 70},
                                    }
                                ],
                                "offers": [
                                    {
                                        "offerId": "off-1",
                                        "cabin": "economy",
                                        "pricing": {"display": {"total": 48.5, "currency": "GBP"}},
                                        "baggage": {"included": True},
                                    }
                                ],
                            }
                        ]
                    }
                ]
            },
        )

    adapter = LiteApiFlightSearchAdapter(api_key=_key(), transport=httpx.MockTransport(handler))
    result = adapter.search(_flight_query())
    assert isinstance(result, FlightSearchPage)
    assert result.source is SearchProvenance.SANDBOX
    assert result.offers[0].airline == "British Airways"
    assert result.offers[0].booking_authority == "none"
