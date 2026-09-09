import { opaqueId } from "../api/ids.js";
import type { BuyerSnapshot } from "../api/types.js";

const INBOX_KEY = "itaa.ui01.inbox";
const ACTOR_KEY = "itaa.ui01.actor";
const COMPETITION_KEY = "itaa.compg102.intents";

export interface InboxCard {
  intentId: string;
  airport: string;
  category: string;
  state: string;
  updatedAt: string;
}

export interface SessionActor {
  actorId: string;
  ownerId: string;
}

const a4Keys = new Map<string, string>();

function storage(): Storage | undefined {
  try {
    return globalThis.sessionStorage;
  } catch {
    return undefined;
  }
}

export function readInbox(): InboxCard[] {
  const raw = storage()?.getItem(INBOX_KEY);
  if (raw === undefined || raw === null || raw === "") {
    return [];
  }
  try {
    const parsed = JSON.parse(raw) as unknown;
    if (!Array.isArray(parsed)) {
      return [];
    }
    return parsed.filter(isInboxCard);
  } catch {
    return [];
  }
}

function isInboxCard(value: unknown): value is InboxCard {
  if (typeof value !== "object" || value === null) {
    return false;
  }
  const record = value as Record<string, unknown>;
  return (
    typeof record.intentId === "string" &&
    typeof record.airport === "string" &&
    typeof record.category === "string" &&
    typeof record.state === "string" &&
    typeof record.updatedAt === "string"
  );
}

function readCompetitionIds(): string[] {
  const raw = storage()?.getItem(COMPETITION_KEY);
  if (raw === undefined || raw === null || raw === "") {
    return [];
  }
  try {
    const parsed = JSON.parse(raw) as unknown;
    if (!Array.isArray(parsed)) {
      return [];
    }
    return parsed.filter(
      (item): item is string => typeof item === "string" && item.startsWith("pi_"),
    );
  } catch {
    return [];
  }
}

export function rememberCompetitionIntent(intentId: string): void {
  const ids = readCompetitionIds().filter((item) => item !== intentId);
  ids.unshift(intentId);
  storage()?.setItem(COMPETITION_KEY, JSON.stringify(ids.slice(0, 24)));
}

export function isCompetitionIntent(intentId: string): boolean {
  return readCompetitionIds().includes(intentId);
}

export function rememberSnapshot(snapshot: BuyerSnapshot): void {
  const cards = readInbox().filter((card) => card.intentId !== snapshot.intentId);
  cards.unshift({
    intentId: snapshot.intentId,
    airport: snapshot.airport,
    category: snapshot.category,
    state: snapshot.state,
    updatedAt: snapshot.updatedAt,
  });
  storage()?.setItem(INBOX_KEY, JSON.stringify(cards.slice(0, 12)));
}

export function sessionActor(): SessionActor {
  const existing = storage()?.getItem(ACTOR_KEY);
  if (existing !== undefined && existing !== null && existing !== "") {
    try {
      const parsed = JSON.parse(existing) as SessionActor;
      if (parsed.actorId.startsWith("ar_") && parsed.ownerId.startsWith("ar_")) {
        return parsed;
      }
    } catch {
      // regenerate
    }
  }
  const actorId = opaqueId("ar_");
  const created = { actorId, ownerId: actorId };
  storage()?.setItem(ACTOR_KEY, JSON.stringify(created));
  return created;
}

export function idempotencyKeyFor(intentId: string): string {
  const existing = a4Keys.get(intentId);
  if (existing !== undefined) {
    return existing;
  }
  const created = opaqueId("ik_");
  a4Keys.set(intentId, created);
  return created;
}

export function peekIdempotencyKey(intentId: string): string | undefined {
  return a4Keys.get(intentId);
}

export function clearIdempotencyKey(intentId: string): void {
  a4Keys.delete(intentId);
}

export const sessionMemoryInternals = { a4Keys };
