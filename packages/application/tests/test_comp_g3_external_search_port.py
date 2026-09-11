from __future__ import annotations

from itaa_application.external_search_port import (
    ExperienceOffer,
    ExperienceSearchPage,
    ExternalSearchFailure,
    ExternalSearchPage,
    ExternalSearchQuery,
    PlaceRef,
    SearchFailureCode,
    SearchProvenance,
    StayOffer,
    public_experience_search_result,
    public_search_result,
)


def _query() -> ExternalSearchQuery:
    return ExternalSearchQuery(
        domain="stay",
        destination=PlaceRef("city", "Milan"),
        start="2026-10-20",
        end="2026-10-30",
        origin=PlaceRef("city", "Mumbai"),
        correlation_id="cr_01k2m3n4p5q6r7s8t9v0w1x2k2",
    )


def test_public_page_is_buyer_safe_and_not_a_booking() -> None:
    query = _query()
    page = ExternalSearchPage(
        provider_id="liteapi",
        source=SearchProvenance.SANDBOX,
        fetched_at="2026-09-09T00:00:00Z",
        query=query,
        offers=(
            StayOffer(
                provider_id="liteapi",
                source=SearchProvenance.SANDBOX,
                external_id="lp-milan-1",
                name="Hotel Spadari al Duomo",
                locality="Milan, Italy",
                check_in="2026-10-20",
                check_out="2026-10-30",
                currency="EUR",
                amount_minor=24_000,
                cancellation="Free cancellation",
                availability="available",
            ),
        ),
    )
    public = public_search_result(page)
    assert public["status"] == "ok"
    assert public["label"] == "Sandbox hotel search"
    assert public["bookingAuthority"] == "none"
    assert "booked" not in str(public).lower()
    assert "reserved" not in str(public).lower()
    assert "confirmed" not in str(public).lower()
    offer = public["offers"][0]  # type: ignore[index]
    assert isinstance(offer, dict)
    assert offer["name"] == "Hotel Spadari al Duomo"
    assert "photoUrl" not in offer
    assert "rateRef" not in offer
    assert "roomTypes" not in offer
    assert "retailRate" not in str(public)


def test_public_offer_includes_https_photo_only() -> None:
    query = _query()
    offer = StayOffer(
        provider_id="liteapi",
        source=SearchProvenance.SANDBOX,
        external_id="lp-milan-1",
        name="Hotel Spadari al Duomo",
        locality="Milan, Italy",
        check_in="2026-10-20",
        check_out="2026-10-30",
        currency="EUR",
        amount_minor=24_000,
        cancellation="Free cancellation",
        availability="available",
        photo_url="https://cdn.example.invalid/spadari.jpg",
        rate_ref="secret-offer-token",
    )
    page = ExternalSearchPage(
        provider_id="liteapi",
        source=SearchProvenance.SANDBOX,
        fetched_at="2026-09-09T00:00:00Z",
        query=query,
        offers=(offer,),
    )
    public = public_search_result(page)
    item = public["offers"][0]  # type: ignore[index]
    assert isinstance(item, dict)
    assert item["photoUrl"] == "https://cdn.example.invalid/spadari.jpg"
    assert item["rateRef"] == "secret-offer-token"


def test_failure_codes_stay_visible_without_parking_fixtures() -> None:
    query = _query()
    for code in SearchFailureCode:
        failure = ExternalSearchFailure(
            code=code,
            provider_id="liteapi",
            source=SearchProvenance.SANDBOX,
            query=query,
        )
        public = public_search_result(failure)
        assert public["status"] == code.value
        assert public["offers"] == []
        blob = str(public).lower()
        assert "skyshield" not in blob
        assert "parkdirect" not in blob
        assert "jfk" not in blob


def test_public_experience_page_is_domain_native() -> None:
    query = ExternalSearchQuery(
        domain="experience",
        destination=PlaceRef("city", "London"),
        start="",
        end="",
        preferences=("evening",),
    )
    page = ExperienceSearchPage(
        provider_id="prioticket",
        source=SearchProvenance.SANDBOX,
        fetched_at="2026-09-10T00:00:00Z",
        query=query,
        offers=(
            ExperienceOffer(
                provider_id="prioticket",
                source=SearchProvenance.SANDBOX,
                external_id="pt-1",
                title="West End evening theatre",
                category="Event",
                location="London, United Kingdom",
                availability="available",
                currency="GBP",
                amount_minor=8900,
                duration_minutes=150,
                cancellation="Cancellation allowed",
            ),
        ),
    )
    public = public_experience_search_result(page)
    assert public["status"] == "ok"
    assert public["label"] == "Sandbox experience search"
    offer = public["offers"][0]  # type: ignore[index]
    assert isinstance(offer, dict)
    assert offer["title"] == "West End evening theatre"
    assert "checkIn" not in offer
    assert "name" not in offer
    assert "product_content" not in str(public)
    assert public["bookingAuthority"] == "none"
