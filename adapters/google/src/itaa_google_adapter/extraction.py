"""Validate extraction proposals. Requirement fields only. Never confirm."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from itaa_application.errors import ApplicationError
from itaa_domain.errors import DomainInvariantError
from itaa_domain.value_objects import TimeWindow, parse_utc
from itaa_google_adapter.ports import (
    EvidenceSpan,
    ExtractionRequest,
    ExtractionResponse,
    FieldAttribution,
    FieldOrigin,
)
from itaa_google_adapter.privacy import REQUIREMENT_FIELDS, scan_extraction_text

REQUIRED_BUYER_FIELDS: tuple[str, ...] = (
    "location.airportCode",
    "serviceWindow.start",
    "serviceWindow.end",
    "requirements.vehicleClass",
    "requirements.covered",
    "requirements.shuttleMaxMinutes",
    "constraints.currency",
)

ALLOWED_PROPOSAL_KEYS: frozenset[str] = frozenset(
    {
        "category",
        "location",
        "serviceWindow",
        "requirements",
        "constraints",
    }
)
FORBIDDEN_PROPOSAL_KEYS: frozenset[str] = frozenset(
    {
        "intentId",
        "buyerToken",
        "disclosure",
        "solicitation",
        "createdAt",
        "expiresAt",
        "schemaVersion",
        "approvedPayloadHash",
    }
)
ALLOWED_LOCATION_KEYS: frozenset[str] = frozenset({"airportCode"})
ALLOWED_WINDOW_KEYS: frozenset[str] = frozenset({"start", "end"})
ALLOWED_REQUIREMENT_KEYS: frozenset[str] = frozenset(
    {"vehicleClass", "covered", "shuttleMaxMinutes"}
)
ALLOWED_CONSTRAINT_KEYS: frozenset[str] = frozenset({"currency", "accessibility"})
ALLOWED_VEHICLE: frozenset[str] = frozenset({"standard", "compact", "suv", "oversized"})
ALLOWED_COVERED: frozenset[str] = frozenset({"none", "preferred", "required"})
ALLOWED_ACCESS: frozenset[str] = frozenset({"step_free", "wheelchair", "ev_charging"})
ALLOWED_ORIGINS: frozenset[str] = frozenset(
    {"extracted", "user_confirmed", "deterministic_default"}
)
REJECTION_UNKNOWN_SHAPE = "unknown_shape"
REJECTION_ATTRIBUTION = "attribution_mismatch"
REJECTION_MISSING = "missing_required"
REJECTION_PRIVACY = "privacy_blocked"
REJECTION_INVALID_PREFIX = "invalid:"
CLOSED_REJECTION_CODES: frozenset[str] = frozenset(
    {
        REJECTION_UNKNOWN_SHAPE,
        REJECTION_ATTRIBUTION,
        REJECTION_MISSING,
        REJECTION_PRIVACY,
        "invalid:location.airportCode",
        "invalid:serviceWindow.start",
        "invalid:serviceWindow.end",
        "invalid:requirements.vehicleClass",
        "invalid:requirements.covered",
        "invalid:requirements.shuttleMaxMinutes",
        "invalid:constraints.currency",
        "invalid:constraints.accessibility",
        "invalid:evidence",
        "invalid:confidence",
    }
)


def _confidence(fields: Mapping[str, float]) -> dict[str, float]:
    cleaned: dict[str, float] = {}
    for key, value in fields.items():
        if key not in REQUIREMENT_FIELDS:
            continue
        if 0.0 <= float(value) <= 1.0:
            cleaned[key] = float(value)
    return cleaned


def closed_rejection_code(code: str | None) -> str | None:
    """Return a field-path diagnostic. Never include rejected values."""

    if code is None:
        return None
    if code not in CLOSED_REJECTION_CODES:
        return REJECTION_UNKNOWN_SHAPE
    return code


def _closed(
    request: ExtractionRequest,
    *,
    missing: tuple[str, ...] = (),
    ambiguous: tuple[str, ...] = (),
    evidence: tuple[EvidenceSpan, ...] = (),
    confidence: Mapping[str, float] | None = None,
    fallback: str | None = "manual_structured_input",
    attributions: tuple[FieldAttribution, ...] = (),
    rejection_code: str | None = None,
) -> ExtractionResponse:
    del request
    return ExtractionResponse(
        proposal=None,
        field_confidence=_confidence(confidence or {}),
        missing_fields=missing,
        ambiguous_fields=ambiguous,
        evidence_spans=evidence,
        requires_a1=True,
        accepted=False,
        fallback=fallback,
        field_attributions=attributions,
        rejection_code=closed_rejection_code(rejection_code),
    )


def _present_fields(proposal: Mapping[str, object]) -> tuple[str, ...]:
    found: list[str] = []
    location = proposal.get("location")
    if isinstance(location, Mapping) and "airportCode" in location:
        found.append("location.airportCode")
    window = proposal.get("serviceWindow")
    if isinstance(window, Mapping):
        if "start" in window:
            found.append("serviceWindow.start")
        if "end" in window:
            found.append("serviceWindow.end")
    requirements = proposal.get("requirements")
    if isinstance(requirements, Mapping):
        if "vehicleClass" in requirements:
            found.append("requirements.vehicleClass")
        if "covered" in requirements:
            found.append("requirements.covered")
        if "shuttleMaxMinutes" in requirements:
            found.append("requirements.shuttleMaxMinutes")
    constraints = proposal.get("constraints")
    if isinstance(constraints, Mapping):
        if "currency" in constraints:
            found.append("constraints.currency")
        if "accessibility" in constraints:
            found.append("constraints.accessibility")
    return tuple(found)


def _nested_unknown(mapping: object, allowed: frozenset[str]) -> bool:
    if mapping is None:
        return False
    if not isinstance(mapping, Mapping):
        return True
    return any(str(key) not in allowed for key in mapping)


def _has_forbidden_or_unknown(candidate: Mapping[str, object]) -> bool:
    keys = {str(key) for key in candidate}
    if keys & FORBIDDEN_PROPOSAL_KEYS:
        return True
    if any(key not in ALLOWED_PROPOSAL_KEYS for key in keys):
        return True
    if _nested_unknown(candidate.get("location"), ALLOWED_LOCATION_KEYS):
        return True
    if _nested_unknown(candidate.get("serviceWindow"), ALLOWED_WINDOW_KEYS):
        return True
    if _nested_unknown(candidate.get("requirements"), ALLOWED_REQUIREMENT_KEYS):
        return True
    return _nested_unknown(candidate.get("constraints"), ALLOWED_CONSTRAINT_KEYS)


def invalid_requirement_field(proposal: Mapping[str, object]) -> str | None:
    """Return a dotted field path when a closed vocabulary check fails.

    Never includes the rejected value.
    """

    location = proposal.get("location")
    if isinstance(location, Mapping):
        airport = location.get("airportCode")
        if not isinstance(airport, str) or len(airport) != 3 or not airport.isalpha():
            return "location.airportCode"
        if airport != airport.upper():
            return "location.airportCode"
    requirements = proposal.get("requirements")
    if isinstance(requirements, Mapping):
        vehicle = requirements.get("vehicleClass")
        if vehicle is not None and vehicle not in ALLOWED_VEHICLE:
            return "requirements.vehicleClass"
        covered = requirements.get("covered")
        if covered is not None and covered not in ALLOWED_COVERED:
            return "requirements.covered"
        shuttle = requirements.get("shuttleMaxMinutes")
        if shuttle is not None and (
            not isinstance(shuttle, int)
            or isinstance(shuttle, bool)
            or shuttle < 0
            or shuttle > 180
        ):
            return "requirements.shuttleMaxMinutes"
    constraints = proposal.get("constraints")
    if isinstance(constraints, Mapping):
        currency = constraints.get("currency")
        currency_ok = (
            isinstance(currency, str) and len(currency) == 3 and currency == currency.upper()
        )
        if currency is not None and not currency_ok:
            return "constraints.currency"
        access = constraints.get("accessibility")
        if access is not None:
            if not isinstance(access, list):
                return "constraints.accessibility"
            if any(item not in ALLOWED_ACCESS for item in access):
                return "constraints.accessibility"
    return None


def _valid_requirement_values(proposal: Mapping[str, object]) -> bool:
    return invalid_requirement_field(proposal) is None


def _attribution_from_mapping(item: Mapping[str, object]) -> FieldAttribution | None:
    field = item.get("field")
    origin = item.get("origin")
    confidence = item.get("confidence")
    if not isinstance(field, str) or origin not in ALLOWED_ORIGINS:
        return None
    if not isinstance(confidence, int | float) or isinstance(confidence, bool):
        return None
    if not 0.0 <= float(confidence) <= 1.0:
        return None
    no_evidence = bool(item.get("noEvidence") or item.get("no_evidence"))
    start = item.get("start")
    end = item.get("end")
    evidence = item.get("evidence")
    if isinstance(evidence, Mapping):
        start = evidence.get("start")
        end = evidence.get("end")
    if no_evidence:
        return FieldAttribution(
            field=field,
            origin=origin,  # type: ignore[arg-type]
            confidence=float(confidence),
            no_evidence=True,
        )
    if isinstance(start, int) and isinstance(end, int) and end >= start >= 0:
        return FieldAttribution(
            field=field,
            origin=origin,  # type: ignore[arg-type]
            confidence=float(confidence),
            evidence_start=start,
            evidence_end=end,
            no_evidence=False,
        )
    return FieldAttribution(
        field=field,
        origin=origin,  # type: ignore[arg-type]
        confidence=float(confidence),
        no_evidence=True,
    )


def parse_attributions(value: object) -> tuple[FieldAttribution, ...]:
    if value is None:
        return ()
    if not isinstance(value, list | tuple):
        return ()
    built: list[FieldAttribution] = []
    for item in value:
        if not isinstance(item, Mapping):
            continue
        parsed = _attribution_from_mapping(item)
        if parsed is not None:
            built.append(parsed)
    return tuple(built)


def _complete_attributions(
    fields: tuple[str, ...],
    *,
    evidence: tuple[EvidenceSpan, ...],
    confidence: Mapping[str, float],
    supplied: tuple[FieldAttribution, ...],
) -> tuple[FieldAttribution, ...] | None:
    by_field = {item.field: item for item in supplied}
    evidence_by_field = {item.field: item for item in evidence}
    completed: list[FieldAttribution] = []
    for field in fields:
        existing = by_field.get(field)
        if existing is not None:
            if existing.no_evidence or (
                existing.evidence_start is not None and existing.evidence_end is not None
            ):
                completed.append(existing)
                continue
            return None
        span = evidence_by_field.get(field)
        origin: FieldOrigin = "extracted"
        completed.append(
            FieldAttribution(
                field=field,
                origin=origin,
                confidence=float(confidence.get(field, 0.0)),
                evidence_start=span.start if span is not None else None,
                evidence_end=span.end if span is not None else None,
                no_evidence=span is None,
            )
        )
    return tuple(completed)


def validate_proposal(
    candidate: Mapping[str, object] | None,
    *,
    request: ExtractionRequest,
    missing: tuple[str, ...] = (),
    ambiguous: tuple[str, ...] = (),
    evidence: tuple[EvidenceSpan, ...] = (),
    confidence: Mapping[str, float] | None = None,
    fallback: str | None = None,
    attributions: tuple[FieldAttribution, ...] = (),
) -> ExtractionResponse:
    if request.category != "airport_parking":
        raise ApplicationError("category", "must_be_airport_parking")
    privacy_hits = scan_extraction_text(request)
    if privacy_hits:
        return _closed(
            request,
            missing=REQUIRED_BUYER_FIELDS if "over_disclosure" in privacy_hits else (),
            ambiguous=("text",) if "prompt_injection" in privacy_hits else (),
            fallback="manual_structured_input",
            rejection_code=REJECTION_PRIVACY,
        )
    if candidate is None:
        if missing:
            filled_missing = missing
            code = REJECTION_MISSING
        elif ambiguous:
            filled_missing = ()
            first = ambiguous[0]
            candidate_code = f"{REJECTION_INVALID_PREFIX}{first}"
            code = (
                candidate_code
                if candidate_code in CLOSED_REJECTION_CODES
                else REJECTION_UNKNOWN_SHAPE
            )
        else:
            filled_missing = REQUIRED_BUYER_FIELDS
            code = REJECTION_MISSING
        return _closed(
            request,
            missing=filled_missing,
            ambiguous=ambiguous,
            evidence=evidence,
            confidence=confidence,
            fallback=fallback,
            rejection_code=code,
        )
    if _has_forbidden_or_unknown(candidate):
        return _closed(
            request,
            missing=REQUIRED_BUYER_FIELDS,
            ambiguous=("payload",),
            rejection_code=REJECTION_UNKNOWN_SHAPE,
        )
    invalid_field = invalid_requirement_field(candidate)
    if invalid_field is not None:
        return _closed(
            request,
            missing=missing,
            ambiguous=ambiguous or (invalid_field,),
            confidence=confidence,
            rejection_code=f"{REJECTION_INVALID_PREFIX}{invalid_field}",
        )
    present = _present_fields(candidate)
    still_missing = tuple(field for field in REQUIRED_BUYER_FIELDS if field not in present)
    if still_missing:
        return _closed(
            request,
            missing=still_missing,
            ambiguous=ambiguous,
            evidence=evidence,
            confidence=confidence,
            fallback="manual_structured_input",
            rejection_code=REJECTION_MISSING,
        )
    window = candidate.get("serviceWindow")
    if not isinstance(window, Mapping):
        return _closed(
            request,
            missing=(),
            ambiguous=("serviceWindow.start", "serviceWindow.end"),
            confidence=confidence,
            rejection_code="invalid:serviceWindow.start",
        )
    try:
        start = parse_utc(str(window["start"]), "serviceWindow.start")
        end = parse_utc(str(window["end"]), "serviceWindow.end")
        TimeWindow(start, end)
    except (DomainInvariantError, KeyError, TypeError):
        return _closed(
            request,
            missing=(),
            ambiguous=("serviceWindow.start", "serviceWindow.end"),
            confidence=confidence,
            rejection_code="invalid:serviceWindow.start",
        )
    cleaned_confidence = _confidence(confidence or {field: 1.0 for field in present})
    completed = _complete_attributions(
        present,
        evidence=evidence,
        confidence=cleaned_confidence,
        supplied=attributions,
    )
    if completed is None:
        return _closed(
            request,
            missing=REQUIRED_BUYER_FIELDS,
            ambiguous=("payload",),
            confidence=cleaned_confidence,
            rejection_code=REJECTION_ATTRIBUTION,
        )
    proposal = {str(key): value for key, value in candidate.items() if key in ALLOWED_PROPOSAL_KEYS}
    return ExtractionResponse(
        proposal=proposal,
        field_confidence=cleaned_confidence,
        missing_fields=(),
        ambiguous_fields=(),
        evidence_spans=evidence,
        requires_a1=True,
        accepted=False,
        fallback=None,
        field_attributions=completed,
        rejection_code=None,
    )


def proposal_from_extracted_fields(fields: Mapping[str, Any]) -> dict[str, object]:
    """Build a requirement-only proposal. Never copies the JFK fixture."""

    proposal: dict[str, object] = {}
    if "category" in fields:
        proposal["category"] = fields["category"]
    if "airportCode" in fields:
        proposal["location"] = {"airportCode": fields["airportCode"]}
    window: dict[str, object] = {}
    if "start" in fields:
        window["start"] = fields["start"]
    if "end" in fields:
        window["end"] = fields["end"]
    if window:
        proposal["serviceWindow"] = window
    requirements: dict[str, object] = {}
    if "vehicleClass" in fields:
        requirements["vehicleClass"] = fields["vehicleClass"]
    if "covered" in fields:
        requirements["covered"] = fields["covered"]
    if "shuttleMaxMinutes" in fields:
        requirements["shuttleMaxMinutes"] = fields["shuttleMaxMinutes"]
    if requirements:
        proposal["requirements"] = requirements
    constraints: dict[str, object] = {}
    if "currency" in fields:
        constraints["currency"] = fields["currency"]
    if "accessibility" in fields:
        constraints["accessibility"] = list(fields["accessibility"])
    if constraints:
        proposal["constraints"] = constraints
    return proposal


def manual_fallback(*, missing: tuple[str, ...] | None = None) -> ExtractionResponse:
    return ExtractionResponse(
        proposal=None,
        field_confidence={},
        missing_fields=missing or REQUIRED_BUYER_FIELDS,
        ambiguous_fields=(),
        evidence_spans=(),
        requires_a1=True,
        accepted=False,
        fallback="manual_structured_input",
        field_attributions=(),
        rejection_code=REJECTION_MISSING,
    )


def attribution_to_http(item: FieldAttribution) -> dict[str, object]:
    payload: dict[str, object] = {
        "field": item.field,
        "origin": item.origin,
        "confidence": item.confidence,
    }
    if item.no_evidence or item.evidence_start is None or item.evidence_end is None:
        payload["noEvidence"] = True
    else:
        payload["evidence"] = {"start": item.evidence_start, "end": item.evidence_end}
    return payload
