"""Deterministic fake PlanTurns. Never silently maps generics onto JFK."""

from __future__ import annotations

import re
from typing import Literal

from itaa_aws_adapter.projector import (
    buyer_invite_copy,
    evidence_for_kind,
    extract_facts,
    parse_exact_calendar,
    select_clarifications,
)
from itaa_aws_adapter.schemas import (
    BlockingQuestion,
    EvidenceSpan,
    ExtractedFacts,
    PlanAnswers,
    PlanTurn,
    RequirementPatch,
    SuggestedTask,
)

DEMO_A_OBJECTIVE = (
    "I'm flying from JFK on September 3 at 1 PM and returning September 8 at 10 PM. "
    "I have a standard EV, prefer covered parking, and don't want a shuttle longer than 20 minutes."
)
DEMO_B_OBJECTIVE = (
    "I'm travelling from London to Edinburgh for a conference 14–19 October 2026 "
    "and I'll need a car when I land, somewhere near the venue."
)
DEMO_C_OBJECTIVE = "I'm going away next month and I'll need a car."


def normalize_objective(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def fake_plan_turn(objective: str, answers: PlanAnswers | None = None) -> PlanTurn:
    token = normalize_objective(objective)
    if token == normalize_objective(DEMO_A_OBJECTIVE):
        return _demo_a(objective, answers)
    if token == normalize_objective(DEMO_B_OBJECTIVE):
        return _demo_b(objective, answers)
    if token == normalize_objective(DEMO_C_OBJECTIVE):
        return _demo_c(objective, answers)
    return _generic(objective, answers)


def _demo_a(objective: str, answers: PlanAnswers | None = None) -> PlanTurn:
    facts = extract_facts(objective, answers)
    evidence = [EvidenceSpan(**item) for item in evidence_for_kind(objective, "parking")] + [
        EvidenceSpan(**item) for item in evidence_for_kind(objective, "flight")
    ]
    return PlanTurn(
        understanding="Airport parking at JFK for a dated trip.",
        facts=facts,
        evidence=evidence,
        blockingQuestions=[],
        suggestedTasks=[
            SuggestedTask(kind="parking", provenance="explicit"),
        ],
        buyerSafeMessage=(
            "Parking is the live simulated task. Confirm before suppliers are contacted."
        ),
        fallback=False,
    )


def _demo_b(objective: str, answers: PlanAnswers | None = None) -> PlanTurn:
    facts = extract_facts(objective, answers)
    evidence = [EvidenceSpan(**item) for item in evidence_for_kind(objective, "rental")]
    questions = []
    if not facts.hasExactDates:
        questions.append(
            BlockingQuestion(
                id="dates",
                label="Exact dates",
                why="Sets parking duration, car hire window and hotel nights.",
            )
        )
    return PlanTurn(
        understanding="Edinburgh conference trip with a car on arrival.",
        facts=facts,
        evidence=evidence,
        blockingQuestions=questions,
        suggestedTasks=[
            SuggestedTask(kind="rental", provenance="explicit"),
            SuggestedTask(kind="parking", provenance="inferred"),
            SuggestedTask(kind="hotel", provenance="proposed"),
            SuggestedTask(kind="flight", provenance="proposed"),
        ],
        buyerSafeMessage=(
            "Rental is explicit. Parking is inferred from landing. "
            "I still need a parking airport; Edinburgh is the destination, not parking evidence."
        ),
        fallback=False,
    )


def _demo_c(objective: str, answers: PlanAnswers | None = None) -> PlanTurn:
    facts = extract_facts(objective, answers)
    evidence = [EvidenceSpan(**item) for item in evidence_for_kind(objective, "rental")]
    questions: list[BlockingQuestion] = []
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
    return PlanTurn(
        understanding="A trip with a car is mentioned, but dates and destination are missing.",
        facts=facts,
        evidence=evidence,
        blockingQuestions=questions[:3],
        suggestedTasks=[SuggestedTask(kind="rental", provenance="explicit")],
        buyerSafeMessage="Need dates before a plan can be confirmed.",
        fallback=False,
    )


def _generic(objective: str, answers: PlanAnswers | None) -> PlanTurn:
    from itaa_api.agent_requirements import extract_conversation_patches

    facts = extract_facts(objective, answers)
    evidence: list[EvidenceSpan] = []
    for kind in ("parking", "rental", "ents", "flight", "hotel"):
        evidence.extend(EvidenceSpan(**item) for item in evidence_for_kind(objective, kind))
    questions = select_clarifications(facts)
    suggested: list[SuggestedTask] = []
    if facts.parkingStated:
        suggested.append(SuggestedTask(kind="parking", provenance="explicit"))
    if facts.rentalStated:
        suggested.append(SuggestedTask(kind="rental", provenance="explicit"))
    if facts.experienceStated:
        suggested.append(SuggestedTask(kind="experience", provenance="explicit"))
    named_component = (
        facts.parkingStated
        or facts.rentalStated
        or facts.hotelStated
        or facts.entsStated
        or facts.experienceStated
        or facts.flightStated
        or facts.carNeed != ""
    )
    if facts.hotelStated or facts.experienceStated:
        bits: list[str] = []
        if facts.hotelStated:
            if facts.destination and facts.hasExactDates:
                bits.append(
                    "Stay is on the plan. Hotel search is research only — nothing is booked."
                )
            else:
                bits.append(
                    "Stay is on the plan. I can look up hotels once destination and dates are set."
                )
        if facts.experienceStated:
            bits.append(
                "Experience search is research only — attractions and activities, not a booking."
            )
        if facts.rentalStated:
            bits.append("Rental is a requirement only — no rental inventory adapter is integrated.")
        message = " ".join(bits)
    elif facts.tripLike and not named_component:
        message = buyer_invite_copy(facts)
    elif facts.rentalStated and not facts.parkingStated:
        from itaa_api.agent_requirements import RENTAL_NO_ADAPTER_COPY

        message = RENTAL_NO_ADAPTER_COPY
    elif facts.entsStated and not facts.parkingStated:
        from itaa_api.agent_requirements import COMPETITION_PARKING_ONLY_COPY

        message = COMPETITION_PARKING_ONLY_COPY
    elif facts.parkingStated and facts.parkingAirport == "":
        dest = facts.destination.lower()
        message = (
            "Which London airport do you need parking at?"
            if dest == "london"
            else "Which airport do you need parking at?"
        )
    elif facts.parkingStated and not facts.hasExactDates:
        message = "When should parking start and finish?"
    else:
        message = "Plan is based on this objective. Confirm before any supplier contact."
    patches: list[RequirementPatch] = []
    for item in extract_conversation_patches(objective, source="current_turn"):
        kind = str(item.get("kind") or "parking")
        if kind not in {"parking", "rental"}:
            continue
        patch_kind: Literal["parking", "rental"] = "rental" if kind == "rental" else "parking"
        field_id = str(item.get("fieldId") or "")
        if not field_id:
            continue
        value = item.get("value")
        if isinstance(value, str | int | list) or value is None:
            patches.append(
                RequirementPatch(
                    kind=patch_kind,
                    fieldId=field_id,
                    value=value if not isinstance(value, list) else [str(v) for v in value],
                    evidence=objective[:180],
                )
            )
    return PlanTurn(
        understanding="Interpreted from the supplied objective only.",
        facts=facts,
        evidence=evidence,
        blockingQuestions=questions,
        suggestedTasks=suggested,
        buyerSafeMessage=message,
        fallback=False,
        requirementPatches=patches,
    )


def parking_fields_from_objective(objective: str, facts: ExtractedFacts) -> dict[str, object]:
    """Canonical parking fields. Does not mint ids or approve A1."""

    fields: dict[str, object] = {}
    airport = facts.parkingAirport
    if airport:
        fields["airportCode"] = airport
    exact: tuple[str, str] | None = None
    if facts.hasExactDates and facts.startDate and facts.endDate:
        exact = (facts.startDate, facts.endDate)
    elif facts.hasExactDates:
        exact = parse_exact_calendar(facts.dates)
    if exact is None:
        exact = parse_exact_calendar(objective)
    if exact is not None:
        fields["startDate"] = exact[0]
        fields["endDate"] = exact[1]
        lower_obj = objective.lower()
        if "1 pm" in lower_obj or "1pm" in lower_obj:
            fields["start"] = f"{exact[0]}T13:00:00Z"
        else:
            fields["start"] = exact[0]
        if "10 pm" in lower_obj or "10pm" in lower_obj:
            fields["end"] = f"{exact[1]}T22:00:00Z"
        else:
            fields["end"] = exact[1]
    lower = objective.lower()
    if "standard" in lower or "ev" in lower:
        fields["vehicleClass"] = "standard"
    covered = re.search(
        r"(?:\b(?:don(?:['’]?t)|do\s+not|no|not|never|without)\b(?:\s+\w+){0,4}\s+covered)"
        r"|\buncovered\b|\bopen[-\s]?air\b",
        lower,
    )
    if covered:
        fields["covered"] = "none"
    elif "covered" in lower:
        fields["covered"] = "preferred"
    shuttle = re.search(r"shuttle[^\d]{0,24}(\d{1,2})", lower)
    if shuttle:
        fields["shuttleMaxMinutes"] = int(shuttle.group(1))
    if "usd" in lower or "dollar" in lower:
        fields["currency"] = "USD"
    if "ev" in lower:
        fields["accessibility"] = ["ev_charging"]
    return fields
