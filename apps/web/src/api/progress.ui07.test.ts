import { describe, expect, it, vi } from "vitest";
import { openProgressStream } from "./progress.js";

describe("openProgressStream", () => {
  it("falls back when EventSource is unavailable", () => {
    const onError = vi.fn();
    const subscription = openProgressStream({
      baseUrl: "",
      intentId: "pi_01k2m3n4p5q6r7s8t9v0w1x2y3",
      onEvent: () => undefined,
      onError,
      eventSource: 0 as unknown as typeof EventSource,
    });
    expect(onError).toHaveBeenCalledTimes(1);
    subscription.close();
  });

  it("subscribes to closed kinds and parses payloads", () => {
    const listeners = new Map<string, (event: MessageEvent) => void>();
    let opened = "";
    class FakeSource {
      onerror: ((event: Event) => void) | null = null;
      constructor(public readonly url: string) {
        opened = url;
      }
      addEventListener(type: string, handler: EventListener) {
        listeners.set(type, handler as (event: MessageEvent) => void);
      }
      close() {
        listeners.clear();
      }
    }
    const onEvent = vi.fn();
    const subscription = openProgressStream({
      baseUrl: "http://itaa.test",
      intentId: "pi_01k2m3n4p5q6r7s8t9v0w1x2y3",
      lastEventId: "4",
      generationId: "pg_01k2m3n4p5q6r7s8t9v0w1x2g1",
      onEvent,
      onError: () => undefined,
      eventSource: FakeSource as unknown as typeof EventSource,
    });
    expect(opened).toContain("generationId=pg_01k2m3n4p5q6r7s8t9v0w1x2g1");
    expect(opened).toContain("lastEventId=4");
    expect(opened).not.toContain("approvalId");
    expect(opened).not.toContain("idempotency");
    const handler = listeners.get("SUPPLIER_OFFER_RECEIVED");
    expect(handler).toBeTypeOf("function");
    handler?.(
      new MessageEvent("SUPPLIER_OFFER_RECEIVED", {
        data: JSON.stringify({
          intentId: "pi_01k2m3n4p5q6r7s8t9v0w1x2y3",
          generationId: "pg_01k2m3n4p5q6r7s8t9v0w1x2g1",
          kind: "SUPPLIER_OFFER_RECEIVED",
          sequence: 5,
          occurredAt: "2026-08-20T16:00:00Z",
          simulation: true,
          supplierToken: "sp_01k2m3n4p5q6r7s8t9v0w1x2b2",
          status: null,
          correlationId: null,
          terminal: false,
        }),
      }),
    );
    expect(onEvent).toHaveBeenCalledWith(
      expect.objectContaining({
        kind: "SUPPLIER_OFFER_RECEIVED",
        sequence: 5,
        generationId: "pg_01k2m3n4p5q6r7s8t9v0w1x2g1",
      }),
    );
    expect(listeners.size).toBeGreaterThan(0);
    subscription.close();
    expect(listeners.size).toBe(0);
  });

  it("closes EventSource on error so the browser cannot auto-reconnect", () => {
    const instances: Array<{
      onerror: ((event: Event) => void) | null;
      closed: boolean;
    }> = [];
    class FakeSource {
      onerror: ((event: Event) => void) | null = null;
      closed = false;
      constructor(public readonly url: string) {
        instances.push(this);
      }
      addEventListener() {
        return undefined;
      }
      close() {
        this.closed = true;
      }
    }
    const onError = vi.fn();
    openProgressStream({
      baseUrl: "http://itaa.test",
      intentId: "pi_01k2m3n4p5q6r7s8t9v0w1x2y3",
      onEvent: () => undefined,
      onError,
      eventSource: FakeSource as unknown as typeof EventSource,
    });
    expect(instances).toHaveLength(1);
    instances[0]?.onerror?.(new Event("error"));
    expect(instances[0]?.closed).toBe(true);
    expect(onError).toHaveBeenCalledTimes(1);
  });
});
