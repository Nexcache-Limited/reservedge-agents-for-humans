import type {
  AgentSessionView,
  BuyerSnapshot,
  IntakeExtraction,
  ItaaApi,
  RankedOffer,
} from "../api/types.js";
import { ClosedApiError } from "../api/errors.js";
import { LOCKED_OFFER_IDS, LOCKED_SUPPLIER_TOKENS } from "../fixtures/golden.js";
import {
  createPlanSession,
  firstTurnCopy,
  mergeSchedule,
  parkingPrefill,
  projectPlan,
  type PlanSession,
} from "../intent-first/plan.js";

export function rankedOffers(): RankedOffer[] {
  return [
    {
      offerId: LOCKED_OFFER_IDS.skyShield,
      supplierToken: LOCKED_SUPPLIER_TOKENS.skyShield,
      version: 1,
      rank: 1,
      scoreMicros: 671000,
      totalMinor: 14800,
      currency: "USD",
      recommended: true,
      simulation: true,
    },
    {
      offerId: LOCKED_OFFER_IDS.parkDirect,
      supplierToken: LOCKED_SUPPLIER_TOKENS.parkDirect,
      version: 1,
      rank: 2,
      scoreMicros: 660000,
      totalMinor: 11900,
      currency: "USD",
      recommended: false,
      simulation: true,
    },
    {
      offerId: LOCKED_OFFER_IDS.terminalFlex,
      supplierToken: LOCKED_SUPPLIER_TOKENS.terminalFlex,
      version: 1,
      rank: 3,
      scoreMicros: 535000,
      totalMinor: 16900,
      currency: "USD",
      recommended: false,
      simulation: true,
    },
  ];
}

export function snapshot(overrides: Partial<BuyerSnapshot> = {}): BuyerSnapshot {
  return {
    environment: "local_simulation",
    simulation: true,
    intentId: "pi_01k2m3n4p5q6r7s8t9v0w1x2y3",
    state: "AWAITING_REQUIREMENT_CONFIRMATION",
    airport: "JFK",
    category: "airport_parking",
    createdAt: "2026-08-20T15:00:00Z",
    updatedAt: "2026-08-20T15:00:00Z",
    expiresAt: "2026-08-22T15:00:00Z",
    marketEvidence: [],
    supplierOutcomes: [],
    offers: [],
    recommendedOfferId: null,
    downside: null,
    acceptance: null,
    transaction: null,
    ...overrides,
  };
}

export function rankedSnapshot(overrides: Partial<BuyerSnapshot> = {}): BuyerSnapshot {
  const offers = rankedOffers();
  return snapshot({
    state: "OFFERS_RANKED",
    offers,
    recommendedOfferId: LOCKED_OFFER_IDS.skyShield,
    downside: { dimension: "total_minor", delta: 2900, versusOfferId: LOCKED_OFFER_IDS.parkDirect },
    supplierOutcomes: [
      { supplierToken: LOCKED_SUPPLIER_TOKENS.parkDirect, kind: "OFFER", reason: null },
      { supplierToken: LOCKED_SUPPLIER_TOKENS.skyShield, kind: "OFFER", reason: null },
      { supplierToken: LOCKED_SUPPLIER_TOKENS.terminalFlex, kind: "OFFER", reason: null },
    ],
    ...overrides,
  });
}

export function intakeExtraction(overrides: Partial<IntakeExtraction> = {}): IntakeExtraction {
  return {
    intakeId: "in_01k2m3n4p5q6r7s8t9v0w1x2aa",
    correlationId: "cr_01k2m3n4p5q6r7s8t9v0w1x2k2",
    proposal: {
      category: "airport_parking",
      location: { airportCode: "JFK" },
      serviceWindow: { start: "2026-09-03T13:00:00Z", end: "2026-09-08T22:00:00Z" },
      requirements: { vehicleClass: "standard", covered: "preferred", shuttleMaxMinutes: 20 },
      constraints: { currency: "USD", accessibility: ["ev_charging"] },
    },
    fieldConfidence: {
      "location.airportCode": 0.91,
      "serviceWindow.start": 0.88,
      "serviceWindow.end": 0.87,
    },
    missingFields: [],
    ambiguousFields: [],
    evidenceSpans: [{ field: "location.airportCode", start: 16, end: 19 }],
    requiresA1: true,
    accepted: false,
    fallback: null,
    rejectionCode: null,
    ...overrides,
  };
}

export function mockApi(overrides: Partial<ItaaApi> = {}): ItaaApi {
  return {
    healthz: async () => ({ status: "ok", environment: "local_simulation" }),
    readyz: async () => ({
      status: "ready",
      environment: "local_simulation",
      durability: "unsupported",
    }),
    createIntent: async () => snapshot(),
    getSnapshot: async () => snapshot(),
    confirmRequirement: async () => snapshot({ state: "AWAITING_DISPATCH_APPROVAL" }),
    approveAndDispatch: async () => rankedSnapshot(),
    acceptOffer: async () =>
      rankedSnapshot({
        state: "ACCEPTANCE_RECORDED",
        acceptance: {
          acceptanceId: "ac_01k2m3n4p5q6r7s8t9v0w1x2d1",
          offerId: LOCKED_OFFER_IDS.skyShield,
          offerVersion: 1,
          status: "recorded",
        },
      }),
    authorizeTransaction: async () =>
      rankedSnapshot({
        state: "TRANSACTION_AUTHORIZED_SIMULATED",
        acceptance: {
          acceptanceId: "ac_01k2m3n4p5q6r7s8t9v0w1x2d1",
          offerId: LOCKED_OFFER_IDS.skyShield,
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
      }),
    extractIntake: async () => intakeExtraction(),
    confirmIntakeIntent: async () => snapshot(),
    intakeConfirm: async () => snapshot({ state: "AWAITING_DISPATCH_APPROVAL" }),
    intakeDispatch: async () => rankedSnapshot(),
    intakeAccept: async () =>
      rankedSnapshot({
        state: "ACCEPTANCE_RECORDED",
        acceptance: {
          acceptanceId: "ac_01k2m3n4p5q6r7s8t9v0w1x2d1",
          offerId: LOCKED_OFFER_IDS.skyShield,
          offerVersion: 1,
          status: "recorded",
        },
      }),
    intakeAuthorize: async () =>
      rankedSnapshot({
        state: "TRANSACTION_AUTHORIZED_SIMULATED",
        acceptance: {
          acceptanceId: "ac_01k2m3n4p5q6r7s8t9v0w1x2d1",
          offerId: LOCKED_OFFER_IDS.skyShield,
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
      }),
    listIntents: async () => ({ needsYou: [], running: [], saved: [], history: [] }),
    getOwnedIntent: async (intentId) => snapshot({ intentId }),
    cancelIntent: async () => snapshot({ state: "CANCELLED" }),
    replaceIntent: async () => ({
      previous: snapshot({ state: "CANCELLED" }),
      draft: snapshot({ intentId: "pi_01k2m3n4p5q6r7s8t9v0w1x2n1" }),
    }),
    deleteDraft: async () => undefined,
    saveIntent: async () => snapshot({ saved: true, savedAt: "2026-08-20T16:00:00Z" }),
    unsaveIntent: async () => snapshot({ saved: false }),
    intentActivity: async () => [{ occurredAt: "2026-08-20T15:00:00Z", label: "Request created" }],
    subscribeProgress: () => ({ close: () => undefined }),
    ...localAgentMethods(),
    ...overrides,
  };
}

function localAgentMethods(): Pick<
  ItaaApi,
  | "createAgentSession"
  | "getAgentSession"
  | "postAgentTurn"
  | "confirmAgentSession"
  | "grantAgentSession"
  | "subscribeAgentEvents"
> {
  const store = new Map<string, PlanSession>();
  let seq = 0;

  function mint(): string {
    seq += 1;
    return `as_01k2m3n4p5q6r7s8t9v0w1x2${String(seq).padStart(2, "0")}`;
  }

  function requireSession(sessionId: string): PlanSession {
    const session = store.get(sessionId);
    if (session === undefined) {
      throw new ClosedApiError({
        status: 404,
        code: "unknown_resource",
        field: "sessionId",
        correlationId: "cr_01k2m3n4p5q6r7s8t9v0w1x2k2",
      });
    }
    return session;
  }

  function toView(sessionId: string, session: PlanSession): AgentSessionView {
    const projection = projectPlan(session);
    const questions = session.phase === "clarify" ? projection.questions : [];
    const prefill = parkingPrefill(session.objective, projection.facts, session.answers);
    const start = session.answers.startDate.trim();
    const end = session.answers.oneDay ? start : session.answers.endDate.trim();
    const structuredDates =
      start !== "" && end !== ""
        ? {
            dates: `${start} to ${end}`,
            hasExactDates: true as const,
            startDate: start,
            endDate: end,
          }
        : {
            dates: projection.facts.dates,
            hasExactDates: projection.facts.hasExactDates,
            startDate: projection.facts.startDate,
            endDate: projection.facts.endDate,
          };
    return {
      sessionId,
      projection: {
        facts: { ...projection.facts, ...structuredDates },
        questions,
        tasks: projection.tasks,
        phase: session.phase,
        title: projection.title,
        summary: projection.summary,
        confirmedCount: projection.confirmedCount,
        proposedCount: projection.proposedCount,
      },
      questions,
      toolTrace: [],
      pendingAuthorizations: [],
      pendingAuthorization: null,
      parkingHandoff:
        session.phase === "ready"
          ? {
              path: "/intents/new/parking",
              support: "live_simulated",
              fields: {
                ...prefill.knownParking,
                intakeId: `in_${sessionId}`,
              },
            }
          : null,
      confirmed: session.phase === "ready",
      fallback: false,
      correlationId: "cr_01k2m3n4p5q6r7s8t9v0w1x2k2",
      transcript: [
        { role: "user", text: session.objective },
        { role: "agent", text: firstTurnCopy(projection.facts) || projection.summary },
      ],
      domains: {},
      buyerSafeMessage: firstTurnCopy(projection.facts) || projection.summary,
    };
  }

  return {
    createAgentSession: async ({ objective }) => {
      const session = createPlanSession(objective);
      const sessionId = mint();
      store.set(sessionId, session);
      return toView(sessionId, session);
    },
    getAgentSession: async (sessionId) => toView(sessionId, requireSession(sessionId)),
    postAgentTurn: async (sessionId, body) => {
      const current = requireSession(sessionId);
      const next: PlanSession = {
        ...current,
        extraNote: body.message?.trim()
          ? `${current.extraNote} ${body.message.trim()}`.trim()
          : current.extraNote,
        answers: body.answers
          ? mergeSchedule(current.answers, body.answers, current.answers.dates)
          : current.answers,
        phase: body.answers !== undefined ? "forming" : current.phase,
      };
      store.set(sessionId, next);
      return toView(sessionId, next);
    },
    confirmAgentSession: async (sessionId) => {
      const current = requireSession(sessionId);
      const next: PlanSession = { ...current, phase: "ready", pane: "plan" };
      store.set(sessionId, next);
      return toView(sessionId, next);
    },
    grantAgentSession: async (sessionId) => toView(sessionId, requireSession(sessionId)),
    subscribeAgentEvents: () => ({ close: () => undefined }),
  };
}
