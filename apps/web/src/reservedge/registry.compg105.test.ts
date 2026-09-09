import { describe, expect, it } from "vitest";
import { intakeExtraction } from "../test/fixtures.js";
import {
  applyChip,
  applySkip,
  applyTyped,
  canonicalizeFromTyped,
  correctField,
  displayFor,
  EMPTY_VALUES,
  extractAirport,
  missingRequiredFields,
  noteFor,
  parkingFieldsOrNull,
  parseWindow,
  QUESTION_CAP,
  selectQuestions,
  valuesFromExtraction,
} from "./composer-engine.js";
import { SEED_INTENTS } from "./inbox.js";
import {
  canonicalizeAccessibility,
  hintsFromRequirementText,
  interpretCorrection,
  SAMPLE_JFK_TEXT,
} from "./parking-intake.js";
import { landingTab } from "./portfolio.js";
import {
  assertRegistry,
  DOMAIN_REGISTRY,
  domainById,
  listDomains,
  type DomainDefinition,
} from "./registry.js";

describe("COMP-G1-05 Phase 2 domain registry", () => {
  it("declares Pk, Rc, and En through one registry with at most three questions", () => {
    expect(DOMAIN_REGISTRY.map((domain) => domain.code)).toEqual(["Pk", "Rc", "En"]);
    for (const domain of DOMAIN_REGISTRY) {
      expect(domain.questions.length).toBeLessThanOrEqual(QUESTION_CAP);
      expect(domain.offerDimensions.length).toBeGreaterThan(0);
      expect(domain.offerDimensions.length).toBeLessThanOrEqual(6);
      expect(domain.fields.length).toBeGreaterThan(0);
    }
    expect(domainById("parking")?.simulation).toBe("competition_path");
    expect(domainById("rental")?.simulation).toBe("design_fixture");
    expect(domainById("ents")?.simulation).toBe("design_fixture");
    expect(JSON.stringify(DOMAIN_REGISTRY)).not.toMatch(/671000|SkyShield|ParkDirect|TerminalFlex/);
    assertRegistry(DOMAIN_REGISTRY);
  });

  it("adds a fourth domain through configuration without new screen types", () => {
    const spa: DomainDefinition = {
      ...DOMAIN_REGISTRY[2]!,
      name: "Spa booking",
      pickerBody: "Same picker and composer.",
    };
    const extended = listDomains([...DOMAIN_REGISTRY, spa]);
    expect(extended).toHaveLength(4);
    expect(extended.map((domain) => domain.name)).toContain("Spa booking");
  });

  it("rejects a domain with more than three questions", () => {
    const overflow = {
      ...DOMAIN_REGISTRY[1]!,
      questions: [...DOMAIN_REGISTRY[1]!.questions, DOMAIN_REGISTRY[1]!.questions[0]!],
    };
    expect(() => assertRegistry([overflow])).toThrow(/more than 3 questions/);
  });
});

describe("COMP-G1-05 Phase 2 composer engine", () => {
  it("skips parking questions when Gemini already filled required fields", () => {
    const parking = domainById("parking")!;
    const values = valuesFromExtraction(intakeExtraction());
    expect(selectQuestions(parking, values, intakeExtraction())).toEqual([]);
    const fields = parkingFieldsOrNull("in_01k2m3n4p5q6r7s8t9v0w1x2aa", values);
    expect(fields).toEqual(
      expect.objectContaining({
        intakeId: "in_01k2m3n4p5q6r7s8t9v0w1x2aa",
        airportCode: "JFK",
        vehicleClass: "standard",
        covered: "preferred",
        shuttleMaxMinutes: 20,
        currency: "USD",
        accessibility: ["ev_charging"],
      }),
    );
    expect(JSON.stringify(fields)).not.toMatch(/flying from JFK|September 3 at 1 PM/);
  });

  it("asks at most three parking questions for missing and ambiguous fields", () => {
    const parking = domainById("parking")!;
    const extraction = intakeExtraction({
      missingFields: [
        "location.airportCode",
        "serviceWindow.start",
        "serviceWindow.end",
        "requirements.vehicleClass",
        "requirements.covered",
        "constraints.currency",
      ],
      ambiguousFields: ["requirements.shuttleMaxMinutes"],
      proposal: {
        location: { airportCode: null },
        serviceWindow: { start: null, end: null },
        requirements: { vehicleClass: null, covered: null, shuttleMaxMinutes: null },
        constraints: { currency: null, accessibility: [] },
      },
    });
    const values = valuesFromExtraction(extraction);
    const asked = selectQuestions(parking, values, extraction);
    expect(asked.length).toBe(QUESTION_CAP);
    expect(asked.map((item) => item.id)).toEqual(["airport", "window", "prefs"]);
  });

  it("does not skip a required question", () => {
    const rental = domainById("rental")!;
    const driver = rental.questions.find((item) => item.id === "driver")!;
    const skipped = applySkip(driver, { fields: {}, provenance: {} });
    expect(skipped.fields.driver).toBeUndefined();
    expect(missingRequiredFields(rental, skipped).map((field) => field.id)).toContain("driver");
    const optional = rental.questions.find((item) => item.id === "class")!;
    const allowed = applySkip(optional, { fields: {}, provenance: {} });
    expect(allowed.fields.class).toBe("skipped");
  });

  it("maps chips and typed answers without storing the original sentence as a field", () => {
    const parking = domainById("parking")!;
    const airport = parking.questions[0]!;
    const fromChip = applyChip({ fields: {}, provenance: {} }, airport.chips[0]!);
    expect(fromChip.fields.airportCode).toBe("JFK");
    const typed = applyTyped(airport, { fields: {}, provenance: {} }, "please use LGA tomorrow");
    expect(typed.fields.airportCode).toBe("LGA");
    expect(JSON.stringify(typed)).not.toMatch(/please use LGA tomorrow/);
  });

  it("parses typed parking preferences without dropping already-answered fields", () => {
    const parking = domainById("parking")!;
    const prefs = parking.questions.find((item) => item.parse === "parking_prefs")!;
    const existing = {
      fields: { covered: "required", shuttleMaxMinutes: "15" },
      provenance: { covered: "answered" as const, shuttleMaxMinutes: "answered" as const },
    };
    const suvEv = applyTyped(prefs, existing, "need an SUV with EV charging");
    expect(suvEv.fields).toEqual(
      expect.objectContaining({
        covered: "required",
        shuttleMaxMinutes: "15",
        vehicleClass: "suv",
        accessibility: "ev_charging",
      }),
    );
    expect(applyTyped(prefs, EMPTY_VALUES, "no extra access").fields.accessibility).toBe("none");
    expect(applyTyped(prefs, EMPTY_VALUES, "wheelchair access").fields.accessibility).toBe(
      "wheelchair",
    );
    expect(applyTyped(prefs, EMPTY_VALUES, "step-free bay").fields.accessibility).toBe("step_free");
    expect(applyTyped(prefs, EMPTY_VALUES, "quiet lot please").fields.mustHaves).toBe(
      "quiet lot please",
    );
    expect(JSON.stringify(suvEv)).not.toMatch(/need an SUV with EV charging/);
  });

  it("keeps window times from the typed sentence when extraction left them blank", () => {
    const parking = domainById("parking")!;
    const window = parking.questions.find((item) => item.id === "window")!;
    const kept = applyChip(
      { fields: { airportCode: "JFK" }, provenance: { airportCode: "answered" } },
      window.chips[0]!,
      SAMPLE_JFK_TEXT,
    );
    expect(kept.fields.start).toBe("2026-09-03T13:00:00Z");
    expect(kept.fields.end).toBe("2026-09-08T22:00:00Z");
    const typed = applyTyped(window, { fields: {}, provenance: {} }, SAMPLE_JFK_TEXT);
    expect(typed.fields.start).toBe("2026-09-03T13:00:00Z");
    expect(typed.fields.end).toBe("2026-09-08T22:00:00Z");
  });

  it("canonicalizes EV phrases from the typed sentence without hard-coding the golden line", () => {
    const parking = domainById("parking")!;
    const extracted = valuesFromExtraction(
      intakeExtraction({
        proposal: {
          location: { airportCode: "JFK" },
          serviceWindow: { start: "2026-09-03T13:00:00Z", end: "2026-09-08T22:00:00Z" },
          requirements: { vehicleClass: "standard", covered: "preferred", shuttleMaxMinutes: 20 },
          constraints: { currency: "USD", accessibility: [] },
        },
      }),
    );
    const withEv = canonicalizeFromTyped(
      "I have a standard EV and need electric-vehicle charging.",
      extracted,
    );
    expect(withEv.fields.accessibility).toBe("ev_charging");
    const electric = canonicalizeFromTyped("This is an electric vehicle.", extracted);
    expect(electric.fields.accessibility).toBe("ev_charging");
    const explicit = canonicalizeFromTyped("Please include EV charging.", extracted);
    expect(explicit.fields.accessibility).toBe("ev_charging");
    expect(JSON.stringify(withEv)).not.toMatch(/flying from JFK|September 3 at 1 PM/);
    const asked = selectQuestions(parking, withEv, intakeExtraction());
    expect(asked.length).toBeLessThanOrEqual(QUESTION_CAP);
    expect(asked.map((item) => item.id)).not.toContain("prefs");
  });

  it("covers remaining composer notes, windows, and parking corrections", () => {
    const parking = domainById("parking")!;
    const airport = parking.fields.find((field) => field.id === "airportCode")!;
    expect(displayFor(airport, { fields: { airportCode: "JFK" }, provenance: {} })).toBe("JFK");
    expect(noteFor(airport, { fields: {}, provenance: {} }, "why")).toMatch(/Required/);
    expect(noteFor(airport, { fields: { airportCode: "skipped" }, provenance: {} }, "why")).toMatch(
      /Correctable/,
    );
    expect(
      noteFor(
        airport,
        { fields: { airportCode: "JFK" }, provenance: { airportCode: "proposed" } },
        "why",
      ),
    ).toMatch(/Proposed/);
    expect(
      noteFor(
        airport,
        { fields: { airportCode: "LGA" }, provenance: { airportCode: "corrected" } },
        "why",
      ),
    ).toBe("You corrected this");
    expect(
      noteFor(
        airport,
        { fields: { airportCode: "JFK" }, provenance: { airportCode: "answered" } },
        "why",
      ),
    ).toBe("You answered");
    expect(extractAirport("JFK")).toBe("JFK");
    expect(extractAirport("need parking")).toBe("NEED PARKING");
    expect(parseWindow("2026-09-03T13:00:00Z then 2026-09-08T22:00:00Z")).toEqual({
      start: "2026-09-03T13:00:00Z",
      end: "2026-09-08T22:00:00Z",
    });
    expect(parseWindow("only 2026-09-03T13:00:00Z").start).toBe("2026-09-03T13:00:00Z");
    expect(parseWindow("Jan 4 at 12 AM back Jan 5 at 3:15").end).toBe("2026-01-05T03:15:00Z");
    const corrected = correctField(
      { fields: { airportCode: "JFK" }, provenance: { airportCode: "proposed" } },
      "airportCode",
      "LGA",
    );
    expect(corrected.provenance.airportCode).toBe("corrected");
    expect(
      canonicalizeFromTyped("compact uncovered shuttle 12 minutes", EMPTY_VALUES).fields,
    ).toEqual(
      expect.objectContaining({
        vehicleClass: "compact",
        covered: "none",
        shuttleMaxMinutes: "12",
      }),
    );
  });
});

describe("COMP-G1-05 parking intake helpers", () => {
  it("canonicalizes access phrases and rejects invalid corrections", () => {
    expect(canonicalizeAccessibility("")).toBeNull();
    expect(canonicalizeAccessibility("none")).toBe("none");
    expect(canonicalizeAccessibility("step-free, wheelchair")).toBe("step_free,wheelchair");
    expect(canonicalizeAccessibility("electric car")).toBe("ev_charging");
    expect(interpretCorrection("vehicleClass", "")).toMatchObject({ ok: false });
    expect(interpretCorrection("vehicleClass", "boat")).toMatchObject({ ok: false });
    expect(interpretCorrection("vehicleClass", "suv")).toEqual({ ok: true, value: "suv" });
    expect(interpretCorrection("covered", "maybe")).toMatchObject({ ok: false });
    expect(interpretCorrection("covered", "required")).toEqual({ ok: true, value: "required" });
    expect(interpretCorrection("accessibility", "zzz")).toMatchObject({ ok: false });
    expect(interpretCorrection("accessibility", "wheelchair")).toEqual({
      ok: true,
      value: "wheelchair",
    });
    expect(interpretCorrection("airportCode", "JFKK")).toMatchObject({ ok: false });
    expect(interpretCorrection("airportCode", "ewr")).toEqual({ ok: true, value: "EWR" });
    expect(
      hintsFromRequirementText("LGA parking, oversized, uncovered, shuttle 8 minutes, USD"),
    ).toEqual(
      expect.objectContaining({
        airportCode: "LGA",
        vehicleClass: "oversized",
        covered: "none",
        shuttleMaxMinutes: "8",
        currency: "USD",
      }),
    );
    expect(hintsFromRequirementText("required cover compact")).toEqual(
      expect.objectContaining({ covered: "required", vehicleClass: "compact" }),
    );
  });
});

describe("COMP-G1-05 portfolio landing tab", () => {
  it("maps seed stages to the matching workspace tab", () => {
    expect(landingTab(null)).toBe("request");
    expect(landingTab({ ...SEED_INTENTS[0]!, stage: "offers" })).toBe("offers");
    expect(landingTab({ ...SEED_INTENTS[0]!, stage: "gate" })).toBe("offers");
    expect(landingTab({ ...SEED_INTENTS[0]!, stage: "done" })).toBe("offers");
    expect(landingTab({ ...SEED_INTENTS[0]!, stage: "research" })).toBe("research");
    expect(landingTab({ ...SEED_INTENTS[0]!, stage: "request" })).toBe("request");
  });
});
