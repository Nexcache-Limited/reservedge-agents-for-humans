import { describe, expect, it } from "vitest";
import {
  createPlanSession,
  DOMAIN_CARD_ORDER,
  extractFacts,
  projectPlan,
  refinementPinKind,
  sortPlanTasks,
  type PlanSession,
  type PlanTask,
} from "./plan.js";

const LONDON_UAT =
  "Travelling from New York to London on 17 October. Need hotel in London for two days. " +
  "Also need covered parking in London from 5pm on the 17th October to 5pm on the 18th. " +
  "If any sightseeing attractions are there, show me that too.";

const DEMO_A =
  "I'm flying from JFK on September 3 at 1 PM and returning September 8 at 10 PM. " +
  "I have a standard EV, prefer covered parking, and don't want a shuttle longer than 20 minutes.";

function task(kind: PlanTask["kind"], extra: Partial<PlanTask> = {}): PlanTask {
  return {
    id: `task-${kind}`,
    kind,
    code: kind.slice(0, 2),
    title: kind,
    detail: kind,
    provenance: "explicit",
    support: "sandbox_search",
    supportLabel: "Sandbox",
    accepted: true,
    ...extra,
  };
}

describe("COMP-RECORDING-FINAL-UX plan projection", () => {
  it("resolves London stay dates to 17–19 Oct without inheriting parking clocks", () => {
    const facts = extractFacts(LONDON_UAT);
    expect(facts.destination).toBe("London");
    expect(facts.originCity).toBe("New York");
    expect(facts.startDate).toBe("2026-10-17");
    expect(facts.endDate).toBe("2026-10-19");
    expect(facts.hotelStated).toBe(true);
    expect(facts.parkingStated).toBe(true);
    expect(facts.experienceStated).toBe(true);
    expect(facts.parkingAirport).toBe("");
  });

  it("proposes a flight from origin plus destination without another transport mode", () => {
    const kinds = projectPlan(createPlanSession(LONDON_UAT)).tasks.map((item) => item.kind);
    expect(kinds[0]).toBe("flight");
    expect(kinds).toEqual(["flight", "hotel", "parking", "experience"]);
    const flight = projectPlan(createPlanSession(LONDON_UAT)).tasks.find(
      (item) => item.kind === "flight",
    );
    expect(flight?.provenance).toBe("proposed");
    expect(flight?.accepted).toBe(false);
  });

  it("does not open a flight lane for Demo A parking-only flying from JFK", () => {
    const facts = extractFacts(DEMO_A);
    expect(facts.originCity).toBe("");
    expect(facts.destination).toBe("");
    const kinds = projectPlan(createPlanSession(DEMO_A)).tasks.map((item) => item.kind);
    expect(kinds).toEqual(["parking"]);
  });

  it("does not infer a flight when another transport mode is stated", () => {
    const kinds = projectPlan(
      createPlanSession("Travelling from Paris to London on 17 October by train. Need a hotel."),
    ).tasks.map((item) => item.kind);
    expect(kinds).not.toContain("flight");
    expect(kinds[0]).toBe("hotel");
  });

  it("uses a code-owned domain card order", () => {
    expect(DOMAIN_CARD_ORDER).toEqual([
      "flight",
      "hotel",
      "rental",
      "parking",
      "experience",
      "ents",
    ]);
    expect(
      sortPlanTasks([
        task("experience"),
        task("parking"),
        task("rental"),
        task("hotel"),
        task("flight"),
      ]).map((item) => item.kind),
    ).toEqual(["flight", "hotel", "rental", "parking", "experience"]);
    expect(sortPlanTasks([task("parking"), task("hotel")]).map((item) => item.kind)).toEqual([
      "hotel",
      "parking",
    ]);
  });

  it("pins a stale stay domain to the top during refinement", () => {
    const session: PlanSession = {
      ...createPlanSession(LONDON_UAT),
      agent: {
        sessionId: "as_01k2m3n4p5q6r7s8t9v0w1x2rf",
        fallback: false,
        confirmed: false,
        failed: false,
        failureMessage: "",
        parkingHandoff: null,
        activity: [],
        remote: projectPlan(createPlanSession(LONDON_UAT)),
        transcript: [],
        domains: {},
        pendingAuthorization: null,
        pendingSearchAuthorization: {
          capabilities: ["stay.search"],
          fingerprints: {},
          prompt: "Shall I search for your hotel?",
        },
        buyerSafeMessage: "",
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
      },
    };
    expect(refinementPinKind(session)).toBe("hotel");
    const ordered = sortPlanTasks(
      [task("flight"), task("hotel"), task("parking")],
      refinementPinKind(session),
    ).map((item) => item.kind);
    expect(ordered[0]).toBe("hotel");
  });
});
