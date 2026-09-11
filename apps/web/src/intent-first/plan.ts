/**
 * Process-local Clarify & plan simulation.
 * Deterministic, no network, no LLM, no persistence claim.
 * Replaceable later by an authorized orchestration API.
 */

import type {
  AgentDomainState,
  AgentPendingAuthorization,
  AgentSharedBookingContext,
  AgentExperienceSearch,
  AgentStaySearch,
  AgentTranscriptItem,
  AgentWorkspaceMeta,
} from "../api/types.js";
import {
  composeScheduleLabel,
  detectDayPart,
  detectFlexible,
  emptySchedule,
  formatHumanRange,
  localityLabel,
  normalizeSchedule,
  parseExactCalendar,
  parkingWindowFromSchedule,
  periodLabel,
  resolvedEndDate,
  seedScheduleFromText,
  type DayPart,
  type ScheduleAnswers,
} from "./schedule.js";

export type { DateInputMode, DayPart } from "./schedule.js";

export const PLAN_QUESTION_CAP = 3;

export type ClarifyPhase = "clarify" | "forming" | "ready";
export type ClarifyPane = "conversation" | "plan";
export type CarNeed = "yes" | "no" | "unsure";
export type TaskKind = "parking" | "rental" | "ents" | "flight" | "hotel" | "experience";
export type TaskProvenance = "explicit" | "inferred" | "proposed";
export type TaskSupport = "live_simulated" | "demonstration" | "unsupported" | "sandbox_search";
export type QuestionId = "dates" | "departureAirport" | "carNeed" | "helpWith";
export type HelpWith =
  | "stay"
  | "rental"
  | "parking"
  | "flights_sorted"
  | "experience"
  | "unsure"
  | "";

export interface PlanAnswers extends ScheduleAnswers {
  departureAirport: string;
  carNeed: CarNeed | "";
  helpWith: HelpWith;
}

export interface TaskOverride {
  id: string;
  action: "removed" | "accepted" | "added";
  kind?: TaskKind;
}

export interface PlanSession {
  objective: string;
  answers: PlanAnswers;
  extraNote: string;
  overrides: TaskOverride[];
  phase: ClarifyPhase;
  pane: ClarifyPane;
  agent?: AgentPlanBinding | null;
  shelf?: "pending" | "history";
}

export interface AgentPlanBinding {
  sessionId: string;
  fallback: boolean;
  confirmed: boolean;
  failed: boolean;
  failureMessage: string;
  parkingHandoff: {
    path: string;
    support: TaskSupport | null;
    fields: Record<string, string>;
  } | null;
  activity: Array<{ kind: string; message: string }>;
  remote: PlanProjection;
  transcript: AgentTranscriptItem[];
  domains: Record<string, AgentDomainState>;
  pendingAuthorization: AgentPendingAuthorization | null;
  buyerSafeMessage: string;
  staySearch: AgentStaySearch | null;
  experienceSearch?: AgentExperienceSearch | null;
  sharedBookingContext?: AgentSharedBookingContext | null;
  workspace?: AgentWorkspaceMeta | null;
}

export interface ExtractedFacts {
  destination: string;
  originCity: string;
  destinationAirport: string;
  parkingAirport: string;
  departureAirport: string;
  dates: string;
  hasExactDates: boolean;
  hasLooseDates: boolean;
  startDate: string;
  endDate: string;
  carNeed: CarNeed | "";
  parkingStated: boolean;
  rentalStated: boolean;
  entsStated: boolean;
  hotelStated: boolean;
  experienceStated: boolean;
  experiencePreferences: string[];
  flightStated: boolean;
  flightSatisfied: boolean;
  helpWith: HelpWith;
  landing: boolean;
  travel: boolean;
  conference: boolean;
  nights: boolean;
  tripLike: boolean;
  dayPart: DayPart;
  timeFlexible: boolean;
}

export interface ClarificationQuestion {
  id: QuestionId;
  label: string;
  why: string;
  kind: "text" | "choice";
  choices?: ReadonlyArray<{ id: string; label: string }>;
  unblocks: string[];
}

export interface PlanTask {
  id: string;
  kind: TaskKind;
  code: string;
  title: string;
  detail: string;
  provenance: TaskProvenance;
  support: TaskSupport;
  supportLabel: string;
  accepted: boolean;
}

export interface ContextChip {
  id: string;
  label: string;
  source: "YOU SAID" | "INFERRED" | "CONFIRMED";
}

export interface PlanProjection {
  facts: ExtractedFacts;
  questions: ClarificationQuestion[];
  tasks: PlanTask[];
  chips: ContextChip[];
  title: string;
  summary: string;
  confirmedCount: number;
  proposedCount: number;
}

export const EMPTY_ANSWERS: PlanAnswers = {
  ...emptySchedule(),
  departureAirport: "",
  carNeed: "",
  helpWith: "",
};

const KNOWN_AIRPORTS: Record<string, { city: string; label: string }> = {
  JFK: { city: "New York", label: "JFK" },
  LGA: { city: "New York", label: "LGA" },
  EWR: { city: "Newark", label: "EWR" },
  EDI: { city: "Edinburgh", label: "EDI" },
  MAN: { city: "Manchester", label: "MAN" },
  LHR: { city: "London", label: "LHR" },
  LGW: { city: "London", label: "LGW" },
  STN: { city: "London", label: "STN" },
  AMS: { city: "Amsterdam", label: "AMS" },
  CDG: { city: "Paris", label: "CDG" },
  DUB: { city: "Dublin", label: "DUB" },
  GLA: { city: "Glasgow", label: "GLA" },
};

const CITY_AIRPORTS: Array<{ pattern: RegExp; city: string; airport: string }> = [
  { pattern: /\bedinburgh\b/, city: "Edinburgh", airport: "EDI" },
  { pattern: /\bnew york\b|\bnyc\b|\bmanhattan\b/, city: "New York", airport: "" },
  { pattern: /\bmanchester\b/, city: "Manchester", airport: "MAN" },
  { pattern: /\bmilan\b|\bmilano\b/, city: "Milan", airport: "" },
  { pattern: /\bmumbai\b|\bbombay\b/, city: "Mumbai", airport: "" },
  { pattern: /\brome\b|\broma\b/, city: "Rome", airport: "" },
  { pattern: /\blondon\b/, city: "London", airport: "LHR" },
  { pattern: /\bamsterdam\b/, city: "Amsterdam", airport: "AMS" },
  { pattern: /\bparis\b/, city: "Paris", airport: "CDG" },
  { pattern: /\bdublin\b/, city: "Dublin", airport: "DUB" },
  { pattern: /\bglasgow\b/, city: "Glasgow", airport: "GLA" },
  { pattern: /\bmiami\b/, city: "Miami", airport: "" },
  { pattern: /\bbarcelona\b/, city: "Barcelona", airport: "" },
  { pattern: /\bmadrid\b/, city: "Madrid", airport: "" },
  { pattern: /\bberlin\b/, city: "Berlin", airport: "" },
  { pattern: /\btokyo\b/, city: "Tokyo", airport: "" },
  { pattern: /\bdubai\b/, city: "Dubai", airport: "" },
  { pattern: /\blos angeles\b/, city: "Los Angeles", airport: "" },
  { pattern: /\bchicago\b/, city: "Chicago", airport: "" },
  { pattern: /\bboston\b/, city: "Boston", airport: "" },
  { pattern: /\bsan francisco\b/, city: "San Francisco", airport: "" },
  { pattern: /\btoronto\b/, city: "Toronto", airport: "" },
  { pattern: /\bsydney\b/, city: "Sydney", airport: "" },
];

const MONTH_NAMES =
  "january|february|march|april|may|june|july|august|september|october|november|december|jan|feb|mar|apr|jun|jul|aug|sept?|oct|nov|dec";
const MONTH = new RegExp(`\\b(?:${MONTH_NAMES})\\b`, "i");
const WEEKDAY = /\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b/i;
const MONTH_DAY = new RegExp(
  `\\b(?:\\d{1,2}\\s*[–-]\\s*\\d{1,2}\\s+(?:${MONTH_NAMES})(?:\\s+\\d{4})?|(?:${MONTH_NAMES})\\.?\\s+\\d{1,2}(?:st|nd|rd|th)?(?:,?\\s+\\d{4})?)\\b`,
  "i",
);

const TASK_META: Record<
  TaskKind,
  { code: string; title: string; support: TaskSupport; supportLabel: string }
> = {
  parking: {
    code: "Pk",
    title: "Airport parking",
    support: "live_simulated",
    supportLabel: "Live simulated path",
  },
  rental: {
    code: "Rc",
    title: "Rental car",
    support: "demonstration",
    supportLabel: "Demonstration task",
  },
  ents: {
    code: "En",
    title: "Entertainment",
    support: "demonstration",
    supportLabel: "Demonstration task",
  },
  flight: {
    code: "Fl",
    title: "Flight",
    support: "unsupported",
    supportLabel: "Unsupported in this build",
  },
  hotel: {
    code: "Ht",
    title: "Hotel",
    support: "sandbox_search",
    supportLabel: "Sandbox hotel search",
  },
  experience: {
    code: "Ex",
    title: "Experience",
    support: "sandbox_search",
    supportLabel: "Sandbox experience search",
  },
};

export function emptyAnswers(): PlanAnswers {
  return { ...EMPTY_ANSWERS };
}

export function normalizeAnswers(value: Partial<PlanAnswers> | undefined): PlanAnswers {
  const schedule = normalizeSchedule(value);
  return {
    ...schedule,
    departureAirport: value?.departureAirport ?? "",
    carNeed: value?.carNeed ?? "",
    helpWith: value?.helpWith ?? "",
  };
}

export function mergeSchedule(
  answers: PlanAnswers,
  patch: Partial<PlanAnswers>,
  factsDates: string,
): PlanAnswers {
  const prevMode = answers.dateInputMode;
  const next = normalizeAnswers({ ...answers, ...patch });
  if (next.oneDay && next.startDate !== "") {
    next.endDate = next.startDate;
  }
  if (prevMode === "structured" && patch.dateInputMode === "text") {
    const label = composeScheduleLabel({ ...next, dateInputMode: "structured" });
    if (label !== "") {
      next.dates = label;
    } else if (next.dates.trim() === "" && factsDates !== "") {
      next.dates = factsDates;
    }
  }
  if (prevMode === "text" && patch.dateInputMode === "structured") {
    const parsed = parseExactCalendar(answers.dates);
    if (parsed !== null) {
      next.startDate = parsed.start;
      next.endDate = parsed.end;
      next.oneDay = parsed.start === parsed.end;
    }
  }
  if (next.dateInputMode === "structured") {
    const label = composeScheduleLabel(next);
    if (label !== "") {
      next.dates = label;
    }
  }
  return next;
}

export function createPlanSession(objective: string): PlanSession {
  const facts = extractFacts(objective);
  const questions = selectClarifications(facts);
  return {
    objective,
    answers: seedAnswers(facts, objective),
    extraNote: "",
    overrides: [],
    phase: questions.length === 0 ? "forming" : "clarify",
    pane: questions.length === 0 ? "plan" : "conversation",
  };
}

function seedAnswers(facts: ExtractedFacts, objective: string): PlanAnswers {
  const seeded = seedScheduleFromText(objective);
  return normalizeAnswers({
    ...seeded,
    dates: facts.hasExactDates ? formatHumanRange(seeded.startDate, seeded.endDate) : "",
    startPeriod: facts.dayPart,
    endPeriod: facts.dayPart,
    timeFlexible: facts.timeFlexible,
  });
}

function experiencePrefs(lower: string): string[] {
  const prefs: string[] = [];
  if (/\bevening\b|\btonight\b/.test(lower)) {
    prefs.push("evening");
  }
  if (/\bfamily[-\s]?friendly\b/.test(lower)) {
    prefs.push("family-friendly");
  }
  if (/\bmuseums?\b/.test(lower)) {
    prefs.push("museum");
  }
  if (/\btours?\b/.test(lower)) {
    prefs.push("tour");
  }
  if (/\bcity\s+centre\b|\bcity\s+center\b|\bdowntown\b/.test(lower)) {
    prefs.push("city-centre");
  }
  return prefs;
}

export function extractFacts(objective: string): ExtractedFacts {
  const text = objective.trim();
  const lower = text.toLowerCase();
  const parkingWord = /\bparking\b/.test(lower);
  const rentalStated = carMentioned(lower);
  const entsStated =
    /\b(tickets?|concerts?|entertainment|gigs?)\b/.test(lower) ||
    (/\b(?:a |the |tonight'?s )?shows?\b/.test(lower) && !/\bshow(?:s)?\s+(?:me|us)\b/.test(lower));
  const hotelStated = /\b(hotel|accommodation|place to stay)\b/.test(lower);
  const experienceStated =
    /\b(?:things?\s+to\s+do|what\s+to\s+do|places?\s+to\s+visit|attractions?|activit(?:y|ies)|museums?|tours?|sightseeing|experiences|family[-\s]?friendly)\b/.test(
      lower,
    );
  const experiencePreferences = experiencePrefs(lower);
  const flightSatisfied =
    /\bflights?\s+(?:are|is|were|'re)\s+(?:already\s+)?booked\b/.test(lower) ||
    /\balready booked(?:\s+\w+){0,4}\s+flights?\b/.test(lower);
  const flightStated = /\b(flight|flights|flying)\b/.test(lower) && !flightSatisfied;
  const landing = /\b(when i land|when we land|when i arrive|when we arrive|land(?:ing)?)\b/.test(
    lower,
  );
  const conference = /\bconference\b/.test(lower);
  const travel = /\b(travell?ing|trip to|going to|visit(?:ing)?)\b/.test(lower);
  const nights = /\bnights?\b/.test(lower);
  const route = parseRoute(text);
  const city = matchCity(route.destination || lower);
  const originMatched = matchCity(route.origin);
  const originCity = originMatched?.city ?? (route.origin ? titleCase(route.origin) : "");
  const airports = matchAirports(text);
  const flyingFrom = text.match(/\b(?:flying|departing|leaving)\s+from\s+([A-Za-z]{3})\b/i);
  const parkingAt = text.match(/\b(?:parking\s+(?:at|in)|at)\s+([A-Za-z]{3})\b/i);
  const namedAirport = airports[0] ?? "";
  const airportLedParking =
    namedAirport !== "" && !travel && !landing && !conference && city === null && !rentalStated;
  const parkingStated = parkingWord || airportLedParking;
  const departureAirport =
    flyingFrom?.[1] !== undefined && isAirport(flyingFrom[1])
      ? flyingFrom[1].toUpperCase()
      : (airports.find((code) => flyingFrom !== null && code === flyingFrom[1]?.toUpperCase()) ??
        "");
  const parkingAirportFromText =
    parkingAt?.[1] !== undefined && isAirport(parkingAt[1])
      ? parkingAt[1].toUpperCase()
      : parkingStated
        ? namedAirport
        : "";
  const destination = city?.city ?? guessCity(text);
  const cityAirport = city?.airport ?? "";
  const destinationAirport = cityAirport;
  const parkingAirport = parkingAirportFromText;
  const monthDay = text.match(MONTH_DAY)?.[0]?.trim() ?? "";
  const weekday = text.match(WEEKDAY)?.[0] ?? "";
  const monthOnly = monthDay === "" && MONTH.test(lower);
  const exact = parseExactCalendar(text);
  const hasExactDates = exact !== null;
  const hasLooseDates = hasExactDates || weekday !== "" || monthOnly || nights || monthDay !== "";
  const dates =
    exact !== null
      ? formatHumanRange(exact.start, exact.end)
      : monthDay || (weekday !== "" ? titleCase(weekday) : "") || "";
  const dayPart = detectDayPart(text);
  const timeFlexible = detectFlexible(text);
  const tripLike =
    travel ||
    landing ||
    conference ||
    nights ||
    (destination !== "" && !parkingStated) ||
    (destination !== "" && rentalStated);
  return {
    destination,
    originCity,
    destinationAirport,
    parkingAirport,
    departureAirport,
    dates,
    hasExactDates,
    hasLooseDates,
    startDate: exact?.start ?? "",
    endDate: exact?.end ?? "",
    carNeed: rentalStated ? (carDeclined(lower) ? "no" : "yes") : "",
    parkingStated,
    rentalStated,
    entsStated,
    hotelStated,
    experienceStated,
    experiencePreferences,
    flightStated,
    flightSatisfied,
    helpWith: "",
    landing,
    travel,
    conference,
    nights,
    tripLike,
    dayPart,
    timeFlexible,
  };
}

export function selectClarifications(facts: ExtractedFacts): ClarificationQuestion[] {
  const questions: ClarificationQuestion[] = [];
  const parkingActive = facts.parkingStated || facts.landing;
  if (facts.parkingStated) {
    if (!facts.hasExactDates) {
      questions.push({
        id: "dates",
        label: "Exact dates",
        why: "Sets parking duration, car hire window and hotel nights.",
        kind: "text",
        unblocks: unblocksFor(facts, "dates"),
      });
    }
    return questions.slice(0, PLAN_QUESTION_CAP);
  }
  if (!facts.hasExactDates) {
    questions.push({
      id: "dates",
      label: "Exact dates",
      why: "Sets parking duration, car hire window and hotel nights.",
      kind: "text",
      unblocks: unblocksFor(facts, "dates"),
    });
  }
  if (
    facts.tripLike &&
    facts.departureAirport === "" &&
    facts.originCity === "" &&
    (parkingActive || facts.flightStated)
  ) {
    questions.push({
      id: "departureAirport",
      label: "Departing from",
      why: "Only the airport code reaches parking suppliers. Not your address.",
      kind: "text",
      unblocks: unblocksFor(facts, "departure"),
    });
  }
  if (facts.tripLike && facts.carNeed === "" && (parkingActive || facts.rentalStated)) {
    const place = facts.destination || "your destination";
    questions.push({
      id: "carNeed",
      label: `Will you need a car in ${place}?`,
      why: "Confirms whether a rental-car task belongs on this plan.",
      kind: "choice",
      choices: [
        { id: "yes", label: "Yes" },
        { id: "no", label: "No" },
        { id: "unsure", label: "Not sure" },
      ],
      unblocks: ["Rental car"],
    });
  }
  return questions.slice(0, PLAN_QUESTION_CAP);
}

export function projectPlan(session: PlanSession): PlanProjection {
  const facts = applyAnswerOverlay(extractFacts(combinedObjective(session)), session.answers);
  const questions = selectClarifications(facts);
  const tasks = applyTaskOverrides(baseTasks(facts, session.answers), session.overrides);
  const chips = planContextChips(facts, session.answers, session.extraNote);
  const visible = sortPlanTasks(
    tasks.filter(
      (task) => task.accepted || task.provenance === "proposed" || task.provenance === "inferred",
    ),
  );
  const confirmed = visible.filter((task) => task.accepted && task.provenance !== "proposed");
  const proposed = visible.filter((task) => !task.accepted || task.provenance === "proposed");
  const title = planTitle(session.objective, facts);
  const summary = planSummary(confirmed.length, proposed.length, questions.length, session.phase);
  return {
    facts,
    questions,
    tasks: visible,
    chips,
    title,
    summary,
    confirmedCount: confirmed.length,
    proposedCount: proposed.filter((task) => task.provenance === "proposed").length,
  };
}

export function parkingNeedsTimes(facts: ExtractedFacts): boolean {
  return facts.parkingStated || facts.landing || facts.parkingAirport !== "";
}

export function localityForFacts(facts: ExtractedFacts): string {
  const airport = facts.parkingAirport || facts.destinationAirport;
  const city = facts.destination || KNOWN_AIRPORTS[airport]?.city || "";
  return localityLabel(city, airport);
}

export function parkingPrefill(
  objective: string,
  facts: ExtractedFacts,
  answers: PlanAnswers,
): { draft: string; knownParking: Record<string, string> } {
  const airport = facts.parkingAirport || facts.destinationAirport;
  const schedule = normalizeAnswers({
    ...answers,
    startDate: answers.startDate.trim() || facts.startDate,
    endDate: answers.endDate.trim() || facts.endDate,
  });
  const dates = composeScheduleLabel(schedule) || schedule.dates.trim() || facts.dates;
  const origin = answers.departureAirport.trim() || facts.departureAirport;
  const parts = [objective.trim()];
  if (airport !== "") {
    parts.push(`Airport parking at ${airport}.`);
  }
  if (dates !== "") {
    parts.push(`Dates: ${dates}.`);
  }
  if (schedule.startPeriod !== "" || schedule.timeFlexible) {
    parts.push(
      [periodNote(schedule.startPeriod, schedule.timeFlexible), "Not an exact clock time."]
        .filter((item) => item !== "")
        .join(" "),
    );
  }
  if (origin !== "") {
    parts.push(`Departing from ${origin}.`);
  }
  const knownParking: Record<string, string> = {};
  if (airport !== "") {
    knownParking.airportCode = airport;
  }
  const window = parkingWindowFromSchedule(schedule, facts.dates);
  if (window.start !== undefined) {
    knownParking.start = window.start;
  }
  if (window.end !== undefined) {
    knownParking.end = window.end;
  }
  if (schedule.startDate !== "") {
    knownParking.startDate = schedule.startDate;
  }
  if (resolvedEndDate(schedule) !== "") {
    knownParking.endDate = resolvedEndDate(schedule);
  }
  return { draft: parts.join(" "), knownParking };
}

function periodNote(part: DayPart, flexible: boolean): string {
  if (part === "anytime" || (flexible && part === "")) {
    return "Anytime / Flexible.";
  }
  if (part === "morning") {
    return flexible ? "Morning, flexible." : "Morning.";
  }
  if (part === "afternoon") {
    return flexible ? "Afternoon, flexible." : "Afternoon.";
  }
  if (part === "evening") {
    return flexible ? "Evening, flexible." : "Evening.";
  }
  return flexible ? "Flexible." : "";
}

export function supportedAddableKinds(tasks: PlanTask[]): TaskKind[] {
  const present = new Set(tasks.map((task) => task.kind));
  return (["parking", "rental", "ents", "experience"] as const).filter(
    (kind) => !present.has(kind),
  );
}

export function addTaskOverride(kind: TaskKind): TaskOverride {
  return { id: `task-${kind}`, action: "added", kind };
}

export function removeTaskOverride(id: string): TaskOverride {
  return { id, action: "removed" };
}

export function acceptTaskOverride(id: string): TaskOverride {
  return { id, action: "accepted" };
}

export function provenanceLabel(provenance: TaskProvenance): string {
  if (provenance === "explicit") {
    return "Explicit";
  }
  if (provenance === "inferred") {
    return "Inferred";
  }
  return "Proposed";
}

export function provenanceNote(provenance: TaskProvenance): string {
  if (provenance === "explicit") {
    return "You asked for this.";
  }
  if (provenance === "inferred") {
    return "Strongly implied by the objective or your answers. Not an explicit request.";
  }
  return "Useful, but you did not request this. Inactive until you accept it.";
}

export function taskStatusLabel(task: PlanTask): string {
  if (task.accepted) {
    return "On the plan";
  }
  return "Not confirmed";
}

export function combinedObjective(session: Pick<PlanSession, "objective" | "extraNote">): string {
  return [session.objective.trim(), session.extraNote.trim()]
    .filter((item) => item !== "")
    .join(" ");
}

function applyAnswerOverlay(facts: ExtractedFacts, answers: PlanAnswers): ExtractedFacts {
  const help = answers.helpWith;
  const next: ExtractedFacts = { ...facts, helpWith: help };
  if (help === "stay") {
    next.hotelStated = true;
  } else if (help === "rental") {
    next.rentalStated = true;
    if (next.carNeed === "") {
      next.carNeed = "yes";
    }
  } else if (help === "parking") {
    next.parkingStated = true;
  } else if (help === "flights_sorted") {
    next.flightSatisfied = true;
    next.flightStated = false;
  } else if (help === "experience") {
    next.experienceStated = true;
  }
  return next;
}

function baseTasks(facts: ExtractedFacts, answers: PlanAnswers): PlanTask[] {
  const tasks: PlanTask[] = [];
  const where = facts.destination || facts.parkingAirport || "the airport";
  const car = answers.carNeed || facts.carNeed;
  const parking =
    facts.parkingStated || facts.landing || (facts.tripLike && facts.parkingAirport !== "");
  if (parking) {
    const provenance: TaskProvenance = facts.parkingStated ? "explicit" : "inferred";
    tasks.push(
      makeTask(
        "parking",
        provenance,
        provenance === "explicit",
        parkingDetail(facts, answers, provenance, where),
        facts.parkingAirport || facts.destinationAirport || facts.destination,
      ),
    );
  }
  if (car === "yes" || facts.rentalStated) {
    const provenance: TaskProvenance = facts.rentalStated ? "explicit" : "inferred";
    tasks.push(
      makeTask(
        "rental",
        provenance,
        provenance === "explicit",
        rentalDetail(facts, provenance, where),
        facts.destination,
      ),
    );
  } else if (car === "unsure") {
    tasks.push(
      makeTask(
        "rental",
        "proposed",
        false,
        `You were not sure about a car in ${where}. Proposed only — not something you requested.`,
      ),
    );
  }
  if (facts.entsStated) {
    tasks.push(
      makeTask(
        "ents",
        "explicit",
        true,
        "Taken from your objective. This remains a demonstration task in this build.",
      ),
    );
  }
  if (facts.experienceStated) {
    tasks.push(
      makeTask(
        "experience",
        "explicit",
        true,
        "You asked for things to do, attractions, or experiences.",
      ),
    );
  }
  if (facts.tripLike && (facts.landing || facts.flightStated) && !facts.flightSatisfied) {
    const provenance: TaskProvenance = facts.flightStated ? "explicit" : "proposed";
    const accepted = provenance === "explicit";
    tasks.push(
      makeTask(
        "flight",
        provenance,
        accepted,
        provenance === "explicit"
          ? `You mentioned a flight${facts.destination ? ` to ${facts.destination}` : ""}.`
          : `Inferred from travelling${facts.destination ? ` to ${facts.destination}` : ""}. Inactive until you accept it.`,
      ),
    );
  }
  if (facts.hotelStated) {
    tasks.push(makeTask("hotel", "explicit", true, "You mentioned accommodation."));
  } else if (facts.conference || facts.nights) {
    tasks.push(
      makeTask(
        "hotel",
        "proposed",
        false,
        facts.conference
          ? `A stay is often needed for a conference in ${where}. Proposed only — not something you requested.`
          : `A stay is often needed for this trip. Proposed only — not something you requested.`,
      ),
    );
  }
  return tasks;
}

export function applyTaskOverrides(tasks: PlanTask[], overrides: TaskOverride[]): PlanTask[] {
  const byId = new Map(tasks.map((task) => [task.id, task]));
  for (const override of overrides) {
    if (override.action === "removed") {
      byId.delete(override.id);
      continue;
    }
    if (override.action === "accepted") {
      const current = byId.get(override.id);
      if (current !== undefined) {
        byId.set(override.id, {
          ...current,
          accepted: true,
          detail: `${current.detail} You accepted this proposed task.`,
        });
      }
      continue;
    }
    if (override.action === "added" && override.kind !== undefined && !byId.has(override.id)) {
      const meta = TASK_META[override.kind];
      byId.set(override.id, {
        id: override.id,
        kind: override.kind,
        code: meta.code,
        title: meta.title,
        detail: "Added by you during plan review.",
        provenance: "explicit",
        support: meta.support,
        supportLabel: meta.supportLabel,
        accepted: true,
      });
    }
  }
  return [...byId.values()];
}

function makeTask(
  kind: TaskKind,
  provenance: TaskProvenance,
  accepted: boolean,
  detail: string,
  titleSuffix = "",
): PlanTask {
  const meta = TASK_META[kind];
  return {
    id: `task-${kind}`,
    kind,
    code: meta.code,
    title: titleSuffix === "" ? meta.title : `${meta.title} · ${titleSuffix}`,
    detail,
    provenance,
    support: meta.support,
    supportLabel: meta.supportLabel,
    accepted,
  };
}

function parkingDetail(
  facts: ExtractedFacts,
  answers: PlanAnswers,
  provenance: TaskProvenance,
  where: string,
): string {
  const airport = facts.parkingAirport || facts.destinationAirport;
  const schedule = normalizeAnswers(answers);
  const dates =
    schedule.startDate !== "" || schedule.dateInputMode === "text"
      ? composeScheduleLabel(schedule) || facts.dates
      : facts.dates;
  const airportBit =
    airport !== "" ? ` at ${airport}` : where !== "the airport" ? ` in ${where}` : "";
  if (provenance === "explicit") {
    return `You asked for airport parking${airportBit}.${dates ? ` Dates: ${dates}.` : ""} Ready once you confirm the plan.`;
  }
  return `Implied by landing or airport travel${airportBit}. Not an explicit parking request.${dates ? ` Dates: ${dates}.` : ""}`;
}

function rentalDetail(facts: ExtractedFacts, provenance: TaskProvenance, where: string): string {
  if (provenance === "explicit") {
    return `You said you need a car${where !== "the airport" ? ` in ${where}` : ""}.`;
  }
  return `Implied by your answer that a car is needed${where !== "the airport" ? ` in ${where}` : ""}. Not an explicit original request.`;
}

export function planContextChips(
  facts: ExtractedFacts,
  answers: PlanAnswers,
  extraNote: string,
): ContextChip[] {
  const chips: ContextChip[] = [];
  const schedule = normalizeAnswers(answers);
  const calendar =
    schedule.startDate !== ""
      ? formatHumanRange(schedule.startDate, resolvedEndDate(schedule))
      : facts.dates;
  if (calendar !== "") {
    const startClock = clockLabel(schedule.startTime);
    const endClock = clockLabel(schedule.endTime);
    let label = calendar;
    if (startClock !== "" && endClock !== "") {
      label = `${calendar} · ${startClock}–${endClock}`;
    } else if (startClock !== "") {
      label = `${calendar} · from ${startClock}`;
    } else if (endClock !== "") {
      label = `${calendar} · until ${endClock}`;
    }
    chips.push({
      id: "dates",
      label,
      source: "YOU SAID",
    });
  }
  const part = schedule.startPeriod || schedule.endPeriod;
  if (part !== "" || schedule.timeFlexible) {
    chips.push({
      id: "time",
      label:
        part === "anytime" || (schedule.timeFlexible && part === "")
          ? "Anytime / Flexible"
          : `${periodLabel(part)}${schedule.timeFlexible && part !== "" ? " · Flexible" : ""}`,
      source: "YOU SAID",
    });
  }
  const origin = answers.departureAirport.trim() || facts.departureAirport;
  if (origin !== "") {
    chips.push({
      id: "origin",
      label: origin,
      source: "YOU SAID",
    });
  } else if (facts.originCity !== "") {
    chips.push({
      id: "originCity",
      label: facts.originCity,
      source: "YOU SAID",
    });
  }
  if (facts.destination !== "") {
    chips.push({ id: "destination", label: facts.destination, source: "YOU SAID" });
  }
  if (facts.rentalStated) {
    chips.push({
      id: "car",
      label: "Car needed on arrival",
      source: "YOU SAID",
    });
  }
  if (facts.parkingAirport !== "" && facts.parkingAirport !== facts.destination) {
    chips.push({
      id: "airport",
      label: facts.parkingAirport,
      source: facts.parkingStated ? "YOU SAID" : "INFERRED",
    });
  }
  const noteLabel = leftoverNote(extraNote, chips);
  if (noteLabel !== "") {
    chips.push({ id: "note", label: noteLabel, source: "YOU SAID" });
  }
  return dedupeContextChips(chips);
}

export function overlayParkingDomainFacts(
  facts: ExtractedFacts,
  parking?: AgentDomainState | null,
): ExtractedFacts {
  if (parking == null) {
    return facts;
  }
  const airport = domainFieldValue(parking, "airportCode");
  const startRaw = domainFieldValue(parking, "start");
  const endRaw = domainFieldValue(parking, "end");
  const start = isoYmd(startRaw);
  const end = isoYmd(endRaw);
  return {
    ...facts,
    parkingAirport: airport || facts.parkingAirport,
    startDate: start || facts.startDate,
    endDate: end || facts.endDate,
    dates: start !== "" && end !== "" ? formatHumanRange(start, end) : facts.dates,
    hasExactDates: (start !== "" && end !== "") || facts.hasExactDates,
  };
}

export function parkingBookingStarted(
  parking?: Pick<AgentDomainState, "intentId" | "completeness"> | null,
): boolean {
  if (parking == null) {
    return false;
  }
  if (typeof parking.intentId === "string" && parking.intentId.startsWith("pi_")) {
    return true;
  }
  return (
    parking.completeness === "offers" ||
    parking.completeness === "accepted" ||
    parking.completeness === "authorized" ||
    parking.completeness === "soliciting"
  );
}

export function compactSharedContext(
  facts: ExtractedFacts,
  parking?: AgentDomainState | null,
): string {
  const airport = domainFieldValue(parking, "airportCode") || facts.parkingAirport;
  const start = domainFieldValue(parking, "start") || facts.startDate;
  const end = domainFieldValue(parking, "end") || facts.endDate;
  const dates = isoRangeLabel(start, end) || facts.dates;
  const clocks = isoClockRange(start, end);
  const intentId = parking?.intentId?.trim() ?? "";
  const shortIntent = intentId.startsWith("pi_") ? intentId.slice(0, 8) : "";
  return [airport, dates, clocks, shortIntent].filter((part) => part !== "").join(" · ");
}

function domainFieldValue(parking: AgentDomainState | null | undefined, id: string): string {
  if (parking == null) {
    return "";
  }
  const held = parking.fields[id];
  if (held === undefined || held.value === undefined || held.value === null) {
    return "";
  }
  return String(held.value);
}

function isoYmd(raw: string): string {
  const match = raw.trim().match(/^(\d{4}-\d{2}-\d{2})/);
  return match?.[1] ?? "";
}

function isoRangeLabel(start: string, end: string): string {
  const a = isoYmd(start);
  const b = isoYmd(end);
  if (a === "") {
    return "";
  }
  return formatHumanRange(a, b === "" ? a : b);
}

function isoClockRange(start: string, end: string): string {
  const startClock = isoClock(start);
  const endClock = isoClock(end);
  if (startClock === "" || endClock === "") {
    return "";
  }
  return `${startClock}–${endClock}`;
}

function isoClock(raw: string): string {
  const match = raw.trim().match(/T(\d{2}):(\d{2})/);
  if (match === null) {
    return "";
  }
  return `${match[1]}:${match[2]}`;
}

function clockLabel(hhmm: string): string {
  const match = hhmm.trim().match(/^(\d{2}):(\d{2})$/);
  if (match === null) {
    return "";
  }
  return `${match[1]}:${match[2]}`;
}

function leftoverNote(extraNote: string, chips: ContextChip[]): string {
  let label = extraNote.trim();
  if (label === "") {
    return "";
  }
  for (const chip of chips) {
    const token = chip.label.trim();
    if (token === "") {
      continue;
    }
    const escaped = token.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    label = label.replace(new RegExp(`\\b${escaped}\\b`, "gi"), " ");
  }
  return label.replace(/\s+/g, " ").trim();
}

function dedupeContextChips(chips: ContextChip[]): ContextChip[] {
  const seen = new Set<string>();
  const out: ContextChip[] = [];
  for (const chip of chips) {
    const key = chip.label.trim().toLowerCase();
    if (key === "" || seen.has(key)) {
      continue;
    }
    seen.add(key);
    out.push(chip);
  }
  return out;
}

function planTitle(objective: string, facts: ExtractedFacts): string {
  if (facts.destination !== "" && facts.conference) {
    return `${facts.destination} conference`;
  }
  if (facts.destination !== "") {
    return `Trip to ${facts.destination}`;
  }
  if (facts.parkingAirport !== "") {
    return `Airport parking · ${facts.parkingAirport}`;
  }
  const clipped = objective.trim().replace(/\s+/g, " ");
  return clipped.length <= 48 ? clipped : `${clipped.slice(0, 45)}…`;
}

function planSummary(
  confirmed: number,
  proposed: number,
  questionCount: number,
  phase: ClarifyPhase,
): string {
  if (phase === "clarify") {
    if (questionCount === 1) {
      return "One answer decides most of this plan.";
    }
    if (questionCount > 1) {
      return `${questionCount} answers decide most of this plan. I've grouped them so you only stop once.`;
    }
    return "I have enough to form a plan from what you already told me.";
  }
  if (confirmed === 0 && proposed > 0) {
    return `${proposed} ${proposed === 1 ? "task is" : "tasks are"} proposed. Confirm or remove them before execution.`;
  }
  const proposedBit =
    proposed > 0
      ? ` ${proposed} ${proposed === 1 ? "is" : "are"} proposed and stay inactive until you accept them.`
      : "";
  return `${confirmed} ${confirmed === 1 ? "task is" : "tasks are"} confirmed by what you've told me.${proposedBit}`;
}

export function firstTurnCopy(facts: ExtractedFacts): string {
  const named =
    facts.parkingStated ||
    facts.rentalStated ||
    facts.hotelStated ||
    facts.entsStated ||
    facts.experienceStated ||
    facts.flightStated ||
    facts.carNeed !== "";
  if (!facts.tripLike || named) {
    return "";
  }
  return buyerInviteCopy(facts);
}

export function buyerInviteCopy(facts: ExtractedFacts): string {
  const invite = "I can help with hotels, things to do, car rentals, and parking. Say the word.";
  const origin = facts.originCity ? ` from ${facts.originCity}` : "";
  if (facts.destination !== "" && facts.hasExactDates) {
    return `I have ${facts.destination}${origin} and the dates. ${invite}`;
  }
  if (facts.destination !== "") {
    return `I have ${facts.destination}${origin}. When are you travelling? ${invite}`;
  }
  if (facts.hasExactDates) {
    return `I have the dates. Where are you travelling? ${invite}`;
  }
  return `Where and when are you travelling? ${invite}`;
}

export function sortPlanTasks(tasks: PlanTask[]): PlanTask[] {
  return [...tasks].sort((left, right) => taskPlanRank(left) - taskPlanRank(right));
}

function taskPlanRank(task: PlanTask): number {
  if (task.provenance === "explicit" || (task.accepted && task.provenance !== "proposed")) {
    return 0;
  }
  if (task.provenance === "inferred") {
    return 1;
  }
  return 2;
}

function unblocksFor(facts: ExtractedFacts, which: "dates" | "departure"): string[] {
  const names = ["Airport parking"];
  if (facts.rentalStated || facts.tripLike) {
    names.push("Rental car");
  }
  if (facts.conference || facts.hotelStated || facts.tripLike) {
    names.push("Hotel");
  }
  if (which === "departure") {
    names.push("Flight");
  }
  return [...new Set(names)];
}

function carMentioned(lower: string): boolean {
  return (
    /\bneed(?:ed)? a car\b/.test(lower) ||
    /\bneed(?:ed)? the car\b/.test(lower) ||
    /\brental car\b/.test(lower) ||
    /\bhire car\b/.test(lower) ||
    /\bcar hire\b/.test(lower) ||
    /\brent a car\b/.test(lower) ||
    /\bdriving\b/.test(lower)
  );
}

function carDeclined(lower: string): boolean {
  return /\b(no car|without a car|don't need a car|do not need a car|won't need a car|will not need a car)\b/.test(
    lower,
  );
}

function matchCity(text: string): { city: string; airport: string } | null {
  const lower = text.trim().toLowerCase();
  if (!lower) {
    return null;
  }
  for (const item of CITY_AIRPORTS) {
    if (item.pattern.test(lower)) {
      return { city: item.city, airport: item.airport };
    }
  }
  return null;
}

const CITY_STOP = new Set([
  "january",
  "february",
  "march",
  "april",
  "may",
  "june",
  "july",
  "august",
  "september",
  "october",
  "november",
  "december",
  "jan",
  "feb",
  "mar",
  "apr",
  "jun",
  "jul",
  "aug",
  "sept",
  "sep",
  "oct",
  "nov",
  "dec",
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
]);

function plausibleCity(token: string): boolean {
  const cleaned = token.trim().toLowerCase().replace(/\s+/g, " ");
  if (cleaned.length < 3 || CITY_STOP.has(cleaned)) {
    return false;
  }
  if (cleaned.split(" ").some((part) => CITY_STOP.has(part))) {
    return false;
  }
  if (isAirport(cleaned.toUpperCase())) {
    return false;
  }
  return /^[a-z][a-z .'-]{1,40}$/.test(cleaned);
}

function guessCity(text: string): string {
  const toPlace = text.match(
    /\b(?:to|in)\s+([A-Za-z][A-Za-z .'-]{1,40}?)(?=\s+(?:\d|from\s+\d|,|;|$))/i,
  );
  if (toPlace?.[1] && plausibleCity(toPlace[1])) {
    return titleCase(toPlace[1].trim());
  }
  const leading = text.trim().match(/^([A-Za-z][A-Za-z'-]{2,32})\b/);
  if (leading?.[1] && plausibleCity(leading[1])) {
    return titleCase(leading[1]);
  }
  return "";
}

function parseRoute(text: string): { destination: string; origin: string } {
  const toFrom = text.match(
    /\bto\s+([A-Za-z][A-Za-z .'-]+?)\s+from\s+([A-Za-z][A-Za-z .'-]+?)(?=\s+from\s+\d|\s+on\b|\s+\d{1,2}\b|\s*$)/i,
  );
  if (toFrom?.[1] && toFrom[2]) {
    return { destination: toFrom[1].trim(), origin: toFrom[2].trim() };
  }
  const fromTo = text.match(
    /\bfrom\s+([A-Za-z][A-Za-z .'-]+?)\s+to\s+([A-Za-z][A-Za-z .'-]+?)(?=\s+for\b|\s+from\s+\d|\s+on\b|\s*$)/i,
  );
  if (fromTo?.[1] && fromTo[2]) {
    return { destination: fromTo[2].trim(), origin: fromTo[1].trim() };
  }
  return { destination: "", origin: "" };
}

function matchAirports(text: string): string[] {
  const found: string[] = [];
  for (const match of text.toUpperCase().matchAll(/\b([A-Z]{3})\b/g)) {
    const code = match[1] ?? "";
    if (isAirport(code) && !found.includes(code)) {
      found.push(code);
    }
  }
  return found;
}

function isAirport(code: string): boolean {
  return Object.prototype.hasOwnProperty.call(KNOWN_AIRPORTS, code.toUpperCase());
}

function titleCase(value: string): string {
  return value.slice(0, 1).toUpperCase() + value.slice(1).toLowerCase();
}
