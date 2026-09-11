export type DomainCode = "Pk" | "Rc" | "En" | "St";
export type DomainId = "parking" | "rental" | "ents" | "stay";
export type IntentStatus =
  | "decision"
  | "needs"
  | "running"
  | "pending"
  | "draft"
  | "done"
  | "cancelled";
export type DayKey = "today" | "yesterday" | "earlier";
export type FilterKey = "all" | "needs" | "running" | "pending" | "history";
export type IntentStage = "request" | "research" | "gate" | "offers" | "done";

export interface IntentRow {
  id: string;
  domain: DomainId;
  title: string;
  sub: string;
  status: IntentStatus;
  stage: IntentStage;
  step: string;
  day: DayKey;
  date: string;
  canDelete: boolean;
  pillLabel?: string;
}

export const DOMAIN_META: Record<DomainId, { code: DomainCode; name: string }> = {
  parking: { code: "Pk", name: "Airport parking" },
  rental: { code: "Rc", name: "Rental car" },
  ents: { code: "En", name: "Entertainment" },
  stay: { code: "St", name: "Stay" },
};

export const STATUS_STYLE: Record<IntentStatus, { label: string; bg: string; fg: string }> = {
  decision: {
    label: "Decision ready",
    bg: "var(--itaa-color-surface-accent-soft)",
    fg: "var(--itaa-color-action-pressed)",
  },
  needs: {
    label: "Needs a detail",
    bg: "var(--itaa-color-surface-attention-tint)",
    fg: "var(--itaa-color-status-attention)",
  },
  running: {
    label: "Researching",
    bg: "var(--itaa-color-surface-info-tint)",
    fg: "var(--itaa-color-status-info)",
  },
  pending: {
    label: "Pending · paused by you",
    bg: "var(--itaa-color-surface-muted)",
    fg: "var(--itaa-color-text-secondary)",
  },
  draft: {
    label: "Draft",
    bg: "var(--itaa-color-surface-muted)",
    fg: "var(--itaa-color-text-secondary)",
  },
  done: {
    label: "Authorized · simulated",
    bg: "var(--itaa-color-surface-confidence-tint)",
    fg: "var(--itaa-color-status-confidence)",
  },
  cancelled: {
    label: "Cancelled by you",
    bg: "var(--itaa-color-surface-muted)",
    fg: "var(--itaa-color-text-tertiary)",
  },
};

export const FILTERS: Array<{ key: FilterKey; label: string }> = [
  { key: "all", label: "All" },
  { key: "needs", label: "Needs you" },
  { key: "running", label: "Running" },
  { key: "pending", label: "Pending" },
  { key: "history", label: "History" },
];

export const DAY_LABELS: Record<DayKey, string> = {
  today: "TODAY · 29 AUG",
  yesterday: "YESTERDAY · 28 AUG",
  earlier: "EARLIER",
};

export const SEED_INTENTS: IntentRow[] = [
  {
    id: "jfk",
    domain: "parking",
    title: "JFK airport parking · Sep 4–8",
    sub: "3 private offers · recommended $71.40 all-in",
    status: "decision",
    stage: "offers",
    step: "Decision ready · offers tab",
    day: "today",
    date: "29 Aug · 14:09",
    canDelete: true,
  },
  {
    id: "rental",
    domain: "rental",
    title: "Rental car from JFK · Sep 8–11",
    sub: "3 offers · 1 incomplete · recommended $214.60",
    status: "decision",
    stage: "offers",
    step: "Decision ready · one offer incomplete",
    day: "today",
    date: "29 Aug · 13:40",
    canDelete: true,
  },
  {
    id: "bkn",
    domain: "ents",
    title: "Two tickets · Brooklyn Sep 12",
    sub: "3 offers · recommended $118.00 all-in",
    status: "decision",
    stage: "offers",
    step: "Decision ready · offers tab",
    day: "today",
    date: "29 Aug · 12:15",
    canDelete: true,
  },
  {
    id: "lga",
    domain: "parking",
    title: "LGA parking · Oct 2–4",
    sub: "Public listings only. Nothing shared yet.",
    status: "running",
    stage: "research",
    step: "Market research · research tab",
    day: "today",
    date: "29 Aug · 11:02",
    canDelete: true,
  },
  {
    id: "bos",
    domain: "rental",
    title: "Rental car · Boston Oct 12–15",
    sub: "Paused before the tier 2 disclosure.",
    status: "pending",
    stage: "gate",
    step: "Paused at disclosure",
    day: "yesterday",
    date: "28 Aug · 19:02",
    canDelete: true,
  },
  {
    id: "jfkjul",
    domain: "parking",
    title: "JFK parking · Jul 2–6",
    sub: "$44.10 · ref SIM-3B77",
    status: "done",
    stage: "done",
    step: "Completed",
    day: "earlier",
    date: "2 Jul · 08:10",
    canDelete: false,
  },
  {
    id: "mia",
    domain: "rental",
    title: "Rental car · Miami Jun 8–11",
    sub: "Cancelled before any disclosure.",
    status: "cancelled",
    stage: "done",
    step: "Cancelled at requirement",
    day: "earlier",
    date: "8 Jun · 21:30",
    canDelete: true,
  },
];

export function matchesFilter(row: IntentRow, filter: FilterKey): boolean {
  if (filter === "all") {
    return row.status !== "done" && row.status !== "cancelled";
  }
  if (filter === "needs") {
    return row.status === "decision" || row.status === "needs";
  }
  if (filter === "running") {
    return row.status === "running";
  }
  if (filter === "pending") {
    return row.status === "pending" || row.status === "draft";
  }
  return row.status === "done" || row.status === "cancelled";
}

export function groupIntents(
  rows: IntentRow[],
): Array<{ key: DayKey; label: string; items: IntentRow[] }> {
  return (["today", "yesterday", "earlier"] as const)
    .map((key) => ({
      key,
      label: DAY_LABELS[key],
      items: rows.filter((row) => row.day === key),
    }))
    .filter((group) => group.items.length > 0);
}
