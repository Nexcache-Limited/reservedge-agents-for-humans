import { describe, expect, it } from "vitest";
import type { ProgressEventPayload } from "../api/types.js";
import { LOCKED_SUPPLIER_TOKENS } from "../fixtures/golden.js";
import { progressAnnouncement, progressLanes } from "./workspace.js";

function event(
  kind: string,
  supplierToken: string | null,
  status: string | null = null,
  generationId = "pg_01k2m3n4p5q6r7s8t9v0w1x2g1",
): ProgressEventPayload {
  return {
    intentId: "pi_01k2m3n4p5q6r7s8t9v0w1x2y3",
    generationId,
    kind,
    sequence: 1,
    occurredAt: "2026-08-20T16:00:00Z",
    simulation: true,
    supplierToken,
    status,
    correlationId: null,
    terminal: kind === "STREAM_COMPLETED",
  };
}

describe("progress lanes", () => {
  it("keeps three isolated named suppliers without cross-lane details", () => {
    const lanes = progressLanes([
      event("SUPPLIER_OFFER_RECEIVED", LOCKED_SUPPLIER_TOKENS.skyShield),
      event("SUPPLIER_DECLINED", LOCKED_SUPPLIER_TOKENS.parkDirect),
    ]);
    expect(lanes).toHaveLength(3);
    const sky = lanes.find((item) => item.displayName === "SkyShield");
    const park = lanes.find((item) => item.displayName === "ParkDirect");
    const flex = lanes.find((item) => item.displayName === "TerminalFlex");
    expect(sky?.statusLabel).toBe("Offer received");
    expect(park?.statusLabel).toBe("Declined");
    expect(flex?.statusLabel).toBe("Waiting");
    expect(sky?.displayName).not.toContain("ParkDirect");
    expect(progressAnnouncement(event("STREAM_COMPLETED", null, "complete"))).toMatch(
      /authoritative/i,
    );
  });

  it("scopes lanes to the latest generation so a prior unavailable attempt is ignored", () => {
    const lanes = progressLanes([
      event(
        "SUPPLIER_FAILED",
        LOCKED_SUPPLIER_TOKENS.skyShield,
        "closed",
        "pg_aaaaaaaaaaaaaaaaaaaaaaaaaa",
      ),
      event(
        "SUPPLIER_OFFER_RECEIVED",
        LOCKED_SUPPLIER_TOKENS.skyShield,
        null,
        "pg_bbbbbbbbbbbbbbbbbbbbbbbbbb",
      ),
    ]);
    const sky = lanes.find((item) => item.displayName === "SkyShield");
    expect(sky?.statusLabel).toBe("Offer received");
  });
});
