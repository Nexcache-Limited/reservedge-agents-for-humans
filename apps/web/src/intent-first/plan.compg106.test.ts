import { describe, expect, it } from "vitest";
import {
  acceptTaskOverride,
  addTaskOverride,
  compactSharedContext,
  createPlanSession,
  extractFacts,
  firstTurnCopy,
  parkingPrefill,
  projectPlan,
  provenanceLabel,
  removeTaskOverride,
  selectClarifications,
  sortPlanTasks,
  supportedAddableKinds,
  taskStatusLabel,
} from "./plan.js";

const EDINBURGH = "I'm travelling to Edinburgh for a conference and I'll need a car when I land.";
const JFK = "Airport parking at JFK next Thursday";
const NY = "I'm planning a five-day trip to New York in October.";

describe("intent-first plan simulation", () => {
  it("keeps Edinburgh destination and explicit car need, and asks only missing facts", () => {
    const facts = extractFacts(EDINBURGH);
    expect(facts.destination).toBe("Edinburgh");
    expect(facts.carNeed).toBe("yes");
    expect(facts.landing).toBe(true);
    expect(facts.hasExactDates).toBe(false);
    expect(facts.departureAirport).toBe("");
    const questions = selectClarifications(facts);
    expect(questions.map((item) => item.id)).toEqual(["dates", "departureAirport"]);
    expect(questions.some((item) => item.id === "carNeed")).toBe(false);
  });

  it("forms multiple tasks with explicit rental, inferred parking, and proposed extras", () => {
    const projection = projectPlan(createPlanSession(EDINBURGH));
    const byKind = Object.fromEntries(projection.tasks.map((task) => [task.kind, task]));
    expect(projection.tasks.length).toBeGreaterThan(1);
    expect(byKind.rental?.provenance).toBe("explicit");
    expect(byKind.parking?.provenance).toBe("inferred");
    expect(byKind.flight?.provenance).toBe("proposed");
    expect(byKind.hotel?.provenance).toBe("proposed");
    expect(provenanceLabel("explicit")).toBe("Explicit");
    expect(provenanceLabel("inferred")).toBe("Inferred");
    expect(provenanceLabel("proposed")).toBe("Proposed");
  });

  it("does not collapse a JFK parking objective into travel questions", () => {
    const facts = extractFacts(JFK);
    expect(facts.parkingStated).toBe(true);
    expect(facts.parkingAirport).toBe("JFK");
    expect(facts.hasExactDates).toBe(false);
    expect(selectClarifications(facts).map((item) => item.id)).toEqual(["dates"]);
    const projection = projectPlan(createPlanSession(JFK));
    expect(projection.tasks.map((task) => task.kind)).toEqual(["parking"]);
    expect(projection.tasks[0]?.provenance).toBe("explicit");
  });

  it("opens a dated city trip by asking what to help book, without parking or hotel search", () => {
    const objective = "I'm travelling to Edinburgh from 14 to 19 October 2026.";
    const facts = extractFacts(objective);
    expect(facts.destination).toBe("Edinburgh");
    expect(facts.hasExactDates).toBe(true);
    expect(facts.parkingStated).toBe(false);
    expect(facts.landing).toBe(false);
    expect(selectClarifications(facts).map((item) => item.id)).toEqual([]);
    const session = createPlanSession(objective);
    expect(session.phase).toBe("forming");
    const projection = projectPlan(session);
    expect(projection.tasks.map((task) => task.kind)).not.toContain("parking");
    expect(projection.tasks.map((task) => task.kind)).not.toContain("hotel");
    expect(projection.tasks.map((task) => task.kind)).not.toContain("rental");
  });

  it("keeps Milan and Mumbai on a dated stay trip and does not invent JFK", () => {
    const facts = extractFacts("I'm travelling to Milan from Mumbai from 20 to 30 October");
    expect(facts.destination).toBe("Milan");
    expect(facts.originCity).toBe("Mumbai");
    expect(facts.startDate).toBe("2026-10-20");
    expect(facts.endDate).toBe("2026-10-30");
    const miami = extractFacts("Miami 15th October to 20th October, hotel");
    expect(miami.destination).toBe("Miami");
    expect(miami.hotelStated).toBe(true);
    expect(miami.startDate).toBe("2026-10-15");
    expect(miami.endDate).toBe("2026-10-20");
    const inverted = extractFacts("Miami 20th October to 15th October, hotel");
    expect(inverted.destination).toBe("Miami");
    expect(inverted.hasExactDates).toBe(false);
    expect(facts.parkingAirport).toBe("");
    expect(facts.parkingStated).toBe(false);
    expect(JSON.stringify(facts).toLowerCase()).not.toContain("jfk");
    const projection = projectPlan(
      createPlanSession("I'm travelling to Milan from Mumbai from 20 to 30 October"),
    );
    expect(projection.questions.map((item) => item.id)).not.toContain("helpWith");
    expect(projection.tasks.map((task) => task.kind)).not.toContain("hotel");
    expect(projection.tasks.map((task) => task.kind)).not.toContain("parking");
  });

  it("acknowledges a named city and only asks when dates are missing", () => {
    const facts = extractFacts("travelling to London");
    expect(facts.destination).toBe("London");
    expect(facts.hasExactDates).toBe(false);
    expect(firstTurnCopy(facts)).toBe(
      "I have London. When are you travelling? I can help with hotels, things to do, car rentals, and parking. Say the word.",
    );
    expect(firstTurnCopy(facts).toLowerCase()).not.toContain("where and when");
  });

  it("puts explicit hotel first on a named stay trip", () => {
    const session = createPlanSession(
      "I'm travelling to London from 20 to 25 October. I need a hotel.",
    );
    const kinds = projectPlan(session).tasks.map((task) => task.kind);
    expect(kinds[0]).toBe("hotel");
    expect(kinds).not.toContain("parking");
    expect(sortPlanTasks(projectPlan(session).tasks)[0]?.kind).toBe("hotel");
  });

  it("does not force parking IATA or car questions for a New York stay trip", () => {
    const questions = selectClarifications(extractFacts(NY));
    expect(questions.map((item) => item.id)).toEqual(["dates"]);
    const session = createPlanSession(NY);
    session.answers.carNeed = "yes";
    const rental = projectPlan(session).tasks.find((task) => task.kind === "rental");
    expect(rental?.provenance).toBe("inferred");
    expect(rental?.accepted).toBe(false);
  });

  it("lets the user remove a proposed task and add a supported one", () => {
    const session = createPlanSession(EDINBURGH);
    const flight = projectPlan(session).tasks.find((task) => task.kind === "flight");
    expect(flight).toBeDefined();
    session.overrides.push(removeTaskOverride(flight!.id));
    expect(projectPlan(session).tasks.some((task) => task.kind === "flight")).toBe(false);
    session.overrides.push(addTaskOverride("ents"));
    expect(projectPlan(session).tasks.some((task) => task.kind === "ents")).toBe(true);
    expect(supportedAddableKinds(projectPlan(session).tasks)).not.toContain("ents");
  });

  it("accepts a proposed task without relabelling it as an explicit request", () => {
    const session = createPlanSession(EDINBURGH);
    const hotel = projectPlan(session).tasks.find((task) => task.kind === "hotel")!;
    session.overrides.push(acceptTaskOverride(hotel.id));
    const next = projectPlan(session).tasks.find((task) => task.kind === "hotel")!;
    expect(next.accepted).toBe(true);
    expect(next.provenance).toBe("proposed");
  });

  it("prefills parking with inferred airport and parsed dates without inventing an API", () => {
    const session = createPlanSession(EDINBURGH);
    session.answers.dates = "14–19 October 2026";
    session.answers.departureAirport = "MAN";
    const facts = extractFacts(session.objective);
    const prefill = parkingPrefill(session.objective, facts, session.answers);
    expect(prefill.knownParking.airportCode).toBe("EDI");
    expect(prefill.knownParking.start).toContain("2026-10-14");
    expect(prefill.knownParking.end).toContain("2026-10-19");
    expect(prefill.draft).toContain(EDINBURGH);
    expect(prefill.draft).toContain("EDI");
  });

  it("treats an unsure car answer as a proposed rental, not an explicit request", () => {
    const session = createPlanSession(NY);
    session.answers.carNeed = "unsure";
    const rental = projectPlan(session).tasks.find((task) => task.kind === "rental");
    expect(rental?.provenance).toBe("proposed");
    expect(rental?.accepted).toBe(false);
  });

  it("seeds exact calendar dates from the objective and does not re-ask them", () => {
    const objective =
      "I'm travelling to Edinburgh for a conference 14–19 October 2026 and I'll need a car when I land.";
    const session = createPlanSession(objective);
    expect(session.answers.startDate).toBe("2026-10-14");
    expect(session.answers.endDate).toBe("2026-10-19");
    expect(selectClarifications(extractFacts(objective)).map((item) => item.id)).toEqual([
      "departureAirport",
    ]);
  });

  it("does not invent a calendar date from next Thursday", () => {
    const facts = extractFacts(JFK);
    expect(facts.hasExactDates).toBe(false);
    expect(facts.dates).toBe("Thursday");
    const session = createPlanSession(JFK);
    expect(session.answers.startDate).toBe("");
    expect(session.answers.endDate).toBe("");
  });

  it("treats a named airport such as JFK as the live parking path", () => {
    const facts = extractFacts("jfk+evening");
    expect(facts.parkingStated).toBe(true);
    expect(facts.parkingAirport).toBe("JFK");
    expect(facts.dayPart).toBe("evening");
    expect(facts.tripLike).toBe(false);
    const projection = projectPlan(createPlanSession("jfk+evening"));
    expect(projection.tasks.map((task) => task.kind)).toEqual(["parking"]);
    expect(projection.tasks[0]?.provenance).toBe("explicit");
    expect(projection.tasks[0]?.accepted).toBe(true);
    expect(projection.tasks[0]?.detail).toMatch(/You asked for airport parking at JFK/i);
    expect(projection.tasks[0]?.detail).not.toMatch(/No domain was named/);
  });

  it("keeps evening/flexible as non-exact values in parking prefill", () => {
    const objective = "I need airport parking Friday evening but I'm flexible.";
    const facts = extractFacts(objective);
    expect(facts.dayPart).toBe("evening");
    expect(facts.timeFlexible).toBe(true);
    expect(facts.hasExactDates).toBe(false);
    const session = createPlanSession(objective);
    expect(session.answers.startPeriod).toBe("evening");
    expect(session.answers.timeFlexible).toBe(true);
    const prefill = parkingPrefill(objective, facts, session.answers);
    expect(prefill.knownParking.start).toBeUndefined();
    expect(prefill.knownParking.end).toBeUndefined();
    expect(prefill.draft).toMatch(/Evening/i);
    expect(prefill.draft).toMatch(/flexible/i);
    expect(prefill.draft).not.toMatch(/\d{2}:\d{2}/);
  });

  it("retains a from-to natural-language range and still hands dates to parking when Evening is selected", () => {
    const objective = "I'm travelling to Edinburgh from 14 to 19 October 2026.";
    const facts = extractFacts(objective);
    expect(facts.hasExactDates).toBe(true);
    expect(facts.startDate).toBe("2026-10-14");
    expect(facts.endDate).toBe("2026-10-19");
    expect(facts.dates).toBe("14–19 Oct 2026");
    const session = createPlanSession(objective);
    expect(session.answers.startDate).toBe("2026-10-14");
    expect(session.answers.endDate).toBe("2026-10-19");
    session.answers.startPeriod = "evening";
    session.answers.endPeriod = "evening";
    const prefill = parkingPrefill(objective, facts, session.answers);
    expect(prefill.knownParking.start).toContain("2026-10-14");
    expect(prefill.knownParking.end).toContain("2026-10-19");
    expect(prefill.knownParking.startDate).toBe("2026-10-14");
    expect(prefill.knownParking.endDate).toBe("2026-10-19");
    expect(prefill.draft).toMatch(/Evening/i);
    expect(prefill.draft).toContain("14–19 Oct 2026");
  });

  it("does not invent JFK from a New York city trip and keeps parking unconfirmed until asked", () => {
    const facts = extractFacts("travelling to New York for 10 days.");
    expect(facts.destination).toBe("New York");
    expect(facts.parkingAirport).toBe("");
    expect(facts.destinationAirport).toBe("");
    expect(facts.parkingStated).toBe(false);
    const projection = projectPlan(createPlanSession("travelling to New York for 10 days."));
    expect(JSON.stringify(projection)).not.toMatch(/JFK/);
    const parking = projection.tasks.find((task) => task.kind === "parking");
    if (parking !== undefined) {
      expect(parking.provenance).not.toBe("explicit");
      expect(parking.accepted).toBe(false);
      expect(taskStatusLabel(parking)).toBe("Not confirmed");
    }
  });

  it("keeps parking and rental Explicit when the buyer asked for both, without inventing JFK", () => {
    const objective = "travelling to New York for 10 days. need parking and rental car.";
    const facts = extractFacts(objective);
    expect(facts.destination).toBe("New York");
    expect(facts.parkingStated).toBe(true);
    expect(facts.rentalStated).toBe(true);
    expect(facts.parkingAirport).toBe("");
    const projection = projectPlan(createPlanSession(objective));
    const byKind = Object.fromEntries(projection.tasks.map((task) => [task.kind, task]));
    expect(byKind.parking?.provenance).toBe("explicit");
    expect(byKind.parking?.accepted).toBe(true);
    expect(byKind.rental?.provenance).toBe("explicit");
    expect(byKind.rental?.accepted).toBe(true);
    expect(JSON.stringify(projection)).not.toMatch(/JFK/);
  });

  it("turns a same-session parking follow-up into an Explicit parking task", () => {
    const session = createPlanSession("travelling to New York for 10 days.");
    expect(
      projectPlan(session).tasks.some(
        (task) => task.kind === "parking" && task.provenance === "explicit",
      ),
    ).toBe(false);
    session.extraNote = "I also need parking";
    const parking = projectPlan(session).tasks.find((task) => task.kind === "parking");
    expect(parking?.provenance).toBe("explicit");
    expect(parking?.accepted).toBe(true);
    expect(JSON.stringify(projectPlan(session))).not.toMatch(/JFK/);
  });

  it("does not treat a rental-only LHR request as explicit parking", () => {
    const facts = extractFacts("rental car needed on the 6th September in lhr");
    expect(facts.rentalStated).toBe(true);
    expect(facts.parkingStated).toBe(false);
    expect(facts.parkingAirport).toBe("");
    const projection = projectPlan(
      createPlanSession("rental car needed on the 6th September in lhr"),
    );
    const parking = projection.tasks.find((task) => task.kind === "parking");
    const rental = projection.tasks.find((task) => task.kind === "rental");
    expect(rental?.provenance).toBe("explicit");
    expect(rental && taskStatusLabel(rental)).toBe("On the plan");
    if (parking !== undefined) {
      expect(parking.provenance).not.toBe("explicit");
      expect(parking.accepted).toBe(false);
      expect(taskStatusLabel(parking)).toBe("Not confirmed");
    }
  });

  it("does not repeat Manchester in shared context chips", () => {
    const session = createPlanSession("parking needed from 5 to 10 October");
    session.extraNote = "manchester";
    const labels = projectPlan(session).chips.map((chip) => chip.label.toLowerCase());
    expect(labels.filter((label) => label === "manchester").length).toBeLessThanOrEqual(1);
  });

  it("compacts shared context once a parking intent exists", () => {
    const line = compactSharedContext(
      {
        destination: "Manchester",
        originCity: "",
        destinationAirport: "",
        parkingAirport: "MAN",
        departureAirport: "",
        dates: "26–28 Oct 2026",
        hasExactDates: true,
        hasLooseDates: false,
        startDate: "2026-10-26",
        endDate: "2026-10-28",
        carNeed: "",
        parkingStated: true,
        rentalStated: false,
        entsStated: false,
        hotelStated: false,
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
      {
        kind: "parking",
        support: "live_simulated",
        provenance: "explicit",
        accepted: true,
        fields: {
          airportCode: { value: "MAN", source: "current_turn", provenance: "explicit" },
          start: { value: "2026-10-26T07:00:00Z", source: "current_turn", provenance: "explicit" },
          end: { value: "2026-10-28T22:00:00Z", source: "current_turn", provenance: "explicit" },
        },
        missing: [],
        ask: [],
        completeness: "offers",
        intentId: "pi_01k2m3n4p5q6r7s8t9v0w1x2ag",
        offerSet: { stale: false, snapshot: null },
      },
    );
    expect(line).toContain("MAN");
    expect(line).toContain("26–28 Oct 2026");
    expect(line).toContain("07:00–22:00");
    expect(line).toContain("pi_01k2");
    expect(line.split(" · ").length).toBeGreaterThanOrEqual(3);
  });
});
