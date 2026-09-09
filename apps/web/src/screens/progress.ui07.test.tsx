import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ClosedApiError } from "../api/errors.js";
import type { ProgressEventPayload, ProgressHandlers } from "../api/types.js";
import { LOCKED_SUPPLIER_TOKENS } from "../fixtures/golden.js";
import { mockApi, rankedSnapshot, snapshot } from "../test/fixtures.js";
import { IntentWorkspace } from "./IntentWorkspace.js";

function renderWorkspace(api = mockApi()) {
  return render(
    <MemoryRouter initialEntries={["/intents/pi_01k2m3n4p5q6r7s8t9v0w1x2y3"]}>
      <Routes>
        <Route path="/intents/:intentId" element={<IntentWorkspace api={api} />} />
      </Routes>
    </MemoryRouter>,
  );
}

afterEach(() => {
  cleanup();
});

describe("WP-07 progress UI", () => {
  it("opens the stream before dispatch, isolates lanes, and keeps the snapshot authoritative", async () => {
    const order: string[] = [];
    let send: ((event: ProgressEventPayload) => void) | undefined;
    const subscribeProgress = vi.fn((_intent: string, handlers: ProgressHandlers) => {
      order.push("subscribe");
      send = handlers.onEvent;
      return { close: vi.fn() };
    });
    let release: (value: ReturnType<typeof rankedSnapshot>) => void = () => undefined;
    const approveAndDispatch = vi.fn(
      () =>
        new Promise<ReturnType<typeof rankedSnapshot>>((resolve) => {
          order.push("dispatch");
          release = resolve;
        }),
    );
    renderWorkspace(
      mockApi({
        getSnapshot: async () => snapshot({ state: "AWAITING_DISPATCH_APPROVAL" }),
        subscribeProgress,
        approveAndDispatch,
      }),
    );
    fireEvent.click(
      await screen.findByRole("button", { name: "Authorize disclosure to 3 suppliers" }),
    );
    await waitFor(() => expect(subscribeProgress).toHaveBeenCalledTimes(1));
    expect(order[0]).toBe("subscribe");
    expect(order[1]).toBe("dispatch");
    const closer = subscribeProgress.mock.results[0]?.value as { close: ReturnType<typeof vi.fn> };
    send?.({
      intentId: "pi_01k2m3n4p5q6r7s8t9v0w1x2y3",
      generationId: "pg_01k2m3n4p5q6r7s8t9v0w1x2g1",
      kind: "SUPPLIER_OFFER_RECEIVED",
      sequence: 6,
      occurredAt: "2026-08-20T16:00:00Z",
      simulation: true,
      supplierToken: LOCKED_SUPPLIER_TOKENS.skyShield,
      status: null,
      correlationId: null,
      terminal: false,
    });
    expect(await screen.findByText("SkyShield")).toBeInTheDocument();
    expect(screen.getByText("Offer received")).toBeInTheDocument();
    expect(screen.queryByText("Why this is recommended")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Authorize disclosure/ }));
    expect(approveAndDispatch).toHaveBeenCalledTimes(1);
    release(rankedSnapshot());
    expect(await screen.findByText("Why this is recommended")).toBeInTheDocument();
    expect(screen.getAllByText("USD 148.00").length).toBeGreaterThan(0);
    expect(closer.close).not.toHaveBeenCalled();
  });

  it("falls back to bounded loading when subscribe reports an error path by still awaiting dispatch", async () => {
    const subscribeProgress = vi.fn((_intent: string, handlers: ProgressHandlers) => {
      handlers.onError();
      return { close: vi.fn() };
    });
    let release: (value: ReturnType<typeof rankedSnapshot>) => void = () => undefined;
    const approveAndDispatch = vi.fn(
      () =>
        new Promise<ReturnType<typeof rankedSnapshot>>((resolve) => {
          release = resolve;
        }),
    );
    renderWorkspace(
      mockApi({
        getSnapshot: async () => snapshot({ state: "AWAITING_DISPATCH_APPROVAL" }),
        subscribeProgress,
        approveAndDispatch,
      }),
    );
    fireEvent.click(
      await screen.findByRole("button", { name: "Authorize disclosure to 3 suppliers" }),
    );
    expect(await screen.findByRole("button", { name: /Authorize disclosure/ })).toHaveAttribute(
      "aria-busy",
      "true",
    );
    release(rankedSnapshot());
    expect(await screen.findByText("Why this is recommended")).toBeInTheDocument();
  });

  it("starts a new generation stream on retry and does not pass prior identifiers", async () => {
    const subscribeProgress = vi.fn((_intent: string, handlers: ProgressHandlers) => {
      handlers.onEvent({
        intentId: "pi_01k2m3n4p5q6r7s8t9v0w1x2y3",
        generationId: "pg_01k2m3n4p5q6r7s8t9v0w1x2g1",
        kind: "STREAM_COMPLETED",
        sequence: 2,
        occurredAt: "2026-08-20T16:00:00Z",
        simulation: true,
        supplierToken: null,
        status: "unavailable",
        correlationId: null,
        terminal: true,
      });
      return { close: vi.fn() };
    });
    const approveAndDispatch = vi
      .fn()
      .mockRejectedValueOnce(
        new ClosedApiError({
          status: 500,
          code: "injected_fault",
          field: "internal",
          correlationId: "cr_01k2m3n4p5q6r7s8t9v0w1x2k2",
        }),
      )
      .mockResolvedValueOnce(rankedSnapshot());
    renderWorkspace(
      mockApi({
        getSnapshot: async () => snapshot({ state: "AWAITING_DISPATCH_APPROVAL" }),
        subscribeProgress,
        approveAndDispatch,
      }),
    );
    const buttonName = "Authorize disclosure to 3 suppliers";
    fireEvent.click(await screen.findByRole("button", { name: buttonName }));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    const retry = await screen.findByRole("button", { name: buttonName });
    expect(retry).not.toHaveAttribute("aria-busy", "true");
    fireEvent.click(retry);
    await waitFor(() => expect(subscribeProgress).toHaveBeenCalledTimes(2));
    expect(subscribeProgress.mock.calls[0]?.length).toBe(2);
    expect(subscribeProgress.mock.calls[1]?.length).toBe(2);
    expect(approveAndDispatch).toHaveBeenCalledTimes(2);
    expect(await screen.findByText("Why this is recommended")).toBeInTheDocument();
  });
});
