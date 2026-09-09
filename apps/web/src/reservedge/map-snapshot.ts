import type { BuyerSnapshot, BuyerSessionState } from "../api/types.js";
import type { IntentRow, IntentStatus } from "./inbox.js";

const STATE_STATUS: Record<BuyerSessionState, IntentStatus> = {
  AWAITING_REQUIREMENT_CONFIRMATION: "needs",
  AWAITING_DISPATCH_APPROVAL: "pending",
  OFFERS_RANKED: "decision",
  ACCEPTANCE_RECORDED: "decision",
  TRANSACTION_AUTHORIZED_SIMULATED: "done",
  CANCELLED: "cancelled",
  SUPERSEDED: "cancelled",
};

function dayFromIso(iso: string): IntentRow["day"] {
  const updated = new Date(iso);
  const now = new Date();
  const startToday = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const startYesterday = new Date(startToday);
  startYesterday.setDate(startToday.getDate() - 1);
  if (updated >= startToday) {
    return "today";
  }
  if (updated >= startYesterday) {
    return "yesterday";
  }
  return "earlier";
}

function formatStamp(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) {
    return "";
  }
  return date.toLocaleString("en-GB", {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function snapshotToRow(
  snapshot: Pick<BuyerSnapshot, "intentId" | "airport" | "state" | "updatedAt"> & {
    saved?: boolean;
  },
): IntentRow {
  let status: IntentStatus =
    snapshot.state === "SUPERSEDED" ? "cancelled" : STATE_STATUS[snapshot.state];
  if (snapshot.saved === true && status !== "done" && status !== "cancelled") {
    status = "pending";
  }
  const title = `Airport parking · ${snapshot.airport}`;
  const sub =
    snapshot.state === "TRANSACTION_AUTHORIZED_SIMULATED"
      ? "Authorized · simulated"
      : snapshot.state === "CANCELLED"
        ? "Cancelled by you"
        : snapshot.state === "SUPERSEDED"
          ? "Replaced by a later intent"
          : snapshot.state === "AWAITING_DISPATCH_APPROVAL"
            ? "Paused before disclosure."
            : snapshot.state === "OFFERS_RANKED" || snapshot.state === "ACCEPTANCE_RECORDED"
              ? "Private offers ready to compare."
              : "Needs a confirmation before research.";
  const row: IntentRow = {
    id: snapshot.intentId,
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
    day: dayFromIso(snapshot.updatedAt),
    date: formatStamp(snapshot.updatedAt),
    canDelete: snapshot.state === "AWAITING_REQUIREMENT_CONFIRMATION",
  };
  if (snapshot.state === "SUPERSEDED") {
    row.pillLabel = "Replaced";
  } else if (snapshot.state === "TRANSACTION_AUTHORIZED_SIMULATED") {
    row.pillLabel = "Completed";
  }
  return row;
}
