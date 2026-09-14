import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { AgentSessionView } from "../api/types.js";
import { AppRoutes } from "../App.js";
import { mockApi, rankedSnapshot } from "../test/fixtures.js";
import { extractFacts } from "../intent-first/plan.js";

afterEach(() => {
  cleanup();
  sessionStorage.clear();
});

const JOURNEY_B =
  "Travelling from Mumbai to London from 8 to 12 November. Need flight, hotel and car parking. " +
  "I need car parking in Heathrow from 8 am to 9 pm, preferable covered.";

function journeyView(overrides: Partial<AgentSessionView> = {}): AgentSessionView {
  return {
    sessionId: "as_01k2m3n4p5q6r7s8t9v0w1u2a",
    projection: {
      facts: {
        destination: "London",
        originCity: "Mumbai",
        destinationAirport: "",
        parkingAirport: "LHR",
        departureAirport: "",
        dates: "2026-11-08 to 2026-11-12",
        hasExactDates: true,
        hasLooseDates: true,
        startDate: "2026-11-08",
        endDate: "2026-11-12",
        carNeed: "",
        parkingStated: true,
        rentalStated: false,
        entsStated: false,
        hotelStated: true,
        experienceStated: false,
        experiencePreferences: [],
        flightStated: true,
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
          id: "task-flight",
          kind: "flight",
          code: "Fl",
          title: "Flight",
          detail: "BOM to LON",
          provenance: "explicit",
          support: "sandbox_search",
          supportLabel: "Sandbox flight search",
          accepted: true,
        },
        {
          id: "task-hotel",
          kind: "hotel",
          code: "Ht",
          title: "Hotel",
          detail: "London hotel",
          provenance: "explicit",
          support: "sandbox_search",
          supportLabel: "Sandbox hotel search",
          accepted: true,
        },
        {
          id: "task-parking",
          kind: "parking",
          code: "Pk",
          title: "Airport parking",
          detail: "LHR parking",
          provenance: "explicit",
          support: "live_simulated",
          supportLabel: "Live simulated path",
          accepted: true,
        },
      ],
      phase: "forming",
      title: "London",
      summary: "3 confirmed task(s).",
      confirmedCount: 3,
      proposedCount: 0,
    },
    questions: [],
    toolTrace: [],
    pendingAuthorizations: [],
    pendingAuthorization: null,
    parkingHandoff: null,
    confirmed: false,
    fallback: false,
    correlationId: "corr_uat02",
    buyerSafeMessage: "I have what I need to search for your flight, hotel, and parking at LHR.",
    transcript: [
      { role: "user", text: JOURNEY_B },
      {
        role: "agent",
        text: "Flight and hotel search results are ready and available in the panel on the right. Parking offers are available there as well.",
      },
    ],
    domains: {
      parking: {
        kind: "parking",
        support: "live_simulated",
        accepted: true,
        provenance: "explicit",
        completeness: "offers",
        intentId: "pi_01k2m3n4p5q6r7s8t9v0w1x2zz",
        fields: {
          airportCode: { value: "LHR", source: "current_turn", provenance: "explicit" },
          start: {
            value: "2026-11-08T08:00:00",
            source: "current_turn",
            provenance: "explicit",
          },
          end: {
            value: "2026-11-12T21:00:00",
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
        missing: [],
        ask: [],
        offerSet: { stale: false, snapshot: rankedSnapshot() },
      },
    },
    ...overrides,
  };
}

async function start(view: AgentSessionView) {
  let current = view;
  const intakeAccept = vi.fn(async () => {
    throw new Error("parking take must stay on /v1/agent grants");
  });
  const api = mockApi({
    createAgentSession: async () => current,
    getAgentSession: async () => current,
    postAgentTurn: async () => current,
    intakeAccept,
    grantAgentSession: async (_sessionId, body) => {
      const parking = current.domains?.parking;
      if (parking == null) {
        return current;
      }
      if (body.gate === "A3") {
        const offerId = body.offerId ?? parking.offerSet.snapshot?.recommendedOfferId ?? "";
        current = {
          ...current,
          pendingAuthorization: {
            gate: "A4",
            domain: "parking",
            prompt: "Authorize the simulated reservation?",
            resourceId: current.sessionId,
          },
          domains: {
            ...current.domains,
            parking: {
              ...parking,
              completeness: "accepted",
              offerSet: {
                ...parking.offerSet,
                snapshot: {
                  ...parking.offerSet.snapshot,
                  state: "ACCEPTANCE_RECORDED",
                  acceptance: {
                    acceptanceId: "ac_01k2m3n4p5q6r7s8t9v0w1x2d1",
                    offerId,
                    offerVersion: 1,
                    status: "recorded",
                  },
                },
              },
            },
          },
        };
      }
      if (body.gate === "A4") {
        const accepted = current.domains?.parking;
        if (accepted == null) {
          return current;
        }
        current = {
          ...current,
          pendingAuthorization: null,
          domains: {
            ...current.domains,
            parking: {
              ...accepted,
              completeness: "authorized",
              offerSet: {
                ...accepted.offerSet,
                snapshot: {
                  ...accepted.offerSet.snapshot,
                  state: "TRANSACTION_AUTHORIZED_SIMULATED",
                  transaction: {
                    authorizationId: "ta_01k2m3n4p5q6r7s8t9v0w1x2e1",
                    acceptanceId: "ac_01k2m3n4p5q6r7s8t9v0w1x2d1",
                    action: "reserve_parking",
                    mode: "SIMULATED",
                    amountMinor: 14800,
                    currency: "USD",
                    resultRef: "rr_01k2m3n4p5q6r7s8t9v0w1x2g1",
                  },
                },
              },
            },
          },
        };
      }
      return current;
    },
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
    { target: { value: JOURNEY_B } },
  );
  await user.click(screen.getByRole("button", { name: "Start booking" }));
  await screen.findByText("parking.search");
  return user;
}

describe("COMP-FINAL-HUMAN-UAT-02 chat UX", () => {
  it("does not render the LGA demo card inside an active Running conversation", async () => {
    await start(journeyView());
    const runningChat = document.querySelector(".re-list-chat") as HTMLElement | null;
    expect(runningChat).not.toBeNull();
    expect(within(runningChat as HTMLElement).queryByText(/LGA parking/i)).toBeNull();
    expect(screen.queryByText(/LGA parking/i)).toBeNull();
    expect(screen.queryByRole("button", { name: "Accept recommended offer" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Request parking offers" })).toBeNull();
  });

  it("keeps flight, hotel, then parking after search results", async () => {
    await start(journeyView());
    const titles = [...document.querySelectorAll(".re-clarify-task-title")].map(
      (item) => item.textContent?.trim() ?? "",
    );
    expect(
      titles.filter((title) => ["Flight", "Hotel", "Airport parking"].includes(title)),
    ).toEqual(["Flight", "Hotel", "Airport parking"]);
  });

  it("makes every simulated parking offer independently selectable", async () => {
    await start(journeyView());
    const cards = await screen.findByRole("list", { name: "Parking offers, scroll sideways" });
    expect(within(cards).getAllByRole("button", { name: "Take this one" })).toHaveLength(3);
    expect(within(cards).getAllByText("Curated offer").length).toBeGreaterThan(0);
  });

  it("shows the buyer message in chat before the plan update spinner", async () => {
    const hanging = mockApi({
      createAgentSession: async () => journeyView(),
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
      { target: { value: JOURNEY_B } },
    );
    await user.click(screen.getByRole("button", { name: "Start booking" }));
    const chat = await screen.findByLabelText("Add anything else about this trip");
    fireEvent.change(chat, { target: { value: "proceed" } });
    await user.click(screen.getByRole("button", { name: "Add note" }));
    const wrap = document.querySelector(".re-clarify-compose-wrap");
    expect(wrap).not.toBeNull();
    expect(within(wrap as HTMLElement).getByRole("status")).toHaveTextContent("Updating your plan");
    const log = document.querySelector(".re-clarify-log");
    expect(log?.textContent).toContain("proceed");
    expect(log?.textContent).not.toContain("Updating your plan");
  });

  it("keeps Running chat open and shows a parking receipt after authorization", async () => {
    const user = await start(journeyView());
    await user.click((await screen.findAllByRole("button", { name: "Take this one" }))[0]!);
    await user.click(await screen.findByRole("button", { name: /Authorize USD 148\.00/ }));
    expect(await screen.findByLabelText("Simulated parking receipt")).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Running" })).toHaveAttribute("aria-selected", "true");
    expect(document.querySelector(".re-list-chat")).not.toBeNull();
    await user.click(screen.getByRole("tab", { name: "History" }));
    const historyList = document.querySelector(".re-list") as HTMLElement;
    expect(within(historyList).getByText("Airport parking · LHR")).toBeInTheDocument();
    expect(within(historyList).getAllByText("Authorized · simulated").length).toBeGreaterThan(0);
    await user.click(screen.getByRole("tab", { name: "Running" }));
    expect(document.querySelector(".re-list-chat")).not.toBeNull();
    expect(screen.getByLabelText("Simulated parking receipt")).toBeInTheDocument();
  });

  it("scrolls the active chat when the buyer is already near the bottom", async () => {
    const scrollIntoView = vi.fn();
    HTMLElement.prototype.scrollIntoView = scrollIntoView;
    await start(journeyView());
    expect(scrollIntoView).toHaveBeenCalled();
  });

  it("parks Journey B and opens a blank New intent composer", async () => {
    const user = await start(journeyView());
    await user.click(screen.getAllByRole("button", { name: "New intent" })[0]!);
    expect(
      await screen.findByRole("heading", { name: "What are you planning or trying to get done?" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("textbox", { name: "What are you planning or trying to get done?" }),
    ).toHaveValue("");
    await user.click(screen.getByRole("tab", { name: "Pending" }));
    expect(screen.getByText("Paused here. Open to continue.")).toBeInTheDocument();
  });
});

describe("COMP-FINAL-HUMAN-UAT-02 route projection", () => {
  it("projects New York to London from a to-to utterance", () => {
    const facts = extractFacts("travelling to New York to London from 5th to 10th October");
    expect(facts.originCity).toBe("New York");
    expect(facts.destination).toBe("London");
  });
});
