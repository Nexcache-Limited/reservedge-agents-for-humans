"""Typed pending provider-search authorization.

The model never dispatches a supplier. A buyer affirmative executes only the
exact capabilities recorded in pendingSearchAuthorization. Requirement changes
invalidate that record.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

SearchCapability = str

STAY = "stay.search"
PARKING = "parking.search"
EXPERIENCE = "experience.search"
FLIGHT = "flight.search"

RESULTS_LOCATION = "in the panel on the right"

_AFFIRM_LEAD = re.compile(
    r"^(?:yes|yeah|yep|yup|ok|okay|sure)(?: (?:please(?: do)?|go ahead|proceed|"
    r"search(?: both| them| now)?|do it))*$",
    re.I,
)
_AFFIRM_BARE = re.compile(
    r"^(?:please(?: do)?|go ahead|proceed|search both|search them|search now|"
    r"search please|do it)$",
    re.I,
)
_NAMED_CAPS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (FLIGHT, re.compile(r"\bflights?\b", re.I)),
    (STAY, re.compile(r"\bhotels?\b|\bstays?\b", re.I)),
    (PARKING, re.compile(r"\bparking\b", re.I)),
    (EXPERIENCE, re.compile(r"\b(?:sightseeing|things to do|experiences?)\b", re.I)),
)
_STAY_PARKING_RE = re.compile(
    r"\b(?:search )?(?:the )?(?:hotel|stay) and parking(?: first)?\b|"
    r"\bparking and (?:the )?(?:hotel|stay)(?: first)?\b",
    re.I,
)
_STAY_ONLY_RE = re.compile(
    r"\b(hotel first|stay first|hotels? only|just (?:the )?hotel|just stay|"
    r"search (?:the )?hotel|search stay)\b",
    re.I,
)
_PARKING_ONLY_RE = re.compile(
    r"\b(parking first|parking only|just parking|search parking|"
    r"request parking)\b",
    re.I,
)
_EXPERIENCE_ONLY_RE = re.compile(
    r"\b(experience first|experiences? only|just (?:the )?experience|"
    r"things to do only)\b",
    re.I,
)
_FLIGHT_ONLY_RE = re.compile(
    r"\b(flight first|flights? only|just (?:the )?flight|search (?:the )?flight)\b",
    re.I,
)
_FLIGHT_RE = re.compile(
    r"\b(book(?:ing)? (?:a |the )?flights?|flight booking|search (?:for )?flights?|"
    r"(?:need|needed) (?:a )?flights?|flights? (?:to|from|needed)|"
    r"(?:want to |i want to )?(?:fly|flying) from)\b",
    re.I,
)


def public_pending(pending: Mapping[str, object] | None) -> dict[str, object] | None:
    if not isinstance(pending, Mapping) or not pending.get("capabilities"):
        return None
    raw_caps = pending.get("capabilities")
    capabilities = (
        [str(item) for item in raw_caps if isinstance(item, str)]
        if isinstance(raw_caps, Sequence)
        else []
    )
    fingerprints = pending.get("fingerprints")
    return {
        "capabilities": capabilities,
        "fingerprints": dict(fingerprints) if isinstance(fingerprints, Mapping) else {},
        "prompt": str(pending.get("prompt") or ""),
    }


def fingerprints_match(pending: Mapping[str, object] | None, current: Mapping[str, str]) -> bool:
    if not isinstance(pending, Mapping):
        return False
    held = pending.get("fingerprints")
    if not isinstance(held, Mapping):
        return False
    capabilities = pending.get("capabilities")
    if not isinstance(capabilities, Sequence):
        return False
    for capability in capabilities:
        key = str(capability)
        if current.get(key) != str(held.get(key) or ""):
            return False
        if not current.get(key):
            return False
    return True


def match_confirmation(
    message: str, pending: Mapping[str, object] | None
) -> tuple[str, ...] | None:
    """Map a buyer reply onto the exact pending search authorization.

    A generic yes executes the full pending set. Subset phrases such as
    "hotel first" execute only that offered capability.
    """

    if not isinstance(pending, Mapping):
        return None
    raw_caps = pending.get("capabilities")
    offered = (
        tuple(str(item) for item in raw_caps if isinstance(item, str))
        if isinstance(raw_caps, Sequence)
        else ()
    )
    if not offered:
        return None
    text = message.strip()
    if not text:
        return None
    named = _named_capabilities(text, offered)
    if len(named) >= 2:
        return named
    if _STAY_PARKING_RE.search(text) and STAY in offered and PARKING in offered:
        return (STAY, PARKING)
    if len(named) <= 1:
        if (
            _STAY_ONLY_RE.search(text)
            and STAY in offered
            and PARKING not in named
            and named in ((), (STAY,))
        ):
            return (STAY,)
        if _PARKING_ONLY_RE.search(text) and PARKING in offered and named in ((), (PARKING,)):
            return (PARKING,)
        if (
            _EXPERIENCE_ONLY_RE.search(text)
            and EXPERIENCE in offered
            and named in ((), (EXPERIENCE,))
        ):
            return (EXPERIENCE,)
        if _FLIGHT_ONLY_RE.search(text) and FLIGHT in offered and named in ((), (FLIGHT,)):
            return (FLIGHT,)
    if named in {(STAY,), (PARKING,), (FLIGHT,), (EXPERIENCE,)} and not _is_generic_yes(text):
        return named
    if _is_generic_yes(text):
        return offered
    if named:
        return named
    return None


def _named_capabilities(text: str, offered: tuple[str, ...]) -> tuple[str, ...]:
    found = [cap for cap, pattern in _NAMED_CAPS if cap in offered and pattern.search(text)]
    return tuple(item for item in (FLIGHT, STAY, PARKING, EXPERIENCE) if item in found)


def _is_generic_yes(text: str) -> bool:
    cleaned = re.sub(r"\s+", " ", re.sub(r"[!?.,]+", " ", text).strip()).strip()
    if not cleaned:
        return False
    return (
        _AFFIRM_LEAD.fullmatch(cleaned) is not None or _AFFIRM_BARE.fullmatch(cleaned) is not None
    )


def flight_requested(text: str) -> bool:
    return _FLIGHT_RE.search(text) is not None


def search_ask_prompt(capabilities: Sequence[str], *, place: str) -> str:
    loc = place.strip() or "those dates"
    has_stay = STAY in capabilities
    has_parking = PARKING in capabilities
    has_experience = EXPERIENCE in capabilities
    has_flight = FLIGHT in capabilities
    if has_stay and has_parking and not has_experience and not has_flight:
        return (
            f"I have what I need to search for your hotel and covered parking at {loc}. "
            "Shall I search both now?"
        )
    ready = [
        name
        for item, name in (
            (has_flight, "flight"),
            (has_stay, "hotel"),
            (has_parking, "parking"),
            (has_experience, "things to do"),
        )
        if item
    ]
    if len(ready) >= 2:
        if len(ready) == 2:
            joined = f"{ready[0]} and {ready[1]}"
        else:
            joined = f"{', '.join(ready[:-1])}, and {ready[-1]}"
        return f"I have what I need to search for your {joined} at {loc}. Shall I search now?"
    if has_stay:
        return f"I have what I need to search for your hotel in {loc}. Shall I search now?"
    if has_parking:
        return (
            f"I have what I need to search for parking at {loc}. "
            "Shall I request offers from 3 isolated simulated suppliers?"
        )
    if has_experience:
        return f"I have what I need to search for things to do in {loc}. Shall I search now?"
    if has_flight:
        return "I have what I need to search for your flight. Shall I search now?"
    return "I have what I need to search. Shall I search now?"


def results_copy(
    dispatched: Sequence[str],
    results: Mapping[str, Any],
    *,
    location: str = RESULTS_LOCATION,
    execution: Sequence[Mapping[str, Any]] | None = None,
) -> str:
    outcomes = _execution_outcomes(dispatched, results, execution)
    succeeded = [
        item for item in (FLIGHT, STAY, PARKING, EXPERIENCE) if outcomes.get(item) == "succeeded"
    ]
    empty = [item for item in (FLIGHT, STAY, PARKING, EXPERIENCE) if outcomes.get(item) == "empty"]
    failed = [
        item for item in (FLIGHT, STAY, PARKING, EXPERIENCE) if outcomes.get(item) == "failed"
    ]
    ready_names = [_domain_noun(item, offers=True) for item in succeeded]
    parts: list[str] = []
    inventory = [item for item in succeeded if item in {FLIGHT, STAY}]
    parking_ok = PARKING in succeeded
    if inventory:
        names = [_domain_noun(item, offers=False) for item in inventory]
        joined = _join_nouns(names)
        parts.append(f"{joined} search results are ready and available {location}.")
        if parking_ok:
            parts.append("Parking offers are available there as well.")
    elif parking_ok:
        parts.append(f"Parking offers are available {location}.")
    elif EXPERIENCE in succeeded:
        parts.append(f"Things to do are listed {location}.")
    for item in empty:
        parts.append(_empty_copy(item))
    for item in failed:
        parts.append(_failed_copy(item))
    if not parts and ready_names:
        parts.append(f"{_join_nouns(ready_names)} are ready {location}.")
    return " ".join(parts)


def _execution_outcomes(
    dispatched: Sequence[str],
    results: Mapping[str, Any],
    execution: Sequence[Mapping[str, Any]] | None,
) -> dict[str, str]:
    held: dict[str, str] = {}
    if execution:
        for item in execution:
            cap = str(item.get("capability") or "")
            outcome = str(item.get("outcome") or "")
            if cap:
                held[cap] = outcome
    for cap in dispatched:
        if cap in held:
            continue
        held[cap] = _infer_outcome(cap, results)
    return held


def _infer_outcome(capability: str, results: Mapping[str, Any]) -> str:
    if capability == STAY:
        stay = results.get("stay") if isinstance(results.get("stay"), Mapping) else {}
        status = str(stay.get("status") or "") if isinstance(stay, Mapping) else ""
        offers = stay.get("offers") if isinstance(stay, Mapping) else None
        count = len(offers) if isinstance(offers, list) else 0
        if status == "ok" and count:
            return "succeeded"
        if status == "ok":
            return "empty"
        return "failed"
    if capability == PARKING:
        parking = results.get("parking") if isinstance(results.get("parking"), Mapping) else {}
        offers = None
        if isinstance(parking, Mapping):
            offer_set = parking.get("offerSet")
            snapshot = offer_set.get("snapshot") if isinstance(offer_set, Mapping) else None
            offers = snapshot.get("offers") if isinstance(snapshot, Mapping) else None
        count = len(offers) if isinstance(offers, list) else 0
        return "succeeded" if count else "failed"
    if capability == EXPERIENCE:
        exp = results.get("experience") if isinstance(results.get("experience"), Mapping) else {}
        offers = exp.get("offers") if isinstance(exp, Mapping) else None
        count = len(offers) if isinstance(offers, list) else 0
        return "succeeded" if count else "empty"
    if capability == FLIGHT:
        flight = results.get("flight") if isinstance(results.get("flight"), Mapping) else {}
        status = str(flight.get("status") or "") if isinstance(flight, Mapping) else ""
        offers = flight.get("offers") if isinstance(flight, Mapping) else None
        count = len(offers) if isinstance(offers, list) else 0
        if count:
            return "succeeded"
        if status == "ok":
            return "empty"
        return "failed"
    return "failed"


def _domain_noun(capability: str, *, offers: bool) -> str:
    names = {
        FLIGHT: "Flight" if not offers else "flight",
        STAY: "hotel" if offers else "hotel",
        PARKING: "parking",
        EXPERIENCE: "things to do",
    }
    if capability == FLIGHT and not offers:
        return "Flight"
    if capability == STAY and not offers:
        return "hotel"
    return names.get(capability, capability)


def _join_nouns(names: Sequence[str]) -> str:
    cleaned = [item for item in names if item]
    if not cleaned:
        return ""
    if len(cleaned) == 1:
        token = cleaned[0]
        return token[:1].upper() + token[1:]
    if len(cleaned) == 2:
        left = cleaned[0][:1].upper() + cleaned[0][1:]
        return f"{left} and {cleaned[1]}"
    lead = ", ".join(cleaned[:-1])
    lead = lead[:1].upper() + lead[1:]
    return f"{lead}, and {cleaned[-1]}"


def _empty_copy(capability: str) -> str:
    if capability == STAY:
        return "Hotel search returned no properties for those dates."
    if capability == FLIGHT:
        return "Flight search returned nothing usable for that route."
    if capability == EXPERIENCE:
        return "Nothing is in the things-to-do catalog for that place in this build."
    if capability == PARKING:
        return "Parking search returned no simulated offers."
    return ""


def _failed_copy(capability: str) -> str:
    if capability == STAY:
        return "Hotel search failed. Nothing was booked."
    if capability == FLIGHT:
        return "Flight search failed and was not executed."
    if capability == PARKING:
        return "Parking search failed."
    if capability == EXPERIENCE:
        return "Things-to-do search failed."
    return f"{capability} failed."


def build_pending(
    capabilities: Sequence[str],
    fingerprints: Mapping[str, str],
    *,
    place: str,
) -> dict[str, object]:
    ordered = tuple(item for item in (FLIGHT, STAY, PARKING, EXPERIENCE) if item in capabilities)
    held = {key: fingerprints[key] for key in ordered if key in fingerprints}
    prompt = search_ask_prompt(ordered, place=place)
    return {
        "capabilities": list(ordered),
        "fingerprints": held,
        "prompt": prompt,
    }
