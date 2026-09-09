"""Immutable ranking inputs. No contract, adapter, or I/O types."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from itaa_domain.errors import DomainInvariantError
from itaa_domain.identifiers import OfferId, SupplierToken
from itaa_domain.value_objects import (
    JS_SAFE_MAX,
    AddOn,
    CancellationTerm,
    CoveredPreference,
    EvidenceRef,
    EvidenceType,
    LotType,
    RefundTerm,
    SimulatedAvailability,
    Version,
    require_distance_metres,
    require_shuttle_minutes,
    require_utc,
)
from itaa_ranking.errors import RankingError
from itaa_ranking.profile import SCORE_SCALE


def _require_int(value: object, field: str) -> int:
    if type(value) is not int or isinstance(value, bool):
        raise RankingError(field, "must_be_integer")
    return value


@dataclass(frozen=True, slots=True)
class ReliabilityFact:
    supplier_token: SupplierToken
    score_micros: int
    evidence_ref: EvidenceRef
    registry_version: str
    observed_at: datetime | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.supplier_token, SupplierToken):
            raise RankingError("supplier_token", "invalid_opaque_syntax")
        score = _require_int(self.score_micros, "score_micros")
        if score < 0 or score > SCORE_SCALE:
            raise RankingError("score_micros", "out_of_range")
        if not isinstance(self.evidence_ref, EvidenceRef):
            raise RankingError("evidence_ref", "invalid")
        try:
            EvidenceRef(self.registry_version)
        except DomainInvariantError as exc:
            raise RankingError("registry_version", exc.code) from None
        if self.observed_at is not None:
            object.__setattr__(self, "observed_at", require_utc(self.observed_at, "observed_at"))


@dataclass(frozen=True, slots=True)
class RankingNeed:
    covered: CoveredPreference
    representable_add_ons: frozenset[AddOn]
    shuttle_max_minutes: int | None = None

    def __post_init__(self) -> None:
        if type(self.covered) is not CoveredPreference:
            raise RankingError("covered", "invalid_enum")
        add_ons = frozenset(self.representable_add_ons)
        for item in add_ons:
            if type(item) is not AddOn:
                raise RankingError("add_ons", "invalid_enum")
        object.__setattr__(self, "representable_add_ons", add_ons)
        if self.shuttle_max_minutes is not None:
            minutes = _require_int(self.shuttle_max_minutes, "shuttle_max_minutes")
            try:
                require_shuttle_minutes(minutes, "shuttle_max_minutes")
            except DomainInvariantError as exc:
                raise RankingError(exc.field, exc.code) from None
            object.__setattr__(self, "shuttle_max_minutes", minutes)


@dataclass(frozen=True, slots=True)
class RankingOffer:
    offer_id: OfferId
    supplier_token: SupplierToken
    version: Version
    total_minor: int
    currency: str
    shuttle_minutes: int
    distance_metres: int
    lot_type: LotType
    add_ons: frozenset[AddOn]
    cancellation: CancellationTerm
    refund: RefundTerm
    valid_from: datetime
    valid_until: datetime
    evidence_types: frozenset[EvidenceType]
    availability: SimulatedAvailability
    simulation: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.offer_id, OfferId):
            raise RankingError("offer_id", "invalid_opaque_syntax")
        if not isinstance(self.supplier_token, SupplierToken):
            raise RankingError("supplier_token", "invalid_opaque_syntax")
        if not isinstance(self.version, Version):
            raise RankingError("version", "invalid")
        total = _require_int(self.total_minor, "total_minor")
        if total < 0 or total > JS_SAFE_MAX:
            raise RankingError("total_minor", "out_of_range")
        if self.currency != "USD":
            raise RankingError("currency", "unsupported")
        if self.simulation is not True:
            raise RankingError("simulation", "must_be_true")
        if type(self.lot_type) is not LotType:
            raise RankingError("lot_type", "invalid_enum")
        if type(self.cancellation) is not CancellationTerm:
            raise RankingError("cancellation", "invalid_enum")
        if type(self.refund) is not RefundTerm:
            raise RankingError("refund", "invalid_enum")
        if type(self.availability) is not SimulatedAvailability:
            raise RankingError("availability", "invalid_enum")
        try:
            object.__setattr__(
                self, "shuttle_minutes", require_shuttle_minutes(self.shuttle_minutes)
            )
            object.__setattr__(
                self, "distance_metres", require_distance_metres(self.distance_metres)
            )
        except DomainInvariantError as exc:
            raise RankingError(exc.field, exc.code) from None
        add_ons = frozenset(self.add_ons)
        for add_on in add_ons:
            if type(add_on) is not AddOn:
                raise RankingError("add_ons", "invalid_enum")
        evidence = frozenset(self.evidence_types)
        for evidence_type in evidence:
            if type(evidence_type) is not EvidenceType:
                raise RankingError("evidence_types", "invalid_enum")
        object.__setattr__(self, "add_ons", add_ons)
        object.__setattr__(self, "evidence_types", evidence)
        object.__setattr__(self, "valid_from", require_utc(self.valid_from, "valid_from"))
        object.__setattr__(self, "valid_until", require_utc(self.valid_until, "valid_until"))
        if self.valid_until <= self.valid_from:
            raise RankingError("validity", "end_must_follow_start")
