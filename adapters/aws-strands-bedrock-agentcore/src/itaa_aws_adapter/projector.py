"""Deterministic plan projector. Model provenance is never authoritative."""

from __future__ import annotations

import re
from typing import Final

from itaa_api.calendar_resolve import (
    apply_stay_duration,
    other_transport_stated,
    parse_anchor_date,
    resolve_ymd,
    rewrite_past_iso_if_year_omitted,
)
from itaa_aws_adapter import PLAN_QUESTION_CAP
from itaa_aws_adapter.schemas import (
    BlockingQuestion,
    ExtractedFacts,
    PlanAnswers,
    PlanProjection,
    PlanTask,
    PlanTurn,
    TaskKind,
    TaskProvenance,
    TaskSupport,
)
from itaa_liteapi_hotels.gazetteer import CITY_COUNTRY

KNOWN_AIRPORTS: Final[dict[str, tuple[str, str]]] = {
    "JFK": ("New York", "JFK"),
    "LGA": ("New York", "LGA"),
    "EWR": ("Newark", "EWR"),
    "EDI": ("Edinburgh", "EDI"),
    "MAN": ("Manchester", "MAN"),
    "LHR": ("London", "LHR"),
    "LGW": ("London", "LGW"),
    "STN": ("London", "STN"),
    "AMS": ("Amsterdam", "AMS"),
    "CDG": ("Paris", "CDG"),
    "DUB": ("Dublin", "DUB"),
    "GLA": ("Glasgow", "GLA"),
}

# Airport is empty for multi-airport cities. Do not invent JFK from "New York".
CITY_AIRPORTS: Final[tuple[tuple[re.Pattern[str], str, str], ...]] = (
    (re.compile(r"\bedinburgh\b", re.I), "Edinburgh", "EDI"),
    (re.compile(r"\bnew york\b|\bnyc\b|\bmanhattan\b", re.I), "New York", ""),
    (re.compile(r"\bmanchester\b", re.I), "Manchester", "MAN"),
    (re.compile(r"\bmilan\b|\bmilano\b", re.I), "Milan", ""),
    (re.compile(r"\bmumbai\b|\bbombay\b", re.I), "Mumbai", ""),
    (re.compile(r"\brome\b|\broma\b", re.I), "Rome", ""),
    (re.compile(r"\blondon\b", re.I), "London", "LHR"),
    (re.compile(r"\bamsterdam\b", re.I), "Amsterdam", "AMS"),
    (re.compile(r"\bparis\b", re.I), "Paris", "CDG"),
    (re.compile(r"\bdublin\b", re.I), "Dublin", "DUB"),
    (re.compile(r"\bglasgow\b", re.I), "Glasgow", "GLA"),
)

# Named airports are stay/parking places, not trip cities. Do not override a city
# destination when the buyer is only naming a departure airport.
AIRPORT_PLACES: Final[tuple[tuple[re.Pattern[str], str, str], ...]] = (
    (re.compile(r"\bheathrow\b", re.I), "Heathrow", "LHR"),
    (re.compile(r"\bgatwick\b", re.I), "Gatwick", "LGW"),
    (re.compile(r"\bstansted\b", re.I), "Stansted", "STN"),
)

MONTHS: Final[dict[str, str]] = {
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

_CITY_STOP: Final[frozenset[str]] = frozenset(
    {
        *MONTHS,
        "monday",
        "tuesday",
        "wednesday",
        "thursday",
        "friday",
        "saturday",
        "sunday",
        "hotel",
        "hotels",
        "booking",
        "airport",
        "parking",
        "rental",
        "car",
        "trip",
        "going",
        "travelling",
        "traveling",
        "need",
        "needed",
        "from",
        "with",
        "the",
        "and",
        "for",
        "you",
        "your",
        "this",
        "visit",
        "visiting",
        "please",
        "covered",
        "uncovered",
        "i'm",
        "i've",
        "we're",
        "they're",
        "flying",
        "returning",
    }
)

TASK_META: Final[dict[TaskKind, tuple[str, str, TaskSupport, str]]] = {
    "parking": ("Pk", "Airport parking", "live_simulated", "Live simulated path"),
    "rental": ("Rc", "Rental car", "demonstration", "Demonstration task"),
    "ents": ("En", "Entertainment", "demonstration", "Demonstration task"),
    "flight": ("Fl", "Flight", "sandbox_search", "Sandbox flight search"),
    "hotel": ("Ht", "Hotel", "sandbox_search", "Sandbox hotel search"),
    "experience": ("Ex", "Experience", "sandbox_search", "Sandbox experience search"),
}

_AIRPORT = re.compile(r"\b([A-Za-z]{3})\b")
_FLIGHT_ROUTE = re.compile(
    r"\b(?:flight|flights|fly)\s+from\s+[A-Za-z][A-Za-z .'-]{0,40}?\s+to\s+[A-Za-z]",
    re.I,
)
_EXPLICIT_KIND_NEEDLES: Final[dict[TaskKind, tuple[str, ...]]] = {
    "parking": ("parking",),
    "rental": ("rental car", "hire car", "car hire", "rent a car", "rental"),
    "ents": ("ticket", "concert", "entertainment", "gig"),
    "flight": ("flight", "flights", "flying"),
    "hotel": ("hotel", "accommodation", "place to stay", "stay"),
    "experience": (
        "things to do",
        "thing to do",
        "what to do",
        "attractions",
        "attraction",
        "activities",
        "activity",
        "museum",
        "museums",
        "tour",
        "tours",
        "sightseeing",
        "experiences",
        "family-friendly",
        "places to visit",
    ),
}
_EXPERIENCE_RE = re.compile(
    r"\b(?:things?\s+to\s+do|what\s+to\s+do|places?\s+to\s+visit|"
    r"attractions?|activit(?:y|ies)|museums?|tours?|sightseeing|"
    r"experiences|family[-\s]?friendly)\b",
    re.I,
)
_SHOW_ME_RE = re.compile(r"\bshow(?:s)?\s+(?:me|us)\b", re.I)
_ENTS_RE = re.compile(r"\b(tickets?|concerts?|entertainment|gigs?)\b", re.I)
_SHOW_NOUN_RE = re.compile(r"\b(?:a |the |tonight'?s )?shows?\b", re.I)
_CAR_PARKING_RE = re.compile(r"\bcar\s+park(?:ing)?\b")
_CAR_RENTAL_RE = re.compile(
    r"\b(?:rental\s+cars?|hire\s+cars?|car\s+hire|rent\s+a\s+car|"
    r"need(?:ed)?\s+(?:a\s+|the\s+)?cars?|rental)\b"
)


def extract_facts(objective: str, answers: PlanAnswers | None = None) -> ExtractedFacts:
    text = objective.strip()
    lower = text.lower()
    parking_word = bool(re.search(r"\bparking\b", lower))
    rental_stated = _car_mentioned(lower)
    ents_stated = _ents_stated(lower)
    hotel_stated = bool(re.search(r"\b(hotel|accommodation|place to stay)\b", lower))
    experience_stated = bool(_EXPERIENCE_RE.search(lower))
    flight_satisfied = bool(
        re.search(
            r"\bflights?\s+(?:are|is|were|'re)\s+(?:already\s+)?booked\b|"
            r"\balready booked(?:\s+\w+){0,4}\s+flights?\b",
            lower,
        )
    )
    flight_stated = bool(re.search(r"\b(flight|flights|flying)\b", lower)) and not flight_satisfied
    landing = bool(
        re.search(
            r"\b(when i land|when we land|when i arrive|when we arrive|land(?:ing)?)\b", lower
        )
    )
    conference = bool(re.search(r"\bconference\b", lower))
    travel = bool(re.search(r"\b(travell?ing|trip to|going to|visit(?:ing)?)\b", lower))
    nights = bool(re.search(r"\bnights?\b", lower))
    city = _match_city(lower)
    route_dest, route_origin = _parse_route(text)
    if route_dest:
        routed = _match_city(route_dest.lower())
        if routed is not None:
            city = routed
        elif _plausible_city(route_dest):
            city = (route_dest.strip().title(), "")
    origin_city = ""
    if route_origin:
        origin_match = _match_city(route_origin.lower())
        origin_city = origin_match[0] if origin_match is not None else route_origin.strip().title()
    airports = [item.upper() for item in _AIRPORT.findall(text) if item.upper() in KNOWN_AIRPORTS]
    flying_from = re.search(
        r"\b(?:flying|departing|leaving|travell?ing)\s+from\s+([A-Za-z]{3})\b", text, re.I
    )
    from_city = re.search(
        r"\b(?:flying|departing|leaving|travell?ing)\s+from\s+([A-Za-z][A-Za-z ]+)\b", text, re.I
    )
    parking_at = re.search(r"\b(?:parking\s+(?:at|in)|at)\s+([A-Za-z]{3})\b", text, re.I)
    named = airports[0] if airports else ""
    airport_led = (
        named != ""
        and not travel
        and not landing
        and not conference
        and city is None
        and not rental_stated
    )
    parking_stated = parking_word or airport_led
    departure = ""
    if flying_from is not None and flying_from.group(1).upper() in KNOWN_AIRPORTS:
        departure = flying_from.group(1).upper()
    elif origin_city == "" and from_city is not None:
        matched = _match_city(from_city.group(1).lower())
        if matched is not None:
            origin_city = matched[0]
    parking_from_text = ""
    if parking_at is not None and parking_at.group(1).upper() in KNOWN_AIRPORTS:
        parking_from_text = parking_at.group(1).upper()
    else:
        named_parking = re.search(r"\b([A-Za-z]{3})\s+parking\b", text, re.I)
        if named_parking is not None and named_parking.group(1).upper() in KNOWN_AIRPORTS:
            parking_from_text = named_parking.group(1).upper()
        elif airport_led:
            parking_from_text = named
        else:
            from itaa_api.agent_requirements import parking_iata_from_text

            parking_from_text = parking_iata_from_text(text)
    destination = city[0] if city else _guess_city(text)
    city_airport = city[1] if city else ""
    if not destination and (hotel_stated or parking_word):
        named_place = _match_airport_place(lower)
        if named_place is not None:
            destination = named_place[0]
            city_airport = named_place[1]
    destination_airport = city_airport
    # Trip destination/departure are never parking evidence.
    parking_airport = parking_from_text
    exact = parse_exact_calendar(text)
    month_day = re.search(
        r"\b(?:\d{1,2}\s*[–-]\s*\d{1,2}\s+(?:january|february|march|april|may|june|july|"
        r"august|september|october|november|december|jan|feb|mar|apr|jun|jul|aug|sept?|"
        r"oct|nov|dec)(?:\s+\d{4})?)\b",
        text,
        re.I,
    )
    weekday = re.search(r"\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b", lower)
    has_exact = exact is not None
    has_loose = has_exact or weekday is not None or nights or month_day is not None
    dates = ""
    start_date = ""
    end_date = ""
    if exact is not None:
        dates = f"{exact[0]} to {exact[1]}" if exact[0] != exact[1] else exact[0]
        start_date, end_date = exact
    elif month_day is not None:
        dates = month_day.group(0).strip()
    elif weekday is not None:
        dates = weekday.group(1).title()
    part = ""
    if re.search(r"\bmorning\b", lower):
        part = "morning"
    elif re.search(r"\bafternoon\b", lower):
        part = "afternoon"
    elif re.search(r"\bevening\b|\btonight\b", lower):
        part = "evening"
    elif re.search(r"\banytime\b|\ball day\b", lower):
        part = "anytime"
    trip_like = (
        travel
        or landing
        or conference
        or nights
        or (destination != "" and not parking_stated)
        or (destination != "" and rental_stated)
    )
    car_need = ""
    if answers is not None and answers.carNeed in {"yes", "no", "unsure"}:
        car_need = answers.carNeed
    elif rental_stated:
        car_need = (
            "no" if re.search(r"\b(no car|without a car|don't need a car)\b", lower) else "yes"
        )
    if answers is not None and answers.departureAirport.strip():
        departure = answers.departureAirport.strip().upper()
    overlay = _structured_date_overlay(answers)
    if overlay is not None:
        dates, has_exact, has_loose, start_date, end_date = overlay
    start_date, end_date = _overlay_checkout(text, start_date, end_date)
    if not start_date and not _unresolved_calendar_range(text):
        anchor = parse_anchor_date(text)
        if anchor:
            start_date = end_date or anchor
            end_date = end_date or anchor
    if start_date and (not end_date or start_date == end_date):
        start_date, end_date = apply_stay_duration(start_date, end_date or start_date, text)
    if start_date:
        start_date = rewrite_past_iso_if_year_omitted(start_date, text)
    if end_date:
        end_date = rewrite_past_iso_if_year_omitted(end_date, text)
    if start_date and end_date:
        dates = f"{start_date} to {end_date}" if start_date != end_date else start_date
        has_exact = True
        has_loose = True
    help_with = ""
    if answers is not None and answers.helpWith:
        help_with = answers.helpWith
    if help_with == "stay":
        hotel_stated = True
    elif help_with == "rental":
        rental_stated = True
        if car_need == "":
            car_need = "yes"
    elif help_with == "parking":
        parking_stated = True
    elif help_with == "flights_sorted":
        flight_satisfied = True
        flight_stated = False
    elif help_with == "experience":
        experience_stated = True
    experience_preferences = _experience_preferences(lower)
    return ExtractedFacts(
        destination=destination,
        originCity=origin_city,
        destinationAirport=destination_airport,
        parkingAirport=parking_airport,
        departureAirport=departure,
        dates=dates,
        hasExactDates=has_exact,
        hasLooseDates=has_loose,
        startDate=start_date,
        endDate=end_date,
        carNeed=car_need if car_need in {"yes", "no", "unsure", ""} else "",
        parkingStated=parking_stated,
        rentalStated=rental_stated,
        entsStated=ents_stated,
        hotelStated=hotel_stated,
        experienceStated=experience_stated,
        experiencePreferences=experience_preferences,
        flightStated=flight_stated,
        flightSatisfied=flight_satisfied,
        helpWith=(
            help_with
            if help_with
            in {"stay", "rental", "parking", "flights_sorted", "experience", "unsure", ""}
            else ""
        ),
        landing=landing,
        travel=travel,
        conference=conference,
        nights=nights,
        tripLike=trip_like,
        dayPart=part if part in {"morning", "afternoon", "evening", "anytime", ""} else "",
        timeFlexible=bool(re.search(r"\bflexible\b|\banytime\b", lower)),
    )


def _structured_date_overlay(
    answers: PlanAnswers | None,
) -> tuple[str, bool, bool, str, str] | None:
    """Consume PlanAnswers date fields. No natural-language alias parsing."""

    if answers is None:
        return None
    start = answers.startDate.strip()
    end = answers.endDate.strip()
    raw = answers.dates.strip()
    if not start and not end and not raw:
        return None
    source = raw
    if start and end:
        source = f"{start} to {end}"
    elif start:
        source = start
    elif end:
        source = end
    parsed = parse_exact_calendar(source)
    if parsed is None and raw and source != raw:
        parsed = parse_exact_calendar(raw)
    if parsed is not None:
        label = f"{parsed[0]} to {parsed[1]}" if parsed[0] != parsed[1] else parsed[0]
        return label, True, True, parsed[0], parsed[1]
    return source or raw, True, True, start, end


def parse_exact_calendar(text: str) -> tuple[str, str] | None:
    iso = re.search(r"\b(\d{4}-\d{2}-\d{2})\s*(?:to|[–-])\s*(\d{4}-\d{2}-\d{2})\b", text)
    if iso:
        return _ordered_range(iso.group(1), iso.group(2))
    month = (
        r"(january|february|march|april|may|june|july|august|september|october|"
        r"november|december|jan|feb|mar|apr|jun|jul|aug|sept?|oct|nov|dec)"
    )
    spanned = re.search(
        rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s*(?:to|[–-]|until|through)\s*"
        rf"(?:the\s+)?(\d{{1,2}})(?:st|nd|rd|th)?\s+{month}(?:\s+(\d{{4}}))?\b",
        text,
        re.I,
    )
    if spanned:
        start = resolve_ymd(spanned.group(3), int(spanned.group(1)), spanned.group(4))
        end = resolve_ymd(spanned.group(3), int(spanned.group(2)), spanned.group(4))
        if start and end:
            return _ordered_range(start, end)
    same = re.search(
        rf"\b(\d{{1,2}})\s*[–-]\s*(\d{{1,2}})\s+{month}(?:\s+(\d{{4}}))?\b",
        text,
        re.I,
    )
    if same:
        start = resolve_ymd(same.group(3), int(same.group(1)), same.group(4))
        end = resolve_ymd(same.group(3), int(same.group(2)), same.group(4))
        if start and end:
            return _ordered_range(start, end)
    dual = re.finditer(
        r"\b(january|february|march|april|may|june|july|august|september|october|"
        r"november|december|jan|feb|mar|apr|jun|jul|aug|sept?|oct|nov|dec)"
        r"\.?\s+(\d{1,2})(?:st|nd|rd|th)?(?:\s+(\d{4}))?\b",
        text,
        re.I,
    )
    hits = list(dual)
    if len(hits) >= 2:
        start = resolve_ymd(
            hits[0].group(1), int(hits[0].group(2)), hits[0].group(3) or hits[1].group(3)
        )
        end = resolve_ymd(
            hits[1].group(1), int(hits[1].group(2)), hits[1].group(3) or hits[0].group(3)
        )
        if start and end:
            return _ordered_range(start, end)
    named = re.search(
        r"\b(january|february|march|april|may|june|july|august|september|october|"
        r"november|december|jan|feb|mar|apr|jun|jul|aug|sept?|oct|nov|dec)"
        r"\.?\s+(\d{1,2})\s*[–-]\s*(\d{1,2})(?:\s+(\d{4}))?\b",
        text,
        re.I,
    )
    if named:
        start = resolve_ymd(named.group(1), int(named.group(2)), named.group(4))
        end = resolve_ymd(named.group(1), int(named.group(3)), named.group(4))
        if start and end:
            return _ordered_range(start, end)
    month_pat = (
        r"(january|february|march|april|may|june|july|august|september|october|"
        r"november|december|jan|feb|mar|apr|jun|jul|aug|sept?|oct|nov|dec)"
    )
    leading_month = re.search(
        rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+{month_pat}(?:\s+(\d{{4}}))?\s*"
        rf"(?:to|[–-]|until|through)\s*(?:the\s+)?"
        rf"(\d{{1,2}})(?:st|nd|rd|th)?(?!\s*(?:am|pm))(?:\s+{month_pat})?(?:\s+(\d{{4}}))?\b",
        text,
        re.I,
    )
    if leading_month:
        start = resolve_ymd(
            leading_month.group(2), int(leading_month.group(1)), leading_month.group(3)
        )
        end = resolve_ymd(
            leading_month.group(5) or leading_month.group(2),
            int(leading_month.group(4)),
            leading_month.group(6) or leading_month.group(3),
        )
        if start and end:
            return _ordered_range(start, end)
    single = parse_anchor_date(text)
    if single:
        return single, single
    return None


def select_clarifications(facts: ExtractedFacts) -> list[BlockingQuestion]:
    questions: list[BlockingQuestion] = []
    parking_active = facts.parkingStated or facts.landing
    if facts.parkingStated:
        if not facts.hasExactDates:
            questions.append(
                BlockingQuestion(
                    id="dates",
                    label="Exact dates",
                    why="Sets parking duration, car hire window and hotel nights.",
                )
            )
        return questions[:PLAN_QUESTION_CAP]
    if not facts.hasExactDates:
        questions.append(
            BlockingQuestion(
                id="dates",
                label="Exact dates",
                why="Sets parking duration, car hire window and hotel nights.",
            )
        )
    if (
        facts.tripLike
        and facts.departureAirport == ""
        and facts.originCity == ""
        and (parking_active or facts.flightStated)
    ):
        questions.append(
            BlockingQuestion(
                id="departureAirport",
                label="Departing from",
                why="Only the airport code reaches parking suppliers. Not your address.",
            )
        )
    if facts.tripLike and facts.carNeed == "" and (parking_active or facts.rentalStated):
        place = facts.destination or "your destination"
        questions.append(
            BlockingQuestion(
                id="carNeed",
                label=f"Will you need a car in {place}?",
                why="Confirms whether a rental-car task belongs on this plan.",
            )
        )
    return questions[:PLAN_QUESTION_CAP]


def base_tasks(facts: ExtractedFacts, answers: PlanAnswers, objective: str = "") -> list[PlanTask]:
    tasks: list[PlanTask] = []
    where = facts.destination or facts.parkingAirport or "the airport"
    car = answers.carNeed or facts.carNeed
    parking = facts.parkingStated or facts.landing
    if parking:
        provenance: TaskProvenance = "explicit" if facts.parkingStated else "inferred"
        tasks.append(
            _task(
                "parking",
                provenance,
                provenance == "explicit",
                _parking_detail(facts, provenance, where),
            )
        )
    if car == "yes" or facts.rentalStated:
        provenance = "explicit" if facts.rentalStated else "inferred"
        tasks.append(
            _task(
                "rental",
                provenance,
                provenance == "explicit",
                _rental_detail(provenance, where),
            )
        )
    elif car == "unsure":
        tasks.append(
            _task(
                "rental",
                "proposed",
                False,
                f"You were not sure about a car in {where}. Proposed only.",
            )
        )
    if facts.entsStated:
        tasks.append(
            _task(
                "ents",
                "explicit",
                True,
                "Taken from your objective. This remains a demonstration task in this build.",
            )
        )
    if facts.experienceStated:
        tasks.append(
            _task(
                "experience",
                "explicit",
                True,
                "You asked for things to do, attractions, or experiences.",
            )
        )
    flight_route = bool(_FLIGHT_ROUTE.search(objective))
    inferred_flight = (
        bool(facts.originCity and facts.destination)
        and (facts.hasExactDates or facts.hasLooseDates)
        and not other_transport_stated(objective)
        and facts.tripLike
        and not facts.flightSatisfied
    )
    if not facts.flightSatisfied and (
        flight_route
        or (facts.tripLike and (facts.landing or facts.flightStated))
        or inferred_flight
    ):
        provenance = "explicit" if facts.flightStated or flight_route else "proposed"
        tasks.append(
            _task(
                "flight",
                provenance,
                provenance == "explicit",
                "You mentioned a flight."
                if provenance == "explicit"
                else (
                    f"Inferred from travelling from {facts.originCity} to {where}. "
                    "Inactive until you accept it."
                    if facts.originCity
                    else f"Inferred from travelling to {where}. Inactive until you accept it."
                ),
            )
        )
    if facts.hotelStated:
        tasks.append(
            _task(
                "hotel",
                "explicit",
                True,
                "You mentioned accommodation.",
            )
        )
    elif facts.conference or facts.nights:
        tasks.append(
            _task(
                "hotel",
                "proposed",
                False,
                "You mentioned accommodation."
                if facts.hotelStated
                else f"A stay is often needed for a conference in {where}. Proposed only."
                if facts.conference
                else f"A stay is often needed in {where}. Proposed only.",
            )
        )
    return tasks


def project_plan(
    objective: str,
    answers: PlanAnswers | None = None,
    model_turn: PlanTurn | None = None,
) -> PlanProjection:
    resolved = answers or PlanAnswers()
    facts = extract_facts(objective, resolved)
    if model_turn is not None:
        facts = _overlay_model_trip_facts(facts, model_turn)
    facts = _canonicalize_fact_years(facts, objective)
    questions = select_clarifications(facts)
    tasks = base_tasks(facts, resolved, objective)
    if model_turn is not None:
        tasks = _downgrade_unearned_explicit(objective, facts, tasks, model_turn)
    visible = _sort_plan_tasks(
        [task for task in tasks if task.accepted or task.provenance in {"proposed", "inferred"}]
    )
    confirmed = [task for task in visible if task.accepted and task.provenance != "proposed"]
    proposed = [task for task in visible if task.provenance == "proposed"]
    phase_value = "clarify" if questions else "forming"
    where = facts.destination or facts.parkingAirport or "your trip"
    return PlanProjection(
        facts=facts,
        questions=questions,
        tasks=visible,
        phase=phase_value,
        title=where,
        summary=_summary(len(confirmed), len(proposed), len(questions), phase_value),
        confirmedCount=len(confirmed),
        proposedCount=len(proposed),
    )


def evidence_for_kind(objective: str, kind: TaskKind) -> list[dict[str, object]]:
    spans: list[dict[str, object]] = []
    lower = objective.lower()
    for needle in _EXPLICIT_KIND_NEEDLES.get(kind, ()):
        start = lower.find(needle)
        if start >= 0:
            spans.append({"field": kind, "start": start, "end": start + len(needle)})
    return spans


def _safe_model_place(raw: str) -> str:
    token = raw.strip().split(",")[0].strip()
    if len(token) < 3 or token.lower() in _CITY_STOP:
        return ""
    if token.upper() in KNOWN_AIRPORTS:
        return ""
    if re.fullmatch(r"[A-Za-z][A-Za-z .'-]{1,60}", token) is None:
        return ""
    return token


def _canonicalize_fact_years(facts: ExtractedFacts, objective: str) -> ExtractedFacts:
    if not facts.startDate:
        return facts
    start = rewrite_past_iso_if_year_omitted(facts.startDate, objective)
    end = rewrite_past_iso_if_year_omitted(facts.endDate or facts.startDate, objective)
    if start == facts.startDate and end == (facts.endDate or facts.startDate):
        return facts
    return facts.model_copy(
        update={
            "startDate": start,
            "endDate": end,
            "dates": f"{start} to {end}" if start != end else start,
            "hasExactDates": True,
            "hasLooseDates": True,
        }
    )


def _overlay_model_trip_facts(facts: ExtractedFacts, model_turn: PlanTurn) -> ExtractedFacts:
    """Trust Bedrock-named city/dates when the regex gazetteer missed them."""

    patch: dict[str, object] = {}
    if not facts.destination:
        named = _safe_model_place(model_turn.facts.destination)
        if named:
            patch["destination"] = named
            patch["tripLike"] = True
    if not facts.hasExactDates:
        start = model_turn.facts.startDate.strip()
        end = model_turn.facts.endDate.strip()
        ordered = _ordered_range(start, end) if start and end else None
        if ordered is not None:
            patch["startDate"] = ordered[0]
            patch["endDate"] = ordered[1]
            patch["hasExactDates"] = True
            patch["hasLooseDates"] = True
            patch["dates"] = f"{ordered[0]} to {ordered[1]}"
    if not patch:
        return facts
    return facts.model_copy(update=patch)


def _downgrade_unearned_explicit(
    objective: str,
    facts: ExtractedFacts,
    tasks: list[PlanTask],
    model_turn: PlanTurn,
) -> list[PlanTask]:
    earned = _earned_explicit(objective, facts, model_turn)
    out: list[PlanTask] = []
    for task in tasks:
        if task.provenance == "explicit" and task.kind not in earned:
            out.append(task.model_copy(update={"provenance": "proposed", "accepted": False}))
            continue
        out.append(task)
    model_by_kind = {item.kind: item.provenance for item in model_turn.suggestedTasks}
    adjusted: list[PlanTask] = []
    for task in out:
        suggested = model_by_kind.get(task.kind)
        if suggested == "explicit" and task.kind not in earned:
            adjusted.append(
                task.model_copy(update={"provenance": "inferred" if task.accepted else "proposed"})
            )
            continue
        if (
            suggested in {"inferred", "proposed"}
            and task.provenance == "explicit"
            and task.kind not in earned
        ):
            adjusted.append(
                task.model_copy(
                    update={"provenance": suggested, "accepted": suggested != "proposed"}
                )
            )
            continue
        adjusted.append(task)
    return adjusted


def _earned_explicit(objective: str, facts: ExtractedFacts, model_turn: PlanTurn) -> set[TaskKind]:
    earned: set[TaskKind] = set()
    if facts.parkingStated:
        earned.add("parking")
    if facts.rentalStated:
        earned.add("rental")
    if facts.entsStated:
        earned.add("ents")
    if facts.experienceStated:
        earned.add("experience")
    if facts.flightStated:
        earned.add("flight")
    if facts.hotelStated:
        earned.add("hotel")
    lower = objective.lower()
    for span in model_turn.evidence:
        if span.field not in TASK_META:
            continue
        if not (0 <= span.start < span.end <= len(objective)):
            continue
        snippet = lower[span.start : span.end]
        for kind, needles in _EXPLICIT_KIND_NEEDLES.items():
            if span.field != kind:
                continue
            if kind == "rental" and not _car_mentioned(snippet) and not _car_mentioned(lower):
                continue
            if (
                kind == "hotel"
                and snippet.strip() == "stay"
                and not facts.hotelStated
                and not re.search(
                    r"\b(hotel|accommodation|place to stay|need(?:ed)? a stay)\b",
                    lower,
                )
            ):
                continue
            if any(needle in snippet for needle in needles):
                earned.add(kind)
                break
    return earned


def capabilities() -> dict[str, object]:
    from itaa_api.agent_requirements import capabilities_catalog

    catalog = capabilities_catalog()
    support = catalog.get("support")
    payload: dict[str, object] = dict(support) if isinstance(support, dict) else {}
    payload["catalog"] = catalog
    return payload


def _task(kind: TaskKind, provenance: TaskProvenance, accepted: bool, detail: str) -> PlanTask:
    code, title, support, support_label = TASK_META[kind]
    return PlanTask(
        id=f"task-{kind}",
        kind=kind,
        code=code,
        title=title,
        detail=detail,
        provenance=provenance,
        support=support,
        supportLabel=support_label,
        accepted=accepted,
    )


def _parking_detail(facts: ExtractedFacts, provenance: TaskProvenance, where: str) -> str:
    place = facts.parkingAirport or where
    if provenance == "explicit":
        if facts.parkingAirport:
            return f"You asked for airport parking at {facts.parkingAirport}."
        return f"You asked for airport parking in {place}."
    if facts.parkingAirport:
        return f"Parking is inferred for arrival at {facts.parkingAirport}."
    return f"Parking is inferred for arrival in {place}."


def _rental_detail(provenance: TaskProvenance, where: str) -> str:
    if provenance == "explicit":
        return f"You asked for a car in {where}."
    return f"A car is inferred for {where}."


def buyer_invite_copy(facts: ExtractedFacts) -> str:
    """Acknowledge known trip facts. Do not re-ask a named destination or dates."""

    from itaa_api.agent_requirements import usable_capability_invite

    invite = usable_capability_invite()
    origin = f" from {facts.originCity}" if facts.originCity else ""
    if facts.destination and facts.hasExactDates:
        return f"I have {facts.destination}{origin} and the dates. {invite}"
    if facts.destination:
        return f"I have {facts.destination}{origin}. When are you travelling? {invite}"
    if facts.hasExactDates:
        return f"I have the dates. Where are you travelling? {invite}"
    return f"Where and when are you travelling? {invite}"


_DOMAIN_ORDER: Final[dict[TaskKind, int]] = {
    "flight": 0,
    "hotel": 1,
    "rental": 2,
    "parking": 3,
    "experience": 4,
    "ents": 5,
}


def _task_rank(task: PlanTask) -> int:
    return _DOMAIN_ORDER.get(task.kind, 9)


def _sort_plan_tasks(tasks: list[PlanTask]) -> list[PlanTask]:
    return sorted(tasks, key=_task_rank)


def _summary(confirmed: int, proposed: int, questions: int, phase: str) -> str:
    if phase == "clarify":
        return f"{questions} question(s) still block the plan."
    return f"{confirmed} confirmed task(s), {proposed} proposed."


def _parse_route(text: str) -> tuple[str, str]:
    """Return (destination fragment, origin fragment) without treating dates as cities."""

    to_from = re.search(
        r"\bto\s+([A-Za-z][A-Za-z .'-]+?)\s+from\s+([A-Za-z][A-Za-z .'-]+?)"
        r"(?=\s+from\s+\d|\s+on\b|\s+\d{1,2}\b|\s*$)",
        text,
        re.I,
    )
    if to_from:
        return to_from.group(1).strip(), to_from.group(2).strip()
    from_to = re.search(
        r"\bfrom\s+([A-Za-z][A-Za-z .'-]+?)\s+to\s+([A-Za-z][A-Za-z .'-]+?)"
        r"(?=\s+for\b|\s+from\s+\d|\s+on\b|\s*$)",
        text,
        re.I,
    )
    if from_to:
        return from_to.group(2).strip(), from_to.group(1).strip()
    return "", ""


def _month_num(raw: str) -> str:
    token = raw.lower().rstrip(".")
    return MONTHS.get(token, MONTHS.get(token[:3], ""))


def _ents_stated(lower: str) -> bool:
    if _ENTS_RE.search(lower):
        return True
    if _SHOW_ME_RE.search(lower):
        cleaned = _SHOW_ME_RE.sub(" ", lower)
        return bool(_SHOW_NOUN_RE.search(cleaned))
    return bool(_SHOW_NOUN_RE.search(lower))


def _experience_preferences(lower: str) -> list[str]:
    prefs: list[str] = []
    if re.search(r"\bevening\b|\btonight\b", lower):
        prefs.append("evening")
    if re.search(r"\bfamily[-\s]?friendly\b", lower):
        prefs.append("family-friendly")
    if re.search(r"\bmuseums?\b", lower):
        prefs.append("museum")
    if re.search(r"\btours?\b", lower):
        prefs.append("tour")
    if re.search(r"\bcity\s+centre\b|\bcity\s+center\b|\bdowntown\b", lower):
        prefs.append("city-centre")
    return prefs


def _overlay_checkout(text: str, start_date: str, end_date: str) -> tuple[str, str]:
    if not start_date:
        return start_date, end_date
    month = (
        r"(january|february|march|april|may|june|july|august|september|october|"
        r"november|december|jan|feb|mar|apr|jun|jul|aug|sept?|oct|nov|dec)"
    )
    named = re.search(
        rf"\bcheck[-\s]?out(?:\s+date)?\s+to(?:\s+the)?\s+(\d{{1,2}})(?:st|nd|rd|th)?"
        rf"(?:\s+{month})?(?:\s+(\d{{4}}))?\b",
        text,
        re.I,
    )
    if named is None:
        return start_date, end_date
    day = int(named.group(1))
    month_token = named.group(2)
    year_token = named.group(3)
    if month_token:
        month_num = _month_num(month_token)
    elif end_date:
        month_num = end_date[5:7]
    else:
        month_num = start_date[5:7]
    year = year_token or (end_date[:4] if end_date else start_date[:4])
    if not month_num:
        return start_date, end_date
    new_end = f"{year}-{month_num}-{day:02d}"
    ordered = _ordered_range(start_date, new_end)
    return ordered if ordered is not None else (start_date, end_date)


def _car_mentioned(lower: str) -> bool:
    cleaned = _CAR_PARKING_RE.sub(" ", lower)
    return bool(_CAR_RENTAL_RE.search(cleaned))


def _ordered_range(start: str, end: str) -> tuple[str, str] | None:
    if start > end:
        return None
    return start, end


def _plausible_city(token: str) -> bool:
    cleaned = " ".join(token.strip().lower().split())
    if len(cleaned) < 3 or cleaned in _CITY_STOP:
        return False
    if "'" in cleaned:
        return False
    if any(part in _CITY_STOP for part in cleaned.split()):
        return False
    if cleaned.upper() in KNOWN_AIRPORTS:
        return False
    return bool(re.fullmatch(r"[a-z][a-z .'-]{1,40}", cleaned))


def _unresolved_calendar_range(text: str) -> bool:
    month = (
        r"(january|february|march|april|may|june|july|august|september|october|"
        r"november|december|jan|feb|mar|apr|jun|jul|aug|sept?|oct|nov|dec)"
    )
    return (
        re.search(
            rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+{month}(?:\s+(\d{{4}}))?\s*"
            rf"(?:to|[–-]|until|through)\s*(?:the\s+)?"
            rf"(\d{{1,2}})(?:st|nd|rd|th)?(?!\s*(?:am|pm))",
            text,
            re.I,
        )
        is not None
    )


def _guess_city(text: str) -> str:
    to_place = re.search(
        r"\b(?:to|in)\s+([A-Za-z][A-Za-z .'-]{1,40}?)(?=\s+(?:\d|from\s+\d|,|;|$))",
        text,
        re.I,
    )
    if to_place is not None and _plausible_city(to_place.group(1)):
        return to_place.group(1).strip().title()
    leading = re.match(r"^([A-Za-z][A-Za-z'-]{2,32})\b", text.strip())
    if leading is not None and _plausible_city(leading.group(1)):
        return leading.group(1).title()
    return ""


def _match_city(lower: str) -> tuple[str, str] | None:
    for pattern, city, airport in CITY_AIRPORTS:
        if pattern.search(lower):
            return city, airport
    skip = {place.lower() for _, place, _code in AIRPORT_PLACES}
    skip.update({"london heathrow", "heathrow", "gatwick", "stansted"})
    for slug in sorted(CITY_COUNTRY, key=len, reverse=True):
        if slug in skip:
            continue
        if re.search(rf"\b{re.escape(slug)}\b", lower):
            name, _country, _currency = CITY_COUNTRY[slug]
            airport = next(
                (code for _, labelled, code in CITY_AIRPORTS if labelled == name),
                "",
            )
            return name, airport
    return None


def _match_airport_place(lower: str) -> tuple[str, str] | None:
    for pattern, place, code in AIRPORT_PLACES:
        if pattern.search(lower):
            return place, code
    return None
