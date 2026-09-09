import type { DomainId } from "../reservedge/inbox.js";

export const SUGGESTED_OBJECTIVES = [
  "Two nights in Edinburgh for a conference",
  "Weekend away, driving, dog with us",
  "Airport parking for a work trip on Thursday",
] as const;

export function inferDomain(text: string): DomainId {
  const normalized = text.toLowerCase();
  if (/\b(ticket|concert|show|entertainment)\b/.test(normalized)) {
    return "ents";
  }
  if (/\bparking\b/.test(normalized) || /\bairport\b/.test(normalized)) {
    return "parking";
  }
  if (/\b(rental|hire car|car hire|driving)\b/.test(normalized)) {
    return "rental";
  }
  return "parking";
}

export function simulationNoteFor(domain: DomainId): string {
  if (domain === "parking") {
    return "Opening the simulated airport-parking path. Nothing is sent to a supplier from this step.";
  }
  return "This domain is a demonstration fixture. It does not call the live parking simulation.";
}
