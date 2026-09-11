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

function baseFacts() {
  return {
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
    hotelStated: false,
    flightStated: false,
    landing: false,
    travel: true,
    conference: false,
    nights: false,
    tripLike: true,
    dayPart: "",
    timeFlexible: false,
  };
}

function milanClarifyView(): AgentSessionView {
  const facts = baseFacts();
  const projection: AgentPlanProjection = {
    facts,
    questions: [],
    tasks: [],
    phase: "forming",
    title: "Milan",
    summary: "I'll assemble booking tasks after these answers. No domain is selected yet.",
    confirmedCount: 0,
    proposedCount: 0,
  };
  return {
    sessionId: "as_01k2m3n4p5q6r7s8t9v0w1x2k3",
    projection,
    questions: projection.questions,
    toolTrace: [],
    pendingAuthorizations: [],
    pendingAuthorization: null,
    parkingHandoff: null,
    confirmed: false,
    fallback: false,
    correlationId: "cr_01k2m3n4p5q6r7s8t9v0w1x2k3",
    transcript: [
      { role: "user", text: MILAN },
      {
        role: "agent",
        text: "I have Milan from Mumbai and the dates. I can help with hotels, car rentals, and parking. Say the word.",
      },
    ],
    domains: {},
    buyerSafeMessage:
      "I have Milan from Mumbai and the dates. I can help with hotels, car rentals, and parking. Say the word.",
    staySearch: null,
    sharedBookingContext: {
      facts: [
        {
          id: "originCity",
          label: "origin",
          value: "Mumbai",
          source: "buyer",
          provenance: "explicit",
        },
        {
          id: "destination",
          label: "destination",
          value: "Milan",
          source: "buyer",
          provenance: "explicit",
        },
        {
          id: "dates",
          label: "dates",
          value: "2026-10-20 to 2026-10-30",
          source: "buyer",
          provenance: "explicit",
        },
      ],
      note: "Shared context never travels as one payload.",
    },
    workspace: {
      persistence: "process-local",
      note: "API restart drops agent sessions; resume is not durable.",
    },
  };
}

function milanStayRentalView(): AgentSessionView {
  const view = milanClarifyView();
  return {
    ...view,
    projection: {
      ...view.projection,
      facts: { ...view.projection.facts, hotelStated: true, rentalStated: true, carNeed: "yes" },
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
          id: "task-rental",
          kind: "rental",
          code: "Rc",
          title: "Rental car",
          detail: "You asked for a car in Milan.",
          provenance: "explicit",
          support: "demonstration",
          supportLabel: "Demonstration task",
          accepted: true,
        },
      ],
      confirmedCount: 2,
      proposedCount: 0,
    },
    toolTrace: [{ kind: "execute", tool: "search_stay_offers" }],
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
        offerSet: { stale: false, snapshot: null },
      },
      rental: {
        kind: "rental",
        support: "demonstration",
        provenance: "explicit",
        accepted: true,
        fields: { when: { value: "", source: "current_turn", provenance: "explicit" } },
        missing: [],
        ask: [],
        completeness: "incomplete",
        offerSet: { stale: false, snapshot: null },
      },
    },
    staySearch: {
      status: "ok",
      label: "Labelled fake hotel search",
      providerId: "stay-adapter",
      source: "fake",
      stale: false,
      offerKind: "regular",
      query: {
        domain: "stay",
        destination: { kind: "city", value: "Milan" },
        origin: { kind: "city", value: "Mumbai" },
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
          cancellation: "Free cancellation until 24 hours before check-in",
          availability: "available",
          bookingAuthority: "none",
          offerKind: "regular",
          photoUrl: "https://cdn.example.invalid/spadari.jpg",
        },
      ],
      buyerSafeMessage: "Labelled fake hotel search: 3 properties. Not a booking.",
      bookingAuthority: "none",
    },
    transcript: [
      ...(view.transcript ?? []),
      { role: "user", text: "Flights are booked. I need a hotel and rental car." },
      {
        role: "agent",
        text: "Stay is on the plan. Hotel search is research only — nothing is booked. Rental is a requirement only — no rental inventory adapter is integrated.",
      },
    ],
  };
}

function milanStayRentalParkingView(): AgentSessionView {
  const view = milanStayRentalView();
  return {
    ...view,
    projection: {
      ...view.projection,
      facts: { ...view.projection.facts, parkingStated: true },
      tasks: [
        ...view.projection.tasks,
        {
          id: "task-parking",
          kind: "parking",
          code: "Pk",
          title: "Airport parking",
          detail: "You asked for airport parking in Milan.",
          provenance: "explicit",
          support: "live_simulated",
          supportLabel: "Live simulated path",
          accepted: true,
        },
      ],
    },
    domains: {
      ...view.domains,
      parking: {
        kind: "parking",
        support: "live_simulated",
        provenance: "explicit",
        accepted: true,
        fields: {
          airportCode: { value: "", source: "current_turn", provenance: "explicit" },
          start: { value: "2026-10-20", source: "earlier_turn", provenance: "explicit" },
          end: { value: "2026-10-30", source: "earlier_turn", provenance: "explicit" },
        },
        missing: ["airportCode"],
        ask: [{ id: "airportCode", ask: "Which airport do you need parking at?" }],
        completeness: "incomplete",
        offerSet: { stale: false, snapshot: null },
      },
    },
    transcript: [
      ...(view.transcript ?? []),
      { role: "user", text: "I also need parking." },
      { role: "agent", text: "Which airport do you need parking at?" },
    ],
  };
}

describe("COMP-UX-NEXT multi-domain workspace", () => {
  it("does not treat car parking as a rental request", () => {
    const facts = extractFacts(
      "travelling to manchester from 4th October to 10th October. need car parking and hotel",
    );
    expect(facts.parkingStated).toBe(true);
    expect(facts.hotelStated).toBe(true);
    expect(facts.rentalStated).toBe(false);
  });

  it("keeps Milan shared context and does not force domain cards", async () => {
    const view = milanClarifyView();
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
    fireEvent.change(field, { target: { value: MILAN } });
    await user.click(screen.getByRole("button", { name: "Start booking" }));
    expect(await screen.findByText(/SHARED BOOKING CONTEXT/i)).toBeTruthy();
    expect(screen.getAllByText("Mumbai").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Milan").length).toBeGreaterThan(0);
    expect(screen.queryByText("stay.search")).toBeNull();
    expect(screen.queryByText("parking.search")).toBeNull();
    expect(screen.queryByText("rental.search")).toBeNull();
    expect(screen.getAllByText(/Booking tasks are not selected yet/i).length).toBeGreaterThan(0);
    expect(screen.queryByText("Hotel Spadari al Duomo")).toBeNull();
  });

  it("renders stay sandbox results and rental without invented inventory", async () => {
    const first = milanClarifyView();
    const next = milanStayRentalView();
    const api = mockApi({
      createAgentSession: async () => first,
      getAgentSession: async () => first,
      postAgentTurn: async () => next,
      confirmAgentSession: async () => next,
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
    fireEvent.change(field, { target: { value: MILAN } });
    await user.click(screen.getByRole("button", { name: "Start booking" }));
    const chat = await screen.findByRole("textbox", { name: "Add anything else about this trip" });
    fireEvent.change(chat, {
      target: { value: "Flights are booked. I need a hotel and rental car." },
    });
    await user.click(screen.getByRole("button", { name: "Add note" }));
    expect(await screen.findByText("stay.search")).toBeTruthy();
    expect(screen.getByText("Hotel Spadari al Duomo")).toBeTruthy();
    expect(screen.getByLabelText("Stay offers, scroll sideways")).toBeTruthy();
    expect(screen.queryByText(/curated/i)).toBeNull();
    expect(screen.queryByText(/expires/i)).toBeNull();
    expect(screen.getByText("rental.search")).toBeTruthy();
    expect(screen.getAllByText(/No rental inventory adapter/i).length).toBeGreaterThan(0);
    expect(screen.queryByText("parking.search")).toBeNull();
    expect(screen.queryByText(/SkyShield/i)).toBeNull();
  });

  it("adds parking as an independent simulated lane", async () => {
    const first = milanClarifyView();
    const stay = milanStayRentalView();
    const parked = milanStayRentalParkingView();
    let turns = 0;
    const api = mockApi({
      createAgentSession: async () => first,
      getAgentSession: async () => first,
      postAgentTurn: async () => {
        turns += 1;
        return turns === 1 ? stay : parked;
      },
      confirmAgentSession: async () => parked,
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
    fireEvent.change(field, { target: { value: MILAN } });
    await user.click(screen.getByRole("button", { name: "Start booking" }));
    const chat = await screen.findByRole("textbox", { name: "Add anything else about this trip" });
    fireEvent.change(chat, {
      target: { value: "Flights are booked. I need a hotel and rental car." },
    });
    await user.click(screen.getByRole("button", { name: "Add note" }));
    fireEvent.change(
      await screen.findByRole("textbox", { name: "Add anything else about this trip" }),
      {
        target: { value: "I also need parking." },
      },
    );
    await user.click(screen.getByRole("button", { name: "Add note" }));
    expect(await screen.findByText("parking.search")).toBeTruthy();
    expect(screen.getAllByText(/simulated/i).length).toBeGreaterThan(0);
    expect(screen.getByText("stay.search")).toBeTruthy();
    expect(screen.getByText("rental.search")).toBeTruthy();
    expect(screen.getByText("Hotel Spadari al Duomo")).toBeTruthy();
  });
});
