from __future__ import annotations

import httpx
import pytest

from itaa_application.external_search_port import (
    ExperienceSearchPage,
    ExternalSearchFailure,
    ExternalSearchQuery,
    PlaceRef,
    SearchFailureCode,
    SearchProvenance,
)
from itaa_prioticket_experiences.adapter import (
    PrioticketExperienceAdapter,
    experience_search_mode,
    prioticket_client_id,
    prioticket_timeout_ms,
)
from itaa_prioticket_experiences.compose import compose_experience_search_port
from itaa_prioticket_experiences.fake import FakeExperienceSearchAdapter
from itaa_prioticket_experiences.normalize import (
    iter_items,
    match_destination_id,
    normalize_offers,
    secret_in_text,
)


def _query(city: str = "Milan", prefs: tuple[str, ...] = ()) -> ExternalSearchQuery:
    return ExternalSearchQuery(
        domain="experience",
        destination=PlaceRef("city", city),
        start="2026-10-20",
        end="2026-10-30",
        preferences=prefs,
    )


def _product(title: str = "Duomo museum entry") -> dict[str, object]:
    return {
        "product_id": "PRODUCT_MILAN_1",
        "product_from_price": "45.00",
        "product_duration": 120,
        "product_cancellation_allowed": True,
        "product_availability": True,
        "product_start_date": "2026-10-20T00:00:00Z",
        "product_end_date": "2026-10-30T00:00:00Z",
        "product_payment_detail": {"product_payment_currency": {"currency_code": "EUR"}},
        "product_content": {
            "product_title": title,
            "product_supplier_name": "Milan Museums",
        },
        "product_destinations": [{"destination_name": "Milan"}],
    }


def _handler(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    if path.endswith("/oauth2/token"):
        assert request.headers.get("authorization", "").lower().startswith("basic ")
        return httpx.Response(
            200,
            json={"access_token": "sandbox-token", "token_type": "Bearer", "expires_in": 3600},
        )
    auth = request.headers.get("authorization", "")
    assert auth == "Bearer sandbox-token"
    if path.endswith("/products/destinations"):
        return httpx.Response(
            200,
            json={
                "data": {
                    "items": [
                        {"destination_id": "1001", "destination_name": "Milan"},
                        {"destination_id": "1002", "destination_name": "London"},
                    ]
                }
            },
        )
    if path.endswith("/products"):
        return httpx.Response(200, json={"data": {"items": [_product()]}})
    return httpx.Response(404, json={"error": "missing"})


def test_fake_mode_is_labelled_and_milan_specific() -> None:
    page = FakeExperienceSearchAdapter().search(_query())
    assert isinstance(page, ExperienceSearchPage)
    assert page.source is SearchProvenance.FAKE
    titles = " ".join(item.title for item in page.offers).lower()
    assert "milan" in titles or any("milan" in item.location.lower() for item in page.offers)
    assert all("jfk" not in item.title.lower() for item in page.offers)
    assert all("skyshield" not in item.title.lower() for item in page.offers)
    assert all(item.booking_authority == "none" for item in page.offers)


def test_london_fake_is_not_milan() -> None:
    page = FakeExperienceSearchAdapter().search(_query("London"))
    assert isinstance(page, ExperienceSearchPage)
    blob = " ".join(f"{item.title} {item.location}" for item in page.offers).lower()
    assert "london" in blob
    assert "duomo" not in blob


def test_ci_default_compose_is_fake_without_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ITAA_EXPERIENCE_SEARCH_MODE", raising=False)
    monkeypatch.delenv("ITAA_PRIOTICKET_CLIENT_ID", raising=False)
    monkeypatch.delenv("ITAA_PRIOTICKET_CLIENT_SECRET", raising=False)
    port = compose_experience_search_port()
    assert isinstance(port, FakeExperienceSearchAdapter)


def test_sandbox_compose_without_secret_stays_credential_free(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ITAA_EXPERIENCE_SEARCH_MODE", "sandbox")
    monkeypatch.setenv("ITAA_PRIOTICKET_CLIENT_ID", "demo-client")
    monkeypatch.delenv("ITAA_PRIOTICKET_CLIENT_SECRET", raising=False)
    port = compose_experience_search_port()
    assert isinstance(port, FakeExperienceSearchAdapter)


def test_sandbox_without_credentials_is_unauthorized() -> None:
    result = PrioticketExperienceAdapter(client_id="", client_secret="").search(_query())
    assert isinstance(result, ExternalSearchFailure)
    assert result.code is SearchFailureCode.UNAUTHORIZED


def test_rejected_credentials_are_not_missing_config() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(401, json={"error": "unauthorized"})

    adapter = PrioticketExperienceAdapter(
        client_id="id",
        client_secret="secret",
        transport=httpx.MockTransport(handler),
    )
    result = adapter.search(_query())
    assert isinstance(result, ExternalSearchFailure)
    assert result.code is SearchFailureCode.UNAUTHORIZED
    assert "not configured" not in result.buyer_safe_message.lower()
    assert "rejected" in result.buyer_safe_message.lower()
    assert "secret" not in result.buyer_safe_message.lower()


def test_timeout_is_typed_not_hotel() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        del request
        raise httpx.TimeoutException("slow")

    adapter = PrioticketExperienceAdapter(
        client_id="id",
        client_secret="secret",
        transport=httpx.MockTransport(handler),
    )
    result = adapter.search(_query())
    assert isinstance(result, ExternalSearchFailure)
    assert result.code is SearchFailureCode.TIMEOUT
    assert "spadari" not in result.buyer_safe_message.lower()


def test_empty_result() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/oauth2/token"):
            return httpx.Response(200, json={"access_token": "t", "token_type": "Bearer"})
        if request.url.path.endswith("/products/destinations"):
            return httpx.Response(
                200,
                json={"data": {"items": [{"destination_id": "1", "destination_name": "Milan"}]}},
            )
        return httpx.Response(200, json={"data": {"items": []}})

    adapter = PrioticketExperienceAdapter(
        client_id="id",
        client_secret="secret",
        transport=httpx.MockTransport(handler),
    )
    result = adapter.search(_query())
    assert isinstance(result, ExternalSearchFailure)
    assert result.code is SearchFailureCode.EMPTY


def test_unmatched_destination_is_empty_not_other_city_inventory() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/oauth2/token"):
            return httpx.Response(200, json={"access_token": "t", "token_type": "Bearer"})
        if request.url.path.endswith("/products/destinations"):
            return httpx.Response(
                200,
                json={
                    "data": {
                        "items": [
                            {
                                "destination_id": "129",
                                "destination_name": "Amsterdam Theme Destination",
                            }
                        ]
                    }
                },
            )
        raise AssertionError("must not search products for an unmatched city")

    adapter = PrioticketExperienceAdapter(
        client_id="id",
        client_secret="secret",
        transport=httpx.MockTransport(handler),
    )
    result = adapter.search(_query("Milan"))
    assert isinstance(result, ExternalSearchFailure)
    assert result.code is SearchFailureCode.EMPTY


def test_malformed_provider_result() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/oauth2/token"):
            return httpx.Response(200, json={"access_token": "t", "token_type": "Bearer"})
        return httpx.Response(200, content=b"not-json")

    adapter = PrioticketExperienceAdapter(
        client_id="id",
        client_secret="secret",
        transport=httpx.MockTransport(handler),
    )
    result = adapter.search(_query())
    assert isinstance(result, ExternalSearchFailure)
    assert result.code is SearchFailureCode.INVALID_RESPONSE


def test_provider_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(503, json={"error": "down"})

    adapter = PrioticketExperienceAdapter(
        client_id="id",
        client_secret="secret",
        transport=httpx.MockTransport(handler),
    )
    result = adapter.search(_query())
    assert isinstance(result, ExternalSearchFailure)
    assert result.code is SearchFailureCode.UNAVAILABLE


def test_success_page_is_sandbox_labelled_milan() -> None:
    adapter = PrioticketExperienceAdapter(
        client_id="id",
        client_secret="secret",
        transport=httpx.MockTransport(_handler),
    )
    result = adapter.search(_query())
    assert isinstance(result, ExperienceSearchPage)
    assert result.source is SearchProvenance.SANDBOX
    assert result.offers[0].title == "Duomo museum entry"
    assert result.offers[0].booking_authority == "none"
    assert "product_content" not in str(result.offers[0])
    assert adapter.last_product_params is not None
    assert adapter.last_product_params["matched_destination_id"] == "1001"
    assert "destination_id" not in adapter.last_product_params


def test_normalize_drops_raw_prioticket_keys() -> None:
    offers = normalize_offers(
        {"data": {"items": [_product()]}},
        _query(),
        SearchProvenance.SANDBOX,
    )
    assert len(offers) == 1
    blob = str(offers[0])
    assert "product_content" not in blob
    assert "product_from_price" not in blob
    assert offers[0].currency == "EUR"
    assert offers[0].amount_minor == 4500


def test_wrong_domain_is_invalid() -> None:
    query = ExternalSearchQuery(
        domain="stay",
        destination=PlaceRef("city", "Milan"),
        start="2026-10-20",
        end="2026-10-30",
    )
    result = FakeExperienceSearchAdapter().search(query)
    assert isinstance(result, ExternalSearchFailure)
    assert result.code is SearchFailureCode.INVALID_QUERY


def test_normalize_covers_optional_product_fields() -> None:
    payload = {
        "data": {
            "items": [
                {
                    "product_id": "P2",
                    "product_from_price": 16.4,
                    "product_duration": "90",
                    "product_cancellation_allowed": False,
                    "product_availability": False,
                    "product_categories": [{"category_name": "Tours"}],
                    "product_pickup_point_details": [{"pickup_point_name": "Duomo square"}],
                    "product_content": {
                        "product_title": "Evening canal cruise",
                        "product_duration_text": "1.5 hour",
                        "product_images": [
                            {
                                "image_type": "BANNER",
                                "image_url": "https://cdn.example.invalid/cruise.jpg",
                            }
                        ],
                    },
                }
            ]
        }
    }
    offers = normalize_offers(payload, _query(prefs=("evening",)), SearchProvenance.SANDBOX)
    assert offers[0].category == "Tours"
    assert offers[0].location == "Duomo square"
    assert offers[0].cancellation == "Non-refundable"
    assert "unavailable" in offers[0].availability
    assert offers[0].photo_url is not None
    assert offers[0].duration_minutes == 90


def test_sandbox_compose_with_credentials_uses_live_adapter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ITAA_EXPERIENCE_SEARCH_MODE", "sandbox")
    monkeypatch.setenv("ITAA_PRIOTICKET_CLIENT_ID", "demo-client")
    monkeypatch.setenv("ITAA_PRIOTICKET_CLIENT_SECRET", "demo-secret-value")
    port = compose_experience_search_port()
    assert isinstance(port, PrioticketExperienceAdapter)


def test_timeout_and_base_url_helpers(monkeypatch: pytest.MonkeyPatch) -> None:
    from itaa_prioticket_experiences.adapter import prioticket_base_url, prioticket_timeout_ms

    monkeypatch.setenv("ITAA_PRIOTICKET_TIMEOUT_MS", "not-a-number")
    assert prioticket_timeout_ms() >= 3000
    monkeypatch.setenv("ITAA_PRIOTICKET_TIMEOUT_MS", "4000")
    assert prioticket_timeout_ms() == 4000
    monkeypatch.setenv("ITAA_PRIOTICKET_BASE_URL", "https://example.invalid/distributor/")
    assert prioticket_base_url().endswith("distributor")


def test_unscoped_products_are_not_attached_to_the_search_city() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/oauth2/token"):
            return httpx.Response(200, json={"access_token": "t", "token_type": "Bearer"})
        if request.url.path.endswith("/products/destinations"):
            return httpx.Response(
                200,
                json={"data": {"items": [{"destination_id": "1001", "destination_name": "Milan"}]}},
            )
        return httpx.Response(
            200,
            json={
                "data": {
                    "items": [
                        {
                            "product_id": "P-UNSCOPED",
                            "product_from_price": "10.00",
                            "product_content": {
                                "product_title": "Arabian Adventures - Evening Desert Safari"
                            },
                        }
                    ]
                }
            },
        )

    adapter = PrioticketExperienceAdapter(
        client_id="id",
        client_secret="secret",
        transport=httpx.MockTransport(handler),
    )
    result = adapter.search(_query("Milan"))
    assert isinstance(result, ExternalSearchFailure)
    assert result.code is SearchFailureCode.EMPTY


def test_fake_evening_preference_filters_milan() -> None:
    page = FakeExperienceSearchAdapter().search(_query(prefs=("evening",)))
    assert isinstance(page, ExperienceSearchPage)
    assert any(
        "evening" in item.title.lower() or "evening" in item.availability.lower()
        for item in page.offers
    )


def test_fake_preference_needles_and_unknown_city() -> None:
    adapter = FakeExperienceSearchAdapter()
    museum = adapter.search(_query("New York", prefs=("museum",)))
    assert isinstance(museum, ExperienceSearchPage)
    assert any("museum" in item.category.lower() for item in museum.offers)
    tour = adapter.search(_query("Edinburgh", prefs=("tour",)))
    assert isinstance(tour, ExperienceSearchPage)
    assert any("tour" in item.category.lower() for item in tour.offers)
    family = adapter.search(_query(prefs=("family-friendly",)))
    assert isinstance(family, ExperienceSearchPage)
    assert any("family" in item.title.lower() for item in family.offers)
    centre = adapter.search(_query("London", prefs=("city-centre",)))
    assert isinstance(centre, ExperienceSearchPage)
    unknown = adapter.search(_query("Barcelona", prefs=("city-centre",)))
    assert isinstance(unknown, ExperienceSearchPage)
    assert "barcelona" in unknown.offers[0].location.lower()
    empty = adapter.search(_query(""))
    assert isinstance(empty, ExternalSearchFailure)
    assert empty.code is SearchFailureCode.INVALID_QUERY


def test_iter_items_and_destination_match_shapes() -> None:
    products = {"data": {"products": [{"destination_id": "9", "destination_name": "Milan"}]}}
    assert list(iter_items(products))[0]["destination_id"] == "9"
    nested = {"data": {"product": {"product_id": "P1", "product_title": "Walk"}}}
    assert list(iter_items(nested))[0]["product_id"] == "P1"
    top = {"items": [{"destination_id": "2", "destination_slug": "london-uk"}]}
    assert match_destination_id(top, "London") == "2"
    assert match_destination_id({"data": {"items": []}}, "") == ""
    assert match_destination_id({"data": {"items": []}}, "Milan") == ""


def test_normalize_branch_coverage_for_duration_price_location() -> None:
    payload = {
        "data": {
            "items": [
                {
                    "product_external_id": 88,
                    "product_title": "Museum night opening",
                    "product_duration": "0",
                    "product_from_price": 12,
                    "product_currency": "gbp",
                    "product_destinations": ["Milan", "PRODUCT_SKIP"],
                    "product_content": {"product_duration_text": "hour"},
                },
                {
                    "product_id": "P-TOUR",
                    "product_title": "City walking tour",
                    "product_duration": "75",
                    "product_from_price": "not-a-price",
                    "product_images": "skip",
                },
                {
                    "product_id": "P-BOAT",
                    "product_title": "Canal boat",
                    "product_from_price": 18.5,
                    "product_availability": True,
                    "product_content": {
                        "product_images": [
                            {"image_url": "http://insecure.example/a.jpg"},
                            {"image_url": "https://cdn.example.invalid/ok.jpg"},
                        ]
                    },
                },
                {
                    "product_id": "P-SHOW",
                    "product_title": "Evening concert",
                    "product_content": {"product_supplier_name": "Milan Live"},
                },
                {
                    "product_id": "P-SUP",
                    "product_title": "Workshop",
                    "product_content": {"product_supplier_name": "Duomo Guides"},
                },
                {
                    "product_id": "P-PLAIN",
                    "product_title": "Attraction pass",
                },
                {
                    "product_id": "P-SKIP",
                    "product_title": "",
                },
            ]
        }
    }
    offers = normalize_offers(payload, _query(prefs=("evening",)), SearchProvenance.SANDBOX)
    assert len(offers) == 6
    by_id = {item.external_id: item for item in offers}
    assert by_id["88"].location == "Milan"
    assert by_id["88"].amount_minor == 1200
    assert by_id["88"].currency == "GBP"
    assert by_id["88"].duration_minutes is None
    assert by_id["P-TOUR"].duration_minutes == 75
    assert by_id["P-TOUR"].category == "Tour"
    assert by_id["P-BOAT"].category == "Cruise"
    assert by_id["P-BOAT"].photo_url is not None
    assert by_id["P-SHOW"].category == "Event"
    assert by_id["P-SUP"].category == "Duomo Guides"
    assert "evening" in by_id["P-PLAIN"].availability
    assert secret_in_text("nope", "short") is False


def test_normalize_availability_without_window_or_prefs() -> None:
    open_query = ExternalSearchQuery(
        domain="experience",
        destination=PlaceRef("city", "Milan"),
        start="2026-10-20",
        end="2026-10-30",
    )
    offers = normalize_offers(
        {
            "items": [
                {
                    "product_id": "P-OPEN",
                    "product_title": "Open ticket",
                    "product_availability": True,
                }
            ]
        },
        open_query,
        SearchProvenance.SANDBOX,
    )
    assert offers[0].availability == "available"
    unknown = normalize_offers(
        {"data": {"items": [{"product_id": "P-U", "product_title": "Unknown slot"}]}},
        open_query,
        SearchProvenance.SANDBOX,
    )
    assert unknown[0].availability == "availability unknown"
    assert unknown[0].cancellation is None
    skipped = normalize_offers(
        {"data": {"items": [{"product_id": "P-SKIP", "product_title": ""}]}},
        open_query,
        SearchProvenance.SANDBOX,
    )
    assert skipped == ()
    hour = normalize_offers(
        {
            "data": {
                "items": [
                    {
                        "product_id": "P-HOUR",
                        "product_title": "Guided walk",
                        "product_destinations": [{}],
                        "product_content": {
                            "product_duration_text": "2 hour",
                            "product_images": ["skip", {"image_url": "not-https"}],
                        },
                    }
                ]
            }
        },
        open_query,
        SearchProvenance.SANDBOX,
    )
    assert hour[0].duration_minutes == 120
    assert hour[0].location == ""
    assert hour[0].photo_url is None


def test_live_adapter_invalid_query_and_http_error() -> None:
    blank = PrioticketExperienceAdapter(client_id="id", client_secret="secret").search(_query(""))
    assert isinstance(blank, ExternalSearchFailure)
    assert blank.code is SearchFailureCode.INVALID_QUERY
    stay = PrioticketExperienceAdapter(client_id="id", client_secret="secret").search(
        ExternalSearchQuery(
            domain="stay",
            destination=PlaceRef("city", "Milan"),
            start="2026-10-20",
            end="2026-10-30",
        )
    )
    assert isinstance(stay, ExternalSearchFailure)
    assert stay.code is SearchFailureCode.INVALID_QUERY

    def boom(request: httpx.Request) -> httpx.Response:
        del request
        raise httpx.ConnectError("offline")

    adapter = PrioticketExperienceAdapter(
        client_id="id",
        client_secret="secret",
        transport=httpx.MockTransport(boom),
    )
    result = adapter.search(_query())
    assert isinstance(result, ExternalSearchFailure)
    assert result.code is SearchFailureCode.UNAVAILABLE


def test_token_and_destination_failure_branches() -> None:
    def token_not_json(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(200, content=b"not-json")

    token_bad = PrioticketExperienceAdapter(
        client_id="id",
        client_secret="secret",
        transport=httpx.MockTransport(token_not_json),
    ).search(_query())
    assert isinstance(token_bad, ExternalSearchFailure)
    assert token_bad.code is SearchFailureCode.INVALID_RESPONSE

    def empty_token(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(200, json={"access_token": "", "token_type": "Bearer"})

    empty = PrioticketExperienceAdapter(
        client_id="id",
        client_secret="secret",
        transport=httpx.MockTransport(empty_token),
    ).search(_query())
    assert isinstance(empty, ExternalSearchFailure)
    assert empty.code is SearchFailureCode.UNAUTHORIZED

    def list_body(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(200, json=["not-an-object"])

    listed = PrioticketExperienceAdapter(
        client_id="id",
        client_secret="secret",
        transport=httpx.MockTransport(list_body),
    ).search(_query())
    assert isinstance(listed, ExternalSearchFailure)
    assert listed.code is SearchFailureCode.INVALID_RESPONSE

    def timed_destinations(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/oauth2/token"):
            return httpx.Response(200, json={"access_token": "t"})
        return httpx.Response(408, json={"error": "timeout"})

    timed = PrioticketExperienceAdapter(
        client_id="id",
        client_secret="secret",
        transport=httpx.MockTransport(timed_destinations),
    ).search(_query())
    assert isinstance(timed, ExternalSearchFailure)
    assert timed.code is SearchFailureCode.TIMEOUT

    def dest_not_object(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/oauth2/token"):
            return httpx.Response(200, json={"access_token": "t"})
        return httpx.Response(200, json=["destinations"])

    dest_bad = PrioticketExperienceAdapter(
        client_id="id",
        client_secret="secret",
        transport=httpx.MockTransport(dest_not_object),
    ).search(_query())
    assert isinstance(dest_bad, ExternalSearchFailure)
    assert dest_bad.code is SearchFailureCode.INVALID_RESPONSE


def test_products_invalid_and_secret_echo_and_token_reuse() -> None:
    calls = {"token": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/oauth2/token"):
            calls["token"] += 1
            return httpx.Response(200, json={"access_token": "reuse-token", "token_type": "Bearer"})
        if request.url.path.endswith("/products/destinations"):
            return httpx.Response(
                200,
                json={"data": {"items": [{"destination_id": "1001", "destination_name": "Milan"}]}},
            )
        return httpx.Response(200, json={"data": {"items": [_product()]}})

    adapter = PrioticketExperienceAdapter(
        client_id="id",
        client_secret="secretvalue",
        transport=httpx.MockTransport(handler),
    )
    first = adapter.search(_query())
    second = adapter.search(_query(prefs=("museum",)))
    assert isinstance(first, ExperienceSearchPage)
    assert isinstance(second, ExperienceSearchPage)
    assert calls["token"] == 1
    assert adapter.last_product_params is not None
    assert adapter.last_product_params["product_content"] == "museum"

    def products_not_json(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/oauth2/token"):
            return httpx.Response(200, json={"access_token": "t"})
        if request.url.path.endswith("/products/destinations"):
            return httpx.Response(
                200,
                json={"data": {"items": [{"destination_id": "1001", "destination_name": "Milan"}]}},
            )
        return httpx.Response(200, content=b"not-json")

    products_bad = PrioticketExperienceAdapter(
        client_id="id",
        client_secret="secret",
        transport=httpx.MockTransport(products_not_json),
    ).search(_query())
    assert isinstance(products_bad, ExternalSearchFailure)
    assert products_bad.code is SearchFailureCode.INVALID_RESPONSE

    def products_list(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/oauth2/token"):
            return httpx.Response(200, json={"access_token": "t"})
        if request.url.path.endswith("/products/destinations"):
            return httpx.Response(
                200,
                json={"data": {"items": [{"destination_id": "1001", "destination_name": "Milan"}]}},
            )
        return httpx.Response(200, json=["products"])

    listed = PrioticketExperienceAdapter(
        client_id="id",
        client_secret="secret",
        transport=httpx.MockTransport(products_list),
    ).search(_query())
    assert isinstance(listed, ExternalSearchFailure)
    assert listed.code is SearchFailureCode.INVALID_RESPONSE

    def products_gateway(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/oauth2/token"):
            return httpx.Response(200, json={"access_token": "t"})
        if request.url.path.endswith("/products/destinations"):
            return httpx.Response(
                200,
                json={"data": {"items": [{"destination_id": "1001", "destination_name": "Milan"}]}},
            )
        return httpx.Response(504, json={"error": "gateway"})

    gateway = PrioticketExperienceAdapter(
        client_id="id",
        client_secret="secret",
        transport=httpx.MockTransport(products_gateway),
    ).search(_query())
    assert isinstance(gateway, ExternalSearchFailure)
    assert gateway.code is SearchFailureCode.TIMEOUT

    leaked = dict(_product())
    leaked["note"] = "secretvalue"

    def echo_secret(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/oauth2/token"):
            return httpx.Response(200, json={"access_token": "t"})
        if request.url.path.endswith("/products/destinations"):
            return httpx.Response(
                200,
                json={"data": {"items": [{"destination_id": "1001", "destination_name": "Milan"}]}},
            )
        return httpx.Response(200, json={"data": {"items": [leaked]}})

    secret_fail = PrioticketExperienceAdapter(
        client_id="id",
        client_secret="secretvalue",
        transport=httpx.MockTransport(echo_secret),
    ).search(_query())
    assert isinstance(secret_fail, ExternalSearchFailure)
    assert secret_fail.code is SearchFailureCode.INVALID_RESPONSE


def test_mode_helpers_and_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ITAA_EXPERIENCE_SEARCH_MODE", "unexpected")
    assert experience_search_mode() == "fake"
    monkeypatch.delenv("ITAA_PRIOTICKET_TIMEOUT_MS", raising=False)
    assert prioticket_timeout_ms() >= 3000
    monkeypatch.setenv("ITAA_PRIOTICKET_CLIENT_ID", " env-id ")
    assert prioticket_client_id() == "env-id"
    monkeypatch.setenv("ITAA_PRIOTICKET_CLIENT_ID", "from-env-id")
    monkeypatch.setenv("ITAA_PRIOTICKET_CLIENT_SECRET", "from-env-secret")
    adapter = PrioticketExperienceAdapter.from_env()
    assert adapter._client_id == "from-env-id"
