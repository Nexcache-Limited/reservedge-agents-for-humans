import { describe, expect, it, vi } from "vitest";
import { createItaaApi } from "./api/client.js";
import { API_PREFIX } from "./api/types.js";
import { opaqueId } from "./api/ids.js";
import {
  isCompetitionIntent,
  rememberCompetitionIntent,
  rememberSnapshot,
} from "./session/memory.js";
import { snapshot } from "./test/fixtures.js";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

describe("competition intake client", () => {
  it("posts extract and confirmed fields without Cloud Run or minted ids", async () => {
    const fetchImpl = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      expect(url).not.toMatch(/8080|run\.app|googleapis|cloudfunctions/i);
      if (url.endsWith("/intake/extractions")) {
        const body = JSON.parse(String(init?.body)) as { text: string; category: string };
        expect(body.category).toBe("airport_parking");
        expect(body.text).toContain("flying from JFK");
        expect(body).not.toHaveProperty("intentId");
        return jsonResponse({
          intakeId: "in_01k2m3n4p5q6r7s8t9v0w1x2aa",
          proposal: { location: { airportCode: "JFK" } },
          fieldConfidence: {},
          missingFields: [],
          ambiguousFields: [],
          evidenceSpans: [],
        });
      }
      if (url.endsWith("/intake/intents")) {
        const body = JSON.parse(String(init?.body)) as Record<string, unknown>;
        expect(body).not.toHaveProperty("text");
        expect(body).not.toHaveProperty("actorId");
        expect(body).not.toHaveProperty("approvalId");
        expect(body.airportCode).toBe("JFK");
        return jsonResponse(snapshot());
      }
      return jsonResponse(snapshot());
    });
    const api = createItaaApi({ baseUrl: "http://example.test", fetchImpl });
    const extracted = await api.extractIntake(
      "I'm flying from JFK on September 3 at 1 PM and returning September 8 at 10 PM. I have a standard EV, prefer covered parking, and don't want a shuttle longer than 20 minutes.",
      "airport_parking",
    );
    expect(extracted.intakeId).toBe("in_01k2m3n4p5q6r7s8t9v0w1x2aa");
    await api.confirmIntakeIntent({
      intakeId: extracted.intakeId,
      airportCode: "JFK",
      start: "2026-09-03T13:00:00Z",
      end: "2026-09-08T22:00:00Z",
      vehicleClass: "standard",
      covered: "preferred",
      shuttleMaxMinutes: 20,
      currency: "USD",
      accessibility: ["ev_charging"],
    });
    expect(String(fetchImpl.mock.calls[0]?.[0])).toBe(
      `http://example.test${API_PREFIX}/intake/extractions`,
    );
    expect(String(fetchImpl.mock.calls[1]?.[0])).toBe(
      `http://example.test${API_PREFIX}/intake/intents`,
    );
  });

  it("uses intake A1–A4 paths without governance ids or client keys", async () => {
    const fetchImpl = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      expect(url).toContain("/intake/intents/");
      expect(url).not.toMatch(/8080|run\.app/i);
      const headers = new Headers(init?.headers);
      expect(headers.get("Idempotency-Key")).toBeNull();
      const body = JSON.parse(String(init?.body ?? "{}")) as Record<string, unknown>;
      expect(body).not.toHaveProperty("actorId");
      expect(body).not.toHaveProperty("approvalId");
      expect(body).not.toHaveProperty("correlationId");
      expect(body).not.toHaveProperty("idempotencyKey");
      return jsonResponse(snapshot());
    });
    const api = createItaaApi({ fetchImpl });
    await api.intakeConfirm("pi_01k2m3n4p5q6r7s8t9v0w1x2y3");
    await api.intakeDispatch("pi_01k2m3n4p5q6r7s8t9v0w1x2y3");
    await api.intakeAccept("pi_01k2m3n4p5q6r7s8t9v0w1x2y3", {
      offerId: "of_01k2m3n4p5q6r7s8t9v0w1x2a2",
    });
    await api.intakeAuthorize("pi_01k2m3n4p5q6r7s8t9v0w1x2y3");
    expect(String(fetchImpl.mock.calls[0]?.[0])).toContain("/intake/intents/");
    expect(String(fetchImpl.mock.calls[0]?.[0])).toContain("/confirm");
    expect(String(fetchImpl.mock.calls[3]?.[0])).toContain("/transaction-authorizations");
  });

  it("remembers competition intent ids without Google tokens", () => {
    const minted = opaqueId("pi_");
    rememberCompetitionIntent(minted);
    rememberSnapshot(snapshot({ intentId: minted }));
    expect(isCompetitionIntent(minted)).toBe(true);
    expect(isCompetitionIntent("pi_01k2m3n4p5q6r7s8t9v0w1x2y3")).toBe(false);
    const stored = sessionStorage.getItem("itaa.compg102.intents");
    expect(stored).toContain(minted);
    expect(stored).not.toMatch(/ya29\.|google|oauth|access_token/i);
  });
});
