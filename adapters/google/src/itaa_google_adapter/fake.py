"""Deterministic local model. No network and no provider SDK."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from itaa_application.errors import ApplicationError
from itaa_domain.errors import DomainInvariantError
from itaa_domain.value_objects import parse_utc
from itaa_google_adapter import DEFAULT_MODEL_NAME
from itaa_google_adapter.extraction import proposal_from_extracted_fields
from itaa_google_adapter.ports import (
    CancelToken,
    ModelRequest,
    ModelResponse,
    MonotonicClock,
    QuotaExceeded,
)
from itaa_google_adapter.privacy import is_over_disclosure, is_prompt_injection
from itaa_google_adapter.resilience import FakeMonotonicClock

ISO_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")
LOOSE_ISO_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z?")
AIRPORT_RE = re.compile(r"\b([A-Z]{3})\b")
VEHICLE_RE = re.compile(r"\b(standard|compact|suv|oversized)\b", re.IGNORECASE)
COVERED_RE = re.compile(r"\b(preferred|prefer|required|uncovered|none)\b", re.IGNORECASE)
SHUTTLE_RE = re.compile(r"shuttle.{0,40}?(\d+)\s*minutes", re.IGNORECASE)
CURRENCY_RE = re.compile(r"\b([A-Z]{3})\b")
ACCESS_EXPLICIT_RE = re.compile(r"\b(step_free|wheelchair)\b", re.IGNORECASE)
EV_NEED_RE = re.compile(
    r"\bev[_\s-]?charging\b|\belectric vehicle\b|\belectric car\b|\belectric\b|\bev\b",
    re.IGNORECASE,
)
NATURAL_DATE_RE = re.compile(
    r"\b(january|february|march|april|may|june|july|august|september|"
    r"october|november|december|jan|feb|mar|apr|jun|jul|aug|sept?|oct|nov|dec)"
    r"\.?\s+(\d{1,2})(?:st|nd|rd|th)?(?:,?\s+(\d{4}))?"
    r"(?:\s+at\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?)?",
    re.IGNORECASE,
)
_MONTHS = {
    "january": "01",
    "jan": "01",
    "february": "02",
    "feb": "02",
    "march": "03",
    "mar": "03",
    "april": "04",
    "apr": "04",
    "may": "05",
    "june": "06",
    "jun": "06",
    "july": "07",
    "jul": "07",
    "august": "08",
    "aug": "08",
    "september": "09",
    "sept": "09",
    "sep": "09",
    "october": "10",
    "oct": "10",
    "november": "11",
    "nov": "11",
    "december": "12",
    "dec": "12",
}


class FakeModel:
    def __init__(
        self,
        *,
        clock: MonotonicClock | None = None,
        delay_ms: int = 0,
        quota: bool = False,
        malformed: bool = False,
        unknown_fields: bool = False,
        contradict_winner: bool = False,
        hallucinate_scores: bool = False,
        bypass_approvals: bool = False,
    ) -> None:
        self._clock = clock or FakeMonotonicClock()
        self._delay_ms = delay_ms
        self._quota = quota
        self._malformed = malformed
        self._unknown_fields = unknown_fields
        self._contradict_winner = contradict_winner
        self._hallucinate_scores = hallucinate_scores
        self._bypass_approvals = bypass_approvals
        self.complete_calls = 0
        self.dispatch_attempts = 0

    def complete(
        self,
        request: ModelRequest,
        *,
        cancel: CancelToken | None = None,
        deadline_ms: int | None = None,
    ) -> ModelResponse:
        self.complete_calls += 1
        del deadline_ms
        if cancel is not None:
            cancel.check()
        if self._delay_ms:
            self._clock.sleep_ms(self._delay_ms, cancel)
        if cancel is not None:
            cancel.check()
        if self._quota:
            raise QuotaExceeded()
        if request.task == "extract":
            return ModelResponse(
                mapping=self._extract_mapping(request.payload),
                model_name="fake-deterministic",
                input_tokens=12,
                output_tokens=24,
            )
        if request.task == "explain":
            return ModelResponse(
                mapping=self._explain_mapping(request.payload),
                model_name="fake-deterministic",
                input_tokens=8,
                output_tokens=16,
            )
        raise ApplicationError("task", "unknown")

    def _extract_mapping(self, payload: Mapping[str, object]) -> dict[str, object]:
        text = str(payload.get("text", ""))
        if self._malformed:
            return {"proposal": "not-an-object"}
        if is_prompt_injection(text):
            return {
                "status": "rejected_injection",
                "proposal": None,
                "missing": [],
                "ambiguous": ["text"],
            }
        if is_over_disclosure(text):
            return {"status": "rejected_disclosure", "proposal": None}
        if self._bypass_approvals:
            self.dispatch_attempts += 1
        parsed = _parse_parking_text(text)
        if parsed.get("impossible"):
            return {
                "proposal": None,
                "missing": [],
                "ambiguous": ["serviceWindow.start", "serviceWindow.end"],
            }
        if parsed.get("conflict"):
            return {
                "proposal": None,
                "missing": [],
                "ambiguous": ["serviceWindow.start", "serviceWindow.end"],
            }
        missing = tuple(parsed.get("missing", ()))
        if missing:
            return {"proposal": None, "missing": list(missing), "ambiguous": []}
        fields = parsed["fields"]
        if not isinstance(fields, dict):
            return {"proposal": None, "missing": ["location.airportCode"]}
        fields = dict(fields)
        fields.setdefault("category", "airport_parking")
        proposal = proposal_from_extracted_fields(fields)
        if self._unknown_fields:
            proposal = dict(proposal)
            proposal["secretItinerary"] = "blocked"
        if self._bypass_approvals:
            proposal = dict(proposal)
            return {
                "proposal": proposal,
                "requires_a1": False,
                "accepted": True,
                "dispatch_now": True,
            }
        evidence, attributions, confidence = _evidence_and_attributions(text, fields)
        return {
            "proposal": proposal,
            "confidence": confidence,
            "evidence": evidence,
            "attributions": attributions,
        }

    def _explain_mapping(self, payload: Mapping[str, object]) -> dict[str, object]:
        winner = str(payload.get("winnerDisplayName", ""))
        if self._contradict_winner:
            return {"explanation": "ParkDirect is recommended because it is cheaper."}
        if self._hallucinate_scores:
            return {
                "explanation": f"{winner} wins with score 999999 and downside 1.",
            }
        return {
            "explanation": (
                f"{winner} is the recommended simulated airport-parking option. "
                "The ranking scores, offer totals, and downside remain those already "
                "shown on the buyer snapshot."
            )
        }


def _parse_parking_text(text: str) -> dict[str, Any]:
    missing: list[str] = []
    loose = LOOSE_ISO_RE.findall(text)
    stamps = ISO_RE.findall(text)
    if any(item not in stamps for item in loose) or _has_impossible(loose):
        return {"impossible": True}
    if len(stamps) >= 4:
        return {"conflict": True}
    if len(stamps) == 1:
        return {"missing": ["serviceWindow.end"]}
    start = stamps[0] if len(stamps) >= 2 else None
    end = stamps[1] if len(stamps) >= 2 else None
    if start is None or end is None:
        natural = _natural_window(text)
        if natural is not None:
            start = start or natural[0]
            end = end or natural[1]
    if start is not None and end is not None:
        try:
            if parse_utc(end, "end") <= parse_utc(start, "start"):
                return {"conflict": True}
        except DomainInvariantError:
            return {"impossible": True}
    airport = _airport(text)
    vehicle = _first(VEHICLE_RE, text)
    covered_raw = _first(COVERED_RE, text)
    shuttle_match = SHUTTLE_RE.search(text)
    currency = "USD"
    if airport is None:
        missing.append("location.airportCode")
    if start is None:
        missing.append("serviceWindow.start")
    if end is None:
        missing.append("serviceWindow.end")
    if vehicle is None:
        missing.append("requirements.vehicleClass")
    if covered_raw is None:
        missing.append("requirements.covered")
    if shuttle_match is None:
        missing.append("requirements.shuttleMaxMinutes")
    if currency is None:
        missing.append("constraints.currency")
    if missing:
        return {"missing": missing, "fields": {}}
    covered = "none" if covered_raw == "uncovered" else (covered_raw or "preferred")
    if covered == "prefer":
        covered = "preferred"
    if covered not in {"none", "preferred", "required"}:
        covered = "preferred"
    accessibility = _accessibility_from_text(text)
    fields: dict[str, Any] = {
        "airportCode": airport,
        "start": start,
        "end": end,
        "vehicleClass": (vehicle or "standard").lower(),
        "covered": covered.lower(),
        "shuttleMaxMinutes": int(shuttle_match.group(1)) if shuttle_match else 20,
        "currency": currency,
    }
    if accessibility:
        fields["accessibility"] = accessibility
    return {"fields": fields}


def _natural_window(text: str) -> tuple[str, str] | None:
    hits = list(NATURAL_DATE_RE.finditer(text))
    if len(hits) < 2:
        return None
    return _natural_instant(hits[0], "start"), _natural_instant(hits[1], "end")


def _natural_instant(match: re.Match[str], role: str) -> str:
    month = _MONTHS.get(match.group(1).lower().rstrip("."), "01")
    day = str(match.group(2)).zfill(2)
    year = match.group(3) or "2026"
    hour = 13 if role == "start" else 22
    minute = 0
    if match.group(4) is not None:
        hour = int(match.group(4))
        minute = int(match.group(5) or "0")
        meridiem = (match.group(6) or "").lower()
        if meridiem == "pm" and hour < 12:
            hour += 12
        if meridiem == "am" and hour == 12:
            hour = 0
    return f"{year}-{month}-{day}T{hour:02d}:{minute:02d}:00Z"


def _accessibility_from_text(text: str) -> list[str]:
    found: list[str] = []
    for item in ACCESS_EXPLICIT_RE.findall(text):
        token = item.lower()
        if token not in found:
            found.append(token)
    if EV_NEED_RE.search(text) and "ev_charging" not in found:
        found.append("ev_charging")
    return found


def _airport(text: str) -> str | None:
    if re.search(r"\bJFK\b", text):
        return "JFK"
    match = AIRPORT_RE.search(text)
    if match is None:
        return None
    code = match.group(1)
    if code in {"USD", "THE", "FOR", "AND", "MAX"}:
        return None
    return code


def _first(pattern: re.Pattern[str], text: str) -> str | None:
    match = pattern.search(text)
    return match.group(1) if match is not None else None


def _has_impossible(stamps: list[str]) -> bool:
    for stamp in stamps:
        candidate = stamp if stamp.endswith("Z") else stamp + "Z"
        try:
            parse_utc(candidate, "timestamp")
        except DomainInvariantError:
            return True
        hour = int(stamp[11:13]) if len(stamp) >= 13 else 0
        if hour > 23:
            return True
    return False


def _span(field: str, needles: tuple[str, ...], text: str) -> dict[str, object] | None:
    lowered = text.lower()
    for needle in needles:
        idx = lowered.find(needle.lower())
        if idx >= 0:
            return {"field": field, "start": idx, "end": idx + len(needle)}
    return None


def _evidence_and_attributions(
    text: str,
    fields: Mapping[str, Any],
) -> tuple[list[dict[str, object]], list[dict[str, object]], dict[str, float]]:
    lookups: dict[str, tuple[str, ...]] = {
        "location.airportCode": (str(fields.get("airportCode") or ""),),
        "serviceWindow.start": (str(fields.get("start") or ""),),
        "serviceWindow.end": (str(fields.get("end") or ""),),
        "requirements.vehicleClass": (str(fields.get("vehicleClass") or ""),),
        "requirements.covered": (str(fields.get("covered") or ""), "covered"),
        "requirements.shuttleMaxMinutes": (
            f"{fields.get('shuttleMaxMinutes')} minutes",
            str(fields.get("shuttleMaxMinutes") or ""),
        ),
        "constraints.currency": (str(fields.get("currency") or ""),),
        "constraints.accessibility": tuple(
            str(item) for item in list(fields.get("accessibility") or [])
        ),
    }
    evidence: list[dict[str, object]] = []
    attributions: list[dict[str, object]] = []
    confidence: dict[str, float] = {}
    scores = {
        "location.airportCode": 0.99,
        "serviceWindow.start": 0.98,
        "serviceWindow.end": 0.98,
        "requirements.vehicleClass": 0.95,
        "requirements.covered": 0.9,
        "requirements.shuttleMaxMinutes": 0.9,
        "constraints.currency": 0.99,
        "constraints.accessibility": 0.9,
    }
    present = [
        key for key in scores if key != "constraints.accessibility" or fields.get("accessibility")
    ]
    for field in present:
        needles = lookups[field]
        span = _span(field, needles, text) if any(needles) else None
        score = scores[field]
        confidence[field] = score
        if span is not None:
            evidence.append(span)
            attributions.append(
                {
                    "field": field,
                    "origin": "extracted",
                    "confidence": score,
                    "evidence": {"start": span["start"], "end": span["end"]},
                }
            )
        else:
            attributions.append(
                {
                    "field": field,
                    "origin": "extracted",
                    "confidence": score,
                    "noEvidence": True,
                }
            )
    return evidence, attributions, confidence


def default_model_name() -> str:
    return DEFAULT_MODEL_NAME
