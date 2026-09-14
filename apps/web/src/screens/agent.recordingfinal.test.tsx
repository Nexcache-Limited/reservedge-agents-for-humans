import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it } from "vitest";
import type { AgentPlanProjection, AgentSessionView } from "../api/types.js";
import { AppRoutes } from "../App.js";
import { mockApi } from "../test/fixtures.js";
import { rankedSnapshot } from "../test/fixtures.js";

afterEach(() => {
  cleanup();
  sessionStorage.clear();
});

const LONDON_UAT =
  "Travelling from New York to London on 17 October. Need hotel in London for two days. " +
  "Also need covered parking in London from 5pm on the 17th October to 5pm on the 18th. " +
  "If any sightseeing attractions are there, show me that too.";

function facts() {
  return {
    destination: "London",
    originCity: "New York",
    destinationAirport: "",
    parkingAirport: "",
    departureAirport: "",
    dates: "2026-10-17 to 2026-10-19",
    hasExactDates: true,
    hasLooseDates: true,
    startDate: "2026-10-17",
    endDate: "2026-10-19",
    carNeed: "" as const,
    parkingStated: true,
    rentalStated: false,
    entsStated: false,
    hotelStated: true,
    experienceStated: true,
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
  };
}

function task(
  kind: "flight" | "hotel" | "parking" | "experience" | "rental",
  provenance: "explicit" | "proposed" = "explicit",
) {
  const titles = {
    flight: "Flight",
    hotel: "Hotel",
    parking: "Airport parking",
    experience: "Experience",
    rental: "Rental car",
  };
  return {
    id: `task-${kind}`,
    kind,
    code: kind.slice(0, 2),
    title: titles[kind],
    detail: `${kind} detail`,
    provenance,
    support: kind === "parking" ? ("live_simulated" as const) : ("sandbox_search" as const),
    supportLabel: kind === "parking" ? "Live simulated path" : "Sandbox search",
    accepted: provenance === "explicit",
  };
}

function projection(): AgentPlanProjection {
  return {
    facts: facts(),
    questions: [],
    tasks: [task("flight", "proposed"), task("hotel"), task("parking"), task("experience")],
    phase: "forming",
    title: "London",
    summary: "3 confirmed task(s), 1 proposed.",
    confirmedCount: 3,
    proposedCount: 1,
  };
}

function londonView(overrides: Partial<AgentSessionView> = {}): AgentSessionView {
  return {
    sessionId: "as_01k2m3n4p5q6r7s8t9v0w1rec",
    projection: projection(),
    questions: [],
    toolTrace: [],
    pendingAuthorizations: [],
    pendingAuthorization: null,
    parkingHandoff: null,
    confirmed: false,
    fallback: false,
    correlationId: "corr_recording",
    buyerSafeMessage: "Which London airport do you need parking at?",
    transcript: [
      { role: "user", text: LONDON_UAT },
      { role: "agent", text: "Which London airport do you need parking at?" },
    ],
    domains: {
      parking: {
        kind: "parking",
        support: "live_simulated",
        accepted: true,
        provenance: "explicit",
        completeness: "incomplete",
        fields: {
          start: {
            value: "2026-10-17T17:00:00",
            source: "current_turn",
            provenance: "explicit",
          },
          end: {
            value: "2026-10-18T17:00:00",
            source: "current_turn",
            provenance: "explicit",
          },
          covered: { value: "preferred", source: "current_turn", provenance: "explicit" },
          vehicleClass: {
            value: "standard",
            source: "system_proposal",
            provenance: "proposed",
          },
        },
        missing: ["airportCode"],
        ask: [{ id: "airportCode", ask: "Which London airport do you need parking at?" }],
        offerSet: { stale: false, snapshot: null },
      },
    },
    ...overrides,
  };
}

async function start(view: AgentSessionView) {
  const api = mockApi({
    createAgentSession: async () => view,
    getAgentSession: async () => view,
    postAgentTurn: async () => view,
    subscribeAgentEvents: () => ({ close: () => undefined }),
  });
  const user = userEvent.setup();
  render(
    <MemoryRouter initialEntries={["/"]}>
      <AppRoutes api={api} />
    </MemoryRouter>,
  );
  fireEvent.change(
    await screen.findByRole("textbox", {
      name: "What are you planning or trying to get done?",
    }),
    { target: { value: LONDON_UAT } },
  );
  await user.click(screen.getByRole("button", { name: "Start booking" }));
  await screen.findByText("parking.search");
  return user;
}

describe("COMP-RECORDING-FINAL-UX workspace", () => {
  it("renders one compact card per domain in flight → hotel → parking → experience order", async () => {
    await start(londonView());
    expect(
      await screen.findByText("Which London airport do you need parking at?"),
    ).toBeInTheDocument();
    const plan = document.querySelector(".re-clarify-plan") as HTMLElement;
    expect(plan).not.toBeNull();
    const kickers = within(plan)
      .getAllByText(/^(FLIGHT|STAY|PARKING|EXPERIENCE|RENTAL)$/)
      .map((node) => node.textContent);
    expect(kickers).toEqual(["FLIGHT", "STAY", "PARKING", "EXPERIENCE"]);
    expect(within(plan).getAllByText("Airport parking").length).toBe(1);
    expect(screen.queryByLabelText("Parking airportCode")).toBeNull();
    expect(screen.queryByText("LHR")).toBeNull();
    expect(screen.getByText(/17 Oct 17:00/)).toBeInTheDocument();
    expect(screen.getByText(/18 Oct 17:00/)).toBeInTheDocument();
    expect(screen.queryByText(/2026-10-17T17:00:00/)).toBeNull();
    expect(screen.queryByText(/2026-10-18T17:00:00/)).toBeNull();
    expect(screen.queryByText("Stay search waits until destination and dates")).toBeNull();
    expect(screen.queryByText("Experience search waits until a destination")).toBeNull();
  });

  it("keeps parking form fields behind Edit details", async () => {
    const user = await start(londonView());
    expect(await screen.findByText("parking.search")).toBeInTheDocument();
    expect(screen.queryByLabelText("Parking airportCode")).toBeNull();
    await user.click(await screen.findByRole("button", { name: "Edit details" }));
    expect(await screen.findByLabelText("Parking airportCode")).toBeInTheDocument();
  });

  it("renders parking offers as cards, not a numbered transcript list", async () => {
    const snapshot = rankedSnapshot();
    await start(
      londonView({
        domains: {
          parking: {
            kind: "parking",
            support: "live_simulated",
            accepted: true,
            provenance: "explicit",
            completeness: "offers",
            fields: {
              airportCode: { value: "LHR", source: "current_turn", provenance: "explicit" },
              start: {
                value: "2026-10-17T17:00:00",
                source: "current_turn",
                provenance: "explicit",
              },
              end: {
                value: "2026-10-18T17:00:00",
                source: "current_turn",
                provenance: "explicit",
              },
            },
            missing: [],
            ask: [],
            offerSet: { stale: false, snapshot },
          },
        },
      }),
    );
    expect(await screen.findByText("parking.search")).toBeInTheDocument();
    const cards = await screen.findByRole("list", { name: "Parking offers, scroll sideways" });
    expect(cards.tagName).toBe("UL");
    expect(cards.tagName).not.toBe("OL");
    expect(
      (await screen.findAllByRole("button", { name: "Take this one" })).length,
    ).toBeGreaterThan(0);
  });

  it("pins a stale hotel card above flight during stay refinement", async () => {
    await start(
      londonView({
        lastRevisedKind: "hotel",
        staySearch: {
          status: "ok",
          label: "Sandbox hotel search",
          providerId: "liteapi-hotels",
          source: "sandbox",
          offers: [],
          buyerSafeMessage: "",
          bookingAuthority: "none",
          stale: true,
        },
      }),
    );
    expect(
      await screen.findByText("Which London airport do you need parking at?"),
    ).toBeInTheDocument();
    const plan = document.querySelector(".re-clarify-plan") as HTMLElement;
    const kickers = within(plan)
      .getAllByText(/^(FLIGHT|STAY|PARKING|EXPERIENCE)$/)
      .map((node) => node.textContent);
    expect(kickers[0]).toBe("STAY");
    expect(kickers[1]).toBe("FLIGHT");
  });

  it("places Updating your plan next to the composer, not in the transcript", async () => {
    const hanging = mockApi({
      createAgentSession: async () => londonView(),
      postAgentTurn: () => new Promise(() => undefined),
      subscribeAgentEvents: () => ({ close: () => undefined }),
    });
    const user = userEvent.setup();
    render(
      <MemoryRouter initialEntries={["/"]}>
        <AppRoutes api={hanging} />
      </MemoryRouter>,
    );
    fireEvent.change(
      await screen.findByRole("textbox", {
        name: "What are you planning or trying to get done?",
      }),
      { target: { value: LONDON_UAT } },
    );
    await user.click(screen.getByRole("button", { name: "Start booking" }));
    const chat = await screen.findByLabelText("Add anything else about this trip");
    fireEvent.change(chat, { target: { value: "lhr" } });
    await user.click(screen.getByRole("button", { name: "Add note" }));
    const wrap = document.querySelector(".re-clarify-compose-wrap");
    expect(wrap).not.toBeNull();
    expect(within(wrap as HTMLElement).getByRole("status")).toHaveTextContent("Updating your plan");
    const log = document.querySelector(".re-clarify-log");
    expect(log?.textContent).not.toContain("Updating your plan");
    expect(log?.textContent).toContain("lhr");
  });

  it("turns the send arrow Reservedge orange when the composer has content", async () => {
    const user = await start(londonView());
    const send = screen.getByRole("button", { name: "Add note" });
    expect(send).toBeDisabled();
    expect(send.className).not.toContain("is-ready");
    await user.type(screen.getByLabelText("Add anything else about this trip"), "lhr");
    expect(send).toBeEnabled();
    expect(send.className).toContain("is-ready");
  });
});
