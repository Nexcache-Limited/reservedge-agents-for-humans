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
    r"(?:need|needed) (?:a )?flights?|flights? (?:to|from|needed))\b",
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
    if _STAY_PARKING_RE.search(text) and STAY in offered and PARKING in offered:
        return (STAY, PARKING)
    if _STAY_ONLY_RE.search(text) and STAY in offered:
        return (STAY,)
    if _PARKING_ONLY_RE.search(text) and PARKING in offered:
        return (PARKING,)
    if _EXPERIENCE_ONLY_RE.search(text) and EXPERIENCE in offered:
        return (EXPERIENCE,)
    if _FLIGHT_ONLY_RE.search(text) and FLIGHT in offered:
        return (FLIGHT,)
    if _is_generic_yes(text):
        return offered
    return None


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


def results_copy(dispatched: Sequence[str], results: Mapping[str, Any]) -> str:
    parts: list[str] = []
    if STAY in dispatched:
        stay = results.get("stay") if isinstance(results.get("stay"), Mapping) else {}
        status = str(stay.get("status") or "") if isinstance(stay, Mapping) else ""
        offers = stay.get("offers") if isinstance(stay, Mapping) else None
        count = len(offers) if isinstance(offers, list) else 0
        if status == "ok" and count:
            parts.append(
                "I've found hotel options for those dates. They're displayed in the panel "
                "on the right. You can review them there, or tell me if you'd like more "
                "options or want to change anything."
            )
        elif status == "ok":
            parts.append(
                "I searched for hotels. No properties came back for those dates. "
                "Tell me if you'd like to change the stay details."
            )
        else:
            parts.append("Hotel search is unavailable right now. Nothing was booked.")
    if PARKING in dispatched:
        parking = results.get("parking") if isinstance(results.get("parking"), Mapping) else {}
        offers = None
        if isinstance(parking, Mapping):
            offer_set = parking.get("offerSet")
            snapshot = offer_set.get("snapshot") if isinstance(offer_set, Mapping) else None
            offers = snapshot.get("offers") if isinstance(snapshot, Mapping) else None
        count = len(offers) if isinstance(offers, list) else 0
        if count:
            parts.append(
                "Parking offers from the simulated suppliers are in the parking panel on the right."
            )
        else:
            parts.append(
                "I could not retrieve parking offers yet. Check the parking details "
                "and tell me if you'd like to try again."
            )
    if EXPERIENCE in dispatched:
        exp = results.get("experience") if isinstance(results.get("experience"), Mapping) else {}
        offers = exp.get("offers") if isinstance(exp, Mapping) else None
        count = len(offers) if isinstance(offers, list) else 0
        if count:
            parts.append("Things to do are listed in the panel on the right.")
        else:
            parts.append(
                "I looked for things to do. Nothing is in the catalog for that place in this build."
            )
    if FLIGHT in dispatched:
        flight = results.get("flight") if isinstance(results.get("flight"), Mapping) else {}
        offers = flight.get("offers") if isinstance(flight, Mapping) else None
        count = len(offers) if isinstance(offers, list) else 0
        if count:
            parts.append(
                "I've found flight options. They're displayed in the panel on the right. "
                "Selecting one is not a ticket."
            )
        else:
            parts.append(
                "I searched for flights. Nothing usable came back for that route. "
                "Tell me if you'd like to change the airports or date."
            )
    return " ".join(parts)


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
