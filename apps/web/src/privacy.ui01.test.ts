import { readFileSync, readdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { opaqueId } from "./api/ids.js";
import { createSeededPurchaseIntent, formatMoney, qualitativeFit } from "./fixtures/golden.js";
import {
  clearIdempotencyKey,
  idempotencyKeyFor,
  peekIdempotencyKey,
  readInbox,
  rememberSnapshot,
  sessionActor,
} from "./session/memory.js";
import { snapshot } from "./test/fixtures.js";

const root = dirname(fileURLToPath(import.meta.url));

function walk(directory: string): string[] {
  return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const path = join(directory, entry.name);
    if (entry.isDirectory()) {
      return walk(path);
    }
    return [path];
  });
}

describe("privacy", () => {
  it("does not persist raw PI or approval commands in session keys", () => {
    rememberSnapshot(snapshot());
    const cards = readInbox();
    expect(cards[0]).toMatchObject({ intentId: snapshot().intentId, airport: "JFK" });
    expect(JSON.stringify(cards)).not.toContain("buyerToken");
    expect(JSON.stringify(cards)).not.toContain("approvedPayloadHash");
    const key = idempotencyKeyFor("pi_01k2m3n4p5q6r7s8t9v0w1x2y3");
    expect(peekIdempotencyKey("pi_01k2m3n4p5q6r7s8t9v0w1x2y3")).toBe(key);
    expect(sessionStorage.getItem("itaa.ui01.inbox") ?? "").not.toContain(key);
  });

  it("keeps seeded PI identifiers opaque and scans source for forbidden leakage patterns", () => {
    const intent = createSeededPurchaseIntent();
    expect(intent.intentId).toMatch(/^pi_/);
    expect(intent.buyerToken).toMatch(/^bs_/);
    const files = walk(root).filter(
      (path) =>
        (path.endsWith(".ts") || path.endsWith(".tsx")) &&
        !path.includes(".test.") &&
        !path.includes("/test/"),
    );
    const failures: string[] = [];
    for (const file of files) {
      const source = readFileSync(file, "utf8");
      if (source.includes("localStorage")) {
        failures.push(`${file} uses localStorage`);
      }
      if (source.includes("dangerouslySetInnerHTML")) {
        failures.push(`${file} injects HTML`);
      }
    }
    expect(failures).toEqual([]);
  });

  it("recovers session actor and inbox from invalid session memory", () => {
    sessionStorage.setItem("itaa.ui01.inbox", "{not-json");
    expect(readInbox()).toEqual([]);
    sessionStorage.setItem("itaa.ui01.inbox", "[]");
    expect(readInbox()).toEqual([]);
    sessionStorage.setItem("itaa.ui01.actor", "{}");
    const actor = sessionActor();
    expect(actor.actorId.startsWith("ar_")).toBe(true);
    expect(actor.ownerId).toBe(actor.actorId);
    expect(opaqueId("ik_")).toMatch(/^ik_[0-9a-hjkmnp-tv-z]{26}$/);
    expect(formatMoney(2900, "USD")).toBe("USD 29.00");
    expect(qualitativeFit(1)).toBe("Strong fit");
    expect(qualitativeFit(2)).toBe("Good fit");
    expect(qualitativeFit(3)).toBe("Fair fit");
    const key = idempotencyKeyFor("pi_retry");
    expect(idempotencyKeyFor("pi_retry")).toBe(key);
    clearIdempotencyKey("pi_retry");
    expect(peekIdempotencyKey("pi_retry")).toBeUndefined();
  });
});
