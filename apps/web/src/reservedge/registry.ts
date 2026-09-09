import type { DomainCode, DomainId } from "./inbox.js";
import { SAMPLE_JFK_TEXT } from "./parking-intake.js";

export type SimulationCapability = "competition_path" | "design_fixture";
export type QuestionParse = "airport" | "window" | "verbatim" | "parking_prefs";

export interface RequirementField {
  id: string;
  label: string;
  required: boolean;
  intakePath?: string;
}

export interface AnswerChip {
  label: string;
  values: Record<string, string>;
}

export interface ClarificationQuestion {
  id: string;
  fieldIds: string[];
  label: string;
  text: string;
  why: string;
  required: boolean;
  chips: AnswerChip[];
  parse: QuestionParse;
  gapPaths: string[];
}

export interface DomainDefinition {
  id: DomainId;
  code: DomainCode;
  name: string;
  disclosureTier: {
    label: string;
    explanation: string;
    bg: string;
    fg: string;
  };
  fields: RequirementField[];
  questions: ClarificationQuestion[];
  offerDimensions: string[];
  simulation: SimulationCapability;
  example: string;
  pickerBody: string;
  pickerNeeds: string;
  capabilityNote: string;
  staticRows: Array<{ label: string; value: string; note: string }>;
}

export const KEEP = "__keep__";
const MAX_QUESTIONS = 3;
const MAX_DIMENSIONS = 6;

export const DOMAIN_REGISTRY: DomainDefinition[] = [
  {
    id: "parking",
    code: "Pk",
    name: "Airport parking",
    disclosureTier: {
      label: "Anonymous until you book",
      explanation:
        "Tier 1 · suppliers price without any attribute about you. Name and plate are shared only when you authorize.",
      bg: "var(--green-soft)",
      fg: "var(--green)",
    },
    fields: [
      { id: "airportCode", label: "AIRPORT", required: true, intakePath: "location.airportCode" },
      { id: "start", label: "START", required: true, intakePath: "serviceWindow.start" },
      { id: "end", label: "END", required: true, intakePath: "serviceWindow.end" },
      {
        id: "vehicleClass",
        label: "VEHICLE CLASS",
        required: true,
        intakePath: "requirements.vehicleClass",
      },
      { id: "covered", label: "COVERED", required: true, intakePath: "requirements.covered" },
      {
        id: "shuttleMaxMinutes",
        label: "SHUTTLE MAX",
        required: true,
        intakePath: "requirements.shuttleMaxMinutes",
      },
      { id: "currency", label: "CURRENCY", required: true, intakePath: "constraints.currency" },
      {
        id: "accessibility",
        label: "ACCESSIBILITY",
        required: true,
        intakePath: "constraints.accessibility",
      },
    ],
    questions: [
      {
        id: "airport",
        fieldIds: ["airportCode"],
        label: "AIRPORT",
        text: "Which airport and terminal?",
        why: "changes shuttle pricing",
        required: true,
        parse: "airport",
        gapPaths: ["location.airportCode"],
        chips: [
          { label: "JFK · Terminal 8", values: { airportCode: "JFK" } },
          { label: "JFK · Terminal 4", values: { airportCode: "JFK" } },
          { label: "Another airport", values: { airportCode: "" } },
        ],
      },
      {
        id: "window",
        fieldIds: ["start", "end"],
        label: "PARKING WINDOW",
        text: "When do you need the space?",
        why: "changes availability",
        required: true,
        parse: "window",
        gapPaths: ["serviceWindow.start", "serviceWindow.end"],
        chips: [
          {
            label: "Keep the times from what you typed",
            values: { start: KEEP, end: KEEP },
          },
          { label: "Pick exact times", values: { start: "", end: "" } },
        ],
      },
      {
        id: "prefs",
        fieldIds: ["covered", "shuttleMaxMinutes", "vehicleClass", "accessibility"],
        label: "MUST-HAVES",
        text: "What matters most this trip?",
        why: "ranks the offers",
        required: true,
        parse: "parking_prefs",
        gapPaths: [
          "requirements.covered",
          "requirements.shuttleMaxMinutes",
          "requirements.vehicleClass",
          "constraints.accessibility",
        ],
        chips: [
          { label: "Covered bay", values: { covered: "preferred" } },
          { label: "Shortest shuttle", values: { shuttleMaxMinutes: "20" } },
          {
            label: "Standard EV",
            values: { vehicleClass: "standard", accessibility: "ev_charging" },
          },
          { label: "EV charging", values: { accessibility: "ev_charging" } },
          { label: "No extra access needs", values: { accessibility: "none" } },
          { label: "Lowest total", values: { covered: KEEP } },
        ],
      },
    ],
    offerDimensions: ["Shuttle", "Distance", "Cover", "Cancellation"],
    simulation: "competition_path",
    example: SAMPLE_JFK_TEXT,
    pickerBody:
      "Suppliers price without knowing who you are. Name and plate are shared only at the moment you authorize. This is the live Gemini → ranked-offers path.",
    pickerNeeds: "Needs: airport, dates, vehicle class · compared on 4 dimensions",
    capabilityNote: "Live competition path",
    staticRows: [],
  },
  {
    id: "rental",
    code: "Rc",
    name: "Rental car",
    disclosureTier: {
      label: "Needs licence class and driver age",
      explanation:
        "Tier 2 · rental suppliers cannot price without age band and licence class. Your identity is still withheld until authorization.",
      bg: "var(--amber-soft)",
      fg: "var(--amber)",
    },
    fields: [
      { id: "when", label: "PICKUP AND RETURN", required: true },
      { id: "class", label: "VEHICLE CLASS", required: true },
      { id: "driver", label: "DRIVER AGE AND LICENCE", required: true },
    ],
    questions: [
      {
        id: "when",
        fieldIds: ["when"],
        label: "PICKUP AND RETURN",
        text: "Pickup and return times?",
        why: "derived from your flight",
        required: false,
        parse: "verbatim",
        gapPaths: ["when"],
        chips: [
          {
            label: "Match flight AA118 · 8 Sep 09:15 → 11 Sep 17:00",
            values: { when: "Match flight AA118 · 8 Sep 09:15 → 11 Sep 17:00" },
          },
          { label: "Pick exact times", values: { when: "" } },
        ],
      },
      {
        id: "class",
        fieldIds: ["class"],
        label: "VEHICLE CLASS",
        text: "What size car?",
        why: "changes price band",
        required: false,
        parse: "verbatim",
        gapPaths: ["class"],
        chips: [
          { label: "Compact", values: { class: "Compact" } },
          { label: "Mid-size SUV", values: { class: "Mid-size SUV" } },
          { label: "Estate", values: { class: "Estate" } },
          { label: "No preference", values: { class: "No preference" } },
        ],
      },
      {
        id: "driver",
        fieldIds: ["driver"],
        label: "DRIVER AGE AND LICENCE",
        text: "Driver age band and licence class?",
        why: "required — no offer without it",
        required: true,
        parse: "verbatim",
        gapPaths: ["driver"],
        chips: [
          { label: "30–65 · full EU category B", values: { driver: "30–65 · full EU category B" } },
          { label: "25–29 · full EU category B", values: { driver: "25–29 · full EU category B" } },
          { label: "Under 25", values: { driver: "Under 25" } },
        ],
      },
    ],
    offerDimensions: [
      "Vehicle",
      "Mileage",
      "Deposit hold",
      "Cancellation",
      "Pickup",
      "Fuel policy",
    ],
    simulation: "design_fixture",
    example: "Also need a car when I land back at JFK on the 8th, until the 11th.",
    pickerBody:
      "Rental suppliers cannot price without driver age and licence class. Your name still stays private until you authorize.",
    pickerNeeds: "Needs: pickup, times, class, age, licence · compared on 6 dimensions",
    capabilityNote: "Simulated demonstration",
    staticRows: [
      {
        label: "MUST-HAVES",
        value: "Free cancellation · unlimited mileage · no debit deposit",
        note: "Two global preferences plus one you set for rentals.",
      },
    ],
  },
  {
    id: "ents",
    code: "En",
    name: "Entertainment booking",
    disclosureTier: {
      label: "Anonymous · party size only",
      explanation:
        "Tier 1 · venues price without knowing who you are. Party size and date are sent; your name goes on the ticket only after you authorize.",
      bg: "var(--green-soft)",
      fg: "var(--green)",
    },
    fields: [
      { id: "what", label: "CATEGORY", required: true },
      { id: "when", label: "EVENING", required: true },
      { id: "party", label: "PARTY SIZE", required: true },
    ],
    questions: [
      {
        id: "what",
        fieldIds: ["what"],
        label: "CATEGORY",
        text: "What kind of night?",
        why: "narrows the venues",
        required: false,
        parse: "verbatim",
        gapPaths: ["what"],
        chips: [
          { label: "Live music", values: { what: "Live music" } },
          { label: "Comedy", values: { what: "Comedy" } },
          { label: "Theatre", values: { what: "Theatre" } },
          { label: "Surprise me", values: { what: "Surprise me" } },
        ],
      },
      {
        id: "when",
        fieldIds: ["when"],
        label: "EVENING",
        text: "Which evening?",
        why: "changes availability",
        required: false,
        parse: "verbatim",
        gapPaths: ["when"],
        chips: [
          {
            label: "Fri 12 Sep · doors after 19:00",
            values: { when: "Fri 12 Sep · doors after 19:00" },
          },
          { label: "Sat 13 Sep · any time", values: { when: "Sat 13 Sep · any time" } },
          { label: "Pick exact times", values: { when: "" } },
        ],
      },
      {
        id: "party",
        fieldIds: ["party"],
        label: "PARTY SIZE",
        text: "How many seats, and together?",
        why: "required — venues cannot hold seats without it",
        required: true,
        parse: "verbatim",
        gapPaths: ["party"],
        chips: [
          { label: "2 seats · must be together", values: { party: "2 seats · must be together" } },
          { label: "2 seats · apart is fine", values: { party: "2 seats · apart is fine" } },
          { label: "3 or more", values: { party: "3 or more" } },
        ],
      },
    ],
    offerDimensions: ["Price", "Seats together", "Start time", "Exchangeable", "Mobile ticket"],
    simulation: "design_fixture",
    example: "Two tickets to something good in Brooklyn on the 12th, under $150 total.",
    pickerBody:
      "A venue can hold two seats together without knowing anything about you. Your name goes on the ticket only after you authorize.",
    pickerNeeds: "Needs: category, evening, party size · compared on 5 dimensions",
    capabilityNote: "Simulated demonstration",
    staticRows: [
      {
        label: "CEILING",
        value: "$150 total, all in",
        note: "From what you typed. Sent as a band, not an exact figure.",
      },
    ],
  },
];

assertRegistry(DOMAIN_REGISTRY);

export const DOMAIN_BY_ID = Object.fromEntries(
  DOMAIN_REGISTRY.map((domain) => [domain.id, domain]),
) as Record<DomainId, DomainDefinition>;

export function listDomains(registry: DomainDefinition[] = DOMAIN_REGISTRY): DomainDefinition[] {
  return registry;
}

export function domainById(
  id: string,
  registry: DomainDefinition[] = DOMAIN_REGISTRY,
): DomainDefinition | undefined {
  return registry.find((domain) => domain.id === id);
}

export function assertRegistry(registry: DomainDefinition[]): void {
  for (const domain of registry) {
    if (domain.questions.length > MAX_QUESTIONS) {
      throw new Error(`${domain.id} declares more than ${MAX_QUESTIONS} questions`);
    }
    if (domain.offerDimensions.length > MAX_DIMENSIONS) {
      throw new Error(`${domain.id} declares more than ${MAX_DIMENSIONS} offer dimensions`);
    }
  }
}
