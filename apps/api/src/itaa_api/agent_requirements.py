"""Closed domain catalogs and trusted parking requirement state.

Model output never becomes booking state. System proposals never become Explicit.
Trip departure, trip destination, and parking airport are distinct.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from copy import deepcopy
from datetime import UTC, date, datetime
from typing import Any, Literal

from itaa_application.errors import ApplicationError

FieldSource = Literal["current_turn", "earlier_turn", "direct_edit", "system_proposal"]
FieldProvenance = Literal["explicit", "inferred", "proposed"]
DomainKind = Literal["parking", "rental", "ents", "flight", "hotel"]
Completeness = Literal[
    "incomplete",
    "ready",
    "awaiting_grant",
    "soliciting",
    "offers",
    "stale",
    "accepted",
    "authorized",
]
Gate = Literal["A1", "A2", "A3", "A4"]

VEHICLE = frozenset({"standard", "compact", "suv", "oversized"})
COVERED = frozenset({"none", "preferred", "required"})
ACCESS = frozenset({"step_free", "wheelchair", "ev_charging"})
KNOWN_IATA = frozenset(
    {"JFK", "LGA", "EWR", "EDI", "MAN", "LHR", "LGW", "STN", "AMS", "CDG", "DUB", "GLA"}
)
NAMED_AIRPORTS: dict[str, str] = {
    "heathrow": "LHR",
    "london heathrow": "LHR",
    "gatwick": "LGW",
    "london gatwick": "LGW",
    "stansted": "STN",
    "london stansted": "STN",
    "manchester airport": "MAN",
    "edinburgh airport": "EDI",
    "kennedy": "JFK",
    "jfk airport": "JFK",
    "la guardia": "LGA",
    "laguardia": "LGA",
    "newark": "EWR",
    "newark liberty": "EWR",
    "schiphol": "AMS",
    "charles de gaulle": "CDG",
    "dublin airport": "DUB",
    "glasgow airport": "GLA",
}
MATERIAL_PARKING = frozenset(
    {"airportCode", "start", "end", "vehicleClass", "covered", "shuttleMaxMinutes", "currency"}
)
OFFER_CLAIM_RE = re.compile(
    r"\b(offers? (are|is) (ready|ranked|selected|refreshed)|ranked offers?|"
    r"selected offer|refreshed offers?)\b",
    re.I,
)
AFFIRM_RE = re.compile(
    r"^(yes|yeah|yep|ok|okay|please|confirm|go ahead|request offers|"
    r"authorize|accept)([.!]?)$",
    re.I,
)
IATA_RE = re.compile(r"\b([A-Za-z]{3})\b")
PARKING_AT_RE = re.compile(
    r"\b(?:parking\s+(?:at|in|for)|park(?:ing)?\s+at)\s+([A-Za-z]{3})\b",
    re.I,
)
PARKING_PLACE_RE = re.compile(
    r"\bparking\s+(?:in|at|near)\s+([A-Za-z]{3}|[A-Za-z][A-Za-z .'-]{0,40}?)"
    r"(?=\s+from\b|\s+on\b|\s+to\b|\s*$|[.,;!?]|\s+\d)",
    re.I,
)
PARKING_FROM_DAYS_RE = re.compile(
    r"parking.{0,96}?(?:from|in|on)\s+(\d{1,2})(?:st|nd|rd|th)?"
    r"(?!\s*(?:am|pm))"
    r"\s+to\s+(\d{1,2})(?:st|nd|rd|th)?"
    r"(?!\s*(?:am|pm))"
    r"(?:\s+(january|february|march|april|may|june|july|august|september|october|"
    r"november|december|jan|feb|mar|apr|jun|jul|aug|sept?|oct|nov|dec))?",
    re.I | re.S,
)
IATA_PARKING_RE = re.compile(r"\b([A-Za-z]{3})\s+parking\b", re.I)
PLACE_CITIES: dict[str, str] = {
    "manchester": "MAN",
}
_MONTH_WORDS: tuple[tuple[str, str], ...] = (
    ("january", "01"),
    ("february", "02"),
    ("march", "03"),
    ("april", "04"),
    ("may", "05"),
    ("june", "06"),
    ("july", "07"),
    ("august", "08"),
    ("september", "09"),
    ("october", "10"),
    ("november", "11"),
    ("december", "12"),
    ("sept", "09"),
    ("jan", "01"),
    ("feb", "02"),
    ("mar", "03"),
    ("apr", "04"),
    ("jun", "06"),
    ("jul", "07"),
    ("aug", "08"),
    ("sep", "09"),
    ("oct", "10"),
    ("nov", "11"),
    ("dec", "12"),
)
_CALENDAR_RE = re.compile(
    r"\b(\d{1,2})(?:st|nd|rd|th)?\s*(?:to|[–-]|until|through)\s*"
    r"(?:the\s+)?(\d{1,2})(?:st|nd|rd|th)?\s+"
    r"(january|february|march|april|may|june|july|august|september|october|"
    r"november|december|jan|feb|mar|apr|jun|jul|aug|sept?|oct|nov|dec)"
    r"(?:\s+(\d{4}))?\b",
    re.I,
)
SUV_RE = re.compile(r"\b(suv|compact|standard|oversized)\b", re.I)
COVERED_RE = re.compile(r"\b(covered|uncovered|open[- ]air)\b", re.I)
COVERED_DECLINE_RE = re.compile(
    r"(?:"
    r"(?:\b(?:don(?:['’]?t)|do\s+not|doesn(?:['’]?t)|didn(?:['’]?t)|won(?:['’]?t)|"
    r"wouldn(?:['’]?t)|needn(?:['’]?t)|no|not|never|without)\b"
    r"(?:\s+\w+){0,4}\s+covered)"
    r"|"
    r"(?:\bcovered(?:\s+parking)?\s+(?:is\s+)?(?:not|un)?"
    r"(?:\s+needed|\s+required|\s+wanted|\s+necessary|\s+a\s+preference|\s+preferred))"
    r"|"
    r"(?:\bno\s+covered\b)"
    r"|"
    r"(?:\buncovered\b|\bopen[-\s]?air\b)"
    r")",
    re.I,
)
SHUTTLE_RE = re.compile(r"shuttle[^\d]{0,24}(\d{1,2})", re.I)
CLOCK_RE = re.compile(
    r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b|\b(\d{1,2}):(\d{2})\b",
    re.I,
)
ORDINAL_RE = re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)\b", re.I)
CHANGE_START_RE = re.compile(
    r"change\s+parking\s+start.*?to\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)",
    re.I,
)
CHANGE_FINISH_RE = re.compile(
    r"(?:finish|end|until)\s+(?:at\s+)?(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)",
    re.I,
)

PARKING_FIELDS: tuple[dict[str, object], ...] = (
    {
        "id": "airportCode",
        "type": "iata",
        "requiredForExecution": True,
        "requiredFromBuyer": True,
        "defaultable": False,
        "askWhenMissing": True,
        "ask": "Which airport do you need parking at?",
        "material": True,
    },
    {
        "id": "start",
        "type": "instant",
        "requiredForExecution": True,
        "requiredFromBuyer": True,
        "defaultable": False,
        "askWhenMissing": True,
        "ask": "When should parking start?",
        "material": True,
    },
    {
        "id": "end",
        "type": "instant",
        "requiredForExecution": True,
        "requiredFromBuyer": True,
        "defaultable": False,
        "askWhenMissing": True,
        "ask": "When should parking finish?",
        "material": True,
    },
    {
        "id": "vehicleClass",
        "type": "enum",
        "enum": sorted(VEHICLE),
        "requiredForExecution": True,
        "requiredFromBuyer": False,
        "defaultable": True,
        "askWhenMissing": False,
        "default": "standard",
        "ask": "What vehicle class should I use for the rental car?",
        "material": True,
    },
    {
        "id": "covered",
        "type": "enum",
        "enum": sorted(COVERED),
        "requiredForExecution": True,
        "requiredFromBuyer": True,
        "defaultable": False,
        "askWhenMissing": True,
        "ask": "Do you want covered parking, or is uncovered fine?",
        "material": True,
    },
    {
        "id": "shuttleMaxMinutes",
        "type": "int",
        "requiredForExecution": True,
        "requiredFromBuyer": False,
        "defaultable": True,
        "askWhenMissing": False,
        "default": 20,
        "material": True,
    },
    {
        "id": "currency",
        "type": "currency",
        "requiredForExecution": True,
        "requiredFromBuyer": False,
        "defaultable": True,
        "askWhenMissing": False,
        "default": "USD",
        "material": True,
    },
    {
        "id": "accessibility",
        "type": "access_list",
        "requiredForExecution": True,
        "requiredFromBuyer": False,
        "defaultable": True,
        "askWhenMissing": False,
        "default": [],
        "material": False,
    },
)

RENTAL_FIELDS: tuple[dict[str, object], ...] = (
    {
        "id": "when",
        "type": "text",
        "requiredForExecution": False,
        "requiredFromBuyer": False,
        "defaultable": False,
        "askWhenMissing": False,
        "material": False,
    },
    {
        "id": "class",
        "type": "text",
        "requiredForExecution": False,
        "requiredFromBuyer": False,
        "defaultable": False,
        "askWhenMissing": False,
        "material": False,
    },
    {
        "id": "driver",
        "type": "text",
        "requiredForExecution": False,
        "requiredFromBuyer": False,
        "defaultable": False,
        "askWhenMissing": False,
        "material": False,
    },
)

COMPETITION_PARKING_ONLY_COPY = (
    "This competition demo only simulates airport parking booking. "
    "Rental car and other tasks are demonstration-only and are not booked here. "
    "Send a parking requirement (airport, dates, and times) to test the live simulated path."
)

SUPPORT_LABELS: dict[str, str] = {
    "parking": "live_simulated",
    "rental": "demonstration",
    "ents": "demonstration",
    "flight": "unsupported",
    "hotel": "unsupported",
}


def capabilities_catalog() -> dict[str, object]:
    return {
        "support": dict(SUPPORT_LABELS),
        "domains": {
            "parking": {
                "support": "live_simulated",
                "fields": [dict(item) for item in PARKING_FIELDS],
            },
            "rental": {
                "support": "demonstration",
                "fields": [dict(item) for item in RENTAL_FIELDS],
            },
            "ents": {"support": "demonstration", "fields": []},
            "flight": {"support": "unsupported", "fields": []},
            "hotel": {"support": "unsupported", "fields": []},
        },
    }


def catalog_prompt() -> str:
    named = ", ".join(f"{name}→{code}" for name, code in sorted(NAMED_AIRPORTS.items()))
    return (
        "Closed parking fields: airportCode, start, end, vehicleClass, covered, "
        "shuttleMaxMinutes, currency, accessibility. "
        "Closed rental demonstration fields: when, class, driver. "
        "Emit RequirementPatch values for catalog fields the buyer evidenced this turn. "
        "Ask every remaining askWhenMissing parking fact in one buyer message. "
        "If the buyer answers only some of them, ask the rest together on the next turn. "
        "Do not ask for defaultable execution fields. "
        "Do not ask parking vehicleClass; that is a rental-car fact. Parking vehicleClass "
        "defaults to standard as a system proposal unless the buyer named a class. "
        "Covered parking refusals such as 'I don't need covered parking' are covered=none, "
        "not preferred. "
        "Parking start and end require buyer clock times. Do not invent noon, midnight, "
        "or 12:00Z. Date-only values stay date-only until the buyer states times. "
        "Do not ask trip-level dates, departing from, or car-need when parking or "
        "rental is the active booking domain and those facts are not catalog-missing. "
        "Trip departure, trip destination, and parking airport are distinct. "
        "Do not invent JFK from New York or Mumbai. Do not infer a parking airport "
        "from London or any other city name. "
        "Do not treat a rental-car or entertainment request as airport parking. "
        f"Approved named-airport normalizations only: {named}. "
        "Do not say offers are ready, ranked, selected, or refreshed before A2 completes."
    )


def empty_domain(kind: DomainKind, *, provenance: str, accepted: bool) -> dict[str, object]:
    support = SUPPORT_LABELS[kind]
    return {
        "kind": kind,
        "support": support,
        "provenance": provenance,
        "accepted": accepted,
        "fields": {},
        "missing": [],
        "ask": [],
        "completeness": "incomplete",
        "offerSet": {
            "stale": False,
            "snapshot": None,
            "intentId": None,
        },
        "intentId": None,
    }


def field_spec(kind: str, field_id: str) -> dict[str, object] | None:
    rows = PARKING_FIELDS if kind == "parking" else RENTAL_FIELDS if kind == "rental" else ()
    for item in rows:
        if item["id"] == field_id:
            return dict(item)
    return None


def coerce_value(kind: str, field_id: str, raw: object) -> object | None:
    spec = field_spec(kind, field_id)
    if spec is None:
        return None
    if isinstance(raw, list) and len(raw) == 1:
        raw = raw[0]
    ftype = spec["type"]
    if ftype == "iata":
        return normalize_iata(raw)
    if ftype == "instant":
        return _coerce_instant(raw)
    if ftype == "enum":
        text = str(raw).strip().lower()
        allowed = spec.get("enum")
        if not isinstance(allowed, list):
            return None
        if text in allowed:
            return text
        for item in allowed:
            if re.search(rf"\b{re.escape(str(item))}\b", text):
                return str(item)
        if field_id == "covered":
            if (
                _covered_declined(text)
                or "uncovered" in text
                or "open-air" in text
                or "open air" in text
            ):
                return "none"
            if "covered" in text:
                return "preferred"
        if field_id == "vehicleClass":
            for item in ("suv", "compact", "standard", "oversized"):
                if item in text:
                    return item
        return None
    if ftype == "int":
        if isinstance(raw, bool):
            return None
        if isinstance(raw, int):
            return raw
        try:
            return int(str(raw).strip())
        except ValueError:
            return None
    if ftype == "currency":
        text = str(raw).strip().upper()
        return text if len(text) == 3 and text.isalpha() else None
    if ftype == "access_list":
        if raw in ("", None, "none"):
            return []
        if isinstance(raw, list):
            values = [str(item) for item in raw if str(item) in ACCESS]
            return values
        token = str(raw).strip()
        return [token] if token in ACCESS else None
    if ftype == "text":
        text = str(raw).strip()
        return text or None
    return None


def _coerce_instant(raw: object) -> str | None:
    text = str(raw).strip()
    if re.match(r"^\d{4}-\d{2}-\d{2}$", text):
        return text
    clock = re.match(r"^(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2})(?::(\d{2}))?Z?$", text)
    if clock:
        second = clock.group(3) or "00"
        return f"{clock.group(1)}T{clock.group(2)}:{second}Z"
    named = re.match(
        r"^(\d{1,2})(?:st|nd|rd|th)?\s+"
        r"(january|february|march|april|may|june|july|august|september|october|"
        r"november|december|jan|feb|mar|apr|jun|jul|aug|sept?|oct|nov|dec)"
        r"\.?\s+(\d{4})$",
        text,
        re.I,
    )
    if named:
        months = {
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
        month = months.get(named.group(2).lower())
        if month:
            return f"{named.group(3)}-{month}-{int(named.group(1)):02d}"
    return None


def apply_patch(
    domain: dict[str, object],
    field_id: str,
    value: object,
    *,
    source: FieldSource,
    provenance: FieldProvenance,
) -> bool:
    kind = str(domain.get("kind") or "")
    coerced = coerce_value(kind, field_id, value)
    if coerced is None:
        return False
    if source == "system_proposal":
        provenance = "proposed"
    fields = domain.setdefault("fields", {})
    if not isinstance(fields, dict):
        fields = {}
        domain["fields"] = fields
    previous = fields.get(field_id)
    changed = True
    if isinstance(previous, dict) and previous.get("value") == coerced:
        changed = previous.get("provenance") != provenance or previous.get("source") != source
    fields[field_id] = {
        "value": coerced,
        "source": source,
        "provenance": provenance,
    }
    return changed


def _field_present(spec: Mapping[str, object], held: object) -> bool:
    if not isinstance(held, dict):
        return False
    value = held.get("value")
    if spec.get("type") == "access_list":
        return isinstance(value, list)
    return value not in (None, "")


def apply_defaults(domain: dict[str, object]) -> None:
    if domain.get("kind") != "parking" or not domain.get("accepted"):
        return
    fields = domain.setdefault("fields", {})
    if not isinstance(fields, dict):
        return
    for spec in PARKING_FIELDS:
        if not spec.get("defaultable"):
            continue
        field_id = str(spec["id"])
        held = fields.get(field_id)
        if _field_present(spec, held):
            continue
        apply_patch(
            domain,
            field_id,
            spec.get("default"),
            source="system_proposal",
            provenance="proposed",
        )


def _calendar_date(held: object) -> str:
    if not isinstance(held, dict):
        return ""
    value = held.get("value")
    if not isinstance(value, str) or len(value) < 10:
        return ""
    if re.match(r"^\d{4}-\d{2}-\d{2}", value):
        return value[:10]
    return ""


def _has_buyer_clock(held: object) -> bool:
    if not isinstance(held, dict):
        return False
    value = held.get("value")
    if not isinstance(value, str):
        return False
    if re.match(r"^\d{4}-\d{2}-\d{2}$", value):
        return False
    if not re.search(r"T\d{2}:\d{2}:\d{2}Z$", value):
        return False
    return not (held.get("source") == "system_proposal" and value.endswith("T12:00:00Z"))


def _human_calendar_date(held: object) -> str:
    raw = _calendar_date(held)
    if not raw:
        return "that date"
    year, month, day = raw.split("-")
    months = (
        "January",
        "February",
        "March",
        "April",
        "May",
        "June",
        "July",
        "August",
        "September",
        "October",
        "November",
        "December",
    )
    try:
        label = months[int(month) - 1]
    except (TypeError, ValueError, IndexError):
        return raw
    return f"{int(day)} {label}"


def _instant_ready(spec: Mapping[str, object], held: object) -> bool:
    if spec.get("type") != "instant":
        return _field_present(spec, held)
    return _has_buyer_clock(held)


def refresh_completeness(domain: dict[str, object], pending_gate: str | None) -> None:
    kind = str(domain.get("kind") or "")
    specs = PARKING_FIELDS if kind == "parking" else RENTAL_FIELDS if kind == "rental" else ()
    fields = domain.get("fields") if isinstance(domain.get("fields"), dict) else {}
    missing: list[str] = []
    ask: list[dict[str, str]] = []
    for spec in specs:
        field_id = str(spec["id"])
        held = fields.get(field_id) if isinstance(fields, dict) else None
        present = _instant_ready(spec, held)
        if spec.get("requiredForExecution") and not present:
            missing.append(field_id)
        if spec.get("askWhenMissing") and spec.get("requiredFromBuyer") and not present:
            ask.append({"id": field_id, "ask": str(spec.get("ask") or field_id)})
    if (
        isinstance(fields, dict)
        and "start" in missing
        and "end" in missing
        and _calendar_date(fields.get("start"))
        and _calendar_date(fields.get("end"))
    ):
        start_label = _human_calendar_date(fields.get("start"))
        end_label = _human_calendar_date(fields.get("end"))
        time_ask = {
            "id": "start",
            "ask": (
                f"What time should parking start on {start_label}, "
                f"and what time should it finish on {end_label}?"
            ),
        }
        rewritten: list[dict[str, str]] = []
        skipped_end = False
        for item in ask:
            if item.get("id") == "start":
                rewritten.append(time_ask)
            elif item.get("id") == "end":
                skipped_end = True
            else:
                rewritten.append(item)
        if skipped_end:
            ask = rewritten
    domain["missing"] = missing
    domain["ask"] = ask
    offer = domain.get("offerSet")
    stale = isinstance(offer, dict) and offer.get("stale") is True
    snapshot = offer.get("snapshot") if isinstance(offer, dict) else None
    if domain.get("completeness") == "authorized":
        return
    if domain.get("completeness") == "accepted" and not stale:
        return
    if stale:
        domain["completeness"] = "stale" if missing == [] else "incomplete"
        return
    if isinstance(snapshot, dict) and snapshot.get("offers"):
        domain["completeness"] = "offers"
        return
    if pending_gate in {"A1", "A2", "A3", "A4"} and missing == []:
        domain["completeness"] = "awaiting_grant"
        return
    domain["completeness"] = "ready" if missing == [] and domain.get("accepted") else "incomplete"


def join_catalog_asks(asks: object) -> str:
    texts: list[str] = []
    if isinstance(asks, list):
        for item in asks:
            if not isinstance(item, dict):
                continue
            text = str(item.get("ask") or "").strip()
            if text:
                texts.append(text)
    if not texts:
        return ""
    if len(texts) == 1:
        return texts[0]
    return "I still need a few details to start parking. " + " ".join(texts)


def execution_fields(domain: Mapping[str, object]) -> dict[str, object]:
    fields = domain.get("fields")
    if not isinstance(fields, dict):
        raise ApplicationError("requirements", "incomplete")
    out: dict[str, object] = {}
    for spec in PARKING_FIELDS:
        field_id = str(spec["id"])
        held = fields.get(field_id)
        if not isinstance(held, dict) or held.get("value") in (None, ""):
            if spec.get("requiredForExecution"):
                raise ApplicationError(field_id, "required")
            continue
        out[field_id] = held["value"]
    airport = out.get("airportCode")
    if not isinstance(airport, str) or airport not in KNOWN_IATA:
        raise ApplicationError("airportCode", "required")
    start = out.get("start")
    end = out.get("end")
    if not isinstance(start, str) or not isinstance(end, str):
        raise ApplicationError("start", "required")
    start_held = fields.get("start")
    end_held = fields.get("end")
    if not _has_buyer_clock(start_held) or not _has_buyer_clock(end_held):
        raise ApplicationError("start", "required")
    vehicle = out.get("vehicleClass")
    covered = out.get("covered")
    if vehicle not in VEHICLE:
        raise ApplicationError("vehicleClass", "required")
    if covered not in COVERED:
        raise ApplicationError("covered", "required")
    shuttle = out.get("shuttleMaxMinutes")
    if not isinstance(shuttle, int):
        raise ApplicationError("shuttleMaxMinutes", "required")
    currency = out.get("currency")
    if not isinstance(currency, str):
        raise ApplicationError("currency", "required")
    access = out.get("accessibility")
    if not isinstance(access, list):
        access = []
    out["accessibility"] = access
    return out


def mark_stale(domain: dict[str, object], changed: Sequence[str]) -> None:
    if domain.get("kind") != "parking":
        return
    if not any(item in MATERIAL_PARKING for item in changed):
        return
    offer = domain.setdefault("offerSet", {})
    if not isinstance(offer, dict):
        return
    if offer.get("snapshot") is not None or domain.get("intentId"):
        offer["stale"] = True
        domain["intentId"] = None
        offer["intentId"] = None
        domain["completeness"] = "stale"


def sanitize_buyer_message(text: str, *, a2_complete: bool) -> str:
    if a2_complete or not text.strip():
        return text.strip()
    if OFFER_CLAIM_RE.search(text):
        return "I have what I need to request parking offers after you authorize."
    return text.strip()


def is_affirmative(text: str) -> bool:
    return AFFIRM_RE.fullmatch(text.strip()) is not None


def extract_conversation_patches(
    conversation: str,
    *,
    source: FieldSource,
    calendar_context: str | None = None,
) -> list[dict[str, object]]:
    """Deterministic patches from buyer text. Never copies trip cities into parking IATA."""

    patches: list[dict[str, object]] = []
    lower = conversation.lower()
    airport = _parking_iata(conversation)
    if airport:
        patches.append(
            {"kind": "parking", "fieldId": "airportCode", "value": airport, "source": source}
        )
    vehicle = _vehicle(lower)
    if vehicle:
        patches.append(
            {"kind": "parking", "fieldId": "vehicleClass", "value": vehicle, "source": source}
        )
        patches.append(
            {"kind": "rental", "fieldId": "class", "value": vehicle.upper(), "source": source}
        )
    covered = _covered(lower)
    if covered:
        patches.append(
            {"kind": "parking", "fieldId": "covered", "value": covered, "source": source}
        )
    shuttle = SHUTTLE_RE.search(lower)
    if shuttle:
        patches.append(
            {
                "kind": "parking",
                "fieldId": "shuttleMaxMinutes",
                "value": int(shuttle.group(1)),
                "source": source,
            }
        )
    if "usd" in lower or "dollar" in lower:
        patches.append({"kind": "parking", "fieldId": "currency", "value": "USD", "source": source})
    if re.search(r"\bev\b|ev charging", lower):
        patches.append(
            {
                "kind": "parking",
                "fieldId": "accessibility",
                "value": ["ev_charging"],
                "source": source,
            }
        )
    window = _window_patches(
        conversation,
        source=source,
        calendar_context=calendar_context or conversation,
    )
    patches.extend(window)
    patches.extend(
        _time_only_patches(
            conversation,
            source=source,
            parking_context=calendar_context,
        )
    )
    patches.extend(_change_time_patches(conversation, source=source))
    rental_when = _rental_when(conversation)
    if rental_when:
        patches.append(
            {"kind": "rental", "fieldId": "when", "value": rental_when, "source": source}
        )
    return patches


def parking_iata_from_text(text: str) -> str:
    return _parking_iata(text)


def normalize_iata(raw: object) -> str | None:
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    upper = text.upper()
    if upper in KNOWN_IATA:
        return upper
    cleaned = re.sub(r"[^a-z]+", " ", text.lower()).strip()
    mapped = NAMED_AIRPORTS.get(cleaned)
    if mapped in KNOWN_IATA:
        return mapped
    for token in re.findall(r"\b[A-Za-z]{3}\b", text):
        code = str(token).upper()
        if code in KNOWN_IATA:
            return code
    lower = text.lower()
    for name, code in sorted(NAMED_AIRPORTS.items(), key=lambda item: len(item[0]), reverse=True):
        if name in lower and code in KNOWN_IATA:
            return code
    return None


def apply_model_patches(
    domains: Mapping[str, dict[str, object]],
    patches: Sequence[Mapping[str, object]],
    *,
    conversation: str,
    last_user_message: str,
    source: FieldSource,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    """Validate model-proposed patches. Rejected patches never enter trusted state."""

    accepted: list[dict[str, object]] = []
    rejected: list[dict[str, object]] = []
    changed_by_kind: dict[str, list[str]] = {}
    for raw in patches:
        kind = str(raw.get("kind") or raw.get("taskKind") or "")
        field_id = str(raw.get("fieldId") or "")
        value = raw.get("value")
        evidence = str(raw.get("evidence") or "")
        domain = domains.get(kind)
        report = {
            "kind": kind,
            "fieldId": field_id,
            "value": value,
            "evidence": evidence,
        }
        if not isinstance(domain, dict) or field_spec(kind, field_id) is None:
            rejected.append({**report, "reason": "unknown_field"})
            continue
        coerced = coerce_value(kind, field_id, value)
        if coerced is None:
            rejected.append({**report, "reason": "type"})
            continue
        if field_id in {"start", "end"}:
            coerced = _without_unevidenced_clock(
                coerced, f"{conversation} {last_user_message} {evidence}"
            )
        if not _buyer_evidence(conversation, last_user_message, field_id, coerced, evidence):
            rejected.append({**report, "reason": "no_evidence"})
            continue
        if apply_patch(domain, field_id, coerced, source=source, provenance="explicit"):
            changed_by_kind.setdefault(kind, []).append(field_id)
        accepted.append({**report, "value": coerced})
    parking = domains.get("parking")
    parking_changed = changed_by_kind.get("parking")
    if isinstance(parking, dict) and parking_changed:
        mark_stale(parking, parking_changed)
    return accepted, rejected


def _buyer_evidence(
    conversation: str,
    last_user_message: str,
    field_id: str,
    value: object,
    evidence: str,
) -> bool:
    blob = f"{conversation} {last_user_message} {evidence}".lower()
    if field_id == "airportCode":
        iata = str(value).strip().upper()
        if iata.lower() in blob:
            return True
        return any(name in blob and code == iata for name, code in NAMED_AIRPORTS.items())
    if field_id in {"start", "end"}:
        match = re.search(r"(\d{4})-(\d{2})-(\d{2})", str(value))
        if match is None:
            return False
        if str(value)[:10].lower() in blob:
            year = match.group(1)
            return year in blob or year == "2026"
        day = str(int(match.group(3)))
        month = match.group(2)
        names = {
            "01": "jan",
            "02": "feb",
            "03": "mar",
            "04": "apr",
            "05": "may",
            "06": "jun",
            "07": "jul",
            "08": "aug",
            "09": "sep",
            "10": "oct",
            "11": "nov",
            "12": "dec",
        }
        month_token = names.get(month, "")
        year = match.group(1)
        month_named = any(re.search(rf"\b{re.escape(name)}\b", blob) for name, _num in _MONTH_WORDS)
        return (
            (year in blob or year == "2026")
            and day in blob
            and (month_token in blob or month in blob or not month_named)
        )
    token = str(value).strip().lower()
    if field_id == "covered":
        declined = _covered_declined(blob)
        if token == "none":
            return declined or "uncovered" in blob or "open-air" in blob or "open air" in blob
        if declined:
            return False
        return "covered" in blob or token in blob
    if token and token in blob:
        return True
    return field_id == "vehicleClass" and token == "suv" and "suv" in blob


def _parking_iata(text: str) -> str:
    places = list(PARKING_PLACE_RE.finditer(text))
    if places:
        coded = _place_to_iata(places[-1].group(1))
        if coded:
            return coded
    parking_at = list(PARKING_AT_RE.finditer(text))
    if parking_at and parking_at[-1].group(1).upper() in KNOWN_IATA:
        return parking_at[-1].group(1).upper()
    named_parking = list(IATA_PARKING_RE.finditer(text))
    if named_parking and named_parking[-1].group(1).upper() in KNOWN_IATA:
        return named_parking[-1].group(1).upper()
    named = _named_airport(text, parking_context="parking" in text.lower())
    if named:
        return named
    cleaned = re.sub(r"[^a-z]+", " ", text.lower()).strip()
    if cleaned == "manchester":
        return "MAN"
    stripped = re.sub(r"[^A-Za-z]+", "", text).upper()
    if stripped in KNOWN_IATA:
        return stripped
    return ""


def _place_to_iata(place: str) -> str:
    token = place.strip()
    if not token:
        return ""
    upper = re.sub(r"[^A-Za-z]+", "", token).upper()
    if len(token.strip()) == 3 and upper in KNOWN_IATA:
        return upper
    cleaned = re.sub(r"[^a-z]+", " ", token.lower()).strip()
    if cleaned in NAMED_AIRPORTS:
        return NAMED_AIRPORTS[cleaned]
    if cleaned in PLACE_CITIES:
        return PLACE_CITIES[cleaned]
    names = sorted(NAMED_AIRPORTS, key=len, reverse=True)
    for name in names:
        if name in cleaned:
            return NAMED_AIRPORTS[name]
    return ""


def _named_airport(text: str, *, parking_context: bool) -> str:
    cleaned = re.sub(r"[^a-z]+", " ", text.lower()).strip()
    if cleaned in NAMED_AIRPORTS:
        return NAMED_AIRPORTS[cleaned]
    if not parking_context:
        return ""
    names = sorted(NAMED_AIRPORTS, key=len, reverse=True)
    for name in names:
        for match in re.finditer(rf"\b{re.escape(name)}\b", text, re.I):
            prefix = text[: match.start()].lower()
            if re.search(r"(?:from|departing|leaving|flying from)\s+$", prefix):
                continue
            return NAMED_AIRPORTS[name]
    return ""


def _vehicle(lower: str) -> str:
    match = SUV_RE.search(lower)
    if match is None:
        return ""
    token = match.group(1).lower()
    return token if token in VEHICLE else ""


def _covered_declined(text: str) -> bool:
    return COVERED_DECLINE_RE.search(text) is not None


def _covered(lower: str) -> str:
    if _covered_declined(lower):
        return "none"
    match = COVERED_RE.search(lower)
    if match is None:
        return ""
    token = match.group(1).lower().replace(" ", "-")
    if token in {"uncovered", "open-air"}:
        return "none"
    if "must" in lower or re.search(r"\brequired\b", lower):
        return "required"
    if "prefer" in lower:
        return "preferred"
    return "preferred"


def _clock_to_hhmm(raw: str) -> str | None:
    match = CLOCK_RE.search(raw.strip())
    if match is None:
        return None
    if match.group(1) is not None:
        hour = int(match.group(1))
        minute = int(match.group(2) or "0")
        mer = (match.group(3) or "").lower()
        if mer == "pm" and hour < 12:
            hour += 12
        if mer == "am" and hour == 12:
            hour = 0
        return f"{hour:02d}:{minute:02d}:00Z"
    hour = int(match.group(4))
    minute = int(match.group(5))
    return f"{hour:02d}:{minute:02d}:00Z"


def infer_year_month_for_day(day: int, *, today: date | None = None) -> tuple[str, str]:
    """Next month that still contains `day`, from UTC today if the buyer omitted a month."""

    now = today or datetime.now(UTC).date()
    year = now.year
    month = now.month
    if day < now.day:
        month += 1
        if month == 13:
            month = 1
            year += 1
    return str(year), f"{month:02d}"


def _month_or_iso_mentioned(conversation: str) -> bool:
    if re.search(r"\b(20\d{2})-(\d{2})-\d{2}\b", conversation):
        return True
    lower = conversation.lower()
    return any(re.search(rf"\b{re.escape(name)}\b", lower) for name, _num in _MONTH_WORDS)


def _year_month(conversation: str) -> tuple[str, str]:
    year = "2026"
    year_match = None
    for match in re.finditer(r"\b(20\d{2})\b", conversation):
        year_match = match
    if year_match:
        year = year_match.group(1)
    month = "10"
    mentions: list[tuple[int, str]] = []
    lower = conversation.lower()
    for name, num in _MONTH_WORDS:
        for match in re.finditer(rf"\b{re.escape(name)}\b", lower):
            mentions.append((match.start(), num))
    if mentions:
        month = sorted(mentions)[-1][1]
    iso = list(re.finditer(r"\b(20\d{2})-(\d{2})-\d{2}\b", conversation))
    if iso:
        last = iso[-1]
        return last.group(1), last.group(2)
    return year, month


def _ordinal_date(conversation: str, day: str) -> str:
    if _month_or_iso_mentioned(conversation):
        year, month = _year_month(conversation)
    else:
        year, month = infer_year_month_for_day(int(day))
    return f"{year}-{month}-{int(day):02d}"


def _clock_evidenced(text: str) -> bool:
    return (
        CLOCK_RE.search(text) is not None
        or re.search(r"\b(noon|midnight|midday)\b", text, re.I) is not None
    )


def _without_unevidenced_clock(value: object, blob: str) -> object:
    if not isinstance(value, str):
        return value
    match = re.search(r"^(?P<date>\d{4}-\d{2}-\d{2})T\d{2}:\d{2}:\d{2}Z$", value)
    if match is None:
        return value
    if _clock_evidenced(blob):
        return value
    return match.group("date")


def _window_patches(
    conversation: str,
    *,
    source: FieldSource,
    calendar_context: str | None = None,
) -> list[dict[str, object]]:
    patches: list[dict[str, object]] = []
    context = calendar_context or conversation
    month_names = {name: num for name, num in _MONTH_WORDS}
    day_windows = list(PARKING_FROM_DAYS_RE.finditer(conversation))
    if day_windows:
        match = day_windows[-1]
        start_day = match.group(1)
        end_day = match.group(2)
        month_token = match.group(3)
        if month_token:
            year, _ignored = _year_month(context)
            month = month_names.get(month_token.lower(), "")
            if not month:
                year, month = _year_month(context)
            start = f"{year}-{month}-{int(start_day):02d}"
            end = f"{year}-{month}-{int(end_day):02d}"
        else:
            start = _ordinal_date(context, start_day)
            end = _ordinal_date(context, end_day)
        start, end = _attach_clock_range(conversation, start, end)
        patches.append({"kind": "parking", "fieldId": "start", "value": start, "source": source})
        patches.append({"kind": "parking", "fieldId": "end", "value": end, "source": source})
        return patches
    parking_span = re.search(
        r"parking(?:\s+from)?\s+(?:(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)\s+on\s+)?"
        r"(?:the\s+)?(\d{1,2})(?:st|nd|rd|th)?"
        r".{0,80}?(?:to|until|through)\s+"
        r"(?:(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)\s+(?:on\s+)?)?"
        r"(?:the\s+)?(\d{1,2})(?:st|nd|rd|th)?",
        conversation,
        re.I,
    )
    last_parking = conversation.lower().rfind("parking")
    calendar = None
    for match in _CALENDAR_RE.finditer(conversation):
        if last_parking < 0 or match.start() >= last_parking:
            calendar = match
    if parking_span:
        start_day = parking_span.group(2)
        end_day = parking_span.group(4)
        start_clock = _clock_to_hhmm(parking_span.group(1) or "")
        end_clock = _clock_to_hhmm(parking_span.group(3) or "")
        start = _ordinal_date(context, start_day)
        end = _ordinal_date(context, end_day)
        if start_clock:
            start = f"{start}T{start_clock}"
        if end_clock:
            end = f"{end}T{end_clock}"
        start, end = _attach_clock_range(conversation, start, end)
        patches.append({"kind": "parking", "fieldId": "start", "value": start, "source": source})
        patches.append({"kind": "parking", "fieldId": "end", "value": end, "source": source})
        return patches
    if "parking" in conversation.lower() and calendar is not None:
        year = calendar.group(4) or _year_month(context)[0]
        month = month_names.get(calendar.group(3).lower(), "")
        if month:
            start = f"{year}-{month}-{int(calendar.group(1)):02d}"
            end = f"{year}-{month}-{int(calendar.group(2)):02d}"
            start, end = _attach_clock_range(conversation, start, end)
            patches.append(
                {"kind": "parking", "fieldId": "start", "value": start, "source": source}
            )
            patches.append({"kind": "parking", "fieldId": "end", "value": end, "source": source})
            return patches
    iso = re.search(
        r"parking[^\n]{0,40}(\d{4}-\d{2}-\d{2})T\d{2}:\d{2}:\d{2}Z"
        r".{0,20}(\d{4}-\d{2}-\d{2})T\d{2}:\d{2}:\d{2}Z",
        conversation,
        re.I,
    )
    if iso:
        start = iso.group(1)
        end_match = re.search(
            r"(\d{4}-\d{2}-\d{2})T\d{2}:\d{2}:\d{2}Z.{0,20}(\d{4}-\d{2}-\d{2})T",
            conversation,
        )
        patches.append({"kind": "parking", "fieldId": "start", "value": start, "source": source})
        if end_match:
            patches.append(
                {
                    "kind": "parking",
                    "fieldId": "end",
                    "value": end_match.group(2),
                    "source": source,
                }
            )
    return patches


def _clock_range(conversation: str) -> tuple[str, str] | None:
    match = re.search(
        r"\b(\d{1,2}(?::\d{2})?\s*(?:am|pm))\s+(?:to|until|through)\s+"
        r"(\d{1,2}(?::\d{2})?\s*(?:am|pm))\b",
        conversation,
        re.I,
    )
    if match is None:
        return None
    start_clock = _clock_to_hhmm(match.group(1))
    end_clock = _clock_to_hhmm(match.group(2))
    if not start_clock or not end_clock:
        return None
    return start_clock, end_clock


def _attach_clock_range(conversation: str, start: str, end: str) -> tuple[str, str]:
    clocks = _clock_range(conversation)
    if clocks is None:
        return start, end
    start_clock, end_clock = clocks
    if "T" not in start:
        start = f"{start}T{start_clock}"
    if "T" not in end:
        end = f"{end}T{end_clock}"
    return start, end


def _time_only_patches(
    conversation: str,
    *,
    source: FieldSource,
    parking_context: str | None = None,
) -> list[dict[str, object]]:
    haystack = f"{parking_context or ''} {conversation}".lower()
    if "parking" not in haystack:
        return []
    match = re.search(
        r"\b(\d{1,2}(?::\d{2})?\s*(?:am|pm))\s+(?:to|until|through)\s+"
        r"(\d{1,2}(?::\d{2})?\s*(?:am|pm))\b",
        conversation,
        re.I,
    )
    start_raw = ""
    end_raw = ""
    if match is not None:
        start_raw = match.group(1)
        end_raw = match.group(2)
    else:
        clocks = [item.group(0) for item in CLOCK_RE.finditer(conversation)]
        if len(clocks) >= 2:
            start_raw = clocks[0]
            end_raw = clocks[-1]
    if not start_raw and not end_raw:
        return []
    start_clock = _clock_to_hhmm(start_raw) if start_raw else None
    end_clock = _clock_to_hhmm(end_raw) if end_raw else None
    patches: list[dict[str, object]] = []
    if start_clock:
        patches.append(
            {"kind": "parking", "fieldId": "startTime", "value": start_clock, "source": source}
        )
    if end_clock:
        patches.append(
            {"kind": "parking", "fieldId": "endTime", "value": end_clock, "source": source}
        )
    return patches


def _change_time_patches(conversation: str, *, source: FieldSource) -> list[dict[str, object]]:
    if "parking" not in conversation.lower() or "change" not in conversation.lower():
        return []
    patches: list[dict[str, object]] = []
    start_raw = CHANGE_START_RE.search(conversation)
    finish_raw = CHANGE_FINISH_RE.search(conversation)
    year, month = _year_month(conversation)
    # Times-only change keeps existing dates; caller overlays onto current instants.
    if start_raw:
        clock = _clock_to_hhmm(start_raw.group(1))
        if clock:
            patches.append(
                {
                    "kind": "parking",
                    "fieldId": "startTime",
                    "value": clock,
                    "source": source,
                }
            )
    if finish_raw:
        clock = _clock_to_hhmm(finish_raw.group(1))
        if clock:
            patches.append(
                {
                    "kind": "parking",
                    "fieldId": "endTime",
                    "value": clock,
                    "source": source,
                }
            )
    del year, month
    return patches


def overlay_time_on_instant(current: object, clock: str) -> str | None:
    if not isinstance(current, str) or len(current) < 10:
        return None
    date = current[:10]
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", date):
        return None
    return f"{date}T{clock}"


def _rental_when(conversation: str) -> str:
    match = re.search(
        r"rental(?:\s+car)?\s+from\s+.{0,80}",
        conversation,
        re.I,
    )
    if match is None:
        return ""
    return re.sub(r"\s+", " ", match.group(0)).strip()[:120]


def public_domain(domain: Mapping[str, object]) -> dict[str, object]:
    payload = deepcopy(dict(domain))
    if not payload.get("intentId"):
        payload.pop("intentId", None)
    offer = payload.get("offerSet")
    if isinstance(offer, dict):
        if not offer.get("intentId"):
            offer.pop("intentId", None)
        snapshot = offer.get("snapshot")
        if isinstance(snapshot, dict):
            offer["snapshot"] = _buyer_safe_snapshot(snapshot)
    return payload


def _buyer_safe_snapshot(snapshot: Mapping[str, Any]) -> dict[str, object]:
    offers_raw = snapshot.get("offers")
    offers: list[dict[str, object]] = []
    if isinstance(offers_raw, list):
        for item in offers_raw:
            if not isinstance(item, dict):
                continue
            raw_price = item.get("price")
            price = raw_price if isinstance(raw_price, dict) else {}
            offers.append(
                {
                    "offerId": item.get("offerId"),
                    "supplierToken": item.get("supplierToken"),
                    "version": item.get("version"),
                    "rank": item.get("rank"),
                    "scoreMicros": item.get("scoreMicros"),
                    "totalMinor": item.get("totalMinor") or price.get("totalMinor"),
                    "currency": item.get("currency") or price.get("currency"),
                    "recommended": item.get("recommended"),
                    "simulation": item.get("simulation"),
                }
            )
    return {
        "intentId": snapshot.get("intentId"),
        "state": snapshot.get("state"),
        "offers": offers,
        "recommendedOfferId": snapshot.get("recommendedOfferId"),
        "acceptance": snapshot.get("acceptance"),
        "transaction": snapshot.get("transaction"),
    }
