import { opaqueId, SIMULATION_EXPIRES_AT, SIMULATION_ISSUED_AT } from "../api/ids.js";
import type { PurchaseIntent, RankedOffer } from "../api/types.js";

export const SIMULATION_BANNER_LABEL = "SIMULATED - NO REAL CHARGES OR RESERVATIONS";

export const LOCKED_OFFER_IDS = {
  parkDirect: "of_01k2m3n4p5q6r7s8t9v0w1x2a1",
  skyShield: "of_01k2m3n4p5q6r7s8t9v0w1x2a2",
  terminalFlex: "of_01k2m3n4p5q6r7s8t9v0w1x2a3",
} as const;

export const LOCKED_SUPPLIER_TOKENS = {
  parkDirect: "sp_01k2m3n4p5q6r7s8t9v0w1x2b1",
  skyShield: "sp_01k2m3n4p5q6r7s8t9v0w1x2b2",
  terminalFlex: "sp_01k2m3n4p5q6r7s8t9v0w1x2b3",
} as const;

export const SUPPLIER_NAMES: Record<string, string> = {
  [LOCKED_SUPPLIER_TOKENS.parkDirect]: "ParkDirect",
  [LOCKED_SUPPLIER_TOKENS.skyShield]: "SkyShield",
  [LOCKED_SUPPLIER_TOKENS.terminalFlex]: "TerminalFlex",
};

export const LOCKED_SCORES = {
  [LOCKED_SUPPLIER_TOKENS.skyShield]: 671000,
  [LOCKED_SUPPLIER_TOKENS.parkDirect]: 660000,
  [LOCKED_SUPPLIER_TOKENS.terminalFlex]: 535000,
} as const;

export interface OfferCatalogEntry {
  displayName: string;
  lotType: string;
  shuttleMinutes: number;
  distanceMeters: number;
  cancellation: string;
  refund: string;
  addOns: string[];
  availability: string;
  validUntil: string;
  evidenceRef: string;
  covered: string;
}

export const OFFER_CATALOG: Record<string, OfferCatalogEntry> = {
  [LOCKED_SUPPLIER_TOKENS.parkDirect]: {
    displayName: "ParkDirect",
    lotType: "uncovered",
    shuttleMinutes: 15,
    distanceMeters: 2400,
    cancellation: "free until 24 hours before arrival",
    refund: "original method",
    addOns: [],
    availability: "confirmed_simulated",
    validUntil: "2026-08-21T16:00:00Z",
    evidenceRef: "policy.parkdirect.v1",
    covered: "uncovered",
  },
  [LOCKED_SUPPLIER_TOKENS.skyShield]: {
    displayName: "SkyShield",
    lotType: "covered",
    shuttleMinutes: 8,
    distanceMeters: 2900,
    cancellation: "free until 24 hours before arrival",
    refund: "original method",
    addOns: ["EV charging"],
    availability: "confirmed_simulated",
    validUntil: "2026-08-21T16:00:00Z",
    evidenceRef: "policy.skyshield.v3",
    covered: "covered",
  },
  [LOCKED_SUPPLIER_TOKENS.terminalFlex]: {
    displayName: "TerminalFlex",
    lotType: "garage",
    shuttleMinutes: 5,
    distanceMeters: 900,
    cancellation: "free until 48 hours before arrival",
    refund: "original method",
    addOns: ["indoor walkway"],
    availability: "limited_simulated",
    validUntil: "2026-08-21T16:00:00Z",
    evidenceRef: "policy.terminalflex.v2",
    covered: "garage",
  },
};

export const WITHHELD_FIELDS = [
  { field: "Buyer identity", reason: "Not required to price airport parking." },
  { field: "Raw shared context", reason: "Original intake stays with the buyer agent." },
  { field: "Exact itinerary / flight number", reason: "Service window is sufficient." },
  { field: "Precise budget", reason: "Suppliers receive currency, not a private budget cap." },
  { field: "Payment instrument", reason: "No payment is collected in this simulation." },
  { field: "Address and preference history", reason: "Unrelated to this parking request." },
] as const;

export function supplierDisplayName(token: string): string {
  return SUPPLIER_NAMES[token] ?? "Simulated supplier";
}

export function offerCatalog(supplierToken: string): OfferCatalogEntry | undefined {
  return OFFER_CATALOG[supplierToken];
}

export function formatMoney(amountMinor: number, currency: string): string {
  const major = (amountMinor / 100).toFixed(2);
  return `${currency} ${major}`;
}

export function formatScore(scoreMicros: number | undefined): string {
  if (typeof scoreMicros !== "number" || !Number.isFinite(scoreMicros)) {
    return "";
  }
  return scoreMicros.toLocaleString("en-US");
}

export function qualitativeFit(rank: number): string {
  if (rank === 1) {
    return "Strong fit";
  }
  if (rank === 2) {
    return "Good fit";
  }
  return "Fair fit";
}

export function createSeededPurchaseIntent(): PurchaseIntent {
  return {
    schemaVersion: "1.0",
    intentId: opaqueId("pi_"),
    buyerToken: opaqueId("bs_"),
    category: "airport_parking",
    location: { airportCode: "JFK" },
    serviceWindow: {
      start: "2026-09-03T13:00:00Z",
      end: "2026-09-08T22:00:00Z",
    },
    requirements: {
      vehicleClass: "standard",
      covered: "preferred",
      shuttleMaxMinutes: 20,
    },
    constraints: {
      currency: "USD",
      accessibility: ["ev_charging"],
    },
    disclosure: {
      profile: "parking_v1",
      approvedPayloadHash:
        "sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
    },
    solicitation: {
      responseDeadline: "2026-08-21T15:00:00Z",
      counteroffersAllowed: false,
    },
    createdAt: SIMULATION_ISSUED_AT,
    expiresAt: SIMULATION_EXPIRES_AT,
  };
}

export const DISCLOSED_FIELDS = [
  { field: "Airport", value: "JFK", purpose: "Locate eligible lots." },
  {
    field: "Service window",
    value: "3 Sep 2026 13:00Z to 8 Sep 2026 22:00Z",
    purpose: "Price the stay.",
  },
  {
    field: "Vehicle class",
    value: "standard",
    purpose: "Match stall size. Exact make/model withheld.",
  },
  { field: "Covered preference", value: "preferred", purpose: "Rank covered vs uncovered lots." },
  { field: "Shuttle maximum", value: "20 minutes", purpose: "Filter transfer time." },
  { field: "Accessibility / add-ons", value: "EV charging", purpose: "Match stated access needs." },
  { field: "Currency", value: "USD", purpose: "Normalize totals." },
] as const;

export const RETAINED_FIELDS = [
  { field: "Normalized parking requirement", value: "Retained by the buyer agent for ranking." },
  { field: "Market evidence", value: "Buyer-only synthetic local fixtures." },
  { field: "Recommendation policy scores", value: "Computed after isolated offers return." },
] as const;

export function recommendationReasons(offers: RankedOffer[]): string[] {
  const recommended = offers.find((item) => item.recommended);
  if (recommended === undefined) {
    return ["No reliable recommendation is available from the current offers."];
  }
  const catalog = offerCatalog(recommended.supplierToken);
  const name = supplierDisplayName(recommended.supplierToken);
  const coverage = catalog?.covered ?? "unspecified coverage";
  const addOns = catalog?.addOns ?? [];
  const addOnText = addOns.length > 0 ? addOns.join(", ").toLowerCase() : "no extra add-ons listed";
  const shuttle = catalog?.shuttleMinutes ?? "unknown";
  return [
    `${name} is ${coverage} parking with ${addOnText}.`,
    `Shuttle time ${shuttle} minutes is within the 20-minute preference.`,
    "The ranking policy scores the snapshot winner; coverage, add-ons, shuttle, and price are shown as evidence.",
  ];
}
