import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it } from "vitest";
import { AppRoutes } from "./App.js";
import { mockApi } from "./test/fixtures.js";

afterEach(() => {
  cleanup();
  sessionStorage.clear();
});

const EDINBURGH_DATES =
  "I'm travelling to Edinburgh for a conference 14–19 October 2026 and I'll need a car when I land.";
const JFK = "Airport parking at JFK next Thursday";
const FLEXIBLE = "I need airport parking Friday evening but I'm flexible.";
const EDINBURGH = "I'm travelling to Edinburgh for a conference and I'll need a car when I land.";

function renderApp(path = "/") {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AppRoutes api={mockApi()} />
    </MemoryRouter>,
  );
}

async function startObjective(text: string) {
  const user = userEvent.setup();
  renderApp("/");
  const field = await screen.findByRole("textbox", {
    name: "What are you planning or trying to get done?",
  });
  fireEvent.change(field, { target: { value: text } });
  const start = screen.getByRole("button", { name: "Start booking" });
  expect(start).toBeEnabled();
  await user.click(start);
  expect(
    await screen.findByRole("button", { name: "Answer and update plan" }, { timeout: 8000 }),
  ).toBeEnabled();
  return user;
}

function setDate(label: string, value: string) {
  fireEvent.change(screen.getByLabelText(label), { target: { value } });
}

function setTime(label: string, value: string) {
  fireEvent.change(screen.getByLabelText(label), { target: { value } });
}

function requirementValue(label: string): string {
  const row = screen.getByText(label).closest(".re-req-row");
  return (row?.querySelector(".re-req-value")?.textContent ?? "").trim();
}

function typedNeed(): string {
  return document.querySelector(".re-composer-col .re-card p")?.textContent ?? "";
}

async function expectPreparedParkingReview() {
  expect(screen.queryByRole("button", { name: "Send to Reservedge" })).toBeNull();
  expect(screen.queryByRole("button", { name: /Use the example/ })).toBeNull();
  expect(screen.queryByRole("textbox", { name: "What you need" })).toBeNull();
  expect(
    await screen.findByRole("button", { name: "Confirm requirement and research" }),
  ).toBeInTheDocument();
}

describe("intent-first date and time clarification", () => {
  it("pre-populates structured dates from an exact objective range and does not re-ask them", async () => {
    await startObjective(EDINBURGH_DATES);
    expect(await screen.findByText(EDINBURGH_DATES)).toBeInTheDocument();
    expect(screen.queryByLabelText("Start date")).toBeNull();
    expect(screen.getByLabelText("Departing from")).toBeInTheDocument();
    expect(screen.getByText("14–19 Oct 2026")).toBeInTheDocument();
    expect(screen.getByText("Rental car · Edinburgh")).toBeInTheDocument();
    expect(screen.queryByText("Airport parking · EDI")).toBeNull();
  });

  it("leaves next Thursday unresolved and offers a calendar instead of inventing a date", async () => {
    await startObjective(JFK);
    expect(await screen.findByRole("group", { name: "Exact dates" })).toBeInTheDocument();
    expect(screen.getByLabelText("Start date")).toHaveValue("");
    expect(screen.getByText(/You mentioned Thursday/i)).toBeInTheDocument();
  });

  it("resolves required dates from the calendar and carries them into parking", async () => {
    const user = await startObjective(JFK);
    setDate("Start date", "2026-10-16");
    setDate("End date", "2026-10-20");
    expect(screen.getByText("Selected 16–20 Oct 2026")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Answer and update plan" }));
    await user.click(screen.getByRole("button", { name: "Confirm plan" }));
    await user.click(screen.getByRole("button", { name: "Begin parking requirement" }));
    await expectPreparedParkingReview();
    expect(typedNeed()).toContain("16–20 Oct 2026");
    expect(typedNeed()).toContain("JFK");
    expect(screen.getByText("Live competition path")).toBeInTheDocument();
  });

  it("rejects an end date before the start date", async () => {
    await startObjective(JFK);
    setDate("Start date", "2026-10-20");
    setDate("End date", "2026-10-16");
    expect(screen.getByRole("alert")).toHaveTextContent(/before the start date/i);
    expect(screen.getByRole("button", { name: "Answer and update plan" })).toBeDisabled();
    expect(screen.getByLabelText("Start date")).toHaveValue("2026-10-20");
    expect(screen.getByLabelText("End date")).toHaveValue("2026-10-16");
  });

  it("lets the user select an optional exact clock time", async () => {
    const user = await startObjective(JFK);
    setDate("Start date", "2026-10-16");
    setDate("End date", "2026-10-16");
    setTime("Arrival / start time", "13:00");
    setTime("Departure / end time", "18:00");
    expect(screen.getByText(/Exact clock time selected: 13:00–18:00/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Answer and update plan" }));
    await user.click(screen.getByRole("button", { name: "Confirm plan" }));
    await user.click(screen.getByRole("button", { name: "Begin parking requirement" }));
    await expectPreparedParkingReview();
    expect(typedNeed()).toContain("13:00–18:00");
  });

  it("keeps Morning, Afternoon, Evening and Flexible distinct from HH:MM", async () => {
    const user = await startObjective(FLEXIBLE);
    expect(await screen.findByRole("button", { name: "Evening" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(screen.getByText(/Evening, flexible — not an exact HH:MM/)).toBeInTheDocument();
    expect(screen.getByLabelText("Arrival / start time")).toHaveValue("");
    await user.click(screen.getByRole("button", { name: "Morning" }));
    expect(screen.getByRole("button", { name: "Morning" })).toHaveAttribute("aria-pressed", "true");
    await user.click(screen.getByRole("button", { name: "Afternoon" }));
    expect(screen.getByRole("button", { name: "Afternoon" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    await user.click(screen.getByRole("button", { name: "Anytime / Flexible" }));
    expect(screen.getByRole("button", { name: "Anytime / Flexible" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(screen.getByLabelText("Arrival / start time")).toHaveValue("");
    expect(screen.getByText(/Anytime \/ Flexible — not an exact HH:MM/)).toBeInTheDocument();
  });

  it("keeps a natural-language alternative and does not corrupt values when switching", async () => {
    const user = await startObjective(JFK);
    setDate("Start date", "2026-10-16");
    setDate("End date", "2026-10-20");
    await user.click(screen.getByRole("button", { name: "Type dates instead" }));
    const text = screen.getByLabelText("Dates in your own words");
    expect(text).toHaveValue("16–20 Oct 2026");
    await user.clear(text);
    await user.type(text, "next Thursday evening");
    await user.click(screen.getByRole("button", { name: "Use calendar instead" }));
    expect(screen.getByLabelText("Start date")).toHaveValue("2026-10-16");
    expect(screen.getByLabelText("End date")).toHaveValue("2026-10-20");
  });

  it("preserves selected dates across Clarify & plan tabs and Intent / Bookings / Activity", async () => {
    const user = await startObjective(EDINBURGH);
    setDate("Start date", "2026-10-14");
    setDate("End date", "2026-10-19");
    await user.click(document.querySelector(".re-tabs a[href='/bookings']") as HTMLAnchorElement);
    expect(await screen.findByRole("heading", { name: "Bookings" })).toBeInTheDocument();
    await user.click(document.querySelector(".re-tabs a[href='/activity']") as HTMLAnchorElement);
    expect(await screen.findByRole("heading", { name: "Activity" })).toBeInTheDocument();
    await user.click(
      document.querySelector(".re-tabs a[href='/intents/clarify']") as HTMLAnchorElement,
    );
    expect(await screen.findByLabelText("Start date")).toHaveValue("2026-10-14");
    expect(screen.getByLabelText("End date")).toHaveValue("2026-10-19");
  });

  it("does not change the parking HTTP contract when confirmed exact values are carried forward", async () => {
    const user = await startObjective(EDINBURGH);
    setDate("Start date", "2026-10-14");
    setDate("End date", "2026-10-19");
    await user.type(screen.getByLabelText("Departing from"), "MAN");
    await user.click(screen.getByRole("button", { name: "Answer and update plan" }));
    await user.click(screen.getByRole("button", { name: "Confirm plan" }));
    await user.click(screen.getByRole("button", { name: "Begin parking requirement" }));
    await expectPreparedParkingReview();
    expect(typedNeed()).toContain("14–19 Oct 2026");
    expect(typedNeed()).toContain("EDI");
    expect(screen.getByText("Live competition path")).toBeInTheDocument();
  });

  it("preserves selected dates when switching Conversation and Plan on a narrow viewport", async () => {
    const matchMedia = window.matchMedia;
    window.matchMedia = ((query: string) => ({
      matches: query.includes("max-width: 1179px"),
      media: query,
      onchange: null,
      addListener: () => undefined,
      removeListener: () => undefined,
      addEventListener: () => undefined,
      removeEventListener: () => undefined,
      dispatchEvent: () => false,
    })) as typeof window.matchMedia;
    try {
      const user = await startObjective(JFK);
      setDate("Start date", "2026-10-16");
      setDate("End date", "2026-10-20");
      await user.click(screen.getByRole("tab", { name: /Plan/ }));
      expect(screen.getByText("16–20 Oct 2026")).toBeInTheDocument();
      await user.click(screen.getByRole("tab", { name: /Conversation/ }));
      expect(screen.getByLabelText("Start date")).toHaveValue("2026-10-16");
      expect(screen.getByLabelText("End date")).toHaveValue("2026-10-20");
    } finally {
      window.matchMedia = matchMedia;
    }
  });

  it("retains 14 to 19 October from natural speech and does not collapse to one date", async () => {
    const matchMedia = window.matchMedia;
    window.matchMedia = ((query: string) => ({
      matches: query.includes("max-width: 1179px"),
      media: query,
      onchange: null,
      addListener: () => undefined,
      removeListener: () => undefined,
      addEventListener: () => undefined,
      removeEventListener: () => undefined,
      dispatchEvent: () => false,
    })) as typeof window.matchMedia;
    try {
      const user = userEvent.setup();
      renderApp("/");
      const field = await screen.findByRole("textbox", {
        name: "What are you planning or trying to get done?",
      });
      fireEvent.change(field, {
        target: { value: "I'm travelling to Edinburgh from 14 to 19 October 2026." },
      });
      await user.click(screen.getByRole("button", { name: "Start booking" }));
      expect(
        await screen.findByRole("button", { name: "Confirm plan" }, { timeout: 8000 }),
      ).toBeInTheDocument();
      const planTab = screen.queryByRole("tab", { name: /Plan/ });
      if (planTab !== null && planTab.getAttribute("aria-selected") !== "true") {
        await user.click(planTab);
      }
      const range = /14\s*[–-]\s*19\s+Oct\s+2026/;
      expect(await screen.findByText(range, {}, { timeout: 8000 })).toHaveTextContent(range);
      expect(document.body.textContent ?? "").toMatch(range);
      expect(screen.queryByLabelText("Start date")).toBeNull();
      expect(screen.queryByText(/^19 Oct 2026$/)).toBeNull();
      expect(screen.queryByText(/^14 Oct 2026$/)).toBeNull();
      expect(screen.queryByLabelText("Departing from")).toBeNull();
      expect(screen.queryByRole("group", { name: "What should I help book?" })).toBeNull();
      expect(screen.getByRole("button", { name: "Confirm plan" })).toBeInTheDocument();
      expect(screen.queryByText("Airport parking · EDI")).toBeNull();
    } finally {
      window.matchMedia = matchMedia;
    }
  });

  it("keeps 16–20 Oct after Evening and hands those dates into parking", async () => {
    const user = await startObjective(JFK);
    setDate("Start date", "2026-10-16");
    setDate("End date", "2026-10-20");
    await user.click(screen.getByRole("button", { name: "Evening" }));
    expect(screen.getByLabelText("Start date")).toHaveValue("2026-10-16");
    expect(screen.getByLabelText("End date")).toHaveValue("2026-10-20");
    expect(screen.getByRole("button", { name: "Evening" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByLabelText("Arrival / start time")).toHaveValue("");
    await user.click(screen.getByRole("button", { name: "Answer and update plan" }));
    expect(screen.queryByLabelText("Start date")).toBeNull();
    expect(screen.getByText(/are not asked again/i)).toBeInTheDocument();
    expect(screen.getAllByText("Airport parking · JFK").length).toBeGreaterThan(0);
    expect(screen.queryByRole("button", { name: "Not needed" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Add to plan" })).toBeNull();
    await user.click(screen.getByRole("button", { name: "Confirm plan" }));
    await user.click(screen.getByRole("button", { name: "Begin parking requirement" }));
    await expectPreparedParkingReview();
    expect(typedNeed()).toContain("16–20 Oct 2026");
    expect(typedNeed()).toMatch(/Evening/i);
    expect(requirementValue("START")).toContain("2026-10-16");
    expect(requirementValue("END")).toContain("2026-10-20");
    expect(requirementValue("START")).not.toBe("Not answered yet");
    expect(requirementValue("END")).not.toBe("Not answered yet");
  });

  it("treats jfk+evening as the live parking path and does not re-ask dates after they are answered", async () => {
    const user = await startObjective("jfk+evening");
    expect(await screen.findByText("jfk+evening")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Evening" })).toHaveAttribute("aria-pressed", "true");
    setDate("Start date", "2026-10-16");
    setDate("End date", "2026-10-20");
    await user.click(screen.getByRole("button", { name: "Answer and update plan" }));
    expect(screen.queryByLabelText("Start date")).toBeNull();
    expect(screen.queryByLabelText("End date")).toBeNull();
    expect(screen.getByText(/are not asked again/i)).toBeInTheDocument();
    expect(screen.getAllByText("Airport parking · JFK").length).toBeGreaterThan(0);
    expect(screen.getByText("You asked for this.")).toBeInTheDocument();
    expect(screen.getByText("Live simulated path")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Not needed" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Add to plan" })).toBeNull();
    expect(screen.queryByText(/No domain was named/)).toBeNull();
    await user.click(screen.getByRole("button", { name: "Confirm plan" }));
    await user.click(screen.getByRole("button", { name: "Begin parking requirement" }));
    await expectPreparedParkingReview();
    expect(typedNeed()).toContain("16–20 Oct 2026");
    expect(typedNeed()).toMatch(/Evening/i);
    expect(typedNeed()).not.toMatch(/\d{2}:\d{2}/);
    expect(requirementValue("START")).toContain("2026-10-16");
    expect(requirementValue("END")).toContain("2026-10-20");
  });

  it("keeps the date range when Anytime / Flexible is chosen, without an artificial clock", async () => {
    const user = await startObjective(JFK);
    setDate("Start date", "2026-10-16");
    setDate("End date", "2026-10-20");
    await user.click(screen.getByRole("button", { name: "Anytime / Flexible" }));
    expect(screen.getByLabelText("Start date")).toHaveValue("2026-10-16");
    expect(screen.getByLabelText("End date")).toHaveValue("2026-10-20");
    expect(screen.getByLabelText("Arrival / start time")).toHaveValue("");
    await user.click(screen.getByRole("button", { name: "Answer and update plan" }));
    await user.click(screen.getByRole("button", { name: "Confirm plan" }));
    await user.click(screen.getByRole("button", { name: "Begin parking requirement" }));
    await expectPreparedParkingReview();
    expect(requirementValue("START")).toContain("2026-10-16");
    expect(requirementValue("END")).toContain("2026-10-20");
    expect(typedNeed()).toMatch(/Flexible/i);
  });

  it("preserves dates plus Evening across Conversation and Plan on a narrow viewport", async () => {
    const matchMedia = window.matchMedia;
    window.matchMedia = ((query: string) => ({
      matches: query.includes("max-width: 1179px"),
      media: query,
      onchange: null,
      addListener: () => undefined,
      removeListener: () => undefined,
      addEventListener: () => undefined,
      removeEventListener: () => undefined,
      dispatchEvent: () => false,
    })) as typeof window.matchMedia;
    try {
      const user = await startObjective(JFK);
      setDate("Start date", "2026-10-16");
      setDate("End date", "2026-10-20");
      await user.click(screen.getByRole("button", { name: "Evening" }));
      await user.click(screen.getByRole("tab", { name: /Plan/ }));
      expect(screen.getByText("16–20 Oct 2026")).toBeInTheDocument();
      expect(screen.getByText(/No domain is selected yet/)).toBeInTheDocument();
      await user.click(screen.getByRole("tab", { name: /Conversation/ }));
      expect(screen.getByLabelText("Start date")).toHaveValue("2026-10-16");
      expect(screen.getByLabelText("End date")).toHaveValue("2026-10-20");
      expect(screen.getByRole("button", { name: "Evening" })).toHaveAttribute(
        "aria-pressed",
        "true",
      );
    } finally {
      window.matchMedia = matchMedia;
    }
  });

  it("does not lose a typed from-to range when switching structured and text", async () => {
    const user = await startObjective(JFK);
    await user.click(screen.getByRole("button", { name: "Type dates instead" }));
    const text = screen.getByLabelText("Dates in your own words");
    await user.clear(text);
    await user.type(text, "from 14 to 19 October 2026");
    await user.click(screen.getByRole("button", { name: "Use calendar instead" }));
    expect(screen.getByLabelText("Start date")).toHaveValue("2026-10-14");
    expect(screen.getByLabelText("End date")).toHaveValue("2026-10-19");
  });
});
