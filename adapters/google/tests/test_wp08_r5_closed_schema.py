"""WP-08-R5 closed schema and privacy-safe rejection diagnostics."""

from __future__ import annotations

import json
from dataclasses import asdict

import pytest
from pydantic import ValidationError
from wp08_helpers import CORRELATION, JFK_TEXT

from itaa_google_adapter.extraction import (
    CLOSED_REJECTION_CODES,
    invalid_requirement_field,
    validate_proposal,
)
from itaa_google_adapter.live import ExtractOutput
from itaa_google_adapter.ports import ExtractionRequest

_REQUEST = ExtractionRequest(text=JFK_TEXT, category="airport_parking", correlation_id=CORRELATION)


def _valid_proposal(**overrides: object) -> dict[str, object]:
    proposal: dict[str, object] = {
        "category": "airport_parking",
        "location": {"airportCode": "JFK"},
        "serviceWindow": {
            "start": "2026-09-03T13:00:00Z",
            "end": "2026-09-08T22:00:00Z",
        },
        "requirements": {
            "vehicleClass": "standard",
            "covered": "preferred",
            "shuttleMaxMinutes": 20,
        },
        "constraints": {"currency": "USD"},
    }
    proposal.update(overrides)
    return proposal


def test_extract_output_accepts_every_permitted_enum() -> None:
    for vehicle in ("standard", "compact", "suv", "oversized"):
        parsed = ExtractOutput(vehicleClass=vehicle, airportCode="JFK", currency="USD")
        assert parsed.vehicleClass == vehicle
    for covered in ("none", "preferred", "required"):
        assert ExtractOutput(covered=covered).covered == covered
    parsed = ExtractOutput(accessibility=["step_free", "wheelchair", "ev_charging"])
    assert parsed.accessibility == ["step_free", "wheelchair", "ev_charging"]


def test_extract_output_rejects_synonyms_and_free_text() -> None:
    with pytest.raises(ValidationError):
        ExtractOutput(vehicleClass="sedan")
    with pytest.raises(ValidationError):
        ExtractOutput(vehicleClass="Standard")
    with pytest.raises(ValidationError):
        ExtractOutput(covered="covered")
    with pytest.raises(ValidationError):
        ExtractOutput(covered="uncovered")
    with pytest.raises(ValidationError):
        ExtractOutput(accessibility=["EV charging"])
    with pytest.raises(ValidationError):
        ExtractOutput(accessibility=["ada"])


def test_extract_output_rejects_lowercase_airport_and_currency() -> None:
    with pytest.raises(ValidationError):
        ExtractOutput(airportCode="jfk")
    with pytest.raises(ValidationError):
        ExtractOutput(currency="usd")


def test_extract_output_rejects_impossible_timestamps_and_shuttle() -> None:
    with pytest.raises(ValidationError):
        ExtractOutput(start="2026-02-30T13:00:00Z")
    with pytest.raises(ValidationError):
        ExtractOutput(end="2026-09-08T25:00:00Z")
    with pytest.raises(ValidationError):
        ExtractOutput(start="2026-09-03T13:00:00")
    with pytest.raises(ValidationError):
        ExtractOutput(shuttleMaxMinutes=-1)
    with pytest.raises(ValidationError):
        ExtractOutput(shuttleMaxMinutes=181)
    with pytest.raises(ValidationError):
        ExtractOutput(shuttleMaxMinutes=20.5)  # type: ignore[arg-type]


def test_extract_output_rejects_unknown_evidence_and_confidence() -> None:
    with pytest.raises(ValidationError):
        ExtractOutput.model_validate({"evidence": [{"field": "intentId", "start": 0, "end": 1}]})
    with pytest.raises(ValidationError):
        ExtractOutput.model_validate({"confidence": {"secret": 0.9}})
    with pytest.raises(ValidationError):
        ExtractOutput.model_validate({"confidence": {"location.airportCode": 1.5}})
    with pytest.raises(ValidationError):
        ExtractOutput.model_validate({"missing": ["payload"]})


def test_extract_output_forbids_extra_model_fields() -> None:
    with pytest.raises(ValidationError):
        ExtractOutput.model_validate({"airportCode": "JFK", "intentId": "pi_01"})


def test_domain_validator_reports_field_paths_without_values() -> None:
    sedan = _valid_proposal(
        requirements={"vehicleClass": "sedan", "covered": "preferred", "shuttleMaxMinutes": 20}
    )
    assert invalid_requirement_field(sedan) == "requirements.vehicleClass"
    result = validate_proposal(sedan, request=_REQUEST)
    assert result.proposal is None
    assert result.ambiguous_fields == ("requirements.vehicleClass",)
    assert result.rejection_code == "invalid:requirements.vehicleClass"
    assert result.rejection_code in CLOSED_REJECTION_CODES
    blob = json.dumps(asdict(result), default=str)
    assert "sedan" not in blob
    assert "payload" not in result.ambiguous_fields

    lower = _valid_proposal(location={"airportCode": "jfk"})
    assert invalid_requirement_field(lower) == "location.airportCode"
    lowered = validate_proposal(lower, request=_REQUEST)
    assert lowered.rejection_code == "invalid:location.airportCode"
    assert "jfk" not in json.dumps(asdict(lowered), default=str)

    extra = _valid_proposal()
    extra["secretItinerary"] = "blocked"
    unknown = validate_proposal(extra, request=_REQUEST)
    assert unknown.rejection_code == "unknown_shape"
    assert "secretItinerary" not in json.dumps(asdict(unknown), default=str)
    assert "blocked" not in json.dumps(asdict(unknown), default=str)


def test_missing_required_buyer_fields_are_diagnosed() -> None:
    result = validate_proposal(
        {"location": {"airportCode": "JFK"}},
        request=_REQUEST,
    )
    assert result.proposal is None
    assert result.rejection_code == "missing_required"
    assert "serviceWindow.start" in result.missing_fields


def test_ambiguous_only_none_candidate_is_not_missing_required() -> None:
    result = validate_proposal(
        None,
        request=_REQUEST,
        missing=(),
        ambiguous=("serviceWindow.start", "serviceWindow.end"),
    )
    assert result.proposal is None
    assert result.missing_fields == ()
    assert result.ambiguous_fields == ("serviceWindow.start", "serviceWindow.end")
    assert result.rejection_code == "invalid:serviceWindow.start"
    assert "jfk" not in json.dumps(asdict(result), default=str)
