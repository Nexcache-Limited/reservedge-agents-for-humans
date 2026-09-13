"""Trusted calendar year and parking-window resolution.

Buyer text that omits a year is resolved to the nearest plausible future
occurrence from UTC today. Model-emitted past years must not survive when the
buyer did not type a year.
"""

from __future__ import annotations

import re
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

_MONTH_NAMES = (
    "january|february|march|april|may|june|july|august|september|october|"
    "november|december|jan|feb|mar|apr|jun|jul|aug|sept?|oct|nov|dec"
)
_MONTH_NUM = {
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
_WORD_DAYS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7}
_YEAR_IN_TEXT = re.compile(r"\b(20\d{2})\b")
_ISO_DATE = re.compile(r"\b(20\d{2})-(\d{2})-(\d{2})\b")
_DAY_MONTH = re.compile(
    rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+({_MONTH_NAMES})(?:\s+(\d{{4}}))?\b",
    re.I,
)
_ON_DAY_MONTH = re.compile(
    rf"\bon\s+(?:the\s+)?(\d{{1,2}})(?:st|nd|rd|th)?\s+({_MONTH_NAMES})(?:\s+(\d{{4}}))?\b",
    re.I,
)
_STAY_DURATION = re.compile(
    r"\b(?:for|hotel.{0,48}?\bfor)\s+(one|two|three|four|five|six|seven|\d+)\s+(days?|nights?)\b",
    re.I | re.S,
)
_PARKING_CLOCK_WINDOW = re.compile(
    rf"parking.{{0,96}}?(?:from\s+)?"
    rf"(\d{{1,2}}(?::\d{{2}})?\s*(?:am|pm))\s+on\s+(?:the\s+)?"
    rf"(\d{{1,2}})(?:st|nd|rd|th)?(?:\s+({_MONTH_NAMES}))?"
    rf".{{0,48}}?(?:to|until|through)\s+"
    rf"(\d{{1,2}}(?::\d{{2}})?\s*(?:am|pm))\s+(?:on\s+)?(?:the\s+)?"
    rf"(\d{{1,2}})(?:st|nd|rd|th)?(?:\s+({_MONTH_NAMES}))?",
    re.I | re.S,
)
_CLOCK = re.compile(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", re.I)
_OTHER_TRANSPORT = re.compile(
    r"\b(train|eurostar|ferry|bus|coach|driving|drive there|by car)\b",
    re.I,
)
_LOCAL_INSTANT = re.compile(r"^(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2}:\d{2})(?:Z|[+-]\d{2}:\d{2})?$")

# Closed competition map. Airport code is the timezone key; do not grow this
# into a world gazetteer.
AIRPORT_TIMEZONES: dict[str, str] = {
    "LHR": "Europe/London",
    "LGW": "Europe/London",
    "STN": "Europe/London",
    "LTN": "Europe/London",
    "LCY": "Europe/London",
    "MAN": "Europe/London",
    "BHX": "Europe/London",
    "EDI": "Europe/London",
    "GLA": "Europe/London",
    "JFK": "America/New_York",
    "LGA": "America/New_York",
    "EWR": "America/New_York",
    "AMS": "Europe/Amsterdam",
    "CDG": "Europe/Paris",
    "DUB": "Europe/Dublin",
}


def utc_today(today: date | None = None) -> date:
    return today or datetime.now(UTC).date()


def user_typed_year(text: str) -> bool:
    return _YEAR_IN_TEXT.search(text) is not None


def month_num(raw: str) -> str:
    return _MONTH_NUM.get(raw.strip().lower().rstrip("."), "")


def nearest_future_year(month: int, day: int, *, today: date | None = None) -> int:
    """Year for a month/day with no typed year: this year if still ahead or today, else next."""

    now = utc_today(today)
    try:
        candidate = date(now.year, month, day)
    except ValueError:
        if month == 2 and day == 29:
            year = now.year if _is_leap(now.year) and date(now.year, 2, 28) >= now else now.year + 1
            while not _is_leap(year):
                year += 1
            return year
        raise
    if candidate >= now:
        return now.year
    return now.year + 1


def resolve_ymd(
    month: str,
    day: int,
    year: str | None = None,
    *,
    today: date | None = None,
) -> str | None:
    month_token = month if month.isdigit() else month_num(month)
    if not month_token:
        return None
    month_i = int(month_token)
    if day < 1 or day > 31:
        return None
    if year and re.fullmatch(r"20\d{2}", year):
        iso = f"{year}-{month_token}-{day:02d}"
        return iso if _valid_iso(iso) else None
    resolved_year = nearest_future_year(month_i, day, today=today)
    iso = f"{resolved_year}-{month_token}-{day:02d}"
    return iso if _valid_iso(iso) else None


def rewrite_past_iso_if_year_omitted(
    iso: str,
    user_text: str,
    *,
    today: date | None = None,
) -> str:
    match = _ISO_DATE.search(iso.strip())
    if match is None:
        return iso
    if user_typed_year(user_text):
        return iso
    month = int(match.group(2))
    day = int(match.group(3))
    resolved = resolve_ymd(f"{month:02d}", day, today=today)
    if resolved is None:
        return iso
    return iso.replace(match.group(0), resolved, 1)


def parse_anchor_date(text: str, *, today: date | None = None) -> str | None:
    """First travel/stay calendar day. Prefers 'on 17 October' over later parking ordinals."""

    named = _ON_DAY_MONTH.search(text)
    if named is None:
        named = _DAY_MONTH.search(text)
    if named is None:
        return None
    return resolve_ymd(named.group(2), int(named.group(1)), named.group(3), today=today)


def stay_duration_days(text: str) -> int | None:
    match = _STAY_DURATION.search(text)
    if match is None:
        return None
    count = _WORD_DAYS.get(match.group(1).lower())
    if count is None:
        count = int(match.group(1))
    unit = match.group(2).lower()
    if count < 1:
        return None
    if unit.startswith("night"):
        return count
    return count


def apply_stay_duration(start: str, end: str, text: str) -> tuple[str, str]:
    nights = stay_duration_days(text)
    if not start or nights is None:
        return start, end
    start_date = _parse_iso(start[:10])
    if start_date is None:
        return start, end
    checkout = start_date + timedelta(days=nights)
    return start_date.isoformat(), checkout.isoformat()


def parse_parking_clock_window(text: str, *, today: date | None = None) -> tuple[str, str] | None:
    """Domain-explicit parking start/end instants. Does not use stay checkout."""

    match = _PARKING_CLOCK_WINDOW.search(text)
    if match is None:
        return None
    start_clock = _clock_to_hhmm(match.group(1))
    end_clock = _clock_to_hhmm(match.group(4))
    start_month = match.group(3)
    end_month = match.group(6) or start_month
    if not start_month:
        start_month = _month_from_context(text)
    if not end_month:
        end_month = start_month
    if not start_clock or not end_clock or not start_month:
        return None
    start = resolve_ymd(start_month, int(match.group(2)), today=today)
    end = resolve_ymd(end_month, int(match.group(5)), today=today)
    if start is None or end is None:
        return None
    return f"{start}T{start_clock}", f"{end}T{end_clock}"


def other_transport_stated(text: str) -> bool:
    return _OTHER_TRANSPORT.search(text) is not None


def _month_from_context(text: str) -> str:
    hits = list(_DAY_MONTH.finditer(text))
    if not hits:
        return ""
    return hits[0].group(2)


def _clock_to_hhmm(raw: str) -> str | None:
    match = _CLOCK.search(raw.strip())
    if match is None:
        return None
    hour = int(match.group(1))
    minute = int(match.group(2) or "0")
    mer = (match.group(3) or "").lower()
    if mer == "pm" and hour < 12:
        hour += 12
    if mer == "am" and hour == 12:
        hour = 0
    return f"{hour:02d}:{minute:02d}:00"


def airport_timezone(airport: str) -> str:
    code = airport.strip().upper()
    zone = AIRPORT_TIMEZONES.get(code)
    if not zone:
        raise ValueError(f"unsupported parking airport timezone: {airport}")
    return zone


def parking_local_naive(value: str) -> str | None:
    """Airport-local wall clock. A trailing Z is treated as local, not UTC."""

    match = _LOCAL_INSTANT.fullmatch(value.strip())
    if match is None:
        return None
    return f"{match.group(1)}T{match.group(2)}"


def to_utc_instant(local_instant: str, airport: str) -> str:
    naive = parking_local_naive(local_instant)
    if naive is None:
        raise ValueError(f"invalid parking instant: {local_instant}")
    local_dt = datetime.fromisoformat(naive)
    aware = local_dt.replace(tzinfo=ZoneInfo(airport_timezone(airport)))
    return aware.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def from_utc_to_local(utc_instant: str, airport: str) -> str:
    raw = utc_instant.strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    utc_dt = datetime.fromisoformat(raw).astimezone(UTC)
    local = utc_dt.astimezone(ZoneInfo(airport_timezone(airport)))
    return local.replace(tzinfo=None).strftime("%Y-%m-%dT%H:%M:%S")


def _parse_iso(raw: str) -> date | None:
    match = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", raw)
    if match is None:
        return None
    try:
        return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
    except ValueError:
        return None


def _valid_iso(iso: str) -> bool:
    return _parse_iso(iso) is not None


def _is_leap(year: int) -> bool:
    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)
