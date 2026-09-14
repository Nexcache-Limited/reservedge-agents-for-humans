import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it } from "vitest";
import { AppRoutes } from "../App.js";
import type { AgentSessionView } from "../api/types.js";
import { mockApi } from "../test/fixtures.js";
import { sessionFromAgentView } from "../intent-first/agent.js";
import { isLiveChatRow, parkingHistoryRow, planSessionToRow } from "../reservedge/plan-inbox.js";

afterEach(() => {
  cleanup();
  sessionStorage.clear();
});

function readyParkingView(sessionId = "as_01k2m3n4p5q6r7s8t9v0w1x2aa"): AgentSessionView {
  return {
    sessionId,
    projection: {
      facts: {
        destination: "London",
        originCity: "",
        destinationAirport: "LHR",
        parkingAirport: "LHR",
        departureAirport: "",
        dates: "2026-11-10 to 2026-11-15",
        hasExactDates: true,
        hasLooseDates: false,
        startDate: "2026-11-10",
        endDate: "2026-11-15",
        carNeed: "",
        parkingStated: true,
        rentalStated: false,
        entsStated: false,
        hotelStated: true,
        experienceStated: false,
        experiencePreferences: [],
        flightStated: false,
        flightSatisfied: false,
        helpWith: "",
        landing: false,
        travel: true,
        conference: false,
        nights: false,
        tripLike: true,
        dayPart: "",
        timeFlexible: false,
      },
      questions: [],
      tasks: [
        {
          id: "task-hotel",
          kind: "hotel",
          code: "Ht",
          title: "Hotel",
          detail: "explicit hotel",
          provenance: "explicit",
          support: "sandbox_search",
          supportLabel: "Sandbox search",
          accepted: true,
        },
        {
          id: "task-parking",
          kind: "parking",
          code: "Pk",
          title: "Airport parking",
          detail: "explicit parking",
          provenance: "explicit",
          support: "live_simulated",
          supportLabel: "Live simulated path",
          accepted: true,
        },
      ],
      phase: "forming",
      title: "London · stay + parking",
      summary: "2 confirmed task(s), 0 proposed.",
      confirmedCount: 2,
      proposedCount: 0,
    },
    questions: [],
    toolTrace: [{ kind: "plan" }],
    pendingAuthorizations: [],
    pendingAuthorization: null,
    pendingSearchAuthorization: {
      capabilities: ["stay.search", "parking.search"],
      fingerprints: {
        "stay.search": "London|2026-11-10|2026-11-15",
        "parking.search": "LHR|2026-11-10T08:00:00Z|2026-11-15T18:00:00Z|standard|preferred",
      },
      prompt:
        "I have what I need to search for your hotel and covered parking at LHR. Shall I search both now?",
    },
    parkingHandoff: null,
    confirmed: false,
    fallback: false,
    correlationId: "cr_01k2m3n4p5q6r7s8t9v0w1x2k2",
    transcript: [
      { role: "user", text: "need hotel and covered parking at Heathrow from 10 to 15 November" },
      {
        role: "agent",
        text: "I have what I need to search for your hotel and covered parking at LHR. Shall I search both now?",
      },
    ],
    domains: {
      parking: {
        kind: "parking",
        support: "live_simulated",
        provenance: "explicit",
        accepted: true,
        fields: {
          airportCode: { value: "LHR", source: "current_turn", provenance: "explicit" },
          start: { value: "2026-11-10T08:00:00Z", source: "current_turn", provenance: "explicit" },
          end: { value: "2026-11-15T18:00:00Z", source: "current_turn", provenance: "explicit" },
        },
        missing: [],
        ask: [],
        completeness: "ready",
        offerSet: { stale: false, snapshot: null },
        intentId: "pi_01k2m3n4p5q6r7s8t9v0w1x2zz",
      },
    },
    buyerSafeMessage:
      "I have what I need to search for your hotel and covered parking at LHR. Shall I search both now?",
  };
}

describe("COMP-REMEDIATION-01 resume identity", () => {
  it("keeps Running chats on the agent session id even after a parking intent id exists", () => {
    const view = readyParkingView();
    const session = sessionFromAgentView("need hotel and parking", view);
    const row = planSessionToRow(session);
    expect(row?.id).toBe(view.sessionId);
    expect(row?.id.startsWith("as_")).toBe(true);
    expect(isLiveChatRow(session, view.sessionId)).toBe(true);
    expect(isLiveChatRow(session, "pi_01k2m3n4p5q6r7s8t9v0w1x2zz")).toBe(true);
  });

  it("keeps the live chat identity after parking is authorized", () => {
    const view = readyParkingView();
    const parking = view.domains?.parking;
    if (parking != null) {
      parking.completeness = "authorized";
    }
    const session = sessionFromAgentView("need hotel and parking", view);
    expect(isLiveChatRow(session, view.sessionId)).toBe(true);
    expect(isLiveChatRow(session, `${view.sessionId}:parking`)).toBe(true);
    expect(planSessionToRow(session)?.status).toBe("running");
    expect(parkingHistoryRow(session)?.status).toBe("done");
    expect(parkingHistoryRow(session)?.title).toBe("Airport parking · LHR");
  });

  it("reopens a Running chat into Clarify & plan instead of Unknown intent", async () => {
    const view = readyParkingView();
    const api = mockApi({
      createAgentSession: async () => view,
      getAgentSession: async () => view,
      postAgentTurn: async () => view,
      getOwnedIntent: async () => {
        throw new Error("parking PI should not be fetched for a live agent chat");
      },
      subscribeAgentEvents: () => ({ close: () => undefined }),
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
      target: { value: "need hotel and covered parking at Heathrow from 10 to 15 November" },
    });
    await user.click(screen.getByRole("button", { name: "Start booking" }));
    expect(await screen.findByRole("heading", { name: "Booking Chats" })).toBeInTheDocument();
    await user.click(screen.getByRole("tab", { name: "Running" }));
    expect(screen.queryByRole("heading", { name: "Unknown intent" })).toBeNull();
    expect(screen.getAllByText(/Shall I search both now/i).length).toBeGreaterThan(0);
  });

  it("renders independent flight, hotel, and parking lanes after search", async () => {
    const view = readyParkingView();
    const searched: AgentSessionView = {
      ...view,
      pendingSearchAuthorization: null,
      projection: {
        ...view.projection,
        tasks: [
          ...view.projection.tasks,
          {
            id: "task-flight",
            kind: "flight",
            code: "Fl",
            title: "Flight",
            detail: "Manchester to Heathrow",
            provenance: "explicit",
            support: "sandbox_search",
            supportLabel: "Sandbox search",
            accepted: true,
          },
        ],
      },
      staySearch: {
        status: "ok",
        label: "Sandbox hotel search",
        providerId: "liteapi-hotels",
        source: "sandbox",
        offers: [
          {
            id: "stay-1",
            name: "Heathrow Gate Hotel",
            locality: "Hounslow",
            checkIn: "2026-11-10",
            checkOut: "2026-11-15",
            price: { currency: "GBP", amountMinor: 18000 },
            cancellation: "Free cancellation",
            availability: "available",
            bookingAuthority: "none",
          },
        ],
        buyerSafeMessage: "Sandbox hotel search: 1 property. Not a booking.",
        bookingAuthority: "none",
      },
      flightSearch: {
        status: "ok",
        label: "Sandbox flight search",
        providerId: "liteapi-flights",
        source: "sandbox",
        query: { origin: "MAN", destination: "LHR", date: "2026-10-25" },
        offers: [
          {
            id: "flt-1",
            origin: "MAN",
            destination: "LHR",
            departure: "2026-10-25T07:00:00Z",
            arrival: "2026-10-25T08:10:00Z",
            airline: "BA",
            stops: 0,
            durationMinutes: 70,
            cabin: "ECONOMY",
            price: { currency: "GBP", amountMinor: 8900 },
            bookingAuthority: "none",
          },
        ],
        buyerSafeMessage: "Sandbox flight search: 1 offer. Selecting is not a ticket.",
        bookingAuthority: "none",
      },
      buyerSafeMessage: "Here are independent flight, hotel, and parking results.",
      transcript: [
        { role: "user", text: "flight hotel and parking" },
        {
          role: "agent",
          text: "Here are independent flight, hotel, and parking results.",
        },
      ],
    };
    const api = mockApi({
      createAgentSession: async () => searched,
      getAgentSession: async () => searched,
      postAgentTurn: async () => searched,
      subscribeAgentEvents: () => ({ close: () => undefined }),
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
      target: {
        value: "I need a flight from Manchester to Heathrow, a hotel, and parking",
      },
    });
    await user.click(screen.getByRole("button", { name: "Start booking" }));
    expect(await screen.findByText("FLIGHT")).toBeInTheDocument();
    expect(screen.getByText("flight.search")).toBeInTheDocument();
    expect(screen.getByText(/MAN → LHR/)).toBeInTheDocument();
    expect(screen.getByText("Heathrow Gate Hotel")).toBeInTheDocument();
    expect(screen.getByText("Sandbox search. Not a ticket.")).toBeInTheDocument();
    expect(screen.queryByText("ITAA")).toBeNull();
  });
});
