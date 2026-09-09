from __future__ import annotations

from datetime import UTC, datetime

import pytest
from helpers import CREATED_AT, make_requirement

from itaa_domain.errors import DomainInvariantError
from itaa_domain.identifiers import RequirementId
from itaa_domain.requirement import Requirement
from itaa_domain.value_objects import (
    AccessibilityNeed,
    AirportCode,
    CoveredPreference,
    TimeWindow,
    VehicleClass,
)

UTC = UTC


def test_requirement_factory_accepts_golden_path() -> None:
    requirement = make_requirement()
    snapshot = requirement.to_primitive()
    assert snapshot["airportCode"] == "JFK"
    assert snapshot["vehicleClass"] == "standard"
    assert snapshot["accessibility"] == ["ev_charging"]
    assert "email" not in snapshot
    assert "itinerary" not in snapshot
    assert "prompt" not in snapshot


def test_requirement_rejects_duplicate_accessibility() -> None:
    with pytest.raises(DomainInvariantError) as exc:
        Requirement.create(
            requirement_id=RequirementId("rq_01k2m3n4p5q6r7s8t9v0w1x2z1"),
            airport=AirportCode("JFK"),
            service_window=TimeWindow(
                datetime(2026, 9, 3, 13, 0, tzinfo=UTC),
                datetime(2026, 9, 8, 22, 0, tzinfo=UTC),
            ),
            vehicle_class=VehicleClass.STANDARD,
            covered=CoveredPreference.PREFERRED,
            shuttle_max_minutes=20,
            currency="USD",
            accessibility=(AccessibilityNeed.EV_CHARGING, AccessibilityNeed.EV_CHARGING),
            created_at=CREATED_AT,
        )
    assert exc.value.field == "accessibility"


@pytest.mark.parametrize("minutes", [-1, 181])
def test_requirement_rejects_shuttle_range(minutes: int) -> None:
    with pytest.raises(DomainInvariantError):
        Requirement.create(
            requirement_id=RequirementId("rq_01k2m3n4p5q6r7s8t9v0w1x2z1"),
            airport=AirportCode("JFK"),
            service_window=TimeWindow(
                datetime(2026, 9, 3, 13, 0, tzinfo=UTC),
                datetime(2026, 9, 8, 22, 0, tzinfo=UTC),
            ),
            vehicle_class=VehicleClass.STANDARD,
            covered=CoveredPreference.PREFERRED,
            shuttle_max_minutes=minutes,
            currency="USD",
            created_at=CREATED_AT,
        )


def test_requirement_rejects_lowercase_currency() -> None:
    with pytest.raises(DomainInvariantError) as exc:
        Requirement(
            requirement_id=RequirementId("rq_01k2m3n4p5q6r7s8t9v0w1x2z1"),
            revision=make_requirement().revision,
            airport=AirportCode("JFK"),
            service_window=TimeWindow(
                datetime(2026, 9, 3, 13, 0, tzinfo=UTC),
                datetime(2026, 9, 8, 22, 0, tzinfo=UTC),
            ),
            vehicle_class=VehicleClass.STANDARD,
            covered=CoveredPreference.PREFERRED,
            shuttle_max_minutes=20,
            currency="usd",
            accessibility=(),
            created_at=CREATED_AT,
            updated_at=CREATED_AT,
        )
    assert exc.value.field == "currency"
