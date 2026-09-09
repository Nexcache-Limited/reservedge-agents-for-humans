"""Denylist, redaction, and prompt-free telemetry records."""

from __future__ import annotations

import re
from collections.abc import Mapping

from itaa_google_adapter.ports import ExtractionRequest

REQUIREMENT_FIELDS: tuple[str, ...] = (
    "location.airportCode",
    "serviceWindow.start",
    "serviceWindow.end",
    "requirements.vehicleClass",
    "requirements.covered",
    "requirements.shuttleMaxMinutes",
    "constraints.currency",
    "constraints.accessibility",
)
CLOSED_PI_FIELDS: tuple[str, ...] = (
    "category",
    *REQUIREMENT_FIELDS,
    "disclosure.profile",
    "solicitation.responseDeadline",
    "createdAt",
    "expiresAt",
)

EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
CARD_RE = re.compile(r"\b(?:\d[ -]*?){13,19}\b")
INJECTION_RE = re.compile(
    r"ignore (?:all )?previous|dispatch now|skip a[12]\b|skip approval|"
    r"auto-?approve|confirm now|you are now|system prompt",
    re.IGNORECASE,
)
OVERDISCLOSURE_RE = re.compile(
    r"\b(?:cvv|cvc|pan|visa|mastercard|amex|itinerary|pnr|passenger|"
    r"flight\s+[a-z]{2}\d+|ssn|social security|card number)\b",
    re.IGNORECASE,
)

PRIVACY_DENYLIST: tuple[str, ...] = (
    "email",
    "prompt",
    "buyer identity",
    "payment",
    "itinerary",
    "authorization: bearer",
    "api_key",
    "apikey",
)


def contains_email(text: str) -> bool:
    return EMAIL_RE.search(text) is not None


def contains_payment(text: str) -> bool:
    if CARD_RE.search(text) is not None:
        return True
    return bool(re.search(r"\b(?:visa|mastercard|amex|cvv|card number)\b", text, re.I))


def contains_itinerary_dump(text: str) -> bool:
    return bool(re.search(r"\b(?:itinerary|pnr|passenger|flight\s+[a-z]{2}\d+)\b", text, re.I))


def is_prompt_injection(text: str) -> bool:
    return INJECTION_RE.search(text) is not None


def is_over_disclosure(text: str) -> bool:
    if contains_email(text) or contains_payment(text) or contains_itinerary_dump(text):
        return True
    return OVERDISCLOSURE_RE.search(text) is not None


def redact_secrets(text: str) -> str:
    redacted = EMAIL_RE.sub("[redacted-email]", text)
    return CARD_RE.sub("[redacted-payment]", redacted)


def scan_extraction_text(request: ExtractionRequest) -> tuple[str, ...]:
    reasons: list[str] = []
    if is_prompt_injection(request.text):
        reasons.append("prompt_injection")
    if is_over_disclosure(request.text):
        reasons.append("over_disclosure")
    return tuple(reasons)


def record_is_prompt_free(record: Mapping[str, object]) -> bool:
    blob = " ".join(str(value).lower() for value in record.values())
    if "ignore previous" in blob or "system prompt" in blob:
        return False
    keys = {str(key) for key in record}
    for needle in PRIVACY_DENYLIST:
        if needle not in blob or needle not in {"prompt", "api_key", "apikey"}:
            continue
        if needle == "prompt" and "prompt_template_version" in keys:
            continue
        return False
    if EMAIL_RE.search(blob) or CARD_RE.search(blob):
        return False
    return "prompt_text" not in record and "response_text" not in record
