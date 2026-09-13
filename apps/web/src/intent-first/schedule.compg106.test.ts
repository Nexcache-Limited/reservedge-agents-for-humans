import { describe, expect, it } from "vitest";
import { mergeSchedule, emptyAnswers } from "./plan.js";
import {
  composeScheduleLabel,
  formatHumanRange,
  parseExactCalendar,
  parkingWindowFromSchedule,
  rangeError,
  seedScheduleFromText,
  isRelativeDate,
  looksLikeDateRange,
} from "./schedule.js";

describe("intent-first schedule helpers", () => {
  it("parses an exact calendar range and formats it unambiguously", () => {
    const expected = { start: "2026-10-14", end: "2026-10-19" };
    expect(parseExactCalendar("14–19 October 2026")).toEqual(expected);
    expect(parseExactCalendar("14-19 October 2026")).toEqual(expected);
    expect(parseExactCalendar("14 to 19 October 2026")).toEqual(expected);
    expect(parseExactCalendar("from 14 to 19 October 2026")).toEqual(expected);
    expect(parseExactCalendar("I'm travelling to Edinburgh from 14 to 19 October 2026.")).toEqual(
      expected,
    );
    expect(formatHumanRange("2026-10-14", "2026-10-19")).toBe("14–19 Oct 2026");
  });

  it("does not collapse a malformed range into a single endpoint", () => {
    expect(parseExactCalendar("14 to October")).toBeNull();
    expect(parseExactCalendar("from 14 to sometime in October")).toBeNull();
    expect(parseExactCalendar("14 to 19 October")).toEqual({
      start: "2026-10-14",
      end: "2026-10-19",
    });
    expect(parseExactCalendar("from 20 to 30 October")).toEqual({
      start: "2026-10-20",
      end: "2026-10-30",
    });
    expect(parseExactCalendar("20th October to 25th")).toEqual({
      start: "2026-10-20",
      end: "2026-10-25",
    });
    expect(parseExactCalendar("20 October to 25")).toEqual({
      start: "2026-10-20",
      end: "2026-10-25",
    });
    expect(parseExactCalendar("20th October to 15th October")).toBeNull();
    expect(looksLikeDateRange("14 to October")).toBe(true);
    expect(looksLikeDateRange("from 14 to sometime in October")).toBe(true);
  });

  it("resolves a yearless day-month to the nearest future occurrence", () => {
    expect(parseExactCalendar("17 October", new Date("2026-09-13T00:00:00Z"))).toEqual({
      start: "2026-10-17",
      end: "2026-10-17",
    });
    expect(parseExactCalendar("17 October", new Date("2026-10-17T00:00:00Z"))).toEqual({
      start: "2026-10-17",
      end: "2026-10-17",
    });
    expect(parseExactCalendar("17 October", new Date("2026-10-18T00:00:00Z"))).toEqual({
      start: "2027-10-17",
      end: "2027-10-17",
    });
    expect(parseExactCalendar("17 October", new Date("2025-12-31T00:00:00Z"))).toEqual({
      start: "2026-10-17",
      end: "2026-10-17",
    });
  });

  it("still parses an ordinary single exact date", () => {
    expect(parseExactCalendar("19 October 2026")).toEqual({
      start: "2026-10-19",
      end: "2026-10-19",
    });
    expect(parseExactCalendar("October 16, 2026")).toEqual({
      start: "2026-10-16",
      end: "2026-10-16",
    });
  });

  it("leaves relative and month-only phrases unresolved", () => {
    expect(parseExactCalendar("next Thursday")).toBeNull();
    expect(parseExactCalendar("tomorrow afternoon")).toBeNull();
    expect(parseExactCalendar("in October")).toBeNull();
    expect(parseExactCalendar("14–19 October")).toEqual({
      start: "2026-10-14",
      end: "2026-10-19",
    });
    expect(isRelativeDate("next Thursday")).toBe(true);
    expect(isRelativeDate("14–19 October 2026")).toBe(false);
  });

  it("rejects an end date before the start date", () => {
    expect(
      rangeError({
        ...seedScheduleFromText(""),
        startDate: "2026-10-19",
        endDate: "2026-10-14",
        dateInputMode: "structured",
      }),
    ).toMatch(/before the start date/i);
  });

  it("does not treat morning/afternoon/evening/flexible as clock times", () => {
    const seeded = seedScheduleFromText("I need airport parking Friday evening but I'm flexible.");
    expect(seeded.startPeriod).toBe("evening");
    expect(seeded.timeFlexible).toBe(true);
    expect(parkingWindowFromSchedule(seeded, "Friday")).toEqual({});
    expect(composeScheduleLabel(seeded)).toMatch(/Evening/i);
    expect(composeScheduleLabel(seeded)).toMatch(/Flexible/i);
    expect(composeScheduleLabel(seeded)).not.toMatch(/\d{2}:\d{2}/);
  });

  it("keeps structured and text values when switching modes", () => {
    const structured = mergeSchedule(
      {
        ...emptyAnswers(),
        startDate: "2026-10-14",
        endDate: "2026-10-19",
        dateInputMode: "structured",
      },
      { dateInputMode: "text" },
      "Thursday",
    );
    expect(structured.dateInputMode).toBe("text");
    expect(structured.dates).toBe("14–19 Oct 2026");
    expect(structured.startDate).toBe("2026-10-14");
    const back = mergeSchedule(structured, { dateInputMode: "structured" }, "Thursday");
    expect(back.startDate).toBe("2026-10-14");
    expect(back.endDate).toBe("2026-10-19");
    const edited = mergeSchedule({ ...structured, dates: "next Thursday" }, {}, "Thursday");
    expect(edited.dates).toBe("next Thursday");
    expect(edited.startDate).toBe("2026-10-14");
    const relative = mergeSchedule(edited, { dateInputMode: "structured" }, "Thursday");
    expect(relative.startDate).toBe("2026-10-14");
    expect(parseExactCalendar("next Thursday")).toBeNull();
    expect(relative.dates).toBe("14–19 Oct 2026");
  });

  it("passes exact clock times through to the parking window without inventing a backend", () => {
    const window = parkingWindowFromSchedule(
      {
        ...seedScheduleFromText("14–19 October 2026"),
        startTime: "13:00",
        endTime: "18:30",
      },
      "",
    );
    expect(window.start).toBe("2026-10-14T13:00:00Z");
    expect(window.end).toBe("2026-10-19T18:30:00Z");
  });

  it("keeps exact dates when Evening, Morning, or Flexible is selected", () => {
    const dated = seedScheduleFromText("from 14 to 19 October 2026");
    const evening = parkingWindowFromSchedule(
      { ...dated, startPeriod: "evening", endPeriod: "evening" },
      "",
    );
    expect(evening.start).toContain("2026-10-14");
    expect(evening.end).toContain("2026-10-19");
    expect(evening.start).toBe("2026-10-14T13:00:00Z");
    expect(evening.end).toBe("2026-10-19T22:00:00Z");
    const morning = parkingWindowFromSchedule(
      { ...dated, startPeriod: "morning", endPeriod: "morning" },
      "",
    );
    expect(morning.start).toContain("2026-10-14");
    const flexible = parkingWindowFromSchedule(
      { ...dated, timeFlexible: true, startPeriod: "anytime" },
      "",
    );
    expect(flexible.start).toContain("2026-10-14");
    expect(flexible.end).toContain("2026-10-19");
    expect(composeScheduleLabel({ ...dated, startPeriod: "evening" })).toMatch(/Evening/);
    expect(composeScheduleLabel({ ...dated, startPeriod: "evening" })).not.toMatch(/13:00/);
  });

  it("does not erase dates when time mode changes, and does not erase day-part when dates change", () => {
    const dated = mergeSchedule(
      {
        ...emptyAnswers(),
        startDate: "2026-10-16",
        endDate: "2026-10-20",
        dateInputMode: "structured",
      },
      { startPeriod: "evening", endPeriod: "evening", startTime: "", endTime: "" },
      "",
    );
    expect(dated.startDate).toBe("2026-10-16");
    expect(dated.endDate).toBe("2026-10-20");
    expect(dated.startPeriod).toBe("evening");
    const clock = mergeSchedule(
      dated,
      { startTime: "13:00", endTime: "18:00", startPeriod: "", endPeriod: "", timeFlexible: false },
      "",
    );
    expect(clock.startDate).toBe("2026-10-16");
    expect(clock.startTime).toBe("13:00");
    const cleared = mergeSchedule(
      clock,
      { startTime: "", endTime: "", startPeriod: "evening", endPeriod: "evening" },
      "",
    );
    expect(cleared.startDate).toBe("2026-10-16");
    expect(cleared.endDate).toBe("2026-10-20");
    expect(cleared.startPeriod).toBe("evening");
    const moved = mergeSchedule(cleared, { endDate: "2026-10-21" }, "");
    expect(moved.startPeriod).toBe("evening");
    expect(moved.startDate).toBe("2026-10-16");
    expect(moved.endDate).toBe("2026-10-21");
  });
});
