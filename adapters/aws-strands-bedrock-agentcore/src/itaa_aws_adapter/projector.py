"""Deterministic plan projector. Model provenance is never authoritative."""

from __future__ import annotations

import re
from typing import Final

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
    (re.compile(r"\blondon\b", re.I), "London", "LHR"),
    (re.compile(r"\bamsterdam\b", re.I), "Amsterdam", "AMS"),
    (re.compile(r"\bparis\b", re.I), "Paris", "CDG"),
    (re.compile(r"\bdublin\b", re.I), "Dublin", "DUB"),
    (re.compile(r"\bglasgow\b", re.I), "Glasgow", "GLA"),
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

TASK_META: Final[dict[TaskKind, tuple[str, str, TaskSupport, str]]] = {
    "parking": ("Pk", "Airport parking", "live_simulated", "Live simulated path"),
    "rental": ("Rc", "Rental car", "demonstration", "Demonstration task"),
    "ents": ("En", "Entertainment", "demonstration", "Demonstration task"),
    "flight": ("Fl", "Flight", "unsupported", "Unsupported in this build"),
    "hotel": ("Ht", "Hotel", "unsupported", "Unsupported in this build"),
}

_AIRPORT = re.compile(r"\b([A-Za-z]{3})\b")
_EXPLICIT_KIND_NEEDLES: Final[dict[TaskKind, tuple[str, ...]]] = {
    "parking": ("parking",),
    "rental": ("car", "rental"),
    "ents": ("ticket", "concert", "show", "entertainment", "gig"),
    "flight": ("flight", "flights", "flying"),
    "hotel": ("hotel", "accommodation", "place to stay"),
}


def extract_facts(objective: str, answers: PlanAnswers | None = None) -> ExtractedFacts:
    text = objective.strip()
    lower = text.lower()
    parking_word = bool(re.search(r"\bparking\b", lower))
    rental_stated = _car_mentioned(lower)
    ents_stated = bool(re.search(r"\b(ticket|concert|show|entertainment|gig)\b", lower))
    hotel_stated = bool(re.search(r"\b(hotel|accommodation|place to stay)\b", lower))
    flight_stated = bool(re.search(r"\b(flight|flights|flying)\b", lower))
    landing = bool(
        re.search(
            r"\b(when i land|when we land|when i arrive|when we arrive|land(?:ing)?)\b", lower
        )
    )
    conference = bool(re.search(r"\bconference\b", lower))
    travel = bool(re.search(r"\b(travell?ing|trip to|going to|visit(?:ing)?)\b", lower))
    nights = bool(re.search(r"\bnights?\b", lower))
    city = _match_city(lower)
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
    elif from_city is not None:
        matched = _match_city(from_city.group(1).lower())
        if matched is not None:
            departure = matched[1]
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
    destination = city[0] if city else ""
    city_airport = city[1] if city else ""
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
    return ExtractedFacts(
        destination=destination,
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
        flightStated=flight_stated,
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
        return iso.group(1), iso.group(2)
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
        year = spanned.group(4) or "2026"
        month_num = _month_num(spanned.group(3))
        if month_num:
            start = f"{year}-{month_num}-{int(spanned.group(1)):02d}"
            end = f"{year}-{month_num}-{int(spanned.group(2)):02d}"
            return start, end
    same = re.search(
        rf"\b(\d{{1,2}})\s*[–-]\s*(\d{{1,2}})\s+{month}(?:\s+(\d{{4}}))?\b",
        text,
        re.I,
    )
    if same:
        year = same.group(4) or "2026"
        month = _month_num(same.group(3))
        if month:
            start = f"{year}-{month}-{int(same.group(1)):02d}"
            end = f"{year}-{month}-{int(same.group(2)):02d}"
            return start, end
    dual = re.finditer(
        r"\b(january|february|march|april|may|june|july|august|september|october|"
        r"november|december|jan|feb|mar|apr|jun|jul|aug|sept?|oct|nov|dec)"
        r"\.?\s+(\d{1,2})(?:st|nd|rd|th)?(?:\s+(\d{4}))?\b",
        text,
        re.I,
    )
    hits = list(dual)
    if len(hits) >= 2:
        year = hits[0].group(3) or hits[1].group(3) or "2026"
        m1 = _month_num(hits[0].group(1))
        m2 = _month_num(hits[1].group(1))
        if m1 and m2:
            return (
                f"{year}-{m1}-{int(hits[0].group(2)):02d}",
                f"{year}-{m2}-{int(hits[1].group(2)):02d}",
            )
    named = re.search(
        r"\b(january|february|march|april|may|june|july|august|september|october|"
        r"november|december|jan|feb|mar|apr|jun|jul|aug|sept?|oct|nov|dec)"
        r"\.?\s+(\d{1,2})\s*[–-]\s*(\d{1,2})(?:\s+(\d{4}))?\b",
        text,
        re.I,
    )
    if named:
        year = named.group(4) or "2026"
        month = _month_num(named.group(1))
        if month:
            return (
                f"{year}-{month}-{int(named.group(2)):02d}",
                f"{year}-{month}-{int(named.group(3)):02d}",
            )
    return None


def select_clarifications(facts: ExtractedFacts) -> list[BlockingQuestion]:
    questions: list[BlockingQuestion] = []
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
    if facts.tripLike and facts.departureAirport == "":
        questions.append(
            BlockingQuestion(
                id="departureAirport",
                label="Departing from",
                why="Only the airport code reaches parking suppliers. Not your address.",
            )
        )
    if facts.tripLike and facts.carNeed == "":
        place = facts.destination or "your destination"
        questions.append(
            BlockingQuestion(
                id="carNeed",
                label=f"Will you need a car in {place}?",
                why="Confirms whether a rental-car task belongs on this plan.",
            )
        )
    return questions[:PLAN_QUESTION_CAP]


def base_tasks(facts: ExtractedFacts, answers: PlanAnswers) -> list[PlanTask]:
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
    if facts.tripLike and (facts.landing or facts.travel or facts.flightStated):
        provenance = "explicit" if facts.flightStated else "proposed"
        tasks.append(
            _task(
                "flight",
                provenance,
                provenance == "explicit",
                "You mentioned a flight."
                if provenance == "explicit"
                else f"Inferred from travelling to {where}. Inactive until you accept it.",
            )
        )
    if facts.conference or facts.hotelStated or facts.nights:
        provenance = "explicit" if facts.hotelStated else "proposed"
        tasks.append(
            _task(
                "hotel",
                provenance,
                provenance == "explicit",
                "You mentioned accommodation."
                if facts.hotelStated
                else f"A stay is often needed for a conference in {where}. Proposed only.",
            )
        )
    elif facts.tripLike and not facts.parkingStated:
        tasks.append(
            _task(
                "hotel",
                "proposed",
                False,
                f"A stay is often needed in {where}. Proposed only.",
            )
        )
    if not tasks:
        tasks.append(
            _task(
                "parking",
                "proposed",
                False,
                "No domain was named. Airport parking is proposed so you can confirm.",
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
    questions = select_clarifications(facts)
    tasks = base_tasks(facts, resolved)
    if model_turn is not None:
        tasks = _downgrade_unearned_explicit(objective, facts, tasks, model_turn)
    visible = [
        task for task in tasks if task.accepted or task.provenance in {"proposed", "inferred"}
    ]
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
            if span.field == kind and any(needle in snippet for needle in needles):
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


def _summary(confirmed: int, proposed: int, questions: int, phase: str) -> str:
    if phase == "clarify":
        return f"{questions} question(s) still block the plan."
    return f"{confirmed} confirmed task(s), {proposed} proposed."


def _month_num(raw: str) -> str:
    token = raw.lower().rstrip(".")
    return MONTHS.get(token, MONTHS.get(token[:3], ""))


def _car_mentioned(lower: str) -> bool:
    return bool(re.search(r"\b(car|rental car|hire car)\b", lower))


def _match_city(lower: str) -> tuple[str, str] | None:
    for pattern, city, airport in CITY_AIRPORTS:
        if pattern.search(lower):
            return city, airport
    return None
