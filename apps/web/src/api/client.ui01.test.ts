import { describe, expect, it, vi } from "vitest";
import { createItaaApi } from "./client.js";
import { ClosedApiError } from "./errors.js";
import { API_PREFIX, type AuthorizationBody, type PurchaseIntent } from "./types.js";

const intent: PurchaseIntent = {
  schemaVersion: "1.0",
  intentId: "pi_01k2m3n4p5q6r7s8t9v0w1x2y3",
  buyerToken: "bs_01k2m3n4p5q6r7s8t9v0w1x2y4",
  category: "airport_parking",
  location: { airportCode: "JFK" },
  serviceWindow: { start: "2026-09-03T13:00:00Z", end: "2026-09-08T22:00:00Z" },
  requirements: { vehicleClass: "standard", covered: "preferred", shuttleMaxMinutes: 20 },
  constraints: { currency: "USD", accessibility: ["ev_charging"] },
  disclosure: {
    profile: "parking_v1",
    approvedPayloadHash: "sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
  },
  solicitation: { responseDeadline: "2026-08-21T15:00:00Z", counteroffersAllowed: false },
  createdAt: "2026-08-20T15:00:00Z",
  expiresAt: "2026-08-22T15:00:00Z",
};

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

describe("createItaaApi", () => {
  it("maps successful snapshot reads and mutations", async () => {
    const fetchImpl = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/healthz")) {
        return jsonResponse({ status: "ok", environment: "local_simulation" });
      }
      if (url.endsWith("/readyz")) {
        return jsonResponse({
          status: "ready",
          environment: "local_simulation",
          durability: "unsupported",
        });
      }
      return jsonResponse({
        intentId: intent.intentId,
        state: "AWAITING_REQUIREMENT_CONFIRMATION",
      });
    });
    const api = createItaaApi({ baseUrl: "http://example.test", fetchImpl });
    await expect(api.healthz()).resolves.toMatchObject({ status: "ok" });
    await expect(api.readyz()).resolves.toMatchObject({ durability: "unsupported" });
    await api.createIntent(intent);
    await api.getSnapshot(intent.intentId);
    await api.approveAndDispatch(intent.intentId, {
      actorId: "ar_01k2m3n4p5q6r7s8t9v0w1x2k1",
      ownerId: "ar_01k2m3n4p5q6r7s8t9v0w1x2k1",
      approvalId: "ap_01k2m3n4p5q6r7s8t9v0w1x2f1",
      correlationId: "cr_01k2m3n4p5q6r7s8t9v0w1x2k2",
      issuedAt: "2026-08-20T15:00:00Z",
      expiresAt: "2026-08-22T15:00:00Z",
    });
    await api.acceptOffer(intent.intentId, {
      actorId: "ar_01k2m3n4p5q6r7s8t9v0w1x2k1",
      ownerId: "ar_01k2m3n4p5q6r7s8t9v0w1x2k1",
      approvalId: "ap_01k2m3n4p5q6r7s8t9v0w1x2f2",
      correlationId: "cr_01k2m3n4p5q6r7s8t9v0w1x2k2",
      issuedAt: "2026-08-20T15:00:00Z",
      expiresAt: "2026-08-22T15:00:00Z",
      offerId: "of_01k2m3n4p5q6r7s8t9v0w1x2a2",
      offerVersion: 1,
    });
    await api.confirmRequirement(intent.intentId, {
      actorId: "ar_01k2m3n4p5q6r7s8t9v0w1x2k1",
      ownerId: "ar_01k2m3n4p5q6r7s8t9v0w1x2k1",
      approvalId: "ap_01k2m3n4p5q6r7s8t9v0w1x2f0",
      correlationId: "cr_01k2m3n4p5q6r7s8t9v0w1x2k2",
      issuedAt: "2026-08-20T15:00:00Z",
      expiresAt: "2026-08-22T15:00:00Z",
    });
    expect(fetchImpl).toHaveBeenCalled();
    const created = fetchImpl.mock.calls[2];
    expect(String(created?.[0])).toBe(`http://example.test${API_PREFIX}/intents`);
  });

  it("sends matching A4 header and body idempotency keys", async () => {
    const fetchImpl = vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
      expect(new Headers(init?.headers).get("Idempotency-Key")).toBe(
        "ik_01k2m3n4p5q6r7s8t9v0w1x2c1",
      );
      const body = JSON.parse(String(init?.body)) as AuthorizationBody;
      expect(body.idempotencyKey).toBe("ik_01k2m3n4p5q6r7s8t9v0w1x2c1");
      expect(body.action).toBe("reserve_parking");
      expect(body.mode).toBe("SIMULATED");
      return jsonResponse({ state: "TRANSACTION_AUTHORIZED_SIMULATED" });
    });
    const api = createItaaApi({ fetchImpl });
    await api.authorizeTransaction(
      intent.intentId,
      {
        actorId: "ar_01k2m3n4p5q6r7s8t9v0w1x2k1",
        ownerId: "ar_01k2m3n4p5q6r7s8t9v0w1x2k1",
        approvalId: "ap_01k2m3n4p5q6r7s8t9v0w1x2f3",
        correlationId: "cr_01k2m3n4p5q6r7s8t9v0w1x2k2",
        issuedAt: "2026-08-20T15:00:00Z",
        expiresAt: "2026-08-22T15:00:00Z",
        acceptanceId: "ac_01k2m3n4p5q6r7s8t9v0w1x2d1",
        amountMinor: 14800,
        currency: "USD",
        supplierToken: "sp_01k2m3n4p5q6r7s8t9v0w1x2b2",
        action: "reserve_parking",
        mode: "SIMULATED",
        idempotencyKey: "ik_01k2m3n4p5q6r7s8t9v0w1x2c1",
      },
      "ik_01k2m3n4p5q6r7s8t9v0w1x2c1",
    );
  });

  it("maps closed errors without echoing secrets", async () => {
    const fetchImpl = vi.fn(async () =>
      jsonResponse(
        {
          error: {
            code: "approval_denied",
            field: "approvalId",
            correlationId: "cr_01k2m3n4p5q6r7s8t9v0w1x2k2",
          },
        },
        422,
      ),
    );
    const api = createItaaApi({ fetchImpl });
    await expect(api.getSnapshot("pi_01k2m3n4p5q6r7s8t9v0w1x2y3")).rejects.toMatchObject({
      code: "approval_denied",
      message: expect.not.stringMatching(/ap_|ik_|sg_/),
    });
  });

  it("treats network failure as ambiguous and retryable", async () => {
    const api = createItaaApi({
      fetchImpl: async () => {
        throw new TypeError("failed to fetch");
      },
    });
    await expect(api.getSnapshot("pi_01k2m3n4p5q6r7s8t9v0w1x2y3")).rejects.toBeInstanceOf(
      ClosedApiError,
    );
    try {
      await api.getSnapshot("pi_01k2m3n4p5q6r7s8t9v0w1x2y3");
    } catch (error) {
      expect(error).toBeInstanceOf(ClosedApiError);
      if (error instanceof ClosedApiError) {
        expect(error.ambiguous).toBe(true);
        expect(error.retryable).toBe(true);
        expect(error.message).not.toContain("ik_");
      }
    }
  });

  it("maps empty 500 bodies to a closed retryable error", async () => {
    const api = createItaaApi({
      fetchImpl: async () => new Response("not-json", { status: 500 }),
    });
    await expect(
      api.approveAndDispatch("pi_01k2m3n4p5q6r7s8t9v0w1x2y3", {
        actorId: "ar_01k2m3n4p5q6r7s8t9v0w1x2k1",
        ownerId: "ar_01k2m3n4p5q6r7s8t9v0w1x2k1",
        approvalId: "ap_01k2m3n4p5q6r7s8t9v0w1x2f1",
        correlationId: "cr_01k2m3n4p5q6r7s8t9v0w1x2k2",
        issuedAt: "2026-08-20T15:00:00Z",
        expiresAt: "2026-08-22T15:00:00Z",
      }),
    ).rejects.toMatchObject({ code: "closed", retryable: true, ambiguous: true });
  });

  it("uses cookie-scoped intake portfolio paths with an idempotency key on replace", async () => {
    const fetchImpl = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/intake/intents")) {
        expect(init?.credentials).toBe("same-origin");
        return jsonResponse({ needsYou: [], running: [], saved: [], history: [] });
      }
      if (url.endsWith("/cancel")) {
        return jsonResponse({ state: "CANCELLED" });
      }
      if (url.endsWith("/replace")) {
        expect(new Headers(init?.headers).get("Idempotency-Key")).toBe(
          "ik_01k2m3n4p5q6r7s8t9v0w1x2k1",
        );
        return jsonResponse({
          previous: { intentId: intent.intentId, state: "SUPERSEDED" },
          draft: {
            intentId: "pi_01k2m3n4p5q6r7s8t9v0w1x2n1",
            state: "AWAITING_REQUIREMENT_CONFIRMATION",
          },
        });
      }
      if (url.endsWith("/save") && init?.method === "DELETE") {
        return jsonResponse({ saved: false });
      }
      if (url.endsWith("/save")) {
        return jsonResponse({ saved: true });
      }
      if (url.endsWith("/activity")) {
        return jsonResponse({
          activity: [{ occurredAt: "2026-08-20T15:00:00Z", label: "Request created" }],
        });
      }
      if (init?.method === "DELETE") {
        return new Response(null, { status: 204 });
      }
      return jsonResponse({
        intentId: intent.intentId,
        state: "AWAITING_REQUIREMENT_CONFIRMATION",
      });
    });
    const api = createItaaApi({ baseUrl: "http://example.test", fetchImpl });
    await api.listIntents();
    await api.cancelIntent(intent.intentId);
    await api.replaceIntent(intent.intentId, "ik_01k2m3n4p5q6r7s8t9v0w1x2k1");
    await api.saveIntent(intent.intentId);
    await api.unsaveIntent(intent.intentId);
    await api.intentActivity(intent.intentId);
    await api.deleteDraft(intent.intentId);
    const urls = fetchImpl.mock.calls.map((call) => String(call[0]));
    expect(urls).toContain(`http://example.test${API_PREFIX}/intake/intents`);
    expect(urls.some((url) => url.endsWith("/cancel"))).toBe(true);
    expect(urls.some((url) => url.endsWith("/replace"))).toBe(true);
  });
});
