import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { createItaaApi } from "./api/client.js";
import { ClosedApiError } from "./api/errors.js";
import { governanceIds, opaqueId } from "./api/ids.js";
import { API_PREFIX, type BuyerSnapshot } from "./api/types.js";
import { createSeededPurchaseIntent, LOCKED_SUPPLIER_TOKENS } from "./fixtures/golden.js";

const repo = join(dirname(fileURLToPath(import.meta.url)), "../../..");
const requireLive = process.env.ITAA_WEB_INTEGRATION === "1";
const TERMS_HASH = /^sha256:[a-f0-9]{64}$/;

interface BuyerOfferPrice {
  totalMinor: number;
  taxMinor: number;
  feesMinor: number;
  currency: string;
}

interface BuyerOfferHttp {
  offerId: string;
  supplierToken: string;
  version: number;
  rank: number;
  recommended: boolean;
  termsHash: string;
  fit: "strong" | "good" | "fair";
  price: BuyerOfferPrice;
  simulation: true;
}

function buyerOffers(snapshot: BuyerSnapshot): BuyerOfferHttp[] {
  return snapshot.offers as unknown as BuyerOfferHttp[];
}

function assertBuyerOfferContract(offer: BuyerOfferHttp): void {
  expect(offer).not.toHaveProperty("scoreMicros");
  expect(offer.termsHash).toMatch(TERMS_HASH);
  expect(offer.price.currency).toBe("USD");
  expect(typeof offer.price.totalMinor).toBe("number");
  expect(typeof offer.price.taxMinor).toBe("number");
  expect(typeof offer.price.feesMinor).toBe("number");
}

describe("WP-06 contract integration", () => {
  it("keeps UI paths aligned with the committed OpenAPI document", () => {
    const openapi = JSON.parse(
      readFileSync(join(repo, "apps/api/openapi/itaa-v1.json"), "utf8"),
    ) as { paths: Record<string, unknown> };
    expect(openapi.paths["/healthz"]).toBeDefined();
    expect(openapi.paths["/readyz"]).toBeDefined();
    expect(openapi.paths[`${API_PREFIX}/intents`]).toBeDefined();
    expect(openapi.paths[`${API_PREFIX}/intents/{intent_id}`]).toBeDefined();
    expect(openapi.paths[`${API_PREFIX}/intents/{intent_id}/confirm`]).toBeDefined();
    expect(openapi.paths[`${API_PREFIX}/intents/{intent_id}/dispatch`]).toBeDefined();
    expect(openapi.paths[`${API_PREFIX}/intents/{intent_id}/events`]).toBeDefined();
    expect(openapi.paths[`${API_PREFIX}/intents/{intent_id}/acceptances`]).toBeDefined();
    expect(
      openapi.paths[`${API_PREFIX}/intents/{intent_id}/transaction-authorizations`],
    ).toBeDefined();
  });
});

describe.skipIf(!requireLive)("WP-06 orchestrated local HTTP golden path", () => {
  it("creates a seeded intent, advances A1-A4, replays A4, and reaches the simulated receipt", async () => {
    const base = process.env.ITAA_API_BASE ?? "http://127.0.0.1:8000";
    const api = createItaaApi({ baseUrl: base });
    const actorId = opaqueId("ar_");
    const body = () => governanceIds(actorId, actorId);

    let health: Awaited<ReturnType<typeof api.healthz>>;
    try {
      health = await api.healthz();
    } catch (error) {
      throw new Error(
        `WP-06 FastAPI is required for test:integration at ${base}. Start: uv run uvicorn itaa_api.app:app --app-dir apps/api/src. Cause: ${String(error)}`,
      );
    }
    expect(health.status).toBe("ok");
    expect(health.environment).toBe("local_simulation");

    const ready = await api.readyz();
    expect(ready.status).toBe("ready");

    const intent = createSeededPurchaseIntent();
    let created: BuyerSnapshot;
    try {
      created = await api.createIntent(intent);
    } catch (error) {
      if (error instanceof ClosedApiError) {
        throw new Error(
          `createIntent failed ${intent.intentId} status=${error.status} code=${error.code} field=${error.field}`,
        );
      }
      throw error;
    }
    expect(created.state).toBe("AWAITING_REQUIREMENT_CONFIRMATION");
    expect(created.intentId).toMatch(/^pi_/);
    expect(created.airport).toBe("JFK");

    const confirmed = await api.confirmRequirement(created.intentId, body());
    expect(confirmed.state).toBe("AWAITING_DISPATCH_APPROVAL");
    expect(confirmed.intentId).toBe(created.intentId);

    const dispatched = await api.approveAndDispatch(created.intentId, body());
    expect(dispatched.state).toBe("OFFERS_RANKED");
    const offers = buyerOffers(dispatched);
    expect(offers).toHaveLength(3);
    for (const offer of offers) {
      assertBuyerOfferContract(offer);
    }
    const byToken = Object.fromEntries(offers.map((item) => [item.supplierToken, item]));
    const sky = byToken[LOCKED_SUPPLIER_TOKENS.skyShield];
    const park = byToken[LOCKED_SUPPLIER_TOKENS.parkDirect];
    const flex = byToken[LOCKED_SUPPLIER_TOKENS.terminalFlex];
    expect(sky).toBeDefined();
    expect(park).toBeDefined();
    expect(flex).toBeDefined();
    expect(sky!.rank).toBe(1);
    expect(park!.rank).toBe(2);
    expect(flex!.rank).toBe(3);
    expect(sky!.fit).toBe("strong");
    expect(park!.fit).toBe("good");
    expect(flex!.fit).toBe("fair");
    expect(sky!.price.totalMinor).toBe(14800);
    expect(park!.price.totalMinor).toBe(11900);
    expect(flex!.price.totalMinor).toBe(16900);
    expect(sky!.recommended).toBe(true);
    expect(park!.recommended).toBe(false);
    expect(flex!.recommended).toBe(false);
    expect(dispatched.recommendedOfferId).toBe(sky!.offerId);
    expect(dispatched.downside?.delta).toBe(2900);
    expect(dispatched.downside?.versusOfferId).toBe(park!.offerId);
    const winner = sky!;
    expect(winner.offerId).not.toBe("of_01k2m3n4p5q6r7s8t9v0w1x2a2");

    const accepted = await api.acceptOffer(created.intentId, {
      ...body(),
      offerId: winner.offerId,
      offerVersion: winner.version,
    });
    expect(accepted.state).toBe("ACCEPTANCE_RECORDED");
    expect(accepted.acceptance?.offerId).toBe(winner.offerId);
    for (const offer of buyerOffers(accepted)) {
      assertBuyerOfferContract(offer);
    }

    const key = opaqueId("ik_");
    const authorize = () =>
      api.authorizeTransaction(
        created.intentId,
        {
          ...body(),
          acceptanceId: accepted.acceptance!.acceptanceId,
          amountMinor: winner.price.totalMinor,
          currency: winner.price.currency,
          supplierToken: winner.supplierToken,
          action: "reserve_parking",
          mode: "SIMULATED",
          idempotencyKey: key,
        },
        key,
      );

    const first = await authorize();
    expect(first.state).toBe("TRANSACTION_AUTHORIZED_SIMULATED");
    expect(first.transaction?.mode).toBe("SIMULATED");
    expect(first.transaction?.resultRef).toMatch(/^rr_/);
    for (const offer of buyerOffers(first)) {
      assertBuyerOfferContract(offer);
    }

    const replay = await authorize();
    expect(replay.state).toBe("TRANSACTION_AUTHORIZED_SIMULATED");
    expect(replay.transaction?.authorizationId).toBe(first.transaction?.authorizationId);
    expect(replay.transaction?.resultRef).toBe(first.transaction?.resultRef);

    const receipt: BuyerSnapshot = await api.getSnapshot(created.intentId);
    expect(receipt.state).toBe("TRANSACTION_AUTHORIZED_SIMULATED");
    expect(receipt.transaction?.resultRef).toBe(first.transaction?.resultRef);
    for (const offer of buyerOffers(receipt)) {
      assertBuyerOfferContract(offer);
    }
  });
});
