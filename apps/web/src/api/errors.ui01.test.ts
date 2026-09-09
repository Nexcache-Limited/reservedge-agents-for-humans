import { describe, expect, it } from "vitest";
import {
  buyerMessage,
  ClosedApiError,
  isClosedError,
  isRetryable,
  sanitizeLogValue,
} from "./errors.js";

describe("closed error mapping", () => {
  it("maps known codes and generic failures", () => {
    expect(buyerMessage("unknown_resource", 404)).toContain(
      "not available in this browser session",
    );
    expect(buyerMessage("illegal_state", 409)).toContain("current step");
    expect(buyerMessage("stale_version", 409)).toContain("current version");
    expect(buyerMessage("expired", 422)).toContain("expired");
    expect(buyerMessage("mystery", 500)).toContain("did not confirm");
    expect(buyerMessage("mystery", 400)).toContain("could not be completed");
    expect(buyerMessage("unavailable", 400)).toContain("extraction service is not available");
    expect(isRetryable(500, "injected_fault")).toBe(true);
    const injected = new ClosedApiError({
      status: 500,
      code: "injected_fault",
      field: "internal",
      correlationId: "cr_01k2m3n4p5q6r7s8t9v0w1x2k2",
    });
    expect(injected.retryable).toBe(true);
    expect(injected.ambiguous).toBe(false);
  });

  it("recognizes closed envelopes and redacts identifiers", () => {
    expect(isClosedError({ code: "expired", field: null, correlationId: "cr_1" })).toBe(true);
    expect(isClosedError({ code: "expired" })).toBe(false);
    expect(sanitizeLogValue("approval ap_01k2m3n4p5q6r7s8t9v0w1x2f0")).toBe("approval [redacted]");
    const error = new ClosedApiError({
      status: 0,
      code: "network_failure",
      field: "request",
      correlationId: "unavailable",
    });
    expect(error.retryable).toBe(true);
    expect(error.ambiguous).toBe(true);
  });
});
