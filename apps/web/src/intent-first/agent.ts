/**
 * Maps provider-backed /v1/agent session views onto Clarify & plan chrome.
 * Does not parse travel prose. plan.ts remains the labelled local fallback.
 */

import type {
  AgentFacts,
  AgentParkingHandoff,
  AgentPlanProjection,
  AgentPlanTask,
  AgentQuestion,
  AgentSessionView,
  BuyerSnapshot,
} from "../api/types.js";
import { formatMoney, supplierDisplayName } from "../fixtures/golden.js";
import {
  EMPTY_ANSWERS,
  overlayParkingDomainFacts,
  planContextChips,
  applyTaskOverrides,
  refinementPinKind,
  sortPlanTasks,
  type CarNeed,
  type ClarificationQuestion,
  type ClarifyPhase,
  type DayPart,
  type ExtractedFacts,
  type PlanAnswers,
  type PlanProjection,
  type PlanSession,
  type PlanTask,
  type QuestionId,
  type TaskKind,
  type TaskProvenance,
  type TaskSupport,
} from "./plan.js";

const CAR_CHOICES: ReadonlyArray<{ id: CarNeed; label: string }> = [
  { id: "yes", label: "Yes" },
  { id: "no", label: "No" },
  { id: "unsure", label: "Not sure" },
];

const EMPTY_FACTS: ExtractedFacts = {
  destination: "",
  originCity: "",
  destinationAirport: "",
  parkingAirport: "",
  departureAirport: "",
  dates: "",
  hasExactDates: false,
  hasLooseDates: false,
  startDate: "",
  endDate: "",
  carNeed: "",
  parkingStated: false,
  rentalStated: false,
  entsStated: false,
  hotelStated: false,
  experienceStated: false,
  experiencePreferences: [],
  flightStated: false,
  flightSatisfied: false,
  helpWith: "",
  landing: false,
  travel: false,
  conference: false,
  nights: false,
  tripLike: false,
  dayPart: "",
  timeFlexible: false,
};

export const AGENT_FAILURE_COPY = "Could not complete this step";
export const AGENT_FALLBACK_COPY = "Using the local planner (labelled)";
export const AGENT_OBJECTIVE_COPY = "Understanding your objective";
export const AGENT_UPDATING_COPY = "Updating your plan";
const PROGRESS_MESSAGES = new Set([
  AGENT_OBJECTIVE_COPY,
  "Checking what information is missing",
  AGENT_UPDATING_COPY,
]);

export function isProgressActivity(message: string): boolean {
  return PROGRESS_MESSAGES.has(message) || /^Preparing \d+ tasks$/.test(message);
}

export function answersFromAgentFacts(facts: AgentFacts): PlanAnswers {
  const canonicalStart = facts.startDate.trim();
  const canonicalEnd = facts.endDate.trim();
  const iso = facts.dates.match(/^(\d{4}-\d{2}-\d{2}) to (\d{4}-\d{2}-\d{2})$/);
  const car = facts.carNeed;
  const part = facts.dayPart;
  const startPeriod: DayPart =
    part === "morning" || part === "afternoon" || part === "evening" || part === "anytime"
      ? part
      : "";
  return {
    ...EMPTY_ANSWERS,
    departureAirport: facts.departureAirport,
    carNeed: car === "yes" || car === "no" || car === "unsure" ? car : "",
    helpWith:
      facts.helpWith === "stay" ||
      facts.helpWith === "rental" ||
      facts.helpWith === "parking" ||
      facts.helpWith === "flights_sorted" ||
      facts.helpWith === "unsure"
        ? facts.helpWith
        : "",
    dates: facts.dates,
    startDate: canonicalStart || iso?.[1] || "",
    endDate: canonicalEnd || iso?.[2] || "",
    startPeriod,
    endPeriod: startPeriod,
    timeFlexible: facts.timeFlexible,
  };
}

export function sessionFromAgentView(objective: string, view: AgentSessionView): PlanSession {
  const phase = view.confirmed ? "ready" : normalizePhase(view.projection.phase);
  const clocks = clocksFromParkingDomain(view.domains);
  return {
    objective,
    answers: {
      ...answersFromAgentFacts(view.projection.facts),
      ...clocks,
    },
    extraNote: "",
    overrides: [],
    phase,
    pane: phase === "clarify" ? "conversation" : "plan",
    agent: bindingFromView(view, []),
  };
}

export function mergeAgentView(session: PlanSession, view: AgentSessionView): PlanSession {
  const phase = view.confirmed ? "ready" : normalizePhase(view.projection.phase);
  const fromFacts = answersFromAgentFacts(view.projection.facts);
  const clocks = clocksFromParkingDomain(view.domains);
  const previous = session.agent;
  const activity = withoutUpdatingActivity(previous?.activity ?? []);
  const bound = bindingFromView(view, activity);
  return {
    ...session,
    phase,
    pane: phase === "clarify" ? session.pane : "plan",
    overrides: reconcileOverrides(session.overrides, view.projection.tasks),
    answers: {
      ...session.answers,
      departureAirport: session.answers.departureAirport || fromFacts.departureAirport,
      carNeed: session.answers.carNeed || fromFacts.carNeed,
      helpWith: session.answers.helpWith || fromFacts.helpWith,
      dates: fromFacts.dates || session.answers.dates,
      startDate: fromFacts.startDate || session.answers.startDate,
      endDate: fromFacts.endDate || session.answers.endDate,
      startPeriod: session.answers.startPeriod || fromFacts.startPeriod,
      endPeriod: session.answers.endPeriod || fromFacts.endPeriod,
      timeFlexible: session.answers.timeFlexible || fromFacts.timeFlexible,
      startTime: clocks.startTime || session.answers.startTime,
      endTime: clocks.endTime || session.answers.endTime,
    },
    agent: {
      ...bound,
      transcript: mergeTranscripts(previous?.transcript ?? [], bound.transcript),
      domains: mergeParkingDomains(previous?.domains, bound.domains),
      pendingAuthorization:
        view.pendingAuthorization === undefined
          ? (previous?.pendingAuthorization ?? null)
          : view.pendingAuthorization,
      pendingSearchAuthorization:
        view.pendingSearchAuthorization === undefined
          ? (previous?.pendingSearchAuthorization ?? null)
          : view.pendingSearchAuthorization,
      stayDraft: view.stayDraft ?? previous?.stayDraft ?? null,
      staySearch: view.staySearch ?? previous?.staySearch ?? null,
      experienceSearch: view.experienceSearch ?? previous?.experienceSearch ?? null,
      flightSearch: view.flightSearch ?? previous?.flightSearch ?? null,
      lastRevisedKind:
        view.lastRevisedKind === undefined
          ? (previous?.lastRevisedKind ?? bound.lastRevisedKind ?? null)
          : view.lastRevisedKind,
      sharedBookingContext: view.sharedBookingContext ?? previous?.sharedBookingContext ?? null,
      workspace: view.workspace ?? previous?.workspace ?? null,
    },
  };
}

export function withUpdatingActivity(session: PlanSession): PlanSession {
  if (session.agent === undefined || session.agent === null) {
    return session;
  }
  if (session.agent.activity.some((item) => item.message === AGENT_UPDATING_COPY)) {
    return session;
  }
  return {
    ...session,
    agent: {
      ...session.agent,
      activity: [
        ...session.agent.activity,
        { kind: "PLAN_UPDATING", message: AGENT_UPDATING_COPY },
      ],
    },
  };
}

export function withoutUpdatingActivity(
  activity: Array<{ kind: string; message: string }>,
): Array<{ kind: string; message: string }> {
  return activity.filter(
    (item) => item.message !== AGENT_UPDATING_COPY && !isProgressActivity(item.message),
  );
}

function mergeTranscripts(
  previous: Array<{ role: string; text: string }>,
  next: Array<{ role: string; text: string }>,
): Array<{ role: string; text: string }> {
  const seen = new Set(next.map((item) => `${item.role}:${item.text}`));
  const extra = previous.filter((item) => !seen.has(`${item.role}:${item.text}`));
  return extra.length === 0 ? next : [...next, ...extra];
}

function mergeParkingDomains(
  previous: NonNullable<PlanSession["agent"]>["domains"] | undefined,
  next: NonNullable<PlanSession["agent"]>["domains"] | undefined,
): NonNullable<PlanSession["agent"]>["domains"] {
  const prevParking = previous?.parking;
  const nextParking = next?.parking;
  if (prevParking == null) {
    return next ?? {};
  }
  if (nextParking == null) {
    return { ...next, parking: prevParking };
  }
  const keepOffers =
    prevParking.offerSet?.snapshot != null && nextParking.offerSet?.snapshot == null;
  const rank = (value: string | undefined): number => {
    if (value === "authorized") {
      return 4;
    }
    if (value === "accepted") {
      return 3;
    }
    if (value === "offers" || value === "soliciting") {
      return 2;
    }
    return 1;
  };
  return {
    ...next,
    parking: {
      ...prevParking,
      ...nextParking,
      intentId: nextParking.intentId || prevParking.intentId || null,
      completeness:
        rank(nextParking.completeness) >= rank(prevParking.completeness)
          ? nextParking.completeness
          : prevParking.completeness,
      offerSet: keepOffers ? prevParking.offerSet : nextParking.offerSet,
    },
  };
}

export function failAgentSession(session: PlanSession, message: string): PlanSession {
  const current = session.agent;
  if (current === undefined || current === null) {
    return session;
  }
  return {
    ...session,
    agent: {
      ...current,
      failed: true,
      failureMessage: message,
      activity: withoutUpdatingActivity(current.activity),
    },
  };
}

export function projectAgentSession(session: PlanSession): PlanProjection {
  const remote = session.agent?.remote;
  if (remote === undefined) {
    throw new Error("projectAgentSession requires an agent binding");
  }
  const facts = overlayParkingDomainFacts(remote.facts, session.agent?.domains?.parking);
  const questions = presentQuestions(remote.questions, facts);
  const tasks = sortPlanTasks(
    applyTaskOverrides(remote.tasks, session.overrides),
    refinementPinKind(session),
  );
  const chips = planContextChips(facts, session.answers, session.extraNote);
  return {
    facts,
    questions: session.phase === "clarify" ? questions : [],
    tasks,
    chips,
    title: remote.title,
    summary: session.agent?.confirmed === true ? "Plan confirmed" : remote.summary,
    confirmedCount: remote.confirmedCount,
    proposedCount: remote.proposedCount,
  };
}

export function turnAnswersFromSession(session: PlanSession): {
  departureAirport?: string;
  carNeed?: "yes" | "no" | "unsure";
  helpWith?: "stay" | "rental" | "parking" | "flights_sorted" | "experience" | "unsure";
  dates?: string;
  startDate?: string;
  endDate?: string;
} {
  const answers = session.answers;
  const body: {
    departureAirport?: string;
    carNeed?: "yes" | "no" | "unsure";
    helpWith?: "stay" | "rental" | "parking" | "flights_sorted" | "experience" | "unsure";
    dates?: string;
    startDate?: string;
    endDate?: string;
  } = {};
  if (answers.departureAirport.trim() !== "") {
    body.departureAirport = answers.departureAirport.trim();
  }
  if (answers.carNeed !== "") {
    body.carNeed = answers.carNeed;
  }
  if (answers.helpWith !== "") {
    body.helpWith = answers.helpWith;
  }
  if (answers.dates.trim() !== "") {
    body.dates = answers.dates.trim();
  }
  if (answers.startDate.trim() !== "") {
    body.startDate = answers.startDate.trim();
  }
  if (answers.endDate.trim() !== "") {
    body.endDate = answers.endDate.trim();
  }
  return body;
}

export function parkingKnownFromHandoff(
  handoff: AgentParkingHandoff | null,
): Record<string, string> {
  if (handoff === null) {
    return {};
  }
  const known: Record<string, string> = {};
  for (const [key, value] of Object.entries(handoff.fields)) {
    if (key === "intentId" || key === "buyerToken" || key === "approvalId") {
      continue;
    }
    if (typeof value === "string" && value.trim() !== "") {
      known[key] = value.trim();
    } else if (typeof value === "number" && Number.isFinite(value)) {
      known[key] = String(value);
    } else if (Array.isArray(value)) {
      const text = value.filter((item) => typeof item === "string").join(",");
      if (text !== "") {
        known[key] = text;
      }
    }
  }
  return known;
}

export function presentQuestions(
  questions: AgentQuestion[],
  facts: ExtractedFacts,
): ClarificationQuestion[] {
  return questions
    .filter((question) => question.id !== "helpWith")
    .slice(0, 3)
    .map((question) => {
      const id = asQuestionId(question.id);
      if (id === "carNeed") {
        return {
          id,
          label: question.label,
          why: question.why,
          kind: "choice",
          choices: CAR_CHOICES,
          unblocks: ["Rental car"],
        };
      }
      return {
        id,
        label: question.label,
        why: question.why,
        kind: "text",
        unblocks: id === "departureAirport" ? ["Flight"] : unblocksFromFacts(facts),
      };
    });
}

function reconcileOverrides(
  overrides: PlanSession["overrides"],
  tasks: AgentPlanTask[],
): PlanSession["overrides"] {
  const explicitIds = new Set(
    tasks.filter((task) => task.provenance === "explicit").map((task) => task.id),
  );
  return overrides.filter((item) => !(item.action === "removed" && explicitIds.has(item.id)));
}

function bindingFromView(
  view: AgentSessionView,
  activity: Array<{ kind: string; message: string }>,
): NonNullable<PlanSession["agent"]> {
  const facts = normalizeFacts(view.projection.facts);
  const tasks = view.projection.tasks.map(normalizeTask);
  const questions = presentQuestions(view.projection.questions, facts);
  const remote: PlanProjection = {
    facts,
    questions,
    tasks,
    chips: [],
    title: view.projection.title,
    summary: view.projection.summary,
    confirmedCount: view.projection.confirmedCount,
    proposedCount: view.projection.proposedCount,
  };
  return {
    sessionId: view.sessionId,
    fallback: view.fallback,
    confirmed: view.confirmed,
    failed: false,
    failureMessage: "",
    parkingHandoff:
      view.parkingHandoff === null
        ? null
        : {
            path: view.parkingHandoff.path,
            support: view.parkingHandoff.support,
            fields: parkingKnownFromHandoff(view.parkingHandoff),
          },
    activity,
    remote,
    transcript: view.transcript ?? [],
    domains: view.domains ?? {},
    pendingAuthorization: view.pendingAuthorization ?? null,
    pendingSearchAuthorization: view.pendingSearchAuthorization ?? null,
    stayDraft: view.stayDraft ?? null,
    buyerSafeMessage: view.buyerSafeMessage ?? "",
    staySearch: view.staySearch ?? null,
    experienceSearch: view.experienceSearch ?? null,
    flightSearch: view.flightSearch ?? null,
    lastRevisedKind: view.lastRevisedKind ?? null,
    sharedBookingContext: view.sharedBookingContext ?? null,
    workspace: view.workspace ?? null,
  };
}

function normalizePhase(phase: AgentPlanProjection["phase"]): ClarifyPhase {
  if (phase === "ready") {
    return "forming";
  }
  return phase;
}

function asQuestionId(id: string): QuestionId {
  if (id === "dates" || id === "departureAirport" || id === "carNeed" || id === "helpWith") {
    return id;
  }
  return "dates";
}

function unblocksFromFacts(facts: ExtractedFacts): string[] {
  const names = ["Airport parking"];
  if (facts.rentalStated || facts.tripLike) {
    names.push("Rental car");
  }
  if (facts.conference || facts.hotelStated || facts.tripLike) {
    names.push("Hotel");
  }
  return names;
}

function normalizeFacts(raw: AgentFacts): ExtractedFacts {
  const dayPart = raw.dayPart;
  const part: DayPart =
    dayPart === "morning" ||
    dayPart === "afternoon" ||
    dayPart === "evening" ||
    dayPart === "anytime"
      ? dayPart
      : "";
  return {
    ...EMPTY_FACTS,
    ...raw,
    dayPart: part,
    carNeed:
      raw.carNeed === "yes" || raw.carNeed === "no" || raw.carNeed === "unsure" ? raw.carNeed : "",
    helpWith:
      raw.helpWith === "stay" ||
      raw.helpWith === "rental" ||
      raw.helpWith === "parking" ||
      raw.helpWith === "flights_sorted" ||
      raw.helpWith === "experience" ||
      raw.helpWith === "unsure"
        ? raw.helpWith
        : "",
    experienceStated: raw.experienceStated === true,
    experiencePreferences: Array.isArray(raw.experiencePreferences)
      ? raw.experiencePreferences.filter((item): item is string => typeof item === "string")
      : [],
    flightSatisfied: raw.flightSatisfied === true,
  };
}

function normalizeTask(task: AgentPlanTask): PlanTask {
  return {
    id: task.id,
    kind: task.kind as TaskKind,
    code: task.code,
    title: task.title,
    detail: task.detail,
    provenance: task.provenance as TaskProvenance,
    support: task.support as TaskSupport,
    supportLabel: task.supportLabel,
    accepted: task.accepted,
  };
}

function clocksFromParkingDomain(domains: AgentSessionView["domains"] | undefined): {
  startTime: string;
  endTime: string;
} {
  const parking = domains?.parking;
  const start = parking?.fields.start?.value;
  const end = parking?.fields.end?.value;
  return {
    startTime: hhmmFromInstant(typeof start === "string" ? start : ""),
    endTime: hhmmFromInstant(typeof end === "string" ? end : ""),
  };
}

function hhmmFromInstant(value: string): string {
  const match = value.match(/T(\d{2}):(\d{2})/);
  return match === null ? "" : `${match[1]}:${match[2]}`;
}

export function syncPlanSessionWithSnapshot(
  session: PlanSession,
  snapshot: BuyerSnapshot,
): PlanSession {
  const agent = session.agent;
  if (agent == null) {
    return session;
  }
  const parking = agent.domains?.parking;
  if (parking == null) {
    return session;
  }
  const heldId = parking.intentId;
  if (
    typeof heldId === "string" &&
    heldId.startsWith("pi_") &&
    heldId !== snapshot.intentId &&
    parking.completeness === "authorized"
  ) {
    return session;
  }
  const selected =
    snapshot.offers.find((item) => item.offerId === snapshot.acceptance?.offerId) ??
    snapshot.offers.find((item) => item.offerId === snapshot.recommendedOfferId) ??
    null;
  const supplier = selected ? supplierDisplayName(selected.supplierToken) : "";
  const amount =
    selected && selected.totalMinor !== undefined && selected.currency
      ? formatMoney(selected.totalMinor, selected.currency)
      : "";
  const selection =
    supplier !== "" && amount !== ""
      ? `You accepted the ${supplier} offer at ${amount}.`
      : supplier !== ""
        ? `You accepted the ${supplier} offer.`
        : "You accepted the recommended offer.";
  const confirmed =
    supplier !== ""
      ? `Simulated reservation authorized with ${supplier}. Other tasks on this trip can still be changed.`
      : "Simulated reservation authorized. Other tasks on this trip can still be changed.";
  const lines: string[] = [];
  const accepted =
    snapshot.state === "ACCEPTANCE_RECORDED" ||
    snapshot.state === "TRANSACTION_AUTHORIZED_SIMULATED";
  if (
    accepted &&
    !agent.transcript.some(
      (item) => item.text.includes("You accepted ") || item.text.includes("You selected "),
    )
  ) {
    lines.push(selection);
  }
  if (
    snapshot.state === "TRANSACTION_AUTHORIZED_SIMULATED" &&
    !agent.transcript.some((item) => item.text.includes("parking reservation authorized"))
  ) {
    lines.push(confirmed);
  }
  const completeness =
    snapshot.state === "TRANSACTION_AUTHORIZED_SIMULATED"
      ? "authorized"
      : snapshot.state === "ACCEPTANCE_RECORDED"
        ? "accepted"
        : parking.completeness;
  const pendingAuthorization =
    completeness === "authorized"
      ? null
      : snapshot.state === "ACCEPTANCE_RECORDED"
        ? {
            gate: "A4",
            domain: "parking",
            prompt: "Authorize the simulated reservation?",
            resourceId: snapshot.intentId,
          }
        : agent.pendingAuthorization;
  const samePending =
    (pendingAuthorization == null && agent.pendingAuthorization == null) ||
    (pendingAuthorization?.gate === agent.pendingAuthorization?.gate &&
      pendingAuthorization?.resourceId === agent.pendingAuthorization?.resourceId);
  if (lines.length === 0 && completeness === parking.completeness && samePending) {
    return session;
  }
  return {
    ...session,
    agent: {
      ...agent,
      activity: withoutUpdatingActivity(agent.activity),
      transcript: [...agent.transcript, ...lines.map((text) => ({ role: "agent" as const, text }))],
      pendingAuthorization,
      domains: {
        ...agent.domains,
        parking: {
          ...parking,
          completeness,
          intentId: snapshot.intentId,
        },
      },
    },
  };
}
