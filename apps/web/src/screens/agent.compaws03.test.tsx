import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it } from "vitest";
import { ClosedApiError } from "../api/errors.js";
import type {
  AgentFacts,
  AgentPlanProjection,
  AgentPlanTask,
  AgentSessionView,
  ItaaApi,
} from "../api/types.js";
import { AppRoutes } from "../App.js";
import { mockApi, rankedSnapshot } from "../test/fixtures.js";
import { createPlanSession, projectPlan } from "../intent-first/plan.js";

afterEach(() => {
  cleanup();
  sessionStorage.clear();
});

const DEMO_A =
  "I'm flying from JFK on September 3 at 1 PM and returning September 8 at 10 PM. " +
  "I have a standard EV, prefer covered parking, and don't want a shuttle longer than 20 minutes.";
const DEMO_B =
  "I'm travelling from London to Edinburgh for a conference 14–19 October 2026 " +
  "and I'll need a car when I land, somewhere near the venue.";
const DEMO_C = "I'm going away next month and I'll need a car.";
const GENERIC = "Can you help me organise a quiet weekend with friends in Manchester?";
const EDINBURGH_CAR = "I'm travelling to Edinburgh for a conference and need a car.";
const FOLLOW_UP = "I'm leaving from LHR (Heathrow) on 14–19 October.";
const NYC = "travelling to New York for 10 days.";
const NYC_PARK = "travelling to New York for 10 days. need parking and rental car.";
const ALSO_PARKING = "I also need parking";

function facts(overrides: Partial<AgentFacts> = {}): AgentFacts {
  return {
    destination: "",
    destinationAirport: "",
    parkingAirport: "",
    departureAirport: "",
    dates: "",
    hasExactDates: false,
    hasLooseDates: false,
    startDate: "",
    endDate: "",
    carNeed: "",
    parkingStated: false,
    rentalStated: false,
    entsStated: false,
    hotelStated: false,
    flightStated: false,
    landing: false,
    travel: false,
    conference: false,
    nights: false,
    tripLike: false,
    dayPart: "",
    timeFlexible: false,
    ...overrides,
  };
}

function task(
  kind: AgentPlanTask["kind"],
  provenance: AgentPlanTask["provenance"],
  extra: Partial<AgentPlanTask> = {},
): AgentPlanTask {
  const support =
    kind === "parking"
      ? "live_simulated"
      : kind === "rental" || kind === "ents"
        ? "demonstration"
        : kind === "hotel" || kind === "experience"
          ? "sandbox_search"
          : "unsupported";
  const supportLabel =
    support === "live_simulated"
      ? "Live simulated path"
      : support === "demonstration"
        ? "Demonstration task"
        : support === "sandbox_search"
          ? "Sandbox search"
          : "Unsupported in this build";
  const titles: Record<AgentPlanTask["kind"], string> = {
    parking: "Airport parking",
    rental: "Rental car",
    ents: "Entertainment",
    flight: "Flight",
    hotel: "Hotel",
    experience: "Experience",
  };
  return {
    id: `task-${kind}`,
    kind,
    code: kind.slice(0, 2).replace(/^./, (ch) => ch.toUpperCase()),
    title: titles[kind],
    detail: `${provenance} ${kind}`,
    provenance,
    support,
    supportLabel,
    accepted: provenance === "explicit",
    ...extra,
  };
}

function projection(overrides: Partial<AgentPlanProjection>): AgentPlanProjection {
  const questions = overrides.questions ?? [];
  return {
    facts: facts(),
    questions,
    tasks: [],
    phase: questions.length > 0 ? "clarify" : "forming",
    title: "Trip",
    summary: "Plan",
    confirmedCount: 0,
    proposedCount: 0,
    ...overrides,
  };
}

function view(
  sessionId: string,
  body: Partial<AgentSessionView> & { projection: AgentPlanProjection },
): AgentSessionView {
  return {
    sessionId,
    questions: body.projection.questions,
    toolTrace: [],
    pendingAuthorizations: [],
    pendingAuthorization: null,
    parkingHandoff: null,
    confirmed: false,
    fallback: false,
    correlationId: "cr_01k2m3n4p5q6r7s8t9v0w1x2k2",
    transcript: [
      { role: "user", text: "objective" },
      { role: "agent", text: body.projection.summary },
    ],
    domains: {},
    buyerSafeMessage: body.projection.summary,
    ...body,
  };
}

function demoA(): AgentPlanProjection {
  return projection({
    facts: facts({
      parkingAirport: "JFK",
      departureAirport: "JFK",
      dates: "2026-09-03 to 2026-09-08",
      hasExactDates: true,
      parkingStated: true,
      flightStated: true,
    }),
    tasks: [task("parking", "explicit", { title: "Airport parking · JFK" })],
    phase: "forming",
    title: "Airport parking · JFK",
    confirmedCount: 1,
  });
}

function demoB(): AgentPlanProjection {
  return projection({
    facts: facts({
      destination: "Edinburgh",
      destinationAirport: "EDI",
      parkingAirport: "",
      departureAirport: "LHR",
      dates: "2026-10-14 to 2026-10-19",
      hasExactDates: true,
      carNeed: "yes",
      rentalStated: true,
      travel: true,
      conference: true,
      landing: true,
      tripLike: true,
    }),
    tasks: [
      task("rental", "explicit", { title: "Rental car · Edinburgh" }),
      task("parking", "inferred", { title: "Airport parking" }),
      task("hotel", "proposed", { title: "Hotel" }),
      task("flight", "proposed", { title: "Flight" }),
    ],
    phase: "forming",
    title: "Edinburgh conference",
    confirmedCount: 2,
    proposedCount: 2,
  });
}

function demoC(
  overrides: Partial<AgentFacts> = {},
  questions?: AgentPlanProjection["questions"],
): AgentPlanProjection {
  const next = facts({
    carNeed: "yes",
    rentalStated: true,
    tripLike: true,
    ...overrides,
  });
  const blocking = questions ?? [
    ...(next.hasExactDates
      ? []
      : [
          {
            id: "dates" as const,
            label: "Exact dates",
            why: "Sets parking duration, car hire window and hotel nights.",
          },
        ]),
    ...(next.departureAirport
      ? []
      : [
          {
            id: "departureAirport" as const,
            label: "Departing from",
            why: "Only the airport code reaches parking suppliers. Not your address.",
          },
        ]),
  ];
  return projection({
    facts: next,
    questions: blocking,
    tasks: [
      task("rental", "explicit"),
      ...(next.destination === "Edinburgh"
        ? [task("parking", "inferred"), task("hotel", "proposed")]
        : []),
    ],
    phase: blocking.length > 0 ? "clarify" : "forming",
    title: next.destination || "Trip",
    confirmedCount: blocking.length > 0 ? 0 : 1,
  });
}

function fromLocalPlan(objective: string, extraNote = ""): AgentPlanProjection {
  const session = createPlanSession(objective);
  session.extraNote = extraNote;
  const planned = projectPlan(session);
  return projection({
    facts: planned.facts,
    questions: planned.questions.map((question) => ({
      id: question.id,
      label: question.label,
      why: question.why,
    })),
    tasks: planned.tasks,
    phase: planned.questions.length > 0 ? "clarify" : "forming",
    title: planned.title,
    summary: planned.summary,
    confirmedCount: planned.confirmedCount,
    proposedCount: planned.proposedCount,
  });
}

function genericManchester(): AgentPlanProjection {
  return projection({
    facts: facts({ destination: "Manchester", destinationAirport: "MAN", tripLike: true }),
    tasks: [],
    phase: "clarify",
    title: "Manchester",
    questions: [{ id: "dates", label: "Exact dates", why: "Sets parking duration." }],
    proposedCount: 0,
  });
}

function providerApi(): ItaaApi {
  const store = new Map<string, { objective: string; view: AgentSessionView }>();
  const owned = new Map<string, ReturnType<typeof rankedSnapshot>>();
  let seq = 0;
  const grantRef: {
    run?: (sessionId: string, body: { gate: "A2"; domain: "parking" }) => Promise<AgentSessionView>;
  } = {};
  function mint(): string {
    seq += 1;
    return `as_01k2m3n4p5q6r7s8t9v0w1x2${String(seq).padStart(2, "0")}`;
  }

  const api = mockApi({
    createAgentSession: async ({ objective }) => {
      const sessionId = mint();
      let planned = genericManchester();
      if (objective === DEMO_A) {
        planned = demoA();
      } else if (objective === DEMO_B) {
        planned = demoB();
      } else if (objective === DEMO_C) {
        planned = demoC();
      } else if (objective === EDINBURGH_CAR) {
        planned = demoC({
          destination: "Edinburgh",
          destinationAirport: "EDI",
          parkingAirport: "",
          conference: true,
          travel: true,
          tripLike: true,
        });
      } else if (objective.toLowerCase().includes("manchester")) {
        planned = genericManchester();
      } else {
        planned = fromLocalPlan(objective);
      }
      const next = view(sessionId, {
        projection: planned,
        ...(objective === DEMO_A
          ? {
              domains: {
                parking: {
                  kind: "parking",
                  support: "live_simulated",
                  provenance: "explicit",
                  accepted: true,
                  fields: {
                    airportCode: { value: "JFK", source: "current_turn", provenance: "explicit" },
                    start: {
                      value: "2026-09-03T13:00:00Z",
                      source: "current_turn",
                      provenance: "explicit",
                    },
                    end: {
                      value: "2026-09-08T22:00:00Z",
                      source: "current_turn",
                      provenance: "explicit",
                    },
                    vehicleClass: {
                      value: "standard",
                      source: "current_turn",
                      provenance: "explicit",
                    },
                    covered: { value: "preferred", source: "current_turn", provenance: "explicit" },
                  },
                  missing: [],
                  ask: [],
                  completeness: "ready",
                  offerSet: { stale: false, snapshot: null },
                },
              },
              pendingAuthorization: null,
              pendingSearchAuthorization: {
                capabilities: ["parking.search"],
                fingerprints: {
                  "parking.search":
                    "JFK|2026-09-03T13:00:00Z|2026-09-08T22:00:00Z|standard|preferred",
                },
                prompt:
                  "I have what I need to search for parking at JFK. Shall I request offers from 3 isolated simulated suppliers?",
              },
              buyerSafeMessage:
                "I have what I need to search for parking at JFK. Shall I request offers from 3 isolated simulated suppliers?",
            }
          : {}),
      });
      store.set(sessionId, { objective, view: next });
      return next;
    },
    postAgentTurn: async (sessionId, body) => {
      const current = store.get(sessionId);
      if (current === undefined) {
        throw new ClosedApiError({
          status: 404,
          code: "unknown_resource",
          field: "sessionId",
          correlationId: "cr_01k2m3n4p5q6r7s8t9v0w1x2k2",
        });
      }
      const extra = (body.message ?? "").trim();
      if (
        /^(yes|yeah|yep|ok|okay|go ahead|proceed)([.!]?)$/i.test(extra) &&
        current.view.domains?.parking != null &&
        grantRef.run != null
      ) {
        return grantRef.run(sessionId, { gate: "A2", domain: "parking" });
      }
      if (/new york/i.test(current.objective) || /\bparking\b/i.test(extra)) {
        const planned = fromLocalPlan(current.objective, extra);
        const next = view(sessionId, {
          projection: planned,
          transcript: [
            ...(current.view.transcript ?? []),
            { role: "user", text: extra },
            { role: "agent", text: planned.summary },
          ],
        });
        store.set(sessionId, { objective: current.objective, view: next });
        return next;
      }
      const prev = current.view.projection.facts;
      const answers = body.answers ?? {};
      const message = body.message ?? "";
      const nextFacts = facts({
        ...prev,
        departureAirport:
          answers.departureAirport || (message.includes("LHR") ? "LHR" : prev.departureAirport),
        dates:
          answers.startDate && answers.endDate
            ? `${answers.startDate} to ${answers.endDate}`
            : message.includes("14–19 October")
              ? "2026-10-14 to 2026-10-19"
              : answers.dates || prev.dates,
        hasExactDates:
          Boolean(answers.startDate && answers.endDate) ||
          message.includes("14–19 October") ||
          prev.hasExactDates,
        carNeed: (answers.carNeed as AgentFacts["carNeed"]) || prev.carNeed,
        destination: message.toLowerCase().includes("edinburgh") ? "Edinburgh" : prev.destination,
      });
      const planned = demoC(nextFacts);
      const next = view(sessionId, { projection: planned });
      store.set(sessionId, { objective: current.objective, view: next });
      return next;
    },
    confirmAgentSession: async (sessionId) => {
      const current = store.get(sessionId);
      if (current === undefined) {
        throw new ClosedApiError({
          status: 404,
          code: "unknown_resource",
          field: "sessionId",
          correlationId: "cr_01k2m3n4p5q6r7s8t9v0w1x2k2",
        });
      }
      const next = view(sessionId, {
        ...current.view,
        projection: {
          ...current.view.projection,
          phase: "ready",
          questions: [],
          summary: "Plan confirmed",
        },
        confirmed: true,
        parkingHandoff: {
          path: "/intents/new/parking",
          support: "live_simulated",
          fields: {
            ...(current.view.projection.facts.parkingAirport
              ? { airportCode: current.view.projection.facts.parkingAirport }
              : {}),
            intakeId: "in_01k2m3n4p5q6r7s8t9v0w1x2ag",
          },
        },
      });
      store.set(sessionId, { objective: current.objective, view: next });
      return next;
    },
    grantAgentSession: async (sessionId, body) => {
      const current = store.get(sessionId);
      if (current === undefined) {
        throw new ClosedApiError({
          status: 404,
          code: "unknown_resource",
          field: "sessionId",
          correlationId: "cr_01k2m3n4p5q6r7s8t9v0w1x2k2",
        });
      }
      const parking = current.view.domains?.parking;
      if (parking === undefined) {
        throw new ClosedApiError({
          status: 400,
          code: "illegal_state",
          field: "parking",
          correlationId: "cr_01k2m3n4p5q6r7s8t9v0w1x2k2",
        });
      }
      let nextView = current.view;
      if (body.gate === "A1") {
        nextView = view(sessionId, {
          ...current.view,
          confirmed: true,
          pendingAuthorization: {
            gate: "A2",
            domain: "parking",
            prompt: "Shall I request offers from 3 isolated simulated suppliers?",
            resourceId: "pi_01k2m3n4p5q6r7s8t9v0w1x2ag",
          },
          domains: {
            ...current.view.domains,
            parking: {
              ...parking,
              completeness: "awaiting_grant",
              intentId: "pi_01k2m3n4p5q6r7s8t9v0w1x2ag",
            },
          },
        });
      } else if (body.gate === "A2") {
        nextView = view(sessionId, {
          ...current.view,
          confirmed: true,
          pendingAuthorization: {
            gate: "A3",
            domain: "parking",
            prompt: "Accept the recommended offer? Selection is not a booking.",
            resourceId: "pi_01k2m3n4p5q6r7s8t9v0w1x2ag",
            offerId: "of_01k2m3n4p5q6r7s8t9v0w1x2a2",
          },
          domains: {
            ...current.view.domains,
            parking: {
              ...parking,
              completeness: "offers",
              intentId: "pi_01k2m3n4p5q6r7s8t9v0w1x2ag",
              offerSet: {
                stale: false,
                intentId: "pi_01k2m3n4p5q6r7s8t9v0w1x2ag",
                snapshot: {
                  intentId: "pi_01k2m3n4p5q6r7s8t9v0w1x2ag",
                  recommendedOfferId: "of_01k2m3n4p5q6r7s8t9v0w1x2a2",
                  offers: [
                    {
                      offerId: "of_01k2m3n4p5q6r7s8t9v0w1x2a2",
                      supplierToken: "sp_01k2m3n4p5q6r7s8t9v0w1x2b2",
                      version: 1,
                      rank: 1,
                      totalMinor: 14800,
                      currency: "USD",
                      recommended: true,
                      simulation: true,
                    },
                    {
                      offerId: "of_01k2m3n4p5q6r7s8t9v0w1x2a1",
                      supplierToken: "sp_01k2m3n4p5q6r7s8t9v0w1x2b1",
                      version: 1,
                      rank: 2,
                      totalMinor: 11900,
                      currency: "USD",
                      recommended: false,
                      simulation: true,
                    },
                    {
                      offerId: "of_01k2m3n4p5q6r7s8t9v0w1x2a3",
                      supplierToken: "sp_01k2m3n4p5q6r7s8t9v0w1x2b3",
                      version: 1,
                      rank: 3,
                      totalMinor: 16900,
                      currency: "USD",
                      recommended: false,
                      simulation: true,
                    },
                  ],
                },
              },
            },
          },
        });
      }
      store.set(sessionId, { objective: current.objective, view: nextView });
      return nextView;
    },
    getOwnedIntent: async (intentId) => owned.get(intentId) ?? rankedSnapshot({ intentId }),
    intakeAccept: async (intentId) => {
      const next = rankedSnapshot({
        intentId,
        state: "ACCEPTANCE_RECORDED",
        acceptance: {
          acceptanceId: "ac_01k2m3n4p5q6r7s8t9v0w1x2d1",
          offerId: "of_01k2m3n4p5q6r7s8t9v0w1x2a2",
          offerVersion: 1,
          status: "recorded",
        },
      });
      owned.set(intentId, next);
      return next;
    },
    intakeAuthorize: async (intentId) => {
      const next = rankedSnapshot({
        intentId,
        state: "TRANSACTION_AUTHORIZED_SIMULATED",
        acceptance: {
          acceptanceId: "ac_01k2m3n4p5q6r7s8t9v0w1x2d1",
          offerId: "of_01k2m3n4p5q6r7s8t9v0w1x2a2",
          offerVersion: 1,
          status: "recorded",
        },
        transaction: {
          authorizationId: "ta_01k2m3n4p5q6r7s8t9v0w1x2e1",
          acceptanceId: "ac_01k2m3n4p5q6r7s8t9v0w1x2d1",
          action: "reserve_parking",
          mode: "SIMULATED",
          amountMinor: 14800,
          currency: "USD",
          resultRef: "rr_01k2m3n4p5q6r7s8t9v0w1x2g1",
        },
      });
      owned.set(intentId, next);
      return next;
    },
    subscribeAgentEvents: (_sessionId, handlers) => {
      handlers.onEvent({ kind: "OBJECTIVE_RECEIVED", message: "Understanding your objective" });
      return { close: () => undefined };
    },
  });
  grantRef.run = (sessionId, body) => api.grantAgentSession(sessionId, body);
  return api;
}

function renderApp(api: ItaaApi = providerApi()) {
  return render(
    <MemoryRouter initialEntries={["/"]}>
      <AppRoutes api={api} />
    </MemoryRouter>,
  );
}

async function startObjective(text: string, api?: ItaaApi) {
  const user = userEvent.setup();
  renderApp(api);
  const field = await screen.findByRole("textbox", {
    name: "What are you planning or trying to get done?",
  });
  fireEvent.change(field, { target: { value: text } });
  await user.click(screen.getByRole("button", { name: "Start booking" }));
  return user;
}

describe("COMP-AWS-03 Clarify & plan agent UI", () => {
  it("renders a JFK parking-led plan without unrelated Explicit tasks", async () => {
    await startObjective(DEMO_A);
    expect(await screen.findByText("Live simulated path")).toBeInTheDocument();
    const plan = document.querySelector(".re-clarify-plan");
    expect(plan).not.toBeNull();
    expect(
      within(plan as HTMLElement).getAllByText("Airport parking · JFK").length,
    ).toBeGreaterThan(0);
    expect(within(plan as HTMLElement).getByText("Explicit")).toBeInTheDocument();
    expect(screen.getByText("Live simulated path")).toBeInTheDocument();
    expect(screen.getByText(/process-local and non-durable/i)).toBeInTheDocument();
    expect(screen.getByText(/not persisted to durable storage/i)).toBeInTheDocument();
    expect(screen.queryByText(/nothing is stored on a server/i)).toBeNull();
    expect(screen.queryByText("Hotel")).toBeNull();
    expect(screen.queryByText(/SkyShield|671000/)).toBeNull();
  });

  it("renders Edinburgh as a distinct multi-task plan", async () => {
    await startObjective(DEMO_B);
    expect(await screen.findByText("Rental car · Edinburgh")).toBeInTheDocument();
    expect(screen.getAllByText("Airport parking").length).toBeGreaterThan(0);
    expect(screen.getByText("Hotel")).toBeInTheDocument();
    expect(screen.getByText("Explicit")).toBeInTheDocument();
    expect(screen.getByText("Inferred")).toBeInTheDocument();
    expect(screen.getAllByText("Proposed").length).toBeGreaterThan(0);
    expect(screen.getByText("Demonstration task")).toBeInTheDocument();
    expect(screen.getAllByText("Unsupported in this build").length).toBeGreaterThan(0);
  });

  it("asks clarification then applies structured answers on the same session", async () => {
    const user = await startObjective(DEMO_C);
    expect(await screen.findByRole("group", { name: "Exact dates" })).toBeInTheDocument();
    expect(screen.getByText("Gathering")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Start date"), { target: { value: "2026-10-14" } });
    fireEvent.change(screen.getByLabelText("End date"), { target: { value: "2026-10-19" } });
    await user.type(screen.getByLabelText("Departing from"), "LHR");
    await user.click(screen.getByRole("button", { name: "Answer and update plan" }));
    expect(await screen.findByText("Forming")).toBeInTheDocument();
    expect(screen.queryByLabelText("Start date")).toBeNull();
    expect(screen.getByText("LHR")).toBeInTheDocument();
    expect(screen.queryByText("JFK")).toBeNull();
  });

  it("does not render trip-funnel fields when a parking domain pane is live", async () => {
    const london = "travelling to London. need parking from 15th to 16th october";
    const api = mockApi({
      createAgentSession: async () =>
        view("as_01k2m3n4p5q6r7s8t9v0w1x2zz", {
          projection: projection({
            facts: facts({
              destination: "London",
              destinationAirport: "LHR",
              parkingStated: true,
              travel: true,
              tripLike: true,
              hasExactDates: true,
              startDate: "2026-10-15",
              endDate: "2026-10-16",
            }),
            questions: [
              { id: "dates", label: "Exact dates", why: "Sets parking duration." },
              {
                id: "departureAirport",
                label: "Departing from",
                why: "Only the airport code reaches parking suppliers.",
              },
            ],
            tasks: [task("parking", "explicit", { title: "Airport parking" })],
            phase: "clarify",
            title: "London",
          }),
          domains: {
            parking: {
              kind: "parking",
              support: "live_simulated",
              provenance: "explicit",
              accepted: true,
              fields: {
                start: {
                  value: "2026-10-15T12:00:00Z",
                  source: "current_turn",
                  provenance: "explicit",
                },
                end: {
                  value: "2026-10-16T12:00:00Z",
                  source: "current_turn",
                  provenance: "explicit",
                },
              },
              missing: ["airportCode", "vehicleClass", "covered"],
              ask: [{ id: "airportCode", ask: "Which London airport do you need parking at?" }],
              completeness: "incomplete",
              offerSet: { stale: false, snapshot: null },
            },
          },
          buyerSafeMessage: "Which London airport do you need parking at?",
          transcript: [
            { role: "user", text: london },
            { role: "agent", text: "Which London airport do you need parking at?" },
          ],
        }),
    });
    const user = await startObjective(london, api);
    expect(await screen.findByText("parking.search")).toBeInTheDocument();
    const question = await screen.findByText("Which London airport do you need parking at?");
    const log = document.querySelector(".re-clarify-log");
    const thread = document.querySelector(".re-clarify-thread");
    const compose = document.querySelector(".re-clarify-compose");
    expect(log?.contains(question)).toBe(true);
    expect(thread?.nextElementSibling?.classList.contains("re-clarify-compose-wrap")).toBe(true);
    expect(thread?.nextElementSibling?.contains(compose)).toBe(true);
    expect(screen.queryByLabelText("Departing from")).toBeNull();
    expect(screen.queryByRole("group", { name: "Exact dates" })).toBeNull();
    await user.click(await screen.findByRole("button", { name: "Edit details" }));
    await waitFor(() => {
      expect(document.querySelector('input[aria-label="Parking airportCode"]')).not.toBeNull();
    });
    expect(screen.queryByRole("button", { name: "Begin parking requirement" })).toBeNull();
  });

  it("keeps a free-text follow-up on the same session and updates the plan", async () => {
    const user = await startObjective(EDINBURGH_CAR);
    const note = await screen.findByLabelText("Add anything else about this trip");
    expect((await screen.findAllByText("Edinburgh")).length).toBeGreaterThan(0);
    await user.type(note, FOLLOW_UP);
    await user.click(screen.getByRole("button", { name: "Add note" }));
    expect(await screen.findByText("LHR")).toBeInTheDocument();
    expect(screen.getAllByText("Edinburgh").length).toBeGreaterThan(0);
    expect(screen.queryByText("JFK")).toBeNull();
    expect(screen.queryByText(/SkyShield/)).toBeNull();
  });

  it("does not collapse generic input to JFK", async () => {
    await startObjective(GENERIC);
    expect((await screen.findAllByText("Manchester")).length).toBeGreaterThan(0);
    expect(screen.queryByText("JFK")).toBeNull();
    expect(screen.queryByText(/SkyShield/)).toBeNull();
  });

  it("confirms through the agent session and keeps parking in the same workspace", async () => {
    const user = await startObjective(DEMO_A);
    await user.type(await screen.findByLabelText("Add anything else about this trip"), "yes");
    await user.click(screen.getByRole("button", { name: "Add note" }));
    expect(screen.queryByRole("button", { name: "Send to Reservedge" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Begin parking requirement" })).toBeNull();
    expect(screen.queryByRole("button", { name: /Use the example/ })).toBeNull();
    expect(screen.queryByRole("button", { name: "Request parking offers" })).toBeNull();
    await user.click(await screen.findByRole("button", { name: "Edit details" }));
    expect(await screen.findByLabelText("Parking airportCode")).toHaveValue("JFK");
  });

  it("labels deterministic fallback and shows a safe failure instead of JFK", async () => {
    const falling = mockApi({
      createAgentSession: async () =>
        view("as_01k2m3n4p5q6r7s8t9v0w1x2ff", {
          fallback: true,
          projection: genericManchester(),
        }),
    });
    await startObjective(GENERIC, falling);
    expect(await screen.findByText("Using the local planner (labelled)")).toBeInTheDocument();
    expect(screen.queryByText("JFK")).toBeNull();

    cleanup();
    const failing = mockApi({
      createAgentSession: async () => {
        throw new ClosedApiError({
          status: 400,
          code: "unavailable",
          field: "model",
          correlationId: "cr_01k2m3n4p5q6r7s8t9v0w1x2k2",
        });
      },
    });
    const user = userEvent.setup();
    renderApp(failing);
    fireEvent.change(
      await screen.findByRole("textbox", {
        name: "What are you planning or trying to get done?",
      }),
      { target: { value: GENERIC } },
    );
    await user.click(screen.getByRole("button", { name: "Start booking" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/Could not complete this step/);
    expect(screen.queryByText("JFK")).toBeNull();
    expect(screen.queryByText("Clarify & plan")).toBeNull();
    expect(within(document.body).queryByText(/SkyShield/)).toBeNull();
  });

  it("shows buyer-safe progress while the first plan turn is in flight", async () => {
    const hanging = mockApi({
      createAgentSession: () => new Promise(() => undefined),
    });
    const user = userEvent.setup();
    renderApp(hanging);
    fireEvent.change(
      await screen.findByRole("textbox", {
        name: "What are you planning or trying to get done?",
      }),
      { target: { value: DEMO_C } },
    );
    await user.click(screen.getByRole("button", { name: "Start booking" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Understanding your objective");
    expect(screen.getByRole("button", { name: "Start booking" })).toHaveAttribute(
      "aria-busy",
      "true",
    );
    expect(document.querySelector(".re-processing-spinner")).not.toBeNull();
    expect(screen.queryByText(/global\.anthropic|itaa-comp-aws|eu-west-2|Bedrock/i)).toBeNull();
    expect(screen.queryByText("Clarify & plan")).toBeNull();
  });

  it("shows buyer-safe progress while a refine turn is in flight", async () => {
    const hanging = mockApi({
      postAgentTurn: () => new Promise(() => undefined),
    });
    const user = await startObjective(DEMO_C, hanging);
    const chat = await screen.findByRole("textbox", { name: "Add anything else about this trip" });
    fireEvent.change(chat, { target: { value: "14 to 19 October 2026" } });
    await user.click(screen.getByRole("button", { name: "Add note" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Updating your plan");
    expect(screen.getByRole("button", { name: "Add note" })).toHaveAttribute("aria-busy", "true");
    expect(document.querySelector(".re-processing-spinner")).not.toBeNull();
    expect(screen.queryByText(/global\.anthropic|itaa-comp-aws|eu-west-2|Bedrock/i)).toBeNull();
  });

  it("does not invent JFK or label unconfirmed parking as Not needed on a New York trip", async () => {
    await startObjective(NYC);
    expect((await screen.findAllByText(/New York/)).length).toBeGreaterThan(0);
    expect(screen.queryByText("JFK")).toBeNull();
    expect(screen.queryByText("Not needed")).toBeNull();
    expect(screen.queryByRole("button", { name: "Not needed" })).toBeNull();
  });

  it("keeps parking and rental Explicit for a New York trip that asked for both, without JFK", async () => {
    await startObjective(NYC_PARK);
    expect(await screen.findByText("Airport parking · New York")).toBeInTheDocument();
    expect(screen.getByText("Rental car · New York")).toBeInTheDocument();
    expect(screen.getAllByText("Explicit").length).toBeGreaterThan(1);
    expect(screen.queryByText("JFK")).toBeNull();
    expect(screen.queryByRole("button", { name: "Not needed" })).toBeNull();
  });

  it("applies a same-session parking follow-up on the current agent session", async () => {
    const api = providerApi();
    const user = await startObjective(NYC, api);
    expect((await screen.findAllByText(/New York/)).length).toBeGreaterThan(0);
    const conversationTab = screen.queryByRole("tab", { name: "Conversation" });
    if (conversationTab) {
      await user.click(conversationTab);
    }
    await user.type(
      await screen.findByLabelText("Add anything else about this trip"),
      ALSO_PARKING,
    );
    await user.click(screen.getByRole("button", { name: "Add note" }));
    expect((await screen.findAllByText(ALSO_PARKING)).length).toBeGreaterThan(0);
    const planTab = screen.queryByRole("tab", { name: /Plan/ });
    if (planTab) {
      await user.click(planTab);
    }
    expect(await screen.findByText("Airport parking · New York")).toBeInTheDocument();
    expect(screen.getByText("Explicit")).toBeInTheDocument();
    expect(screen.queryByText("JFK")).toBeNull();
  });

  it("opens a prepared parking requirement after confirm instead of a second intake", async () => {
    const user = await startObjective(DEMO_A);
    expect(screen.queryByRole("button", { name: "Begin parking requirement" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Send to Reservedge" })).toBeNull();
    expect(screen.queryByRole("button", { name: /Use the example/ })).toBeNull();
    expect(screen.queryByRole("button", { name: "Request parking offers" })).toBeNull();
    await user.click(await screen.findByRole("button", { name: "Edit details" }));
    expect(await screen.findByLabelText("Parking airportCode")).toHaveValue("JFK");
  });

  it("opens the offer workspace and continues the chat under Running after requesting offers", async () => {
    const user = await startObjective(DEMO_A);
    expect(screen.queryByRole("button", { name: "Begin parking requirement" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Send to Reservedge" })).toBeNull();
    await user.type(await screen.findByLabelText("Add anything else about this trip"), "yes");
    await user.click(screen.getByRole("button", { name: "Add note" }));
    expect(await screen.findByRole("button", { name: "Take this one" })).toBeInTheDocument();
    expect(screen.getAllByText(/SkyShield/).length).toBeGreaterThan(0);
    expect(await screen.findByText("Continue this booking")).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Running" })).toHaveAttribute("aria-selected", "true");
    const runningChat = document.querySelector(".re-list-chat");
    expect(runningChat).not.toBeNull();
    expect(
      within(runningChat as HTMLElement).getByLabelText("Add anything else about this trip"),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Accept recommended offer" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Begin parking requirement" })).toBeNull();
    expect(screen.queryByText(/SEPARATE FROM DISCLOSURE/i)).toBeNull();
  });

  it("records the selected offer in Running chat and moves a finished booking to History", async () => {
    const user = await startObjective(DEMO_A);
    await user.type(await screen.findByLabelText("Add anything else about this trip"), "yes");
    await user.click(screen.getByRole("button", { name: "Add note" }));
    await user.click(await screen.findByRole("button", { name: "Take this one" }));
    expect(
      await screen.findByText(/You accepted the SkyShield offer at USD 148\.00/),
    ).toBeInTheDocument();
    expect(screen.queryByText("Updating your plan")).toBeNull();
    expect(screen.queryByRole("button", { name: "Accept recommended offer" })).toBeNull();
    await user.click(await screen.findByRole("button", { name: /Authorize USD 148\.00/ }));
    expect(
      (await screen.findByText(/Authorization recorded|This booking is complete/)).textContent,
    ).toMatch(/Authorization recorded|This booking is complete/);
    expect(screen.getByRole("tab", { name: "History" })).toHaveAttribute("aria-selected", "true");
    expect(document.querySelector(".re-list-chat")).toBeNull();
  });

  it("parks an unfinished booking in Pending when a new intent starts", async () => {
    const user = await startObjective(DEMO_A);
    await user.click(await screen.findByRole("button", { name: "Edit details" }));
    expect(await screen.findByLabelText("Parking airportCode")).toHaveValue("JFK");
    await user.click(screen.getAllByRole("button", { name: "New intent" })[0]!);
    expect(
      await screen.findByRole("heading", { name: "What are you planning or trying to get done?" }),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("tab", { name: "Pending" }));
    expect(screen.getByText("Paused here. Open to continue.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Delete Airport parking · JFK" }));
    expect(screen.queryByText("Paused here. Open to continue.")).toBeNull();
  });
});
