"""Parking Requirement snapshot. No competing lifecycle in WP-03."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from itaa_domain.errors import DomainInvariantError
from itaa_domain.identifiers import RequirementId
from itaa_domain.value_objects import (
    CURRENCY_PATTERN,
    AccessibilityNeed,
    AirportCode,
    CoveredPreference,
    TimeWindow,
    VehicleClass,
    Version,
    format_utc,
    require_shuttle_minutes,
    require_utc,
)


@dataclass(frozen=True, slots=True)
class Requirement:
    requirement_id: RequirementId
    revision: Version
    airport: AirportCode
    service_window: TimeWindow
    vehicle_class: VehicleClass
    covered: CoveredPreference
    shuttle_max_minutes: int
    currency: str
    accessibility: tuple[AccessibilityNeed, ...]
    created_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        created = require_utc(self.created_at, "created_at")
        updated = require_utc(self.updated_at, "updated_at")
        if updated < created:
            raise DomainInvariantError("updated_at", "must_not_precede_created_at")
        minutes = require_shuttle_minutes(self.shuttle_max_minutes, "shuttle_max_minutes")
        if not isinstance(self.vehicle_class, VehicleClass):
            raise DomainInvariantError("vehicle_class", "unsupported")
        if not isinstance(self.covered, CoveredPreference):
            raise DomainInvariantError("covered", "unsupported")
        if not isinstance(self.airport, AirportCode):
            raise DomainInvariantError("airport_code", "invalid_iata_code")
        if not isinstance(self.currency, str) or CURRENCY_PATTERN.fullmatch(self.currency) is None:
            raise DomainInvariantError("currency", "invalid_currency_code")
        needs = tuple(self.accessibility)
        if len(set(needs)) != len(needs):
            raise DomainInvariantError("accessibility", "duplicate_values")
        for need in needs:
            if not isinstance(need, AccessibilityNeed):
                raise DomainInvariantError("accessibility", "unsupported")
        object.__setattr__(self, "created_at", created)
        object.__setattr__(self, "updated_at", updated)
        object.__setattr__(self, "shuttle_max_minutes", minutes)
        object.__setattr__(self, "accessibility", needs)

    @classmethod
    def create(
        cls,
        *,
        requirement_id: RequirementId,
        airport: AirportCode,
        service_window: TimeWindow,
        vehicle_class: VehicleClass,
        covered: CoveredPreference,
        shuttle_max_minutes: int,
        currency: str,
        accessibility: tuple[AccessibilityNeed, ...] = (),
        created_at: datetime,
    ) -> Requirement:
        return cls(
            requirement_id=requirement_id,
            revision=Version.initial(),
            airport=airport,
            service_window=service_window,
            vehicle_class=vehicle_class,
            covered=covered,
            shuttle_max_minutes=shuttle_max_minutes,
            currency=currency,
            accessibility=accessibility,
            created_at=created_at,
            updated_at=created_at,
        )

    def to_primitive(self) -> dict[str, object]:
        return {
            "requirementId": self.requirement_id.to_primitive(),
            "revision": self.revision.to_primitive(),
            "airportCode": self.airport.to_primitive(),
            "serviceWindow": self.service_window.to_primitive(),
            "vehicleClass": self.vehicle_class.value,
            "covered": self.covered.value,
            "shuttleMaxMinutes": self.shuttle_max_minutes,
            "currency": self.currency,
            "accessibility": [item.value for item in self.accessibility],
            "createdAt": format_utc(self.created_at),
            "updatedAt": format_utc(self.updated_at),
        }
