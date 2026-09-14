"""Code-owned conversational requirement mutations.

The model may acknowledge a change. Trusted trip/stay/parking/flight state is
updated only by these parsers.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from typing import Literal

from itaa_api.agent_requirements import NAMED_AIRPORTS, normalize_iata
from itaa_api.calendar_resolve import resolve_ymd

DateScope = Literal["all", "stay", "parking", "flight"]

_MONTH = (
    r"(january|february|march|april|may|june|july|august|september|october|"
    r"november|december|jan|feb|mar|apr|jun|jul|aug|sept?|oct|nov|dec)"
)
_MUTATION = re.compile(r"\b(change|update|modify|switch|move|instead)\b", re.I)
_STAY_ONLY = re.compile(
    r"\b(only(?: the)? (?:hotel|stay)|hotel dates|stay dates|change only the hotel)\b",
    re.I,
)
_PARKING_ONLY = re.compile(
    r"\b(only(?: the)? parking|parking dates|change only(?: the)? parking)\b",
    re.I,
)
_FLIGHT_ONLY = re.compile(
    r"\b(?:only(?: the)? flight|flight dates|"
    r"(?:change|update|modify|switch|move)(?: the)? flight(?:s| dates| booking)?|"
    r"change only(?: the)? flight)\b",
    re.I,
)
_CASCADE_FOLLOW = re.compile(
    r"\b(same dates(?: for everything)?|follow(?: the same dates)?|"
    r"hotel and parking (?:too|as well)|everything)\b",
    re.I,
)
_CASCADE_HOLD = re.compile(
    r"\b(keep(?: hotel| parking| them)?|stay on|as they are|"
    r"original dates|don't change(?: the)? (?:hotel|parking)|keep hotel)\b",
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
_CHECKIN_HINT = re.compile(r"\b(check[\s-]?in|hotel|stay)\b", re.I)
_INSTEAD_DAY = re.compile(
    r"(?:to|on)\s+(?:the\s+)?(\d{1,2})(?:st|nd|rd|th)?"
    r"(?:\s+" + _MONTH + r")?"
    r"(?:\s+(\d{4}))?"
    r"\s+instead\s+of(?:\s+(?:the\s+)?)?(\d{1,2})(?:st|nd|rd|th)?",
    re.I,
)
_CHECKIN_ON = re.compile(
    r"\bcheck[\s-]?in\s+(?:to|on|from)\s+(?:the\s+)?(\d{1,2})(?:st|nd|rd|th)?"
    r"(?:\s+" + _MONTH + r")?(?:\s+(\d{4}))?",
    re.I,
)
_BARE_RANGE = re.compile(
    r"\b(\d{1,2})(?:st|nd|rd|th)?\s*(?:to|[–-]|until|through)\s*"
    r"(?:the\s+)?(\d{1,2})(?:st|nd|rd|th)?\b",
    re.I,
)
_CLOCKISH = re.compile(r"\b(?:am|pm)\b|\d:\d{2}", re.I)
_PLACE = r"([A-Za-z]{3}|[A-Za-z][A-Za-z .'-]{1,40}?)"
_FLIGHT_LEG = re.compile(
    r"\b(?:flight|flights|fly)\s+from\s+([A-Za-z][A-Za-z .'-]{1,40}?)\s+to\s+"
    r"([A-Za-z][A-Za-z .'-]{1,40}?)"
    r"(?:\s+on\s+(\d{1,2}(?:st|nd|rd|th)?\s+" + _MONTH + r"(?:\s+\d{4})?))?"
    r"(?=\s*[.,]|$)",
    re.I,
)
_FLIGHT_ORIGIN_CHANGE = re.compile(
    r"\b(?:change|update|modify|switch|move)\s+"
    r"(?:the\s+)?(?:flight\s+)?"
    r"(?:departure|origin)(?:\s+airport)?\s+"
    r"(?:from\s+" + _PLACE + r"\s+)?to\s+" + _PLACE + r"(?=\s*[.,;!?]|$)",
    re.I,
)
_DEPARTURE_AIRPORT_HINT = re.compile(
    r"\b(?:departure|origin)\s+airport\b|\bflight\s+origin\b|\bdeparting\s+airport\b",
    re.I,
)
_TO_PLACE = re.compile(
    r"\bto\s+" + _PLACE + r"(?=\s*[.,;!?]|$)",
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
    flight_origin_place: str | None = None
    flight_destination: str | None = None
    flight_date: str | None = None
    start_day: int | None = None
    end_day: int | None = None
    instead_of_day: int | None = None

    def applies(self) -> bool:
        return any(
            (
                self.start_date,
                self.end_date,
                self.start_day,
                self.end_day,
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

    if change.start_day is not None and change.end_day is not None:
        return True
    if change.start_day is not None and change.instead_of_day is not None:
        return True
    if not change.start_date or not change.end_date:
        return False
    if change.date_scope in {"stay", "parking", "flight"}:
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
    leading = re.search(
        rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+(?:of\s+)?{_MONTH}(?:\s+(\d{{4}}))?\s*"
        rf"(?:to|[–-]|until|through)\s*(?:the\s+)?(\d{{1,2}})(?:st|nd|rd|th)?"
        rf"(?:\s+(?:of\s+)?{_MONTH})?(?:\s+(\d{{4}}))?\b",
        text,
        re.I,
    )
    if leading:
        start = resolve_ymd(leading.group(2), int(leading.group(1)), leading.group(3))
        end = resolve_ymd(
            leading.group(5) or leading.group(2),
            int(leading.group(4)),
            leading.group(6) or leading.group(3),
        )
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
    if _FLIGHT_ONLY.search(cleaned):
        date_scope = "flight"
    elif _STAY_ONLY.search(cleaned):
        date_scope = "stay"
    elif _PARKING_ONLY.search(cleaned):
        date_scope = "parking"
    hold_parking = _HOLD_PARKING.search(cleaned) is not None
    destination = None
    dest_match = _DESTINATION.search(cleaned)
    if dest_match:
        destination = _place_name(dest_match.group(1) or dest_match.group(2) or "")
    origin_change = _FLIGHT_ORIGIN_CHANGE.search(cleaned)
    parking_hint = bool(re.search(r"\bparking\b", cleaned, re.I))
    airport_hint = bool(re.search(r"\bairport\b", cleaned, re.I))
    is_parking_airport = parking_hint or (
        airport_hint and origin_change is None and _DEPARTURE_AIRPORT_HINT.search(cleaned) is None
    )
    airport = None
    if is_parking_airport:
        target = _TO_PLACE.search(cleaned)
        airport = _place_to_iata(target.group(1)) if target else ""
        if not airport:
            airport = normalize_iata(cleaned)
        if not airport:
            for name, code in NAMED_AIRPORTS.items():
                if name in cleaned.lower():
                    airport = code
                    break
    flight_origin = None
    flight_origin_place = None
    flight_destination = None
    flight_date = None
    if origin_change:
        raw_origin = (origin_change.group(2) or origin_change.group(1) or "").strip()
        flight_origin = _place_to_iata(raw_origin)
        flight_origin_place = _place_name(raw_origin) if raw_origin else None
    flight = None if origin_change else _FLIGHT_LEG.search(cleaned)
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
    start_day = None
    end_day = None
    instead_of_day = None
    if start is None:
        bare = _BARE_RANGE.search(cleaned)
        if bare and _CLOCKISH.search(cleaned) is None:
            has_ordinal = re.search(r"\d(?:st|nd|rd|th)", bare.group(0), re.I) is not None
            if has_ordinal or _MUTATION.search(cleaned) is not None:
                start_day = int(bare.group(1))
                end_day = int(bare.group(2))
        shifted = _INSTEAD_DAY.search(cleaned) or _CHECKIN_ON.search(cleaned)
        if shifted and end_day is None:
            start_day = int(shifted.group(1))
            if shifted.re is _INSTEAD_DAY:
                instead_of_day = int(shifted.group(4))
            month = shifted.group(2)
            year = shifted.group(3)
            if month:
                resolved = resolve_ymd(month, start_day, year)
                if resolved:
                    start = resolved
        if (
            start_day is not None
            and end_day is None
            and date_scope == "all"
            and _CHECKIN_HINT.search(cleaned)
        ):
            date_scope = "stay"
    return BuyerRefinement(
        start_date=start,
        end_date=end,
        date_scope=date_scope,
        hold_parking_dates=hold_parking,
        destination=destination,
        parking_airport=airport if is_parking_airport else None,
        drop_parking=_DROP_PARKING.search(cleaned) is not None,
        add_experience=_ADD_EXPERIENCE.search(cleaned) is not None,
        stay_max_minor=budget_minor,
        stay_currency=currency,
        flight_origin=flight_origin,
        flight_origin_place=flight_origin_place,
        flight_destination=flight_destination,
        flight_date=flight_date,
        start_day=start_day,
        end_day=end_day,
        instead_of_day=instead_of_day,
    )


def bind_day_shift(
    change: BuyerRefinement,
    *,
    stay_start: str,
    stay_end: str,
    parking_authorized: bool = False,
    last_text: str = "",
    flight_start: str = "",
    flight_end: str = "",
) -> BuyerRefinement:
    """Resolve month-less day shifts against the current trip window."""

    if change.start_date and change.end_date:
        return change
    if change.start_day is not None and change.end_day is not None:
        anchor = _latest_iso(stay_start, stay_end, flight_start, flight_end)
        if len(anchor) != 10:
            return change
        start = _iso_with_day(anchor, change.start_day)
        end = _iso_with_day(anchor, change.end_day)
        if not start or not end:
            return change
        if start > end:
            end = _shift_month(end, 1)
        return replace(change, start_date=start, end_date=end)
    anchor_start = stay_start.strip()[:10]
    anchor_end = stay_end.strip()[:10]
    if len(anchor_start) != 10 or len(anchor_end) != 10:
        return change
    scope = change.date_scope
    if scope == "all":
        if _CHECKIN_HINT.search(last_text) or parking_authorized:
            scope = "stay"
        elif re.search(r"\bparking\b", last_text, re.I):
            scope = "parking"
        else:
            scope = "stay"
    if scope != "stay":
        return change
    start = change.start_date or (
        _iso_with_day(anchor_start, change.start_day) if change.start_day is not None else ""
    )
    if not start or start > anchor_end:
        return change
    return replace(
        change,
        start_date=start,
        end_date=anchor_end,
        date_scope="stay",
        hold_parking_dates=True,
    )


def parse_date_cascade_reply(text: str) -> Literal["follow", "hold"] | None:
    cleaned = text.strip()
    if not cleaned:
        return None
    if _CASCADE_HOLD.search(cleaned) and not re.search(
        r"\b(same dates|follow|everything)\b", cleaned, re.I
    ):
        return "hold"
    if _CASCADE_FOLLOW.search(cleaned):
        return "follow"
    if re.fullmatch(
        r"(?:yes|yeah|yep|yup|ok|okay|sure|proceed)(?:[,.]?\s+"
        r"(?:please|they should|they can|go ahead|do it))?[.!]?",
        cleaned,
        re.I,
    ):
        return "follow"
    if re.fullmatch(r"(?:go ahead|please do|do it|search (?:them|those) too)[.!]?", cleaned, re.I):
        return "follow"
    return None


def cascade_copy(change: BuyerRefinement, *, original_start: str, original_end: str) -> str:
    if not change.start_date or not change.end_date:
        return ""
    window = f"{_buyer_day(change.start_date)} to {_buyer_day(change.end_date)}"
    held = (
        f"{_buyer_day(original_start)} to {_buyer_day(original_end)}"
        if original_start and original_end
        else "the original dates"
    )
    return (
        f"I'll change the flight to {window}. Should the hotel and parking follow the same dates, "
        f"or stay on {held}?"
    )


def refinement_copy(change: BuyerRefinement, *, had_results: bool = False) -> str:
    parts: list[str] = []
    if change.start_date and change.end_date:
        window = f"{_buyer_day(change.start_date)} to {_buyer_day(change.end_date)}"
        if change.date_scope == "stay":
            parts.append(f"I've updated the hotel dates to {window}. Parking dates are unchanged.")
        elif change.date_scope == "parking":
            parts.append(f"I've updated the parking dates to {window}. Hotel dates are unchanged.")
        elif change.date_scope == "flight":
            parts.append(f"I've updated the flight dates to {window}.")
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
    elif change.flight_origin:
        label = change.flight_origin_place or change.flight_origin
        parts.append(f"I've updated the departure airport to {label}.")
    if not parts:
        return ""
    if had_results:
        parts.append("Previous search results for the changed tasks are out of date.")
    return " ".join(parts)


def _ordered(start: str, end: str) -> tuple[str, str]:
    if start <= end:
        return start, end
    return end, start


def _latest_iso(*values: str) -> str:
    dates = [item.strip()[:10] for item in values if len(item.strip()) >= 10]
    return max(dates) if dates else ""


def _iso_with_day(iso: str, day: int) -> str:
    if day < 1 or day > 31 or len(iso) < 10:
        return ""
    return f"{iso[:8]}{day:02d}"


def _shift_month(iso: str, months: int) -> str:
    if len(iso) < 10:
        return iso
    year = int(iso[:4])
    month = int(iso[5:7]) + months
    while month > 12:
        month -= 12
        year += 1
    while month < 1:
        month += 12
        year -= 1
    return f"{year:04d}-{month:02d}-{iso[8:10]}"


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
    if lower in {"mumbai"}:
        return "Mumbai"
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
    upper = re.sub(r"[^A-Za-z]+", "", raw).upper()
    if len(upper) == 3 and upper in set(_AIRPORT_PLACES.values()):
        return upper
    return ""


_AIRPORT_PLACES: dict[str, str] = {
    "heathrow": "LHR",
    "london heathrow": "LHR",
    "gatwick": "LGW",
    "stansted": "STN",
    "mumbai": "BOM",
    "bom": "BOM",
    "milan": "MXP",
    "dubai": "DXB",
}
