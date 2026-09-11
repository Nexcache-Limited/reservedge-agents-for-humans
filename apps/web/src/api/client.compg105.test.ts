import { afterEach, describe, expect, it, vi } from "vitest";
import { AGENT_REQUEST_TIMEOUT_MS, createItaaApi } from "./client.js";
import { API_PREFIX } from "./types.js";

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

describe("COMP-G1-05 intake client", () => {
  it("loads an owned intake snapshot on the cookie-scoped path", async () => {
    const fetchImpl = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      expect(init?.credentials).toBe("same-origin");
      return jsonResponse({
        intentId: "pi_01k2m3n4p5q6r7s8t9v0w1x2y3",
        state: "AWAITING_REQUIREMENT_CONFIRMATION",
        airport: "JFK",
      });
    });
    const api = createItaaApi({ baseUrl: "http://example.test", fetchImpl });
    const owned = await api.getOwnedIntent("pi_01k2m3n4p5q6r7s8t9v0w1x2y3");
    expect(owned).toEqual(
      expect.objectContaining({
        intentId: "pi_01k2m3n4p5q6r7s8t9v0w1x2y3",
        state: "AWAITING_REQUIREMENT_CONFIRMATION",
      }),
    );
    expect(String(fetchImpl.mock.calls[0]?.[0])).toBe(
      `http://example.test${API_PREFIX}/intake/intents/pi_01k2m3n4p5q6r7s8t9v0w1x2y3`,
    );
    expect(JSON.stringify(owned)).not.toMatch(/ap_|ik_|sg_/);
  });

  it("opens the progress stream with reconnect ids and without approval secrets", () => {
    let opened = "";
    class FakeSource {
      onerror: ((event: Event) => void) | null = null;
      constructor(public readonly url: string) {
        opened = url;
      }
      addEventListener() {
        return undefined;
      }
      close() {
        return undefined;
      }
    }
    vi.stubGlobal("EventSource", FakeSource);
    const api = createItaaApi({ baseUrl: "http://itaa.test" });
    const onError = vi.fn();
    const subscription = api.subscribeProgress(
      "pi_01k2m3n4p5q6r7s8t9v0w1x2y3",
      { onEvent: () => undefined, onError },
      { lastEventId: "4", generationId: "pg_01k2m3n4p5q6r7s8t9v0w1x2g1" },
    );
    expect(opened).toBe(
      `http://itaa.test${API_PREFIX}/intents/pi_01k2m3n4p5q6r7s8t9v0w1x2y3/events?generationId=pg_01k2m3n4p5q6r7s8t9v0w1x2g1&lastEventId=4`,
    );
    expect(opened).not.toContain("approvalId");
    expect(opened).not.toContain("idempotency");
    expect(opened).not.toContain("ap_");
    subscription.close();
    expect(onError).not.toHaveBeenCalled();
  });

  it("times out a hung agent session create instead of hanging forever", async () => {
    vi.useFakeTimers();
    const fetchImpl = vi.fn((_input: RequestInfo | URL, init?: RequestInit) => {
      return new Promise<Response>((_resolve, reject) => {
        const signal = init?.signal;
        if (signal) {
          signal.addEventListener("abort", () => {
            reject(new DOMException("Aborted", "AbortError"));
          });
        }
      });
    });
    const api = createItaaApi({ baseUrl: "http://example.test", fetchImpl });
    const pending = api.createAgentSession({ objective: "I'm travelling to Milan from Mumbai" });
    const rejection = expect(pending).rejects.toMatchObject({ code: "timeout", status: 0 });
    await vi.advanceTimersByTimeAsync(AGENT_REQUEST_TIMEOUT_MS);
    await rejection;
    vi.useRealTimers();
  });
});
