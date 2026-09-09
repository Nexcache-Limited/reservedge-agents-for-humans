import type { IntakeExtraction } from "../api/types.js";
import {
  KEEP,
  type AnswerChip,
  type ClarificationQuestion,
  type DomainDefinition,
  type RequirementField,
} from "./registry.js";
import {
  draftFromExtraction,
  hintsFromRequirementText,
  parkingDraftFromValues,
  toConfirmedFields,
  valuesFromParkingDraft,
} from "./parking-intake.js";

export const SKIPPED = "skipped";
export const QUESTION_CAP = 3;

export type Provenance = "proposed" | "answered" | "skipped" | "corrected";

export interface ComposerValues {
  fields: Record<string, string>;
  provenance: Record<string, Provenance>;
}

export const EMPTY_VALUES: ComposerValues = { fields: {}, provenance: {} };

export function valuesFromExtraction(extraction: IntakeExtraction): ComposerValues {
  const draft = draftFromExtraction(extraction);
  const fields = valuesFromParkingDraft(draft);
  if (fields.currency === "") {
    fields.currency = "USD";
  }
  const provenance: Record<string, Provenance> = {};
  for (const [key, value] of Object.entries(fields)) {
    if (value !== "") {
      provenance[key] = "proposed";
    }
  }
  return { fields, provenance };
}

export function canonicalizeFromTyped(text: string, values: ComposerValues): ComposerValues {
  const hints = hintsFromRequirementText(text);
  const parsed = parseWindow(text);
  const fields = { ...values.fields };
  const provenance = { ...values.provenance };
  for (const [key, value] of Object.entries({ ...parsed, ...hints })) {
    if (!isFilled(fields[key] ?? "") && isFilled(value)) {
      fields[key] = value;
      provenance[key] = "proposed";
    }
  }
  return { fields, provenance };
}

export function fieldValue(values: ComposerValues, fieldId: string): string {
  return values.fields[fieldId] ?? "";
}

export function isFilled(value: string): boolean {
  return value !== "" && value !== SKIPPED;
}

export function selectQuestions(
  domain: DomainDefinition,
  values: ComposerValues,
  extraction: IntakeExtraction | null,
): ClarificationQuestion[] {
  const bounded = domain.questions.slice(0, QUESTION_CAP);
  if (domain.simulation === "design_fixture") {
    return bounded;
  }
  if (extraction === null) {
    return [];
  }
  const gaps = new Set([...extraction.missingFields, ...extraction.ambiguousFields]);
  for (const field of domain.fields) {
    if (isFilled(fieldValue(values, field.id)) && field.intakePath !== undefined) {
      gaps.delete(field.intakePath);
    }
    if (field.required && !isFilled(fieldValue(values, field.id))) {
      if (field.intakePath !== undefined) {
        gaps.add(field.intakePath);
      }
      gaps.add(field.id);
    }
  }
  const picked: ClarificationQuestion[] = [];
  for (const question of bounded) {
    if (picked.length >= QUESTION_CAP) {
      break;
    }
    const coversGap = question.gapPaths.some((path) => gaps.has(path));
    const missingOwn = question.fieldIds.some(
      (id) =>
        domain.fields.find((field) => field.id === id)?.required &&
        !isFilled(fieldValue(values, id)),
    );
    if (coversGap || missingOwn) {
      picked.push(question);
    }
  }
  return picked;
}

export function applyChip(values: ComposerValues, chip: AnswerChip, typed = ""): ComposerValues {
  const fields = { ...values.fields };
  const provenance = { ...values.provenance };
  let keepWindow = false;
  for (const [key, raw] of Object.entries(chip.values)) {
    if (raw === KEEP) {
      keepWindow = key === "start" || key === "end" || keepWindow;
      const next = fields[key] ?? "";
      fields[key] = next;
      if (next !== "") {
        provenance[key] = "answered";
      }
      continue;
    }
    fields[key] = raw;
    if (raw !== "") {
      provenance[key] = "answered";
    }
  }
  if (keepWindow && typed.trim() !== "") {
    const parsed = parseWindow(typed);
    for (const key of ["start", "end"] as const) {
      if (
        chip.values[key] === KEEP &&
        !isFilled(fields[key] ?? "") &&
        isFilled(parsed[key] ?? "")
      ) {
        fields[key] = parsed[key] ?? "";
        provenance[key] = "answered";
      }
    }
  }
  return { fields, provenance };
}

export function applyTyped(
  question: ClarificationQuestion,
  values: ComposerValues,
  text: string,
): ComposerValues {
  const trimmed = text.trim();
  if (question.parse === "airport") {
    return merge(values, { airportCode: extractAirport(trimmed) }, "answered");
  }
  if (question.parse === "window") {
    const parsed = parseWindow(trimmed);
    return merge(values, parsed, "answered");
  }
  if (question.parse === "parking_prefs") {
    return merge(values, parseParkingPrefs(trimmed, values), "answered");
  }
  const patch: Record<string, string> = {};
  for (const id of question.fieldIds) {
    patch[id] = trimmed;
  }
  return merge(values, patch, "answered");
}

export function applySkip(question: ClarificationQuestion, values: ComposerValues): ComposerValues {
  if (question.required) {
    return values;
  }
  const patch: Record<string, string> = {};
  for (const id of question.fieldIds) {
    if (!isFilled(fieldValue(values, id))) {
      patch[id] = SKIPPED;
    }
  }
  return merge(values, patch, "skipped");
}

export function correctField(
  values: ComposerValues,
  fieldId: string,
  value: string,
): ComposerValues {
  return merge(values, { [fieldId]: value.trim() }, "corrected");
}

export function missingRequiredFields(
  domain: DomainDefinition,
  values: ComposerValues,
): RequirementField[] {
  return domain.fields.filter((field) => field.required && !isFilled(fieldValue(values, field.id)));
}

export function missingRequiredQuestions(
  questions: ClarificationQuestion[],
  values: ComposerValues,
): ClarificationQuestion[] {
  return questions.filter(
    (question) =>
      question.required && question.fieldIds.some((id) => !isFilled(fieldValue(values, id))),
  );
}

export function parkingFieldsOrNull(
  intakeId: string,
  values: ComposerValues,
): ReturnType<typeof toConfirmedFields> {
  return toConfirmedFields(intakeId, parkingDraftFromValues(values.fields));
}

export function displayFor(field: RequirementField, values: ComposerValues): string {
  const value = fieldValue(values, field.id);
  if (value === SKIPPED) {
    return "Assumed — you skipped this";
  }
  if (value === "") {
    return "Not answered yet";
  }
  if (field.id === "accessibility") {
    if (value === "none") {
      return "None stated";
    }
    return value
      .split(",")
      .map((item) => (item.trim() === "ev_charging" ? "EV charging" : item.trim()))
      .join(", ");
  }
  return value;
}

export function noteFor(field: RequirementField, values: ComposerValues, why: string): string {
  const value = fieldValue(values, field.id);
  const origin = values.provenance[field.id];
  if (value === SKIPPED) {
    return "Correctable at any time in the Request tab";
  }
  if (value === "") {
    return field.required ? "Required before a Purchase Intent can be created." : why;
  }
  if (origin === "proposed") {
    return "Proposed from what you typed. Confirm or correct it.";
  }
  if (origin === "corrected") {
    return "You corrected this";
  }
  if (origin === "answered") {
    return "You answered";
  }
  return why;
}

export function extractAirport(text: string): string {
  const trimmed = text.trim().toUpperCase();
  if (/^[A-Z]{3}$/.test(trimmed)) {
    return trimmed;
  }
  const blocked = new Set([
    "THE",
    "AND",
    "FOR",
    "USE",
    "YOU",
    "ARE",
    "BUT",
    "NOT",
    "ANY",
    "ALL",
    "NEED",
  ]);
  const matches = trimmed.match(/\b[A-Z]{3}\b/g) ?? [];
  return matches.find((code) => !blocked.has(code)) ?? trimmed;
}

const MONTHS: Record<string, string> = {
  jan: "01",
  january: "01",
  feb: "02",
  february: "02",
  mar: "03",
  march: "03",
  apr: "04",
  april: "04",
  may: "05",
  jun: "06",
  june: "06",
  jul: "07",
  july: "07",
  aug: "08",
  august: "08",
  sep: "09",
  sept: "09",
  september: "09",
  oct: "10",
  october: "10",
  nov: "11",
  november: "11",
  dec: "12",
  december: "12",
};

export function parseWindow(text: string): Record<string, string> {
  const iso = text.match(/\d{4}-\d{2}-\d{2}T[\d:.]+Z/g) ?? [];
  if (iso.length >= 2) {
    return { start: iso[0]!, end: iso[1]! };
  }
  if (iso.length === 1) {
    return { start: iso[0]! };
  }
  const pattern =
    /\b(january|february|march|april|may|june|july|august|september|october|november|december|jan|feb|mar|apr|jun|jul|aug|sept?|oct|nov|dec)\.?\s+(\d{1,2})(?:st|nd|rd|th)?(?:,?\s+(\d{4}))?(?:\s+at\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?|\s+(\d{1,2}):(\d{2}))?/gi;
  const hits = [...text.matchAll(pattern)];
  if (hits.length >= 2) {
    return { start: toIsoInstant(hits[0]!, "start"), end: toIsoInstant(hits[1]!, "end") };
  }
  if (hits.length === 1) {
    return { start: toIsoInstant(hits[0]!, "start") };
  }
  return {};
}

function toIsoInstant(match: RegExpMatchArray, role: "start" | "end"): string {
  const month = MONTHS[match[1]?.toLowerCase() ?? ""] ?? "01";
  const day = String(match[2] ?? "01").padStart(2, "0");
  const year = match[3] ?? "2026";
  let hour = 13;
  let minute = 0;
  if (match[4] !== undefined) {
    hour = Number(match[4]);
    minute = Number(match[5] ?? "0");
    const meridiem = match[6]?.toLowerCase();
    if (meridiem === "pm" && hour < 12) {
      hour += 12;
    }
    if (meridiem === "am" && hour === 12) {
      hour = 0;
    }
  } else if (match[7] !== undefined) {
    hour = Number(match[7]);
    minute = Number(match[8] ?? "0");
  } else if (role === "end") {
    hour = 22;
  }
  return `${year}-${month}-${day}T${String(hour).padStart(2, "0")}:${String(minute).padStart(2, "0")}:00Z`;
}

function parseParkingPrefs(text: string, values: ComposerValues): Record<string, string> {
  const lower = text.toLowerCase();
  const patch: Record<string, string> = {};
  if (lower.includes("cover")) {
    patch.covered = "preferred";
  }
  if (lower.includes("shuttle") || lower.includes("minute")) {
    const minutes = text.match(/\d+/);
    patch.shuttleMaxMinutes = minutes?.[0] ?? "20";
  }
  if (lower.includes("suv")) {
    patch.vehicleClass = "suv";
  } else if (lower.includes("compact")) {
    patch.vehicleClass = "compact";
  } else if (lower.includes("oversized")) {
    patch.vehicleClass = "oversized";
  } else if (lower.includes("standard")) {
    patch.vehicleClass = "standard";
  }
  const access = canonicalizeAccessibilityFromPrefs(lower);
  if (access !== null) {
    patch.accessibility = access;
  }
  if (Object.keys(patch).length === 0) {
    patch.mustHaves = text;
  }
  return {
    ...keepExisting(values, ["covered", "shuttleMaxMinutes", "vehicleClass", "accessibility"]),
    ...patch,
  };
}

function canonicalizeAccessibilityFromPrefs(lower: string): string | null {
  if (lower.includes("no extra") || lower === "none") {
    return "none";
  }
  if (
    lower.includes("ev charging") ||
    lower.includes("ev_charging") ||
    lower.includes("electric") ||
    /\bev\b/.test(lower)
  ) {
    return "ev_charging";
  }
  if (lower.includes("step-free") || lower.includes("step_free")) {
    return "step_free";
  }
  if (lower.includes("wheelchair")) {
    return "wheelchair";
  }
  return null;
}

function keepExisting(values: ComposerValues, keys: string[]): Record<string, string> {
  const next: Record<string, string> = {};
  for (const key of keys) {
    const current = fieldValue(values, key);
    if (isFilled(current)) {
      next[key] = current;
    }
  }
  return next;
}

function merge(
  values: ComposerValues,
  patch: Record<string, string>,
  origin: Provenance,
): ComposerValues {
  const fields = { ...values.fields };
  const provenance = { ...values.provenance };
  for (const [key, value] of Object.entries(patch)) {
    fields[key] = value;
    if (value !== "") {
      provenance[key] = origin;
    }
  }
  return { fields, provenance };
}
