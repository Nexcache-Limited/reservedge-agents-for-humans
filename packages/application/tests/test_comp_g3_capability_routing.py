from __future__ import annotations

from itaa_application.capability_routing import (
    Capability,
    CapabilityRouter,
    FactSnapshot,
    TaskSnapshot,
    established_capabilities,
    snapshots_from_projection,
)
from itaa_application.external_search_port import (
    ExternalSearchFailure,
    ExternalSearchQuery,
    PlaceRef,
    SearchFailureCode,
    SearchProvenance,
)


class _UnavailableStay:
    def search(self, query: ExternalSearchQuery) -> ExternalSearchFailure:
        return ExternalSearchFailure(
            code=SearchFailureCode.UNAVAILABLE,
            provider_id="adapter-a",
            source=SearchProvenance.SANDBOX,
            query=query,
        )


def test_destination_and_dates_do_not_activate_stay_search() -> None:
    tasks = (TaskSnapshot(kind="hotel", provenance="proposed"),)
    facts = FactSnapshot(destination="Milan", start_date="2026-10-20", end_date="2026-10-30")
    assert established_capabilities(tasks, facts) == ()


def test_explicit_stay_with_fields_activates_only_stay_search() -> None:
    tasks = (
        TaskSnapshot(kind="hotel", provenance="explicit", accepted=True),
        TaskSnapshot(kind="flight", provenance="proposed"),
    )
    facts = FactSnapshot(
        destination="Milan",
        origin_city="Mumbai",
        start_date="2026-10-20",
        end_date="2026-10-30",
    )
    assert established_capabilities(tasks, facts) == (Capability.STAY_SEARCH,)


def test_explicit_rental_and_parking_are_independent() -> None:
    tasks = (
        TaskSnapshot(kind="hotel", provenance="explicit", accepted=True),
        TaskSnapshot(kind="rental", provenance="explicit", accepted=True),
        TaskSnapshot(kind="parking", provenance="explicit", accepted=True),
    )
    facts = FactSnapshot(
        destination="Edinburgh",
        parking_airport="EDI",
        start_date="2026-10-14",
        end_date="2026-10-19",
    )
    assert established_capabilities(tasks, facts) == (
        Capability.STAY_SEARCH,
        Capability.RENTAL_SEARCH,
        Capability.PARKING_SEARCH,
    )


def test_parking_without_airport_does_not_activate() -> None:
    tasks = (TaskSnapshot(kind="parking", provenance="explicit", accepted=True),)
    facts = FactSnapshot(destination="Mumbai", start_date="2026-10-20", end_date="2026-10-30")
    assert established_capabilities(tasks, facts) == ()


def test_router_supports_multiple_adapters_per_capability() -> None:
    first = _UnavailableStay()
    second = _UnavailableStay()
    router = CapabilityRouter({Capability.STAY_SEARCH: (first, second)})
    adapters = router.adapters_for(Capability.STAY_SEARCH)
    assert adapters == (first, second)
    assert router.has_adapter(Capability.STAY_SEARCH) is True
    assert router.has_adapter(Capability.RENTAL_SEARCH) is False
    assert router.adapters_for(Capability.PARKING_SEARCH) == ()


def test_projection_snapshot_ignores_inferred_hotel() -> None:
    tasks, facts = snapshots_from_projection(
        {
            "facts": {
                "destination": "Milan",
                "originCity": "Mumbai",
                "startDate": "2026-10-20",
                "endDate": "2026-10-30",
            },
            "tasks": [
                {"kind": "hotel", "provenance": "inferred", "accepted": True},
            ],
        }
    )
    assert facts.destination == "Milan"
    assert established_capabilities(tasks, facts) == ()


def test_projection_skips_malformed_tasks() -> None:
    tasks, facts = snapshots_from_projection(
        {
            "tasks": ["x", {"kind": ""}, {"kind": "hotel", "provenance": "explicit"}],
            "facts": None,
        }
    )
    assert facts.destination == ""
    assert tasks == (TaskSnapshot(kind="hotel", provenance="explicit"),)


def test_explicit_experience_with_destination_activates_experience_search() -> None:
    tasks = (TaskSnapshot(kind="experience", provenance="explicit", accepted=True),)
    facts = FactSnapshot(destination="Milan", start_date="2026-10-20", end_date="2026-10-30")
    assert established_capabilities(tasks, facts) == (Capability.EXPERIENCE_SEARCH,)


def test_travel_alone_does_not_activate_experience_search() -> None:
    tasks = (TaskSnapshot(kind="hotel", provenance="proposed"),)
    facts = FactSnapshot(destination="London", start_date="2026-10-20", end_date="2026-10-30")
    assert Capability.EXPERIENCE_SEARCH not in established_capabilities(tasks, facts)


def test_stay_and_experience_can_activate_together() -> None:
    tasks = (
        TaskSnapshot(kind="hotel", provenance="explicit", accepted=True),
        TaskSnapshot(kind="experience", provenance="explicit", accepted=True),
    )
    facts = FactSnapshot(destination="Edinburgh", start_date="2026-10-14", end_date="2026-10-19")
    assert established_capabilities(tasks, facts) == (
        Capability.STAY_SEARCH,
        Capability.EXPERIENCE_SEARCH,
    )


def test_router_supports_zero_or_many_experience_adapters() -> None:
    router = CapabilityRouter()
    assert router.has_adapter(Capability.EXPERIENCE_SEARCH) is False
    first = _UnavailableStay()
    router = CapabilityRouter({Capability.EXPERIENCE_SEARCH: (first, first)})
    assert len(router.adapters_for(Capability.EXPERIENCE_SEARCH)) == 2


def test_query_shape_stays_provider_neutral() -> None:
    query = ExternalSearchQuery(
        domain="stay",
        destination=PlaceRef("city", "Edinburgh"),
        start="2026-10-14",
        end="2026-10-19",
    )
    assert query.domain == "stay"
    assert "liteapi" not in str(query)
    assert "duffel" not in str(query)
    experience = ExternalSearchQuery(
        domain="experience",
        destination=PlaceRef("city", "London"),
        start="",
        end="",
        preferences=("evening",),
    )
    assert experience.domain == "experience"
    assert "prioticket" not in str(experience)
