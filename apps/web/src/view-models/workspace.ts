import type {
  BuyerSessionState,
  BuyerSnapshot,
  ProgressEventPayload,
  RankedOffer,
  SupplierOutcome,
} from "../api/types.js";

export type { BuyerSessionState };
import {
  formatMoney,
  formatScore,
  LOCKED_SUPPLIER_TOKENS,
  offerCatalog,
  qualitativeFit,
  recommendationReasons,
  supplierDisplayName,
} from "../fixtures/golden.js";

export type WorkspaceStage = "requirement" | "disclosure" | "offers" | "authorization" | "receipt";

export const STATE_TO_STAGE: Record<BuyerSessionState, WorkspaceStage> = {
  AWAITING_REQUIREMENT_CONFIRMATION: "requirement",
  AWAITING_DISPATCH_APPROVAL: "disclosure",
  OFFERS_RANKED: "offers",
  ACCEPTANCE_RECORDED: "authorization",
  TRANSACTION_AUTHORIZED_SIMULATED: "receipt",
  CANCELLED: "requirement",
  SUPERSEDED: "requirement",
};

export const STATE_LABEL: Record<BuyerSessionState, string> = {
  AWAITING_REQUIREMENT_CONFIRMATION: "Needs your review",
  AWAITING_DISPATCH_APPROVAL: "Approve disclosure",
  OFFERS_RANKED: "Decision ready",
  ACCEPTANCE_RECORDED: "Authorization required",
  TRANSACTION_AUTHORIZED_SIMULATED: "Completed",
  CANCELLED: "Cancelled",
  SUPERSEDED: "Replaced",
};

export const NEXT_ACTION: Record<BuyerSessionState, string> = {
  AWAITING_REQUIREMENT_CONFIRMATION: "Confirm details",
  AWAITING_DISPATCH_APPROVAL: "Review what will be shared",
  OFFERS_RANKED: "Review decision",
  ACCEPTANCE_RECORDED: "Review exact action",
  TRANSACTION_AUTHORIZED_SIMULATED: "View simulated receipt",
  CANCELLED: "View timeline",
  SUPERSEDED: "Open the revised request",
};

export function formatHumanDate(iso: string): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})T/.exec(iso);
  if (match === null) {
    return iso;
  }
  const months = [
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
  ];
  const month = months[Number.parseInt(match[2] ?? "01", 10) - 1] ?? "";
  return `${Number.parseInt(match[3] ?? "1", 10)} ${month} ${match[1]}`;
}

export function formatHumanDateTime(iso: string): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/.exec(iso);
  if (match === null) {
    return formatHumanDate(iso);
  }
  return `${formatHumanDate(iso)} ${match[4]}:${match[5]}`;
}

const PARKING_PLACE: Record<string, string> = {
  LHR: "Heathrow",
  LGW: "Gatwick",
  STN: "Stansted",
  MAN: "Manchester",
  EDI: "Edinburgh",
  JFK: "JFK",
};

export function activityHeading(label: string, snapshot: BuyerSnapshot): string {
  const place = PARKING_PLACE[snapshot.airport] ?? snapshot.airport;
  const accepted =
    snapshot.offers.find((item) => item.offerId === snapshot.acceptance?.offerId) ??
    snapshot.offers.find((item) => item.offerId === snapshot.recommendedOfferId);
  const supplier = accepted ? supplierDisplayName(accepted.supplierToken) : "";
  if (label === "Request created") {
    return place !== "" ? `Request created for ${place} parking` : label;
  }
  if (label === "Details confirmed") {
    return "You confirmed to proceed";
  }
  if (label === "Offer selected") {
    return supplier !== "" ? `Supplier ${supplier} offer was approved` : label;
  }
  if (
    label === "Simulated reservation authorized" ||
    label === "Simulated authorization recorded"
  ) {
    return supplier !== "" ? `Booking confirmed for ${supplier} offer` : label;
  }
  return label;
}

export interface SupplierLaneView {
  supplierToken: string;
  displayName: string;
  statusLabel: string;
  variant: "neutral" | "working" | "attention" | "confidence" | "denial" | "offline";
  kind: string;
}

export interface OfferCardView {
  offer: RankedOffer;
  displayName: string;
  total: string;
  score: string;
  fit: string;
  catalog: ReturnType<typeof offerCatalog>;
}

export type A3DenialKind = "expired" | "unavailable" | "stale" | "ineligible";

export interface A3Eligibility {
  eligible: boolean;
  kind: A3DenialKind | null;
  reason: string;
  recoveryLabel: string;
  recoveryAction: "refresh" | "inbox" | "select";
}

export interface A3AcceptanceView {
  supplier: string;
  version: string;
  amount: string;
  currency: string;
  cancellation: string;
  refund: string;
  addOns: string;
  validityDeadline: string;
  simulationStatus: string;
  evaluationTime: string;
}

const KIND_LABEL: Record<string, { label: string; variant: SupplierLaneView["variant"] }> = {
  OFFER: { label: "Offer received", variant: "confidence" },
  DECLINED: { label: "Declined", variant: "attention" },
  INVALID: { label: "Invalid", variant: "denial" },
  TIMED_OUT: { label: "Timed out", variant: "attention" },
  FAILED: { label: "Failed", variant: "denial" },
  DENIED: { label: "Denied", variant: "denial" },
  LATE: { label: "Late", variant: "attention" },
};

export function stageFor(state: BuyerSessionState): WorkspaceStage {
  return STATE_TO_STAGE[state];
}

export function supplierLanes(outcomes: SupplierOutcome[]): SupplierLaneView[] {
  if (outcomes.length === 0) {
    return [
      lane(
        LOCKED_SUPPLIER_TOKENS.parkDirect,
        supplierDisplayName(LOCKED_SUPPLIER_TOKENS.parkDirect),
        "Waiting",
        "working",
      ),
      lane(
        LOCKED_SUPPLIER_TOKENS.skyShield,
        supplierDisplayName(LOCKED_SUPPLIER_TOKENS.skyShield),
        "Waiting",
        "working",
      ),
      lane(
        LOCKED_SUPPLIER_TOKENS.terminalFlex,
        supplierDisplayName(LOCKED_SUPPLIER_TOKENS.terminalFlex),
        "Waiting",
        "working",
      ),
    ];
  }
  return outcomes.map((item) => {
    const mapped = KIND_LABEL[item.kind] ?? { label: item.kind, variant: "neutral" as const };
    return {
      supplierToken: item.supplierToken,
      displayName: supplierDisplayName(item.supplierToken),
      statusLabel: mapped.label,
      variant: mapped.variant,
      kind: item.kind,
    };
  });
}

const PROGRESS_LABEL: Record<string, { label: string; variant: SupplierLaneView["variant"] }> = {
  SUPPLIER_WAITING: { label: "Waiting", variant: "working" },
  SUPPLIER_OFFER_RECEIVED: { label: "Offer received", variant: "confidence" },
  SUPPLIER_DECLINED: { label: "Declined", variant: "attention" },
  SUPPLIER_TIMED_OUT: { label: "Timed out", variant: "attention" },
  SUPPLIER_LATE: { label: "Late", variant: "attention" },
  SUPPLIER_INVALID: { label: "Invalid", variant: "denial" },
  SUPPLIER_FAILED: { label: "Failed", variant: "denial" },
};

export function progressLanes(events: ProgressEventPayload[]): SupplierLaneView[] {
  const generationId = events.at(-1)?.generationId;
  const scoped =
    generationId === undefined
      ? events
      : events.filter((event) => event.generationId === generationId);
  const latest = new Map<string, ProgressEventPayload>();
  for (const event of scoped) {
    if (event.supplierToken !== null) {
      latest.set(event.supplierToken, event);
    }
  }
  return [
    LOCKED_SUPPLIER_TOKENS.parkDirect,
    LOCKED_SUPPLIER_TOKENS.skyShield,
    LOCKED_SUPPLIER_TOKENS.terminalFlex,
  ].map((token) => {
    const event = latest.get(token);
    if (event === undefined) {
      return lane(token, supplierDisplayName(token), "Waiting", "working");
    }
    const denied = event.kind === "SUPPLIER_FAILED" && event.status === "dispatch_denied";
    const mapped = denied
      ? { label: "Denied", variant: "denial" as const }
      : (PROGRESS_LABEL[event.kind] ?? { label: "Working", variant: "working" as const });
    return {
      supplierToken: token,
      displayName: supplierDisplayName(token),
      statusLabel: mapped.label,
      variant: mapped.variant,
      kind: event.kind,
    };
  });
}

export function progressAnnouncement(event: ProgressEventPayload): string {
  if (event.supplierToken !== null) {
    return `${supplierDisplayName(event.supplierToken)}: ${
      progressLanes([event]).find((item) => item.supplierToken === event.supplierToken)
        ?.statusLabel ?? event.kind
    }`;
  }
  if (event.kind === "STREAM_COMPLETED") {
    return "Progress stream completed. Ranking snapshot remains authoritative.";
  }
  return `Progress: ${event.kind.replaceAll("_", " ").toLowerCase()}.`;
}

function lane(
  token: string,
  name: string,
  statusLabel: string,
  variant: SupplierLaneView["variant"],
): SupplierLaneView {
  return { supplierToken: token, displayName: name, statusLabel, variant, kind: "WAITING" };
}

export function offerMoney(offer: RankedOffer): { totalMinor: number; currency: string } {
  const nested = offer.price;
  const totalMinor =
    typeof offer.totalMinor === "number"
      ? offer.totalMinor
      : nested !== undefined && typeof nested.totalMinor === "number"
        ? nested.totalMinor
        : 0;
  const currency = offer.currency || nested?.currency || "USD";
  return { totalMinor, currency };
}

export function offerCards(offers: RankedOffer[]): OfferCardView[] {
  return [...offers]
    .sort((left, right) => left.rank - right.rank)
    .map((offer) => {
      const money = offerMoney(offer);
      return {
        offer,
        displayName: supplierDisplayName(offer.supplierToken),
        total: formatMoney(money.totalMinor, money.currency),
        score: formatScore(offer.scoreMicros),
        fit: qualitativeFit(offer.rank),
        catalog: offerCatalog(offer.supplierToken),
      };
    });
}

export function priceOnlyLeaderCopy(snapshot: BuyerSnapshot): string {
  const cards = offerCards(snapshot.offers);
  const recommended = cards.find((card) => card.offer.recommended) ?? cards[0];
  if (recommended === undefined) {
    return "No alternative is on the snapshot.";
  }
  const cheapest = cards.reduce((winner, card) =>
    offerMoney(card.offer).totalMinor < offerMoney(winner.offer).totalMinor ? card : winner,
  );
  if (cheapest.offer.offerId === recommended.offer.offerId) {
    return "This recommendation is also the lowest all-in total on the snapshot.";
  }
  return `If all-in price were the only factor, ${cheapest.displayName} would rank ahead.`;
}

export function addOnEvidenceCopy(snapshot: BuyerSnapshot): string {
  const cards = offerCards(snapshot.offers);
  const recommended = cards.find((card) => card.offer.recommended) ?? cards[0];
  const catalog = recommended?.catalog;
  if (catalog === undefined) {
    return "Snapshot does not list extra add-ons.";
  }
  if (catalog.addOns.length > 0) {
    return catalog.addOns.join(", ");
  }
  const bits = [`${catalog.covered} parking`, `shuttle ${catalog.shuttleMinutes} min`];
  return bits.join(" · ");
}

export function downsideCopy(snapshot: BuyerSnapshot): string | null {
  if (snapshot.downside === null) {
    return null;
  }
  const versus = snapshot.offers.find((item) => item.offerId === snapshot.downside?.versusOfferId);
  const versusName =
    versus === undefined ? "the next alternative" : supplierDisplayName(versus.supplierToken);
  if (
    snapshot.downside.dimension === "total_minor" ||
    snapshot.downside.dimension === "TOTAL_MINOR"
  ) {
    return `${formatMoney(snapshot.downside.delta, versus?.currency ?? "USD")} versus ${versusName}.`;
  }
  return `Material tradeoff versus ${versusName}.`;
}

export function whyRecommended(snapshot: BuyerSnapshot): string[] {
  return recommendationReasons(snapshot.offers);
}

export function allSuppliersUnavailable(snapshot: BuyerSnapshot): boolean {
  if (snapshot.supplierOutcomes.length === 0) {
    return false;
  }
  return (
    snapshot.supplierOutcomes.every((item) => item.kind !== "OFFER") && snapshot.offers.length === 0
  );
}

export function partialSuppliers(snapshot: BuyerSnapshot): boolean {
  const offers = snapshot.supplierOutcomes.filter((item) => item.kind === "OFFER").length;
  return (
    snapshot.supplierOutcomes.length > 0 && offers > 0 && offers < snapshot.supplierOutcomes.length
  );
}

/** Last API-authored instant on the snapshot. This is the simulation clock, not Date.now(). */
export function snapshotEvaluationTime(snapshot: BuyerSnapshot): string {
  return snapshot.updatedAt;
}

function parseUtcMs(value: string): number | null {
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/.test(value)) {
    return null;
  }
  const ms = Date.parse(value);
  return Number.isFinite(ms) ? ms : null;
}

export function a3AcceptanceView(snapshot: BuyerSnapshot, selected: RankedOffer): A3AcceptanceView {
  const catalog = offerCatalog(selected.supplierToken);
  const money = offerMoney(selected);
  return {
    supplier: supplierDisplayName(selected.supplierToken),
    version: String(selected.version),
    amount: formatMoney(money.totalMinor, money.currency),
    currency: money.currency,
    cancellation: catalog?.cancellation ?? "Not provided by the snapshot",
    refund: catalog?.refund ?? "Not provided by the snapshot",
    addOns:
      catalog === undefined
        ? "Not provided by the snapshot"
        : catalog.addOns.length > 0
          ? catalog.addOns.join(", ")
          : "None",
    validityDeadline: catalog?.validUntil ?? "Not provided by the snapshot",
    simulationStatus: selected.simulation
      ? "SIMULATED — no real reservation or charge"
      : "Not simulated",
    evaluationTime: snapshotEvaluationTime(snapshot),
  };
}

export function a3Eligibility(
  snapshot: BuyerSnapshot,
  selected: RankedOffer | null,
  options: { stale?: boolean } = {},
): A3Eligibility {
  if (options.stale === true) {
    return {
      eligible: false,
      kind: "stale",
      reason: "Status may be stale after an unconfirmed request. Refresh before acceptance.",
      recoveryLabel: "Refresh status",
      recoveryAction: "refresh",
    };
  }
  if (snapshot.state !== "OFFERS_RANKED") {
    return {
      eligible: false,
      kind: "ineligible",
      reason: "Offer acceptance is not available in the current step.",
      recoveryLabel: "Refresh status",
      recoveryAction: "refresh",
    };
  }
  if (allSuppliersUnavailable(snapshot)) {
    return {
      eligible: false,
      kind: "unavailable",
      reason: "No supplier returned an acceptable offer.",
      recoveryLabel: "Return to Intent Inbox",
      recoveryAction: "inbox",
    };
  }
  if (selected === null) {
    return {
      eligible: false,
      kind: "ineligible",
      reason: "Select an eligible offer before acceptance.",
      recoveryLabel: "Select an offer above",
      recoveryAction: "select",
    };
  }

  const current = snapshot.offers.find((item) => item.offerId === selected.offerId);
  if (current === undefined) {
    return {
      eligible: false,
      kind: "unavailable",
      reason: "The selected offer is no longer in the current snapshot.",
      recoveryLabel: "Refresh status",
      recoveryAction: "refresh",
    };
  }

  const outcome = snapshot.supplierOutcomes.find(
    (item) => item.supplierToken === current.supplierToken,
  );
  if (outcome !== undefined && outcome.kind !== "OFFER") {
    return {
      eligible: false,
      kind: "unavailable",
      reason: "The selected supplier is no longer available.",
      recoveryLabel: "Select another offer",
      recoveryAction: "select",
    };
  }

  if (!current.simulation || !snapshot.simulation) {
    return {
      eligible: false,
      kind: "ineligible",
      reason: "Only a simulated offer can be accepted in this demonstration.",
      recoveryLabel: "Return to Intent Inbox",
      recoveryAction: "inbox",
    };
  }

  const evaluatedMs = parseUtcMs(snapshotEvaluationTime(snapshot));
  const intentExpiresMs = parseUtcMs(snapshot.expiresAt);
  if (evaluatedMs !== null && intentExpiresMs !== null && evaluatedMs >= intentExpiresMs) {
    return {
      eligible: false,
      kind: "expired",
      reason: "This intent has expired at the simulation clock. Start a new demonstration.",
      recoveryLabel: "Return to Intent Inbox",
      recoveryAction: "inbox",
    };
  }

  const catalog = offerCatalog(current.supplierToken);
  const validUntilMs = catalog === undefined ? null : parseUtcMs(catalog.validUntil);
  const catalogBelongsToSnapshot =
    validUntilMs !== null &&
    parseUtcMs(snapshot.createdAt) !== null &&
    validUntilMs > (parseUtcMs(snapshot.createdAt) ?? 0);
  if (
    catalogBelongsToSnapshot &&
    evaluatedMs !== null &&
    validUntilMs !== null &&
    evaluatedMs >= validUntilMs
  ) {
    return {
      eligible: false,
      kind: "expired",
      reason: "This offer's validity deadline has passed at the simulation clock.",
      recoveryLabel: "Select another offer",
      recoveryAction: "select",
    };
  }

  return {
    eligible: true,
    kind: null,
    reason: "",
    recoveryLabel: "",
    recoveryAction: "select",
  };
}
