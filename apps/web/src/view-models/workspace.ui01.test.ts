import { describe, expect, it } from "vitest";
import type { RankedOffer } from "../api/types.js";
import { LOCKED_OFFER_IDS, LOCKED_SUPPLIER_TOKENS } from "../fixtures/golden.js";
import { rankedOffers, rankedSnapshot, snapshot } from "../test/fixtures.js";
import {
  a3AcceptanceView,
  a3Eligibility,
  activityHeading,
  allSuppliersUnavailable,
  downsideCopy,
  formatHumanDateTime,
  offerCards,
  offerMoney,
  partialSuppliers,
  priceOnlyLeaderCopy,
  snapshotEvaluationTime,
  stageFor,
  supplierLanes,
  whyRecommended,
} from "./workspace.js";

describe("workspace view models", () => {
  it("maps every backend state to a stage", () => {
    expect(stageFor("AWAITING_REQUIREMENT_CONFIRMATION")).toBe("requirement");
    expect(stageFor("AWAITING_DISPATCH_APPROVAL")).toBe("disclosure");
    expect(stageFor("OFFERS_RANKED")).toBe("offers");
    expect(stageFor("ACCEPTANCE_RECORDED")).toBe("authorization");
    expect(stageFor("TRANSACTION_AUTHORIZED_SIMULATED")).toBe("receipt");
  });

  it("preserves locked ranking, downside, and supplier isolation", () => {
    const cards = offerCards(rankedOffers());
    expect(cards.map((card) => card.displayName)).toEqual([
      "SkyShield",
      "ParkDirect",
      "TerminalFlex",
    ]);
    expect(cards[0]?.score).toBe("671,000");
    expect(cards[1]?.score).toBe("660,000");
    expect(cards[2]?.score).toBe("535,000");
    expect(downsideCopy(rankedSnapshot())).toBe("USD 29.00 versus ParkDirect.");
    expect(priceOnlyLeaderCopy(rankedSnapshot())).toBe(
      "If all-in price were the only factor, ParkDirect would rank ahead.",
    );
    expect(whyRecommended(rankedSnapshot())[0]).toContain("SkyShield");
    expect(whyRecommended(rankedSnapshot())[0]).toContain("covered");
    expect(whyRecommended(rankedSnapshot())[0]).toContain("ev charging");
    const parkDirectWinner = rankedSnapshot({
      recommendedOfferId: LOCKED_OFFER_IDS.parkDirect,
      offers: rankedOffers().map((offer) => ({
        ...offer,
        recommended: offer.offerId === LOCKED_OFFER_IDS.parkDirect,
      })),
    });
    expect(priceOnlyLeaderCopy(parkDirectWinner)).toBe(
      "This recommendation is also the lowest all-in total on the snapshot.",
    );
    expect(whyRecommended(parkDirectWinner)[0]).toContain("ParkDirect");
    expect(whyRecommended(parkDirectWinner)[0]).toContain("uncovered");
    expect(whyRecommended(parkDirectWinner)[0]).not.toContain("ev charging");
    const uniqueIds = rankedOffers().map((offer, index) => ({
      ...offer,
      offerId: `of_01k2m3n4p5q6r7s8t9v0w1x2u${index + 1}`,
    }));
    const uniqueCards = offerCards(uniqueIds);
    expect(uniqueCards[0]?.catalog?.displayName).toBe("SkyShield");
    expect(uniqueCards[1]?.catalog?.displayName).toBe("ParkDirect");
    expect(uniqueCards[2]?.catalog?.displayName).toBe("TerminalFlex");
    const lanes = supplierLanes(rankedSnapshot().supplierOutcomes);
    expect(lanes).toHaveLength(3);
    expect(
      lanes.some(
        (lane) => lane.displayName === "ParkDirect" && lane.statusLabel === "Offer received",
      ),
    ).toBe(true);
  });

  it("covers waiting, partial, failed, and empty recommendation states", () => {
    expect(supplierLanes([])).toHaveLength(3);
    expect(supplierLanes([])[0]?.statusLabel).toBe("Waiting");
    const partial = rankedSnapshot({
      supplierOutcomes: [
        { supplierToken: LOCKED_SUPPLIER_TOKENS.skyShield, kind: "OFFER", reason: null },
        { supplierToken: LOCKED_SUPPLIER_TOKENS.parkDirect, kind: "TIMED_OUT", reason: "deadline" },
        { supplierToken: LOCKED_SUPPLIER_TOKENS.terminalFlex, kind: "DECLINED", reason: null },
      ],
    });
    expect(partialSuppliers(partial)).toBe(true);
    expect(
      allSuppliersUnavailable(
        snapshot({
          supplierOutcomes: [
            { supplierToken: LOCKED_SUPPLIER_TOKENS.skyShield, kind: "FAILED", reason: "closed" },
          ],
        }),
      ),
    ).toBe(true);
    expect(whyRecommended(snapshot())[0]).toContain("No reliable recommendation");
    expect(downsideCopy(snapshot())).toBeNull();
    expect(offerCards([])).toEqual([]);
    expect(LOCKED_OFFER_IDS.skyShield).toMatch(/^of_/);
    expect(
      downsideCopy(
        rankedSnapshot({
          downside: {
            dimension: "coverage_fit",
            delta: 1,
            versusOfferId: LOCKED_OFFER_IDS.parkDirect,
          },
        }),
      ),
    ).toContain("ParkDirect");
    expect(
      supplierLanes([
        { supplierToken: LOCKED_SUPPLIER_TOKENS.skyShield, kind: "FAILED", reason: null },
        { supplierToken: LOCKED_SUPPLIER_TOKENS.parkDirect, kind: "DENIED", reason: null },
        { supplierToken: "sp_unknown", kind: "CUSTOM", reason: null },
      ]).map((lane) => lane.statusLabel),
    ).toEqual(["Failed", "Denied", "CUSTOM"]);
  });

  it("derives A3 acceptance details from the selected snapshot offer, not catalog prices", () => {
    const liveTotals = rankedSnapshot({
      updatedAt: "2026-08-20T16:00:00Z",
      offers: rankedOffers().map((offer) =>
        offer.offerId === LOCKED_OFFER_IDS.skyShield
          ? { ...offer, totalMinor: 545127, scoreMicros: 545127, version: 3 }
          : offer,
      ),
    });
    const sky = liveTotals.offers.find((item) => item.offerId === LOCKED_OFFER_IDS.skyShield);
    expect(sky).toBeDefined();
    const details = a3AcceptanceView(liveTotals, sky!);
    expect(details.supplier).toBe("SkyShield");
    expect(details.version).toBe("3");
    expect(details.amount).toBe("USD 5451.27");
    expect(details.currency).toBe("USD");
    expect(details.cancellation).toContain("24 hours");
    expect(details.refund).toContain("original");
    expect(details.addOns).toContain("EV charging");
    expect(details.validityDeadline).toBe("2026-08-21T16:00:00Z");
    expect(details.simulationStatus).toContain("SIMULATED");
    expect(details.evaluationTime).toBe("2026-08-20T16:00:00Z");
    expect(snapshotEvaluationTime(liveTotals)).toBe(liveTotals.updatedAt);
  });

  it("gates A3 on the snapshot evaluation clock rather than the wall clock", () => {
    const selected = rankedOffers()[0]!;
    const current = rankedSnapshot({
      updatedAt: "2026-08-20T16:00:00Z",
      expiresAt: "2026-08-22T15:00:00Z",
    });
    expect(a3Eligibility(current, selected).eligible).toBe(true);

    const expiredIntent = rankedSnapshot({
      updatedAt: "2026-08-22T15:00:00Z",
      expiresAt: "2026-08-22T15:00:00Z",
    });
    expect(a3Eligibility(expiredIntent, selected)).toMatchObject({
      eligible: false,
      kind: "expired",
      recoveryAction: "inbox",
    });

    const expiredOffer = rankedSnapshot({
      updatedAt: "2026-08-21T16:00:00Z",
      expiresAt: "2026-08-22T15:00:00Z",
    });
    expect(a3Eligibility(expiredOffer, selected)).toMatchObject({
      eligible: false,
      kind: "expired",
    });

    const stale = a3Eligibility(current, selected, { stale: true });
    expect(stale).toMatchObject({ eligible: false, kind: "stale", recoveryAction: "refresh" });

    const missing = a3Eligibility(current, { ...selected, offerId: "of_missing" });
    expect(missing).toMatchObject({ eligible: false, kind: "unavailable" });

    const unavailable = a3Eligibility(
      rankedSnapshot({
        supplierOutcomes: [
          { supplierToken: LOCKED_SUPPLIER_TOKENS.skyShield, kind: "FAILED", reason: "closed" },
          { supplierToken: LOCKED_SUPPLIER_TOKENS.parkDirect, kind: "DECLINED", reason: null },
          { supplierToken: LOCKED_SUPPLIER_TOKENS.terminalFlex, kind: "TIMED_OUT", reason: null },
        ],
        offers: [],
        recommendedOfferId: null,
      }),
      null,
    );
    expect(unavailable).toMatchObject({
      eligible: false,
      kind: "unavailable",
      recoveryAction: "inbox",
    });

    const notSimulated = a3Eligibility(
      rankedSnapshot({
        offers: rankedOffers().map((offer) =>
          offer.offerId === selected.offerId ? { ...offer, simulation: false } : offer,
        ),
      }),
      { ...selected, simulation: false },
    );
    expect(notSimulated).toMatchObject({ eligible: false, kind: "ineligible" });

    const noneSelected = a3Eligibility(current, null);
    expect(noneSelected).toMatchObject({ eligible: false, kind: "ineligible" });

    expect(
      a3Eligibility(snapshot({ state: "AWAITING_DISPATCH_APPROVAL" }), selected),
    ).toMatchObject({
      eligible: false,
      kind: "ineligible",
      recoveryAction: "refresh",
    });
    expect(
      a3Eligibility(
        rankedSnapshot({
          supplierOutcomes: rankedSnapshot().supplierOutcomes.map((item) =>
            item.supplierToken === selected.supplierToken
              ? { ...item, kind: "DECLINED", reason: null }
              : item,
          ),
        }),
        selected,
      ),
    ).toMatchObject({ eligible: false, kind: "unavailable", recoveryAction: "select" });
  });

  it("reads nested buyer-HTTP price and omits ranking scores when scoreMicros is absent", () => {
    const nested: RankedOffer = {
      offerId: LOCKED_OFFER_IDS.skyShield,
      supplierToken: LOCKED_SUPPLIER_TOKENS.skyShield,
      version: 1,
      rank: 1,
      recommended: true,
      simulation: true,
      price: { totalMinor: 14800, currency: "USD" },
    };
    expect(offerMoney(nested)).toEqual({ totalMinor: 14800, currency: "USD" });
    const cards = offerCards([nested]);
    expect(cards[0]?.total).toBe("USD 148.00");
    expect(cards[0]?.score).toBe("");
  });

  it("formats activity instants with a clock time and booking-specific headings", () => {
    expect(formatHumanDateTime("2026-08-20T17:05:00Z")).toBe("20 Aug 2026 17:05");
    const current = rankedSnapshot({ airport: "LHR" });
    expect(activityHeading("Request created", current)).toBe(
      "Request created for Heathrow parking",
    );
    expect(activityHeading("Details confirmed", current)).toBe("You confirmed to proceed");
    expect(activityHeading("Offer selected", current)).toBe(
      "Supplier SkyShield offer was approved",
    );
    expect(activityHeading("Simulated reservation authorized", current)).toBe(
      "Booking confirmed for SkyShield offer",
    );
    expect(activityHeading("Simulated authorization recorded", current)).toBe(
      "Booking confirmed for SkyShield offer",
    );
  });
});
