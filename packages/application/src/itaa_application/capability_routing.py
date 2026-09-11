"""Closed task capabilities and provider-neutral routing.

The buyer conversation produces a validated task plan. Capabilities are derived
from Explicit tasks plus required search fields. Provider adapters fulfil a
capability; they do not choose the task plan. Adapter names belong at
composition, not in this module.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum

from itaa_application.external_search_port import ExperienceSearchPort, ExternalSearchPort

SearchAdapter = ExternalSearchPort | ExperienceSearchPort


class Capability(StrEnum):
    STAY_SEARCH = "stay.search"
    EXPERIENCE_SEARCH = "experience.search"
    RENTAL_SEARCH = "rental.search"
    PARKING_SEARCH = "parking.search"


CLOSED_CAPABILITIES: frozenset[Capability] = frozenset(Capability)


@dataclass(frozen=True, slots=True)
class TaskSnapshot:
    kind: str
    provenance: str
    accepted: bool = False


@dataclass(frozen=True, slots=True)
class FactSnapshot:
    destination: str = ""
    origin_city: str = ""
    parking_airport: str = ""
    start_date: str = ""
    end_date: str = ""


REQUIRED_FIELDS: Mapping[Capability, tuple[str, ...]] = {
    Capability.STAY_SEARCH: ("destination", "start_date", "end_date"),
    Capability.EXPERIENCE_SEARCH: ("destination",),
    Capability.RENTAL_SEARCH: ("destination", "start_date", "end_date"),
    Capability.PARKING_SEARCH: ("parking_airport", "start_date", "end_date"),
}


def _explicit(tasks: Sequence[TaskSnapshot], kind: str) -> bool:
    return any(item.kind == kind and item.provenance == "explicit" for item in tasks)


def _filled(facts: FactSnapshot, field: str) -> bool:
    return str(getattr(facts, field, "") or "").strip() != ""


def fields_ready(capability: Capability, facts: FactSnapshot) -> bool:
    return all(_filled(facts, field) for field in REQUIRED_FIELDS[capability])


def established_capabilities(
    tasks: Sequence[TaskSnapshot],
    facts: FactSnapshot,
) -> tuple[Capability, ...]:
    """Return search capabilities that are Explicit and field-complete.

    Destination plus dates alone never activate stay.search or experience.search.
    Travel alone never activates experience.search.
    """

    out: list[Capability] = []
    if _explicit(tasks, "hotel") and fields_ready(Capability.STAY_SEARCH, facts):
        out.append(Capability.STAY_SEARCH)
    if _explicit(tasks, "experience") and fields_ready(Capability.EXPERIENCE_SEARCH, facts):
        out.append(Capability.EXPERIENCE_SEARCH)
    if _explicit(tasks, "rental") and fields_ready(Capability.RENTAL_SEARCH, facts):
        out.append(Capability.RENTAL_SEARCH)
    if _explicit(tasks, "parking") and fields_ready(Capability.PARKING_SEARCH, facts):
        out.append(Capability.PARKING_SEARCH)
    return tuple(out)


def snapshots_from_projection(
    projection: Mapping[str, object],
) -> tuple[tuple[TaskSnapshot, ...], FactSnapshot]:
    raw_tasks = projection.get("tasks")
    tasks: list[TaskSnapshot] = []
    if isinstance(raw_tasks, list):
        for item in raw_tasks:
            if not isinstance(item, dict):
                continue
            kind = str(item.get("kind") or "")
            provenance = str(item.get("provenance") or "")
            if not kind:
                continue
            tasks.append(
                TaskSnapshot(
                    kind=kind,
                    provenance=provenance,
                    accepted=item.get("accepted") is True,
                )
            )
    raw_facts = projection.get("facts")
    facts_in = raw_facts if isinstance(raw_facts, dict) else {}
    facts = FactSnapshot(
        destination=str(facts_in.get("destination") or "").strip(),
        origin_city=str(facts_in.get("originCity") or "").strip(),
        parking_airport=str(facts_in.get("parkingAirport") or "").strip(),
        start_date=str(facts_in.get("startDate") or "").strip(),
        end_date=str(facts_in.get("endDate") or "").strip(),
    )
    return tuple(tasks), facts


class CapabilityRouter:
    """Maps a closed capability onto zero or more configured search adapters."""

    def __init__(
        self,
        registry: Mapping[Capability, Sequence[SearchAdapter]] | None = None,
    ) -> None:
        self._registry: dict[Capability, tuple[SearchAdapter, ...]] = {
            capability: tuple(registry.get(capability, ()) if registry else ())
            for capability in Capability
        }

    def adapters_for(self, capability: Capability) -> tuple[SearchAdapter, ...]:
        return self._registry.get(capability, ())

    def has_adapter(self, capability: Capability) -> bool:
        return len(self.adapters_for(capability)) > 0
