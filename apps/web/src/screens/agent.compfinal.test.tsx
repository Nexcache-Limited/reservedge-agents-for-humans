import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it } from "vitest";
import type { AgentPlanProjection, AgentSessionView } from "../api/types.js";
import { AppRoutes } from "../App.js";
import { mockApi } from "../test/fixtures.js";
import { extractFacts } from "../intent-first/plan.js";

afterEach(() => {
  cleanup();
  sessionStorage.clear();
});

const MILAN = "I'm travelling to Milan from Mumbai from 20 to 30 October";

function milanStayExperienceView(): AgentSessionView {
  const facts = {
    destination: "Milan",
    originCity: "Mumbai",
    destinationAirport: "",
    parkingAirport: "",
    departureAirport: "",
    dates: "2026-10-20 to 2026-10-30",
    hasExactDates: true,
    hasLooseDates: true,
    startDate: "2026-10-20",
    endDate: "2026-10-30",
    carNeed: "" as const,
    parkingStated: false,
    rentalStated: false,
    entsStated: false,
    hotelStated: true,
    experienceStated: true,
    experiencePreferences: [] as string[],
    flightStated: false,
    flightSatisfied: true,
    landing: false,
    travel: true,
    conference: false,
    nights: false,
    tripLike: true,
    dayPart: "",
    timeFlexible: false,
  };
  const projection: AgentPlanProjection = {
    facts,
    questions: [],
    tasks: [
      {
        id: "task-hotel",
        kind: "hotel",
        code: "Ht",
        title: "Hotel",
        detail: "You mentioned accommodation.",
        provenance: "explicit",
        support: "sandbox_search",
        supportLabel: "Sandbox hotel search",
        accepted: true,
      },
      {
        id: "task-experience",
        kind: "experience",
        code: "Ex",
        title: "Experience",
        detail: "You asked for things to do, attractions, or experiences.",
        provenance: "explicit",
        support: "sandbox_search",
        supportLabel: "Sandbox experience search",
        accepted: true,
      },
    ],
    phase: "forming",
    title: "Milan",
    summary: "2 confirmed task(s), 0 proposed.",
    confirmedCount: 2,
    proposedCount: 0,
  };
  return {
    sessionId: "as_01k2m3n4p5q6r7s8t9v0w1x2k4",
    projection,
    questions: [],
    toolTrace: [
      { kind: "execute", tool: "search_stay_offers" },
      { kind: "execute", tool: "search_experience_offers" },
    ],
    pendingAuthorizations: [],
    pendingAuthorization: null,
    parkingHandoff: null,
    confirmed: false,
    fallback: false,
    correlationId: "cr_01k2m3n4p5q6r7s8t9v0w1x2k4",
    transcript: [
      { role: "user", text: MILAN },
      { role: "user", text: "Flights are booked. I need a hotel and some things to do." },
    ],
    domains: {
      stay: {
        kind: "hotel",
        support: "sandbox_search",
        provenance: "explicit",
        accepted: true,
        fields: {},
        missing: [],
        ask: [],
        completeness: "offers",
        offerSet: { stale: false, snapshot: null, intentId: null },
      },
      experience: {
        kind: "experience",
        support: "sandbox_search",
        provenance: "explicit",
        accepted: true,
        fields: {},
        missing: [],
        ask: [],
        completeness: "offers",
        offerSet: { stale: false, snapshot: null, intentId: null },
      },
    },
    buyerSafeMessage: "Stay and experience search are research only.",
    staySearch: {
      status: "ok",
      label: "Labelled fake hotel search",
      providerId: "liteapi",
      source: "fake",
      query: {
        domain: "stay",
        destination: { kind: "city", value: "Milan" },
        checkIn: "2026-10-20",
        checkOut: "2026-10-30",
      },
      offers: [
        {
          id: "fake-milan-spadari",
          name: "Hotel Spadari al Duomo",
          locality: "Milan, Italy",
          checkIn: "2026-10-20",
          checkOut: "2026-10-30",
          price: { currency: "EUR", amountMinor: 24000 },
          cancellation: "Free cancellation",
          availability: "available",
          bookingAuthority: "none",
          offerKind: "regular",
        },
      ],
      buyerSafeMessage: "Labelled fake hotel search: 1 property. Not a booking.",
      bookingAuthority: "none",
      stale: false,
      offerKind: "regular",
    },
    experienceSearch: {
      status: "ok",
      label: "Labelled fake experience search",
      providerId: "prioticket",
      source: "fake",
      query: {
        domain: "experience",
        destination: { kind: "city", value: "Milan" },
      },
      offers: [
        {
          id: "fake-milan-1",
          title: "Duomo rooftop and museum entry",
          category: "Museum",
          location: "Milan, Italy",
          availability: "available",
          price: { currency: "EUR", amountMinor: 4500 },
          durationMinutes: 120,
          cancellation: "Cancellation allowed",
          bookingAuthority: "none",
          offerKind: "regular",
        },
      ],
      buyerSafeMessage: "Labelled fake experience search: 1 experience. Not a booking.",
      bookingAuthority: "none",
      stale: false,
      offerKind: "regular",
    },
  };
}

describe("COMP-FINAL-01 experience workspace", () => {
  it("travel language does not make experience explicit", () => {
    const facts = extractFacts(MILAN);
    expect(facts.experienceStated).toBe(false);
    expect(facts.hotelStated).toBe(false);
  });

  it("renders stay hotel cards and experience cards as distinct lanes", async () => {
    const view = milanStayExperienceView();
    const api = mockApi({
      createAgentSession: async () => view,
      getAgentSession: async () => view,
      postAgentTurn: async () => view,
      confirmAgentSession: async () => view,
      subscribeAgentEvents: (_sessionId, handlers) => {
        handlers.onEvent({ kind: "OBJECTIVE_RECEIVED", message: "Understanding your objective" });
        return { close: () => undefined };
      },
    });
    const user = userEvent.setup();
    render(
      <MemoryRouter initialEntries={["/"]}>
        <AppRoutes api={api} />
      </MemoryRouter>,
    );
    const field = await screen.findByRole("textbox", {
      name: "What are you planning or trying to get done?",
    });
    fireEvent.change(field, {
      target: { value: "Flights are booked. I need a hotel and some things to do in Milan." },
    });
    await user.click(screen.getByRole("button", { name: "Start booking" }));
    expect(await screen.findByLabelText(/labelled fake hotel search/i)).toBeTruthy();
    expect(screen.getByLabelText(/labelled fake experience search/i)).toBeTruthy();
    expect(screen.getByText("Hotel Spadari al Duomo")).toBeTruthy();
    expect(screen.getByText("Duomo rooftop and museum entry")).toBeTruthy();
    expect(screen.getByText("Museum")).toBeTruthy();
    expect(screen.getByLabelText("Stay offers, scroll sideways")).toBeTruthy();
    expect(screen.getByLabelText("Experience offers, scroll sideways")).toBeTruthy();
    expect(screen.getAllByText(/experience.search/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/Prioticket research and availability only/i)).toBeTruthy();
    expect(screen.queryByText(/curated/i)).toBeNull();
    const workspace = document.querySelector(".re-clarify")?.textContent?.toLowerCase() ?? "";
    expect(workspace).not.toContain("jfk");
    expect(workspace).not.toContain("skyshield");
  });
});
