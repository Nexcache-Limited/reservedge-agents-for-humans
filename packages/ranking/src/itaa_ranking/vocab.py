"""Closed ranking vocabulary. No open explanation strings."""

from __future__ import annotations

from enum import StrEnum


class ScoreComponent(StrEnum):
    PRICE_VALUE = "price_value"
    RELIABILITY_TRUST = "reliability_trust"
    CANCELLATION_FLEXIBILITY = "cancellation_flexibility"
    SHUTTLE_CONVENIENCE = "shuttle_convenience"
    DISTANCE_VALUE = "distance_value"
    COVERAGE_FIT = "coverage_fit"
    ADD_ON_FIT = "add_on_fit"


class ExclusionField(StrEnum):
    SIMULATION = "simulation"
    AVAILABILITY = "availability"
    VALID_FROM = "valid_from"
    VALID_UNTIL = "valid_until"
    COVERAGE = "coverage"
    SHUTTLE_MINUTES = "shuttle_minutes"


class ExclusionCode(StrEnum):
    MUST_BE_TRUE = "must_be_true"
    UNAVAILABLE = "unavailable"
    NOT_YET_VALID = "not_yet_valid"
    EXPIRED = "expired"
    REQUIRED = "required"
    EXCEEDS_MAXIMUM = "exceeds_maximum"


class GapCode(StrEnum):
    NO_ELIGIBLE_OFFERS = "no_eligible_offers"
    RELIABILITY_TRUST = "reliability_trust"


class PenaltyKind(StrEnum):
    MISSING_COMPONENT = "missing_component"


class DownsideDimension(StrEnum):
    TOTAL_MINOR = "total_minor"
    SHUTTLE_MINUTES = "shuttle_minutes"
    DISTANCE_METRES = "distance_metres"
    COVERAGE_FIT = "coverage_fit"
    ADD_ON_FIT = "add_on_fit"
    CANCELLATION = "cancellation"


class DownsideUnit(StrEnum):
    MINOR_CURRENCY = "minor_currency"
    MINUTES = "minutes"
    METRES = "metres"
    SCORE_MICROS = "score_micros"


class FitLabel(StrEnum):
    STRONG = "STRONG"
    GOOD = "GOOD"
    FAIR = "FAIR"


class RecencyStatus(StrEnum):
    OBSERVED = "OBSERVED"
    UNAVAILABLE = "UNAVAILABLE"


class ProfileReason(StrEnum):
    LOCKED_MVP_DEFAULT = "locked_mvp_default"
    TEST_PROFILE = "test_profile"
