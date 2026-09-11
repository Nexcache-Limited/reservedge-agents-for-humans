"""Adapter-local planning schemas. Do not mutate intent-plan.schema.json."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

TaskKind = Literal["parking", "rental", "ents", "flight", "hotel", "experience"]
TaskProvenance = Literal["explicit", "inferred", "proposed"]
TaskSupport = Literal["live_simulated", "demonstration", "unsupported", "sandbox_search"]
ClarifyPhase = Literal["clarify", "forming", "ready"]
QuestionId = Literal["dates", "departureAirport", "carNeed", "helpWith"]
CarNeed = Literal["yes", "no", "unsure", ""]
HelpWith = Literal["stay", "rental", "parking", "flights_sorted", "experience", "unsure", ""]
DayPart = Literal["morning", "afternoon", "evening", "anytime", ""]


class EvidenceSpan(BaseModel):
    model_config = ConfigDict(extra="forbid")
    field: str
    start: int = Field(ge=0)
    end: int = Field(ge=0)


class ExtractedFacts(BaseModel):
    model_config = ConfigDict(extra="forbid")
    destination: str = ""
    originCity: str = ""
    destinationAirport: str = ""
    parkingAirport: str = ""
    departureAirport: str = ""
    dates: str = ""
    hasExactDates: bool = False
    hasLooseDates: bool = False
    startDate: str = ""
    endDate: str = ""
    carNeed: CarNeed = ""
    parkingStated: bool = False
    rentalStated: bool = False
    entsStated: bool = False
    hotelStated: bool = False
    experienceStated: bool = False
    experiencePreferences: list[str] = Field(default_factory=list)
    flightStated: bool = False
    flightSatisfied: bool = False
    helpWith: HelpWith = ""
    landing: bool = False
    travel: bool = False
    conference: bool = False
    nights: bool = False
    tripLike: bool = False
    dayPart: DayPart = ""
    timeFlexible: bool = False


class SuggestedTask(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: TaskKind
    provenance: TaskProvenance = "proposed"


class BlockingQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: QuestionId
    label: str
    why: str


class RequirementPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["parking", "rental"] = "parking"
    fieldId: str
    value: str | int | list[str] | None = None
    evidence: str = ""


class PlanTurn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    understanding: str
    facts: ExtractedFacts
    evidence: list[EvidenceSpan] = Field(default_factory=list)
    blockingQuestions: list[BlockingQuestion] = Field(default_factory=list)
    suggestedTasks: list[SuggestedTask] = Field(default_factory=list)
    buyerSafeMessage: str
    fallback: bool = False
    requirementPatches: list[RequirementPatch] = Field(default_factory=list)


class PlanTurnContext(BaseModel):
    model_config = ConfigDict(extra="forbid")
    lastUserMessage: str = ""
    trustedDomains: dict[str, object] = Field(default_factory=dict)


class PlanAnswers(BaseModel):
    model_config = ConfigDict(extra="forbid")
    departureAirport: str = ""
    carNeed: CarNeed = ""
    helpWith: HelpWith = ""
    dates: str = ""
    startDate: str = ""
    endDate: str = ""


class PlanTask(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    kind: TaskKind
    code: str
    title: str
    detail: str
    provenance: TaskProvenance
    support: TaskSupport
    supportLabel: str
    accepted: bool


class PlanProjection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    facts: ExtractedFacts
    questions: list[BlockingQuestion]
    tasks: list[PlanTask]
    phase: ClarifyPhase
    title: str
    summary: str
    confirmedCount: int
    proposedCount: int
