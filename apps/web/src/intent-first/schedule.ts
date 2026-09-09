/**
 * Deterministic calendar/time helpers for Clarify & plan.
 * No external parser, no LLM, no invented precision from relative phrases.
 */

export type DateInputMode = "structured" | "text";
export type DayPart = "morning" | "afternoon" | "evening" | "anytime" | "";

export interface ScheduleAnswers {
  dates: string;
  startDate: string;
  endDate: string;
  oneDay: boolean;
  startTime: string;
  endTime: string;
  startPeriod: DayPart;
  endPeriod: DayPart;
  timeFlexible: boolean;
  dateInputMode: DateInputMode;
}

export const EMPTY_SCHEDULE: ScheduleAnswers = {
  dates: "",
  startDate: "",
  endDate: "",
  oneDay: false,
  startTime: "",
  endTime: "",
  startPeriod: "",
  endPeriod: "",
  timeFlexible: false,
  dateInputMode: "structured",
};

const MONTH_INDEX: Record<string, string> = {
  january: "01",
  jan: "01",
  february: "02",
  feb: "02",
  march: "03",
  mar: "03",
  april: "04",
  apr: "04",
  may: "05",
  june: "06",
  jun: "06",
  july: "07",
  jul: "07",
  august: "08",
  aug: "08",
  september: "09",
  sept: "09",
  sep: "09",
  october: "10",
  oct: "10",
  november: "11",
  nov: "11",
  december: "12",
  dec: "12",
};

const MONTH_SHORT = [
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

const MONTH_NAMES =
  "january|february|march|april|may|june|july|august|september|october|november|december|jan|feb|mar|apr|jun|jul|aug|sept?|oct|nov|dec";

export function emptySchedule(): ScheduleAnswers {
  return { ...EMPTY_SCHEDULE };
}

export function normalizeSchedule(value: Partial<ScheduleAnswers> | undefined): ScheduleAnswers {
  return {
    ...EMPTY_SCHEDULE,
    ...value,
    dates: value?.dates ?? "",
    startDate: value?.startDate ?? "",
    endDate: value?.endDate ?? "",
    oneDay: Boolean(value?.oneDay),
    startTime: value?.startTime ?? "",
    endTime: value?.endTime ?? "",
    startPeriod: value?.startPeriod ?? "",
    endPeriod: value?.endPeriod ?? "",
    timeFlexible: Boolean(value?.timeFlexible),
    dateInputMode: value?.dateInputMode === "text" ? "text" : "structured",
  };
}

const SAME_MONTH_RANGE = new RegExp(
  `\\b(?:from\\s+)?(\\d{1,2})(?:st|nd|rd|th)?\\s*(?:to|[–-])\\s*(\\d{1,2})(?:st|nd|rd|th)?\\s+(${MONTH_NAMES})(?:\\.?\\s+|\\s+)(\\d{4})\\b`,
  "i",
);
const NAMED_MONTH_RANGE = new RegExp(
  `\\b(${MONTH_NAMES})\\s+(\\d{1,2})(?:st|nd|rd|th)?\\s*(?:to|[–-])\\s*(\\d{1,2})(?:st|nd|rd|th)?(?:,)?\\s+(\\d{4})\\b`,
  "i",
);
const DUAL_DATE_RANGE = new RegExp(
  `\\b(\\d{1,2})(?:st|nd|rd|th)?\\s+(${MONTH_NAMES})\\s+(\\d{4})\\s*(?:to|[–-])\\s*(\\d{1,2})(?:st|nd|rd|th)?\\s+(${MONTH_NAMES})\\s+(\\d{4})\\b`,
  "i",
);

export function parseExactCalendar(text: string): { start: string; end: string } | null {
  const trimmed = text.trim();
  if (trimmed === "") {
    return null;
  }
  const range = parseExactRange(trimmed);
  if (range !== null) {
    return range;
  }
  if (looksLikeDateRange(trimmed)) {
    return null;
  }
  const monthFirst = trimmed.match(
    new RegExp(`\\b(${MONTH_NAMES})\\.?\\s+(\\d{1,2})(?:st|nd|rd|th)?(?:,)?\\s+(\\d{4})\\b`, "i"),
  );
  if (monthFirst) {
    const start = ymd(monthFirst[3] ?? "", monthNumber(monthFirst[1] ?? ""), monthFirst[2] ?? "");
    if (start !== null) {
      return { start, end: start };
    }
  }
  const dayFirst = trimmed.match(
    new RegExp(`\\b(\\d{1,2})(?:st|nd|rd|th)?\\s+(${MONTH_NAMES})\\.?\\s+(\\d{4})\\b`, "i"),
  );
  if (dayFirst) {
    const start = ymd(dayFirst[3] ?? "", monthNumber(dayFirst[2] ?? ""), dayFirst[1] ?? "");
    if (start !== null) {
      return { start, end: start };
    }
  }
  const iso = trimmed.match(/\b(\d{4}-\d{2}-\d{2})\b/);
  if (iso?.[1] !== undefined && validYmd(iso[1])) {
    return { start: iso[1], end: iso[1] };
  }
  return null;
}

export function looksLikeDateRange(text: string): boolean {
  const trimmed = text.trim();
  if (/\b\d{4}-\d{2}-\d{2}\s*(?:to|[–-])\s*\S/.test(trimmed)) {
    return true;
  }
  if (
    SAME_MONTH_RANGE.test(trimmed) ||
    NAMED_MONTH_RANGE.test(trimmed) ||
    DUAL_DATE_RANGE.test(trimmed)
  ) {
    return true;
  }
  if (/\bfrom\s+\d{1,2}(?:st|nd|rd|th)?\s+to\b/i.test(trimmed)) {
    return true;
  }
  if (
    new RegExp(`\\b\\d{1,2}(?:st|nd|rd|th)?\\s+to\\s+(?:${MONTH_NAMES}|sometime)\\b`, "i").test(
      trimmed,
    )
  ) {
    return true;
  }
  if (/\b(?:from\s+)?\d{1,2}(?:st|nd|rd|th)?\s+to\s+\d{1,2}(?:st|nd|rd|th)?\b/i.test(trimmed)) {
    return true;
  }
  if (
    new RegExp(
      `\\b(?:from\\s+)?\\d{1,2}(?:st|nd|rd|th)?\\s*(?:to|[–-])\\s*\\d{1,2}(?:st|nd|rd|th)?\\s+(${MONTH_NAMES})\\b`,
      "i",
    ).test(trimmed)
  ) {
    return true;
  }
  return false;
}

function parseExactRange(text: string): { start: string; end: string } | null {
  const isoRange = text.match(/\b(\d{4}-\d{2}-\d{2})\s*(?:to|[–-])\s*(\d{4}-\d{2}-\d{2})\b/);
  if (
    isoRange?.[1] !== undefined &&
    isoRange[2] !== undefined &&
    validYmd(isoRange[1]) &&
    validYmd(isoRange[2])
  ) {
    return { start: isoRange[1], end: isoRange[2] };
  }
  const range = text.match(SAME_MONTH_RANGE);
  if (range) {
    const month = monthNumber(range[3] ?? "");
    const year = range[4] ?? "";
    const start = ymd(year, month, range[1] ?? "");
    const end = ymd(year, month, range[2] ?? "");
    if (start !== null && end !== null) {
      return { start, end };
    }
  }
  const namedRange = text.match(NAMED_MONTH_RANGE);
  if (namedRange) {
    const month = monthNumber(namedRange[1] ?? "");
    const year = namedRange[4] ?? "";
    const start = ymd(year, month, namedRange[2] ?? "");
    const end = ymd(year, month, namedRange[3] ?? "");
    if (start !== null && end !== null) {
      return { start, end };
    }
  }
  const dual = text.match(DUAL_DATE_RANGE);
  if (dual) {
    const start = ymd(dual[3] ?? "", monthNumber(dual[2] ?? ""), dual[1] ?? "");
    const end = ymd(dual[6] ?? "", monthNumber(dual[5] ?? ""), dual[4] ?? "");
    if (start !== null && end !== null) {
      return { start, end };
    }
  }
  return null;
}

export function detectDayPart(text: string): DayPart {
  const lower = text.toLowerCase();
  if (/\bmorning\b/.test(lower)) {
    return "morning";
  }
  if (/\bafternoon\b/.test(lower)) {
    return "afternoon";
  }
  if (/\bevening\b|\btonight\b/.test(lower)) {
    return "evening";
  }
  if (/\banytime\b|\ball day\b/.test(lower)) {
    return "anytime";
  }
  return "";
}

export function detectFlexible(text: string): boolean {
  return /\bflexible\b|\banytime\b|\bno particular time\b/.test(text.toLowerCase());
}

export function isRelativeDate(text: string): boolean {
  const lower = text.toLowerCase();
  return (
    parseExactCalendar(text) === null &&
    (/\bnext\b/.test(lower) ||
      /\btomorrow\b/.test(lower) ||
      /\btoday\b/.test(lower) ||
      /\bsometime\b/.test(lower) ||
      /\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b/.test(lower) ||
      new RegExp(`\\b(?:${MONTH_NAMES})\\b`, "i").test(lower))
  );
}

export function formatHumanRange(start: string, end: string): string {
  if (!validYmd(start)) {
    return "";
  }
  const endDate = validYmd(end) ? end : start;
  const a = splitYmd(start);
  const b = splitYmd(endDate);
  if (a === null || b === null) {
    return "";
  }
  if (start === endDate) {
    return `${Number(a.day)} ${MONTH_SHORT[Number(a.month) - 1] ?? a.month} ${a.year}`;
  }
  if (a.year === b.year && a.month === b.month) {
    return `${Number(a.day)}–${Number(b.day)} ${MONTH_SHORT[Number(a.month) - 1] ?? a.month} ${a.year}`;
  }
  if (a.year === b.year) {
    return `${Number(a.day)} ${MONTH_SHORT[Number(a.month) - 1] ?? a.month} – ${Number(b.day)} ${MONTH_SHORT[Number(b.month) - 1] ?? b.month} ${a.year}`;
  }
  return `${Number(a.day)} ${MONTH_SHORT[Number(a.month) - 1] ?? a.month} ${a.year} – ${Number(b.day)} ${MONTH_SHORT[Number(b.month) - 1] ?? b.month} ${b.year}`;
}

export function periodLabel(part: DayPart): string {
  if (part === "morning") {
    return "Morning";
  }
  if (part === "afternoon") {
    return "Afternoon";
  }
  if (part === "evening") {
    return "Evening";
  }
  if (part === "anytime") {
    return "Anytime / Flexible";
  }
  return "";
}

export function resolvedEndDate(schedule: ScheduleAnswers): string {
  if (schedule.oneDay) {
    return schedule.startDate;
  }
  return schedule.endDate || schedule.startDate;
}

export function composeScheduleLabel(schedule: ScheduleAnswers): string {
  if (schedule.dateInputMode === "text") {
    return schedule.dates.trim();
  }
  const calendar = formatHumanRange(schedule.startDate, resolvedEndDate(schedule));
  const bits: string[] = [];
  if (calendar !== "") {
    bits.push(calendar);
  }
  const exactClock = hasExactClock(schedule);
  if (exactClock && schedule.startTime !== "" && schedule.endTime !== "") {
    bits.push(`${schedule.startTime}–${schedule.endTime}`);
  } else if (exactClock && schedule.startTime !== "") {
    bits.push(`from ${schedule.startTime}`);
  } else if (exactClock && schedule.endTime !== "") {
    bits.push(`until ${schedule.endTime}`);
  }
  const part = schedule.startPeriod || schedule.endPeriod;
  if (part !== "" && part !== "anytime") {
    bits.push(periodLabel(part));
  }
  if (schedule.timeFlexible || part === "anytime") {
    bits.push(part === "anytime" ? "Anytime / Flexible" : "Flexible");
  }
  return bits.join(" · ");
}

export function rangeError(schedule: ScheduleAnswers): string {
  if (schedule.dateInputMode !== "structured") {
    return "";
  }
  if (schedule.oneDay || schedule.startDate === "" || schedule.endDate === "") {
    return "";
  }
  if (schedule.endDate < schedule.startDate) {
    return "End date cannot be before the start date.";
  }
  if (
    hasExactClock(schedule) &&
    schedule.startDate === schedule.endDate &&
    schedule.startTime !== "" &&
    schedule.endTime !== "" &&
    schedule.endTime < schedule.startTime
  ) {
    return "End time cannot be before the start time on the same day.";
  }
  return "";
}

export function hasExactClock(schedule: ScheduleAnswers): boolean {
  return (
    !schedule.timeFlexible &&
    schedule.startPeriod === "" &&
    schedule.endPeriod === "" &&
    (schedule.startTime !== "" || schedule.endTime !== "")
  );
}

export function seedScheduleFromText(text: string): ScheduleAnswers {
  const schedule = emptySchedule();
  const exact = parseExactCalendar(text);
  if (exact !== null) {
    schedule.startDate = exact.start;
    schedule.endDate = exact.end;
    schedule.oneDay = exact.start === exact.end;
    schedule.dates = formatHumanRange(exact.start, exact.end);
  }
  schedule.startPeriod = detectDayPart(text);
  schedule.endPeriod = schedule.startPeriod;
  schedule.timeFlexible = detectFlexible(text);
  if (schedule.startPeriod === "anytime") {
    schedule.timeFlexible = true;
  }
  return schedule;
}

export function parkingWindowFromSchedule(
  schedule: ScheduleAnswers,
  fallbackText: string,
): { start?: string; end?: string } {
  const exact =
    schedule.dateInputMode === "structured" && schedule.startDate !== ""
      ? { start: schedule.startDate, end: resolvedEndDate(schedule) }
      : parseExactCalendar(schedule.dates || fallbackText);
  if (exact === null) {
    return {};
  }
  return {
    start: `${exact.start}T${hhmm(schedule.startTime) ?? "13:00"}:00Z`,
    end: `${exact.end}T${hhmm(schedule.endTime) ?? "22:00"}:00Z`,
  };
}

export function localityLabel(city: string, airport: string): string {
  if (city !== "" && airport !== "") {
    return `${city} (${airport})`;
  }
  if (airport !== "") {
    return airport;
  }
  if (city !== "") {
    return city;
  }
  return "";
}

function monthNumber(name: string): string {
  return MONTH_INDEX[name.toLowerCase().replace(/\.$/, "")] ?? "";
}

function ymd(year: string, month: string, day: string): string | null {
  if (!/^\d{4}$/.test(year) || !/^\d{2}$/.test(month)) {
    return null;
  }
  const value = `${year}-${month}-${String(Number(day)).padStart(2, "0")}`;
  return validYmd(value) ? value : null;
}

function validYmd(value: string): boolean {
  const bits = splitYmd(value);
  if (bits === null) {
    return false;
  }
  const year = Number(bits.year);
  const month = Number(bits.month);
  const day = Number(bits.day);
  if (month < 1 || month > 12 || day < 1 || day > 31) {
    return false;
  }
  const date = new Date(Date.UTC(year, month - 1, day));
  return (
    date.getUTCFullYear() === year && date.getUTCMonth() === month - 1 && date.getUTCDate() === day
  );
}

function splitYmd(value: string): { year: string; month: string; day: string } | null {
  const match = value.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (match === null) {
    return null;
  }
  return { year: match[1] ?? "", month: match[2] ?? "", day: match[3] ?? "" };
}

function hhmm(value: string): string | null {
  const match = value.trim().match(/^([01]\d|2[0-3]):([0-5]\d)$/);
  if (match === null) {
    return null;
  }
  return `${match[1]}:${match[2]}`;
}
