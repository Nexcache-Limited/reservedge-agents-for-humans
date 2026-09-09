import type { AgentDomainState } from "../api/types.js";
import {
  overlayParkingDomainFacts,
  parkingBookingStarted,
  projectPlan,
  type PlanSession,
} from "../intent-first/plan.js";
import { projectAgentSession } from "../intent-first/agent.js";
import type { IntentRow, IntentStatus } from "./inbox.js";

export function planSessionToRow(session: PlanSession | null): IntentRow | null {
  if (session?.agent == null) {
    return null;
  }
  const parking = session.agent.domains?.parking;
  const projection = session.agent != null ? projectAgentSession(session) : projectPlan(session);
  const facts = overlayParkingDomainFacts(projection.facts, parking);
  const intentId = typeof parking?.intentId === "string" ? parking.intentId : "";
  const id = intentId.startsWith("pi_") ? intentId : session.agent.sessionId;
  const airport = fieldValue(parking, "airportCode") || facts.parkingAirport;
  const liveParking =
    parkingBookingStarted(parking) ||
    parking?.accepted === true ||
    parking?.provenance === "explicit";
  const title =
    liveParking && airport !== ""
      ? `Airport parking · ${airport}`
      : projection.title || "Current booking";
  const status = rowStatus(session, parking);
  const sub = rowSub(status, session);
  const now = new Date();
  return {
    id,
    domain: "parking",
    title,
    sub,
    status,
    stage:
      status === "done" || status === "cancelled"
        ? "done"
        : status === "running"
          ? "research"
          : status === "pending"
            ? "gate"
            : status === "decision"
              ? "offers"
              : "request",
    step: sub,
    day: "today",
    date: now.toLocaleString("en-GB", {
      day: "numeric",
      month: "short",
      hour: "2-digit",
      minute: "2-digit",
    }),
    canDelete: status === "pending" || !intentId.startsWith("pi_"),
  };
}

export function mergeAgentInboxRow(rows: IntentRow[], agentRow: IntentRow | null): IntentRow[] {
  if (agentRow == null) {
    return rows;
  }
  const rest = rows.filter((row) => {
    if (row.id === agentRow.id) {
      return false;
    }
    return !(row.id.startsWith("as_") && agentRow.id.startsWith("pi_"));
  });
  return [agentRow, ...rest];
}

export function mergeAgentInboxRows(
  rows: IntentRow[],
  agentRows: Array<IntentRow | null>,
): IntentRow[] {
  return agentRows.reduce((current, row) => mergeAgentInboxRow(current, row), rows);
}

export function parkPlanSession(session: PlanSession): PlanSession {
  const parking = session.agent?.domains?.parking;
  if (parking?.completeness === "authorized") {
    return { ...session, shelf: "history" };
  }
  return { ...session, shelf: "pending" };
}

export function withParked(parked: PlanSession[], current: PlanSession | null): PlanSession[] {
  if (current == null) {
    return parked;
  }
  const next = parkPlanSession(current);
  const id = planSessionToRow(next)?.id;
  return [next, ...parked.filter((item) => planSessionToRow(item)?.id !== id)];
}

export function isLiveChatRow(session: PlanSession | null, id: string): boolean {
  if (session?.agent == null) {
    return false;
  }
  const parking = session.agent.domains?.parking;
  if (parking?.completeness === "authorized") {
    return false;
  }
  if (id === session.agent.sessionId) {
    return true;
  }
  const intentId = parking?.intentId;
  return typeof intentId === "string" && intentId === id;
}

export function showRunningInboxChat(session: PlanSession | null): boolean {
  const parking = session?.agent?.domains?.parking;
  if (parking?.completeness === "authorized" || session?.shelf === "history") {
    return false;
  }
  if (session?.shelf === "pending") {
    return false;
  }
  return parkingBookingStarted(parking);
}

function rowStatus(session: PlanSession, parking?: AgentDomainState): IntentStatus {
  if (parking?.completeness === "authorized" || session.shelf === "history") {
    return "done";
  }
  if (session.shelf === "pending") {
    return "pending";
  }
  if (parkingBookingStarted(parking)) {
    return "running";
  }
  if (session.phase === "clarify") {
    return "needs";
  }
  if (session.agent?.pendingAuthorization?.gate === "A2") {
    return "needs";
  }
  return "running";
}

function rowSub(status: IntentStatus, session: PlanSession): string {
  if (status === "done") {
    return "Authorized · simulated";
  }
  if (status === "pending") {
    return "Paused here. Open to continue.";
  }
  if (status === "needs") {
    return session.phase === "clarify"
      ? "Waiting on your answers."
      : "Confirm to request parking offers.";
  }
  if (parkingBookingStarted(session.agent?.domains?.parking)) {
    return "Running · continue in chat.";
  }
  return "Plan forming.";
}

function fieldValue(domain: AgentDomainState | undefined, id: string): string {
  if (domain == null) {
    return "";
  }
  const held = domain.fields[id];
  if (held === undefined || held.value === undefined || held.value === null) {
    return "";
  }
  return String(held.value);
}
