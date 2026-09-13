"""Code-owned conversational requirement mutations.

The model may acknowledge a change. Trusted trip/stay/parking/flight state is
updated only by these parsers.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from itaa_api.agent_requirements import NAMED_AIRPORTS, normalize_iata
from itaa_api.calendar_resolve import resolve_ymd

DateScope = Literal["all", "stay", "parking"]

_MONTH = (
    r"(january|february|march|april|may|june|july|august|september|october|"
    r"november|december|jan|feb|mar|apr|jun|jul|aug|sept?|oct|nov|dec)"
)
_MUTATION = re.compile(r"\b(change|update|switch|move|instead)\b", re.I)
_STAY_ONLY = re.compile(
    r"\b(only(?: the)? (?:hotel|stay)|hotel dates|stay dates|change only the hotel)\b",
    re.I,
)
_PARKING_ONLY = re.compile(
    r"\b(only(?: the)? parking|parking dates|change only(?: the)? parking)\b",
    re.I,
)
_HOLD_PARKING = re.compile(
    r"\b(keep parking|parking (?:on|at) the original|leave parking)\b",
    re.I,
)
_DROP_PARKING = re.compile(
    r"\b(don'?t need parking|no longer need parking|remove parking|"
    r"cancel parking|without parking)\b",
    re.I,
)
_ADD_EXPERIENCE = re.compile(
    r"\b(also (?:find |search )?things to do|add (?:an )?experience|"
    r"things to do as well|add things to do)\b",
    re.I,
)
_BUDGET = re.compile(
    r"\b(?:only show |only |under |below |less than |no more than |max(?:imum)? )"
    r"hotels?\s*(?:under |below )?(?:£|gbp\s*)(\d{2,5})\b"
    r"|\bhotels?\s+under\s+(?:£|gbp\s*)(\d{2,5})\b",
    re.I,
)
_DESTINATION = re.compile(
    r"\bchange(?: the)?(?: hotel)? destination to\s+([A-Za-z][A-Za-z .'-]{1,40})"
    r"|\bchange(?: the)? hotel to\s+([A-Za-z][A-Za-z .'-]{1,40})",
    re.I,
)
_FLIGHT_LEG = re.compile(
    r"\b(?:flight|flights|fly)\s+from\s+([A-Za-z][A-Za-z .'-]{1,40}?)\s+to\s+"
    r"([A-Za-z][A-Za-z .'-]{1,40}?)"
    r"(?:\s+on\s+(\d{1,2}(?:st|nd|rd|th)?\s+" + _MONTH + r"(?:\s+\d{4})?))?"
    r"(?=\s*[.,]|$)",
    re.I,
)


@dataclass(frozen=True, slots=True)
class BuyerRefinement:
    start_date: str | None = None
    end_date: str | None = None
    date_scope: DateScope = "all"
    hold_parking_dates: bool = False
    destination: str | None = None
    parking_airport: str | None = None
    drop_parking: bool = False
    add_experience: bool = False
    stay_max_minor: int | None = None
    stay_currency: str | None = None
    flight_origin: str | None = None
    flight_destination: str | None = None
    flight_date: str | None = None

    def applies(self) -> bool:
        return any(
            (
                self.start_date,
                self.end_date,
                self.destination,
                self.parking_airport,
                self.drop_parking,
                self.add_experience,
                self.stay_max_minor is not None,
                self.flight_origin,
                self.flight_destination,
            )
        )


def is_explicit_date_mutation(text: str, change: BuyerRefinement) -> bool:
    """True when the buyer is mutating dates, not first stating them."""

    if not change.start_date or not change.end_date:
        return False
    if change.date_scope in {"stay", "parking"}:
        return True
    return _MUTATION.search(text) is not None


def parse_trip_dates(text: str) -> tuple[str, str] | None:
    """Parse a calendar window from buyer text. Never treats clock hours as days."""

    iso = re.search(r"\b(\d{4}-\d{2}-\d{2})\s*(?:to|[–-])\s*(\d{4}-\d{2}-\d{2})\b", text)
    if iso:
        return _ordered(iso.group(1), iso.group(2))
    spanned = re.search(
        rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s*(?:to|[–-]|until|through)\s*"
        rf"(?:the\s+)?(\d{{1,2}})(?:st|nd|rd|th)?\s+{_MONTH}(?:\s+(\d{{4}}))?\b",
        text,
        re.I,
    )
    if spanned:
        start = resolve_ymd(spanned.group(3), int(spanned.group(1)), spanned.group(4))
        end = resolve_ymd(spanned.group(3), int(spanned.group(2)), spanned.group(4))
        if start and end:
            return _ordered(start, end)
    dashed = re.search(
        rf"\b(\d{{1,2}})\s*[–-]\s*(\d{{1,2}})\s+{_MONTH}(?:\s+(\d{{4}}))?\b",
        text,
        re.I,
    )
    if dashed:
        start = resolve_ymd(dashed.group(3), int(dashed.group(1)), dashed.group(4))
        end = resolve_ymd(dashed.group(3), int(dashed.group(2)), dashed.group(4))
        if start and end:
            return _ordered(start, end)
    return None


def parse_one_date(text: str) -> str | None:
    iso = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", text)
    if iso:
        return iso.group(1)
    named = re.search(
        rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+{_MONTH}(?:\s+(\d{{4}}))?\b",
        text,
        re.I,
    )
    if named is None:
        return None
    return resolve_ymd(named.group(2), int(named.group(1)), named.group(3))


def parse_refinement(text: str) -> BuyerRefinement:
    cleaned = text.strip()
    dates = parse_trip_dates(cleaned)
    date_scope: DateScope = "all"
    if dates is not None:
        if _STAY_ONLY.search(cleaned):
            date_scope = "stay"
        elif _PARKING_ONLY.search(cleaned):
            date_scope = "parking"
    hold_parking = _HOLD_PARKING.search(cleaned) is not None
    destination = None
    dest_match = _DESTINATION.search(cleaned)
    if dest_match:
        destination = _place_name(dest_match.group(1) or dest_match.group(2) or "")
    airport = None
    if re.search(r"\b(airport|parking)\b", cleaned, re.I):
        airport = normalize_iata(cleaned)
        if not airport:
            for name, code in NAMED_AIRPORTS.items():
                if name in cleaned.lower():
                    airport = code
                    break
    flight_origin = None
    flight_destination = None
    flight_date = None
    flight = _FLIGHT_LEG.search(cleaned)
    if flight:
        flight_origin = _place_to_iata(flight.group(1))
        flight_destination = _place_to_iata(flight.group(2))
        if flight.group(3):
            flight_date = parse_one_date(flight.group(3))
        if dates and flight_date is None:
            flight_date = dates[0]
    budget_minor = None
    currency = None
    budget = _BUDGET.search(cleaned)
    if budget:
        raw = budget.group(1) or budget.group(2)
        budget_minor = int(raw) * 100
        currency = "GBP"
    start = dates[0] if dates else None
    end = dates[1] if dates else None
    return BuyerRefinement(
        start_date=start,
        end_date=end,
        date_scope=date_scope,
        hold_parking_dates=hold_parking,
        destination=destination,
        parking_airport=airport if re.search(r"\b(parking|airport)\b", cleaned, re.I) else None,
        drop_parking=_DROP_PARKING.search(cleaned) is not None,
        add_experience=_ADD_EXPERIENCE.search(cleaned) is not None,
        stay_max_minor=budget_minor,
        stay_currency=currency,
        flight_origin=flight_origin,
        flight_destination=flight_destination,
        flight_date=flight_date,
    )


def refinement_copy(change: BuyerRefinement) -> str:
    parts: list[str] = []
    if change.start_date and change.end_date:
        window = f"{_buyer_day(change.start_date)} to {_buyer_day(change.end_date)}"
        if change.date_scope == "stay":
            parts.append(f"I've updated the hotel dates to {window}. Parking dates are unchanged.")
        elif change.date_scope == "parking":
            parts.append(f"I've updated the parking dates to {window}. Hotel dates are unchanged.")
        elif change.hold_parking_dates:
            parts.append(
                f"I've updated the trip and hotel dates to {window}. "
                "Parking stays on the original dates."
            )
        else:
            parts.append(f"I've updated the trip dates to {window}.")
    if change.destination:
        parts.append(f"I've updated the hotel destination to {change.destination}.")
    if change.parking_airport:
        parts.append(f"I've updated the parking airport to {change.parking_airport}.")
    if change.drop_parking:
        parts.append("I've removed parking from this booking chat.")
    if change.add_experience:
        parts.append("I've added things to do to the plan.")
    if change.stay_max_minor is not None:
        amount = change.stay_max_minor // 100
        currency = change.stay_currency or "GBP"
        symbol = "£" if currency == "GBP" else currency
        parts.append(f"I'll only keep hotels under {symbol}{amount}.")
    if change.flight_origin and change.flight_destination:
        parts.append(
            f"I've noted a flight from {change.flight_origin} to {change.flight_destination}."
        )
    if not parts:
        return ""
    parts.append("Previous search results for the changed tasks are out of date.")
    return " ".join(parts)


def _ordered(start: str, end: str) -> tuple[str, str]:
    if start <= end:
        return start, end
    return end, start


def _month_num(raw: str) -> str:
    names = {
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
    return names.get(raw.strip().lower(), "")


def _buyer_day(iso: str) -> str:
    months = (
        "Jan",
        "Feb",
        "Mar",
        "Apr",
        "May",
        "Jun",
        "Jul",
        "Aug",
        "Sep",
        "Oct",
        "Nov",
        "Dec",
    )
    year, month, day = iso.split("-")
    return f"{int(day)} {months[int(month) - 1]} {year}"


def _place_name(raw: str) -> str:
    cleaned = re.sub(r"[^A-Za-z .'-]+", " ", raw).strip(" .'-")
    lower = cleaned.lower()
    if lower in {"heathrow", "london heathrow"}:
        return "Heathrow"
    if lower in {"manchester"}:
        return "Manchester"
    if lower in {"edinburgh"}:
        return "Edinburgh"
    if lower in {"london"}:
        return "London"
    return cleaned.title()


def _place_to_iata(raw: str) -> str:
    coded = normalize_iata(raw) or ""
    if coded:
        return coded
    lower = re.sub(r"[^a-z]+", " ", raw.lower()).strip()
    mapped = NAMED_AIRPORTS.get(lower)
    if mapped:
        return mapped
    mapped = _AIRPORT_PLACES.get(lower)
    if mapped:
        return mapped
    return ""


_AIRPORT_PLACES: dict[str, str] = {
    "heathrow": "LHR",
    "london heathrow": "LHR",
    "gatwick": "LGW",
    "stansted": "STN",
}
