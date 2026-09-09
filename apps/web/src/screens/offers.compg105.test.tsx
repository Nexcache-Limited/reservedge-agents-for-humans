import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AppRoutes } from "../App.js";
import type { ProgressEventPayload, ProgressHandlers } from "../api/types.js";
import { formatScore, LOCKED_OFFER_IDS, LOCKED_SUPPLIER_TOKENS } from "../fixtures/golden.js";
import { mockApi, rankedSnapshot, snapshot } from "../test/fixtures.js";

afterEach(() => {
  cleanup();
  sessionStorage.clear();
});

function renderApp(path: string, api = mockApi()) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AppRoutes api={api} />
    </MemoryRouter>,
  );
}

function competitionMain(): HTMLElement {
  return screen.getByRole("main");
}

function competitionCopy(): string {
  return competitionMain().textContent ?? "";
}

function assertCompetitionVector(root: HTMLElement = competitionMain()): void {
  const copy = root.textContent ?? "";
  expect(copy).toContain(formatScore(671000));
  expect(copy).toContain("USD 29.00");
  expect(copy).not.toContain("JetPark");
  expect(copy).not.toContain("$71.40");
  expect(copy).not.toMatch(/\bA[1-4]\b/);
  expect(copy).not.toMatch(/\bGate\b/);
}

describe("COMP-G1-05 Phase 4 competition offers", () => {
  it("presents the disclosure gate from the owned awaiting-dispatch snapshot", async () => {
    renderApp(
      "/intents/pi_01k2m3n4p5q6r7s8t9v0w1x2y3",
      mockApi({
        getOwnedIntent: async () => snapshot({ state: "AWAITING_DISPATCH_APPROVAL" }),
      }),
    );
    expect(await screen.findByText("What suppliers will see")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Send this request" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Not now — keep pending" })).toBeInTheDocument();
    expect(screen.getByText(/ParkDirect, SkyShield, and TerminalFlex/)).toBeInTheDocument();
    const copy = competitionCopy();
    expect(copy).not.toMatch(/\bGate\b/);
    expect(copy).not.toContain("JetPark");
    expect(copy).not.toContain("$71.40");
  });

  it("renders the locked JFK ranking snapshot, not prototype JetPark values", async () => {
    renderApp(
      "/intents/pi_01k2m3n4p5q6r7s8t9v0w1x2y3",
      mockApi({ getOwnedIntent: async () => rankedSnapshot() }),
    );
    expect(await within(competitionMain()).findAllByText("SkyShield")).not.toHaveLength(0);
    assertCompetitionVector();
    expect(screen.getByRole("button", { name: "Take this one" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Compare all three" })).toBeInTheDocument();
    expect(screen.getByText("Why this is recommended")).toBeInTheDocument();
    expect(screen.getByText("Confirm selected offer")).toBeInTheDocument();
    expect(
      screen.getByText("If all-in price were the only factor, ParkDirect would rank ahead."),
    ).toBeInTheDocument();
    expect(
      screen.queryByText("If all-in price were the only factor, SkyShield would rank ahead."),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByText("Stated coverage and shuttle fit the request."),
    ).not.toBeInTheDocument();
  });

  it("compares all three snapshot offers without inventing ranking values", async () => {
    const user = userEvent.setup();
    renderApp(
      "/intents/pi_01k2m3n4p5q6r7s8t9v0w1x2y3",
      mockApi({ getOwnedIntent: async () => rankedSnapshot() }),
    );
    await user.click(await screen.findByRole("button", { name: "Compare all three" }));
    expect(screen.getByRole("table", { name: "Offer comparison" })).toBeInTheDocument();
    const copy = competitionCopy();
    expect(copy).toContain(formatScore(660000));
    expect(copy).toContain(formatScore(535000));
    expect(within(competitionMain()).getAllByText("ParkDirect").length).toBeGreaterThan(0);
    expect(within(competitionMain()).getAllByText("TerminalFlex").length).toBeGreaterThan(0);
    expect(copy).toContain("USD 148.00");
    expect(copy).not.toContain("JetPark");
    expect(copy).not.toContain("$71.40");
  });

  it("walks confirm, disclosure, recommendation, authorization, and simulated receipt", async () => {
    const user = userEvent.setup();
    let current = snapshot();
    const intakeConfirm = vi.fn(async () => {
      current = snapshot({ state: "AWAITING_DISPATCH_APPROVAL" });
      return current;
    });
    const intakeDispatch = vi.fn(async () => {
      current = rankedSnapshot();
      return current;
    });
    const intakeAccept = vi.fn(async () => {
      current = rankedSnapshot({
        state: "ACCEPTANCE_RECORDED",
        acceptance: {
          acceptanceId: "ac_01k2m3n4p5q6r7s8t9v0w1x2d1",
          offerId: LOCKED_OFFER_IDS.skyShield,
          offerVersion: 1,
          status: "recorded",
        },
      });
      return current;
    });
    const intakeAuthorize = vi.fn(async () => {
      current = rankedSnapshot({
        state: "TRANSACTION_AUTHORIZED_SIMULATED",
        acceptance: {
          acceptanceId: "ac_01k2m3n4p5q6r7s8t9v0w1x2d1",
          offerId: LOCKED_OFFER_IDS.skyShield,
          offerVersion: 1,
          status: "recorded",
        },
        transaction: {
          authorizationId: "ta_01k2m3n4p5q6r7s8t9v0w1x2e1",
          acceptanceId: "ac_01k2m3n4p5q6r7s8t9v0w1x2d1",
          action: "reserve_parking",
          mode: "SIMULATED",
          amountMinor: 14800,
          currency: "USD",
          resultRef: "rr_01k2m3n4p5q6r7s8t9v0w1x2g1",
        },
      });
      return current;
    });
    renderApp(
      "/intents/pi_01k2m3n4p5q6r7s8t9v0w1x2y3",
      mockApi({
        getOwnedIntent: async () => current,
        intakeConfirm,
        intakeDispatch,
        intakeAccept,
        intakeAuthorize,
      }),
    );
    await user.click(await screen.findByRole("button", { name: "Confirm requirement" }));
    await waitFor(() => expect(intakeConfirm).toHaveBeenCalledTimes(1));
    expect(await screen.findByRole("button", { name: "Send this request" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Send this request" }));
    await waitFor(() => expect(intakeDispatch).toHaveBeenCalledTimes(1));
    await user.click(await screen.findByRole("button", { name: "See the recommendation" }));
    assertCompetitionVector();
    await user.click(screen.getByRole("button", { name: "Take this one" }));
    await waitFor(() => expect(intakeAccept).toHaveBeenCalledTimes(1));
    expect(intakeAccept).toHaveBeenCalledWith("pi_01k2m3n4p5q6r7s8t9v0w1x2y3", {
      offerId: LOCKED_OFFER_IDS.skyShield,
      offerVersion: 1,
    });
    expect(
      await screen.findByRole("dialog", { name: "Authorize this purchase" }),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Authorize USD 148.00" }));
    await waitFor(() => expect(intakeAuthorize).toHaveBeenCalledTimes(1));
    await waitFor(
      () => {
        expect(screen.getByText("SIMULATED RECEIPT")).toBeInTheDocument();
      },
      { timeout: 10_000 },
    );
    expect(screen.getByText(/keeps requests in this browser session/)).toBeInTheDocument();
    expect(competitionCopy()).not.toContain("JetPark");
    expect(competitionCopy()).not.toContain("$71.40");
  });

  it("shows isolated supplier progress before the ranking snapshot is applied", async () => {
    const user = userEvent.setup();
    let send: ((event: ProgressEventPayload) => void) | undefined;
    const subscribeProgress = vi.fn((_intent: string, handlers: ProgressHandlers) => {
      send = handlers.onEvent;
      return { close: vi.fn() };
    });
    let release: (value: ReturnType<typeof rankedSnapshot>) => void = () => undefined;
    const intakeDispatch = vi.fn(
      () =>
        new Promise<ReturnType<typeof rankedSnapshot>>((resolve) => {
          release = resolve;
        }),
    );
    renderApp(
      "/intents/pi_01k2m3n4p5q6r7s8t9v0w1x2y3",
      mockApi({
        getOwnedIntent: async () => snapshot({ state: "AWAITING_DISPATCH_APPROVAL" }),
        subscribeProgress,
        intakeDispatch,
      }),
    );
    await user.click(await screen.findByRole("button", { name: "Send this request" }));
    await waitFor(() => expect(subscribeProgress).toHaveBeenCalledTimes(1));
    send?.({
      intentId: "pi_01k2m3n4p5q6r7s8t9v0w1x2y3",
      generationId: "pg_01k2m3n4p5q6r7s8t9v0w1x2g1",
      kind: "SUPPLIER_OFFER_RECEIVED",
      sequence: 1,
      occurredAt: "2026-08-20T16:00:00Z",
      simulation: true,
      supplierToken: LOCKED_SUPPLIER_TOKENS.skyShield,
      status: null,
      correlationId: null,
      terminal: false,
    });
    expect(await screen.findByText("Suppliers are answering")).toBeInTheDocument();
    expect(screen.getByText("SkyShield")).toBeInTheDocument();
    expect(screen.getByText("Offer received")).toBeInTheDocument();
    expect(screen.queryByText("JetPark")).not.toBeInTheDocument();
    expect(screen.queryByText("Why this is recommended")).not.toBeInTheDocument();
    release(rankedSnapshot());
    expect(await screen.findByText("Suppliers answered")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "See the recommendation" }));
    expect(await screen.findByText("Why this is recommended")).toBeInTheDocument();
  });

  it("keeps pending from the disclosure step and opens the disclosure record after ranking", async () => {
    const user = userEvent.setup();
    const saveIntent = vi.fn(async () =>
      snapshot({
        state: "AWAITING_DISPATCH_APPROVAL",
        saved: true,
        savedAt: "2026-08-20T16:00:00Z",
      }),
    );
    renderApp(
      "/intents/pi_01k2m3n4p5q6r7s8t9v0w1x2y3",
      mockApi({
        getOwnedIntent: async () => snapshot({ state: "AWAITING_DISPATCH_APPROVAL" }),
        saveIntent,
      }),
    );
    await user.click(await screen.findByRole("button", { name: "Not now — keep pending" }));
    await waitFor(() => expect(saveIntent).toHaveBeenCalledTimes(1));

    cleanup();
    renderApp(
      "/intents/pi_01k2m3n4p5q6r7s8t9v0w1x2y3",
      mockApi({ getOwnedIntent: async () => rankedSnapshot() }),
    );
    await user.click(await screen.findByRole("tab", { name: "Disclosure record" }));
    expect(screen.getByText("What was sent, and what was not")).toBeInTheDocument();
    expect(competitionCopy()).not.toContain("JetPark");
    await user.click(screen.getByRole("tab", { name: "Research" }));
    expect(screen.getByText("PUBLIC RESEARCH · AUTONOMOUS")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Continue to the offers tab" }));
    expect(await screen.findByText("Why this is recommended")).toBeInTheDocument();
  });

  it("opens authorization from an accepted offer and shows all-unavailable copy when ranking is empty", async () => {
    const user = userEvent.setup();
    renderApp(
      "/intents/pi_01k2m3n4p5q6r7s8t9v0w1x2y3",
      mockApi({
        getOwnedIntent: async () =>
          rankedSnapshot({
            state: "ACCEPTANCE_RECORDED",
            acceptance: {
              acceptanceId: "ac_01k2m3n4p5q6r7s8t9v0w1x2d1",
              offerId: LOCKED_OFFER_IDS.skyShield,
              offerVersion: 1,
              status: "recorded",
            },
          }),
      }),
    );
    await user.click(await screen.findByRole("button", { name: "Continue to authorization" }));
    expect(screen.getByRole("dialog", { name: "Authorize this purchase" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Not now" }));
    expect(screen.queryByRole("dialog", { name: "Authorize this purchase" })).toBeNull();
    await user.click(screen.getByRole("button", { name: "Take this one" }));
    expect(screen.getByRole("dialog", { name: "Authorize this purchase" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Not now" }));

    cleanup();
    renderApp(
      "/intents/pi_01k2m3n4p5q6r7s8t9v0w1x2y3",
      mockApi({
        getOwnedIntent: async () =>
          rankedSnapshot({
            offers: [],
            recommendedOfferId: null,
            supplierOutcomes: [
              { supplierToken: LOCKED_SUPPLIER_TOKENS.skyShield, kind: "FAILED", reason: "closed" },
              { supplierToken: LOCKED_SUPPLIER_TOKENS.parkDirect, kind: "DECLINED", reason: null },
              {
                supplierToken: LOCKED_SUPPLIER_TOKENS.terminalFlex,
                kind: "TIMED_OUT",
                reason: null,
              },
            ],
          }),
      }),
    );
    expect(await screen.findByText("All suppliers unavailable")).toBeInTheDocument();
    expect(screen.getByText("No reliable recommendation is available.")).toBeInTheDocument();
  });

  it("defines portal accent tokens outside .re-app so the authorize CTA is not white-on-white", () => {
    const css = readFileSync(
      join(dirname(fileURLToPath(import.meta.url)), "../styles.css"),
      "utf8",
    );
    expect(css).toMatch(/:root\s*\{[^}]*--ws-accent:\s*#e85d2c/s);
    expect(css).toMatch(/\.re-overlay\s*\{[^}]*--ws-accent:\s*#e85d2c/s);
  });
});
