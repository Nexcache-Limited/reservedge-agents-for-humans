import { afterEach, describe, expect, it, vi } from "vitest";
import { AGENT_ACTIVITY_KINDS, createItaaApi } from "./api/client.js";
import { AGENT_PREFIX, type AgentSessionView } from "./api/types.js";
import {
  answersFromAgentFacts,
  failAgentSession,
  mergeAgentView,
  parkingKnownFromHandoff,
  projectAgentSession,
  sessionFromAgentView,
  turnAnswersFromSession,
} from "./intent-first/agent.js";
import { createPlanSession } from "./intent-first/plan.js";

afterEach(() => {
  vi.unstubAllGlobals();
});

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

const SESSION = {
  sessionId: "as_01k2m3n4p5q6r7s8t9v0w1x2aa",
  projection: {
    facts: { destination: "Edinburgh", parkingAirport: "EDI", dates: "2026-10-14 to 2026-10-19" },
    questions: [],
    tasks: [],
    phase: "forming",
    title: "Edinburgh",
    summary: "Plan",
    confirmedCount: 1,
    proposedCount: 0,
  },
  questions: [],
  toolTrace: [],
  pendingAuthorizations: [],
  parkingHandoff: null,
  confirmed: false,
  fallback: false,
  correlationId: "cr_01k2m3n4p5q6r7s8t9v0w1x2k2",
};

describe("COMP-AWS-03 agent client", () => {
  it("posts plan work to /v1/agent and never to /v1/aws", async () => {
    const fetchImpl = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      expect(url).not.toContain("/v1/aws");
      expect(init?.credentials).toBe("same-origin");
      if (url.endsWith(`${AGENT_PREFIX}/sessions`) && init?.method === "POST") {
        expect(JSON.parse(String(init.body))).toEqual({
          objective: "I'm travelling to Edinburgh for a conference and need a car.",
        });
        return jsonResponse(SESSION);
      }
      if (url.endsWith(`${AGENT_PREFIX}/sessions/${SESSION.sessionId}/turns`)) {
        expect(JSON.parse(String(init?.body))).toEqual({
          answers: { departureAirport: "LHR", startDate: "2026-10-14", endDate: "2026-10-19" },
        });
        return jsonResponse({
          ...SESSION,
          projection: { ...SESSION.projection, phase: "forming" },
        });
      }
      if (url.endsWith(`${AGENT_PREFIX}/sessions/${SESSION.sessionId}/confirm`)) {
        return jsonResponse({
          ...SESSION,
          confirmed: true,
          parkingHandoff: { path: "/intents/new/parking", support: "live_simulated", fields: {} },
        });
      }
      if (url.endsWith(`${AGENT_PREFIX}/sessions/${SESSION.sessionId}`)) {
        return jsonResponse(SESSION);
      }
      throw new Error(`unexpected ${url}`);
    });
    const api = createItaaApi({ baseUrl: "http://example.test", fetchImpl });
    const created = await api.createAgentSession({
      objective: "I'm travelling to Edinburgh for a conference and need a car.",
    });
    expect(created.sessionId).toBe(SESSION.sessionId);
    await api.postAgentTurn(created.sessionId, {
      answers: { departureAirport: "LHR", startDate: "2026-10-14", endDate: "2026-10-19" },
    });
    const confirmed = await api.confirmAgentSession(created.sessionId);
    expect(confirmed.confirmed).toBe(true);
    expect(confirmed.parkingHandoff?.path).toBe("/intents/new/parking");
    await api.getAgentSession(created.sessionId);
    const urls = fetchImpl.mock.calls.map((call) => String(call[0]));
    expect(urls.every((url) => !url.includes("/v1/aws"))).toBe(true);
    expect(JSON.stringify(confirmed)).not.toMatch(/scoreMicros|evidence|account/);
  });

  it("posts A1–A4 grants only to /v1/agent/sessions/{id}/grants", async () => {
    const fetchImpl = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      expect(url).not.toContain("/v1/aws");
      expect(url).not.toContain("/intents/new/parking");
      if (url.endsWith(`${AGENT_PREFIX}/sessions/${SESSION.sessionId}/grants`)) {
        expect(init?.method).toBe("POST");
        expect(JSON.parse(String(init?.body))).toEqual({ gate: "A1", domain: "parking" });
        return jsonResponse({
          ...SESSION,
          pendingAuthorization: null,
          confirmed: true,
        });
      }
      throw new Error(`unexpected ${url}`);
    });
    const api = createItaaApi({ baseUrl: "http://example.test", fetchImpl });
    await api.grantAgentSession(SESSION.sessionId, { gate: "A1", domain: "parking" });
  });

  it("opens agent activity SSE on /v1/agent/sessions/{id}/events", () => {
    let opened = "";
    class FakeSource {
      onerror: ((event: Event) => void) | null = null;
      constructor(public readonly url: string) {
        opened = url;
      }
      addEventListener() {
        return undefined;
      }
      close() {
        return undefined;
      }
    }
    vi.stubGlobal("EventSource", FakeSource);
    const api = createItaaApi({ baseUrl: "http://itaa.test" });
    const subscription = api.subscribeAgentEvents(SESSION.sessionId, {
      onEvent: () => undefined,
      onError: () => undefined,
    });
    expect(opened).toBe(`http://itaa.test${AGENT_PREFIX}/sessions/${SESSION.sessionId}/events`);
    expect(opened).not.toContain("/v1/aws");
    expect(opened).not.toContain("ProgressEventKind");
    expect(AGENT_ACTIVITY_KINDS).toContain("FALLBACK_DETERMINISTIC");
    expect(AGENT_ACTIVITY_KINDS).not.toContain("STREAM_COMPLETED");
    subscription.close();
  });

  it("ignores malformed SSE payloads and no-ops when EventSource is unavailable", () => {
    const sources: FakeSource[] = [];
    class FakeSource {
      onerror: ((event: Event) => void) | null = null;
      readonly listeners = new Map<string, EventListener>();
      constructor(public readonly url: string) {
        sources.push(this);
      }
      addEventListener(type: string, listener: EventListener) {
        this.listeners.set(type, listener);
      }
      close() {
        return undefined;
      }
    }
    const seen: string[] = [];
    let failed = false;
    vi.stubGlobal("EventSource", FakeSource);
    const api = createItaaApi({ baseUrl: "http://itaa.test" });
    const subscription = api.subscribeAgentEvents(SESSION.sessionId, {
      onEvent: (event) => {
        seen.push(event.message);
      },
      onError: () => {
        failed = true;
      },
    });
    const instance = sources[0];
    instance?.listeners.get("OBJECTIVE_RECEIVED")?.(
      new MessageEvent("OBJECTIVE_RECEIVED", { data: "not-json" }),
    );
    instance?.listeners.get("PLAN_READY")?.(
      new MessageEvent("PLAN_READY", { data: JSON.stringify({ kind: 1 }) }),
    );
    instance?.listeners.get("PLAN_CONFIRMED")?.(
      new MessageEvent("PLAN_CONFIRMED", {
        data: JSON.stringify({ kind: "PLAN_CONFIRMED", message: "Plan confirmed" }),
      }),
    );
    instance?.onerror?.(new Event("error"));
    subscription.close();
    vi.stubGlobal("EventSource", undefined);
    const closed = createItaaApi({ baseUrl: "http://itaa.test" }).subscribeAgentEvents(
      SESSION.sessionId,
      {
        onEvent: () => undefined,
        onError: () => undefined,
      },
    );
    closed.close();
    expect(failed).toBe(true);
    expect(seen).toEqual(["Plan confirmed"]);
  });
});

describe("COMP-AWS-03 agent projection mapping", () => {
  it("copies structured dates from facts without reading the objective", () => {
    const iso = answersFromAgentFacts({
      destination: "Edinburgh",
      destinationAirport: "EDI",
      parkingAirport: "EDI",
      departureAirport: "LHR",
      dates: "2026-10-14 to 2026-10-19",
      hasExactDates: true,
      hasLooseDates: true,
      startDate: "2026-10-14",
      endDate: "2026-10-19",
      carNeed: "yes",
      parkingStated: false,
      rentalStated: true,
      entsStated: false,
      hotelStated: false,
      flightStated: false,
      landing: true,
      travel: true,
      conference: true,
      nights: false,
      tripLike: true,
      dayPart: "evening",
      timeFlexible: false,
    });
    expect(iso.startDate).toBe("2026-10-14");
    expect(iso.endDate).toBe("2026-10-19");
    expect(iso.startPeriod).toBe("evening");
    const human = answersFromAgentFacts({
      destination: "Edinburgh",
      destinationAirport: "EDI",
      parkingAirport: "EDI",
      departureAirport: "",
      dates: "14–19 Oct 2026",
      hasExactDates: true,
      hasLooseDates: true,
      startDate: "2026-10-14",
      endDate: "2026-10-19",
      carNeed: "yes",
      parkingStated: false,
      rentalStated: true,
      entsStated: false,
      hotelStated: false,
      flightStated: false,
      landing: true,
      travel: true,
      conference: true,
      nights: false,
      tripLike: true,
      dayPart: "",
      timeFlexible: false,
    });
    expect(human.startDate).toBe("2026-10-14");
    expect(human.endDate).toBe("2026-10-19");
    const unlabeled = answersFromAgentFacts({
      destination: "Edinburgh",
      destinationAirport: "EDI",
      parkingAirport: "EDI",
      departureAirport: "",
      dates: "14–19 Oct 2026",
      hasExactDates: true,
      hasLooseDates: true,
      startDate: "",
      endDate: "",
      carNeed: "yes",
      parkingStated: false,
      rentalStated: true,
      entsStated: false,
      hotelStated: false,
      flightStated: false,
      landing: true,
      travel: true,
      conference: true,
      nights: false,
      tripLike: true,
      dayPart: "",
      timeFlexible: false,
    });
    expect(unlabeled.startDate).toBe("");
    expect(unlabeled.endDate).toBe("");
    const relative = answersFromAgentFacts({
      destination: "",
      destinationAirport: "",
      parkingAirport: "JFK",
      departureAirport: "",
      dates: "Thursday",
      hasExactDates: false,
      hasLooseDates: true,
      startDate: "",
      endDate: "",
      carNeed: "",
      parkingStated: true,
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
    });
    expect(relative.startDate).toBe("");
    expect(relative.dates).toBe("Thursday");
  });

  it("maps a session view onto Clarify & plan chrome and strips secret handoff keys", () => {
    const view: AgentSessionView = {
      sessionId: "as_01k2m3n4p5q6r7s8t9v0w1x2bb",
      projection: {
        facts: {
          destination: "Edinburgh",
          destinationAirport: "EDI",
          parkingAirport: "EDI",
          departureAirport: "",
          dates: "14–19 Oct 2026",
          hasExactDates: true,
          hasLooseDates: true,
          startDate: "2026-10-14",
          endDate: "2026-10-19",
          carNeed: "yes",
          parkingStated: false,
          rentalStated: true,
          entsStated: false,
          hotelStated: false,
          flightStated: false,
          landing: true,
          travel: true,
          conference: true,
          nights: false,
          tripLike: true,
          dayPart: "",
          timeFlexible: false,
        },
        questions: [
          {
            id: "departureAirport",
            label: "Departing from",
            why: "Only the airport code reaches parking suppliers.",
          },
          { id: "unknown", label: "Extra", why: "Ignored id becomes dates." },
        ],
        tasks: [
          {
            id: "task-rental",
            kind: "rental",
            code: "Rc",
            title: "Rental car · Edinburgh",
            detail: "You said you need a car in Edinburgh.",
            provenance: "explicit",
            support: "demonstration",
            supportLabel: "Demonstration task",
            accepted: true,
          },
        ],
        phase: "clarify",
        title: "Edinburgh conference",
        summary: "Need the departure airport.",
        confirmedCount: 1,
        proposedCount: 0,
      },
      questions: [],
      toolTrace: [{ kind: "tool", tool: "project_plan_from_facts" }],
      pendingAuthorizations: [],
      parkingHandoff: {
        path: "/intents/new/parking",
        support: "live_simulated",
        fields: {
          airportCode: "EDI",
          startDate: "2026-10-14",
          endDate: "2026-10-19",
          intentId: "pi_secret",
          buyerToken: "tok_secret",
          approvalId: "ap_secret",
          shuttleMaxMinutes: 20,
          tags: ["covered", "ev"],
        },
      },
      confirmed: false,
      fallback: true,
      correlationId: "cr_01k2m3n4p5q6r7s8t9v0w1x2k2",
    };
    const session = sessionFromAgentView(
      "I'm travelling to Edinburgh for a conference 14–19 October 2026 and I'll need a car when I land.",
      view,
    );
    const projection = projectAgentSession(session);
    expect(session.agent?.sessionId).toBe(view.sessionId);
    expect(session.agent?.fallback).toBe(true);
    expect(projection.questions.map((question) => question.id)).toEqual([
      "departureAirport",
      "dates",
    ]);
    expect(projection.chips.some((chip) => chip.label === "14–19 Oct 2026")).toBe(true);
    expect(JSON.stringify(projection)).not.toMatch(
      /scoreMicros|evidence|chain-of-thought|pi_secret/,
    );
    expect(session.answers.startDate).toBe("2026-10-14");
    expect(session.answers.endDate).toBe("2026-10-19");
    const known = parkingKnownFromHandoff(view.parkingHandoff);
    expect(known.airportCode).toBe("EDI");
    expect(known.startDate).toBe("2026-10-14");
    expect(known.endDate).toBe("2026-10-19");
    expect(known.shuttleMaxMinutes).toBe("20");
    expect(known.tags).toBe("covered,ev");
    expect(known.intentId).toBeUndefined();
    expect(known.buyerToken).toBeUndefined();
    session.answers.departureAirport = "MAN";
    expect(turnAnswersFromSession(session)).toEqual({
      departureAirport: "MAN",
      carNeed: "yes",
      dates: "14–19 Oct 2026",
      startDate: "2026-10-14",
      endDate: "2026-10-19",
    });
    expect(parkingKnownFromHandoff(null)).toEqual({});
    expect(() => projectAgentSession(createPlanSession("x"))).toThrow(/agent binding/);
    const failed = failAgentSession(session, "Could not complete this step");
    expect(failed.agent?.failed).toBe(true);
    expect(failAgentSession(createPlanSession("x"), "nope").agent).toBeUndefined();
    const confirmed = mergeAgentView(session, {
      ...view,
      confirmed: true,
      projection: { ...view.projection, phase: "ready", questions: [], summary: "Plan confirmed" },
    });
    expect(confirmed.phase).toBe("ready");
    expect(projectAgentSession(confirmed).questions).toEqual([]);
    expect(projectAgentSession(confirmed).summary).toBe("Plan confirmed");
  });
});
