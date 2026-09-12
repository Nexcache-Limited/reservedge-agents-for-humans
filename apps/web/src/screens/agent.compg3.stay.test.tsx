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

function milanClarifyView(): AgentSessionView {
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
    sessionId: "as_01k2m3n4p5q6r7s8t9v0w1x2k2",
    projection,
    questions: projection.questions,
    toolTrace: [],
    pendingAuthorizations: [],
    pendingAuthorization: null,
    parkingHandoff: null,
    confirmed: false,
    fallback: false,
    correlationId: "cr_01k2m3n4p5q6r7s8t9v0w1x2k2",
    transcript: [
      { role: "user", text: MILAN },
      {
        role: "agent",
        text: "I have Milan from Mumbai and the dates. I can help with hotels, airport parking, and things to do. Say the word.",
      },
    ],
    domains: {},
    buyerSafeMessage:
      "I have Milan from Mumbai and the dates. I can help with hotels, airport parking, and things to do. Say the word.",
    staySearch: null,
  };
}

function milanHotelView(): AgentSessionView {
  const view = milanClarifyView();
  return {
    ...view,
    projection: {
      ...view.projection,
      phase: "forming",
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
      ],
    },
    questions: [],
    toolTrace: [{ kind: "execute", tool: "search_stay_offers" }],
    staySearch: {
      status: "ok",
      label: "Labelled fake hotel search",
      providerId: "stay-adapter",
      source: "fake",
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
          photoUrl: "https://cdn.example.invalid/spadari.jpg",
        },
      ],
      buyerSafeMessage: "Labelled fake hotel search: 3 properties. Not a booking.",
      bookingAuthority: "none",
    },
  };
}

describe("COMP-G3 capability routing workspace", () => {
  it("keeps Milan origin/dates and does not invent JFK", () => {
    const facts = extractFacts(MILAN);
    expect(facts.destination).toBe("Milan");
    expect(facts.originCity).toBe("Mumbai");
    expect(facts.startDate).toBe("2026-10-20");
    expect(facts.endDate).toBe("2026-10-30");
    expect(facts.parkingAirport).toBe("");
    expect(facts.parkingStated).toBe(false);
    expect(JSON.stringify(facts).toLowerCase()).not.toContain("jfk");
  });

  it("enters the agent workspace and invites hotels, cars, and parking in chat", async () => {
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
    expect((await screen.findAllByText("Clarify & plan")).length).toBeGreaterThan(0);
    expect(screen.queryByRole("group", { name: "What should I help book?" })).toBeNull();
    expect(
      screen.getByText(/I can help with hotels, airport parking, and things to do/i),
    ).toBeTruthy();
    expect(screen.queryByLabelText(/labelled fake hotel search/i)).toBeNull();
    expect(screen.queryByText("Hotel Spadari al Duomo")).toBeNull();
    const workspace = document.querySelector(".re-clarify")?.textContent?.toLowerCase() ?? "";
    expect(workspace).toContain("milan");
    expect(workspace).toContain("mumbai");
    expect(workspace).not.toContain("jfk");
    expect(workspace).not.toContain("skyshield");
  });

  it("renders labelled hotel results under stay after the stay task is explicit", async () => {
    const view = milanHotelView();
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
    fireEvent.change(field, { target: { value: "I need a hotel in Milan from 20 to 30 October" } });
    await user.click(screen.getByRole("button", { name: "Start booking" }));
    expect(await screen.findByLabelText(/labelled fake hotel search/i)).toBeTruthy();
    expect(screen.getByText("Hotel Spadari al Duomo")).toBeTruthy();
    expect(screen.getByLabelText("Stay offers, scroll sideways")).toBeTruthy();
    expect(document.querySelector(".re-stay-search-photo")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Request sandbox hold" })).toBeTruthy();
    expect(screen.getByText(/research until a sandbox hold/i)).toBeTruthy();
  });

  it("does not paste concatenated chat notes as a third user bubble", async () => {
    const first = milanClarifyView();
    const afterDates = {
      ...first,
      transcript: [
        ...(first.transcript ?? []),
        { role: "user" as const, text: "20th October to 25th" },
        {
          role: "agent" as const,
          text: "I have Milan from Mumbai and the dates. I can help with hotels, airport parking, and things to do. Say the word.",
        },
      ],
    };
    const afterHotel = {
      ...milanHotelView(),
      transcript: [
        ...(afterDates.transcript ?? []),
        { role: "user" as const, text: "hotel booking" },
        {
          role: "agent" as const,
          text: "Stay is on the plan. Hotel search is research only — nothing is booked.",
        },
      ],
    };
    let turns = 0;
    const api = mockApi({
      createAgentSession: async () => first,
      getAgentSession: async () => first,
      postAgentTurn: async () => {
        turns += 1;
        return turns === 1 ? afterDates : afterHotel;
      },
      confirmAgentSession: async () => afterHotel,
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
    fireEvent.change(chat, { target: { value: "20th October to 25th" } });
    await user.click(screen.getByRole("button", { name: "Add note" }));
    fireEvent.change(
      await screen.findByRole("textbox", { name: "Add anything else about this trip" }),
      {
        target: { value: "hotel booking" },
      },
    );
    await user.click(screen.getByRole("button", { name: "Add note" }));
    expect(await screen.findAllByText("hotel booking")).toBeTruthy();
    const userBubbles = [...document.querySelectorAll(".re-clarify-bubble-user")].map(
      (node) => node.textContent,
    );
    expect(userBubbles).not.toContain("20th October to 25th hotel booking");
  });
});
