import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it } from "vitest";
import { ClosedApiError } from "../api/errors.js";
import { App, AppRoutes } from "../App.js";
import { LOCKED_SUPPLIER_TOKENS } from "../fixtures/golden.js";
import { rememberSnapshot } from "../session/memory.js";
import { mockApi, rankedSnapshot, snapshot } from "../test/fixtures.js";

afterEach(() => {
  cleanup();
});

describe("screen inventory and recovery", () => {
  it("boots the browser router shell", async () => {
    render(<App api={mockApi()} />);
    expect(await screen.findByRole("heading", { name: "Bookings" })).toBeInTheDocument();
  });

  it("renders inbox empty and unavailable-backend states", async () => {
    render(
      <MemoryRouter initialEntries={["/"]}>
        <AppRoutes
          api={mockApi({
            readyz: async () => {
              throw new ClosedApiError({
                status: 0,
                code: "network_failure",
                field: "request",
                correlationId: "unavailable",
              });
            },
          })}
        />
      </MemoryRouter>,
    );
    expect(await screen.findByRole("heading", { name: "Bookings" })).toBeInTheDocument();
    expect(screen.getByText(/No intents match this filter|need you/)).toBeInTheDocument();
  });

  it("opens the domain picker for a new intent", async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter initialEntries={["/intents/new"]}>
        <AppRoutes api={mockApi()} />
      </MemoryRouter>,
    );
    expect(
      await screen.findByRole("heading", { name: "What are you planning or trying to get done?" }),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Pk Airport parking" }));
    expect(await screen.findByRole("button", { name: "Send to Reservedge" })).toBeInTheDocument();
    expect(screen.queryByText("Purchase Intent review")).not.toBeInTheDocument();
  });

  it("shows unknown-route and unknown-intent recovery", async () => {
    render(
      <MemoryRouter initialEntries={["/not-a-route"]}>
        <AppRoutes api={mockApi()} />
      </MemoryRouter>,
    );
    expect(
      screen.getByRole("heading", { name: "This page is not part of the demo" }),
    ).toBeInTheDocument();
  });

  it("shows unknown intent when the snapshot is missing", async () => {
    render(
      <MemoryRouter initialEntries={["/intents/pi_01k2m3n4p5q6r7s8t9v0w1x2zz"]}>
        <AppRoutes
          api={mockApi({
            getOwnedIntent: async () => {
              throw new ClosedApiError({
                status: 404,
                code: "unknown_resource",
                field: "intentId",
                correlationId: "cr_01k2m3n4p5q6r7s8t9v0w1x2k2",
              });
            },
          })}
        />
      </MemoryRouter>,
    );
    expect(await screen.findByText("Unknown intent")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Back to intents" }).length).toBeGreaterThan(0);
  });

  it("renders inbox cards from session memory", async () => {
    rememberSnapshot(snapshot());
    render(
      <MemoryRouter initialEntries={["/"]}>
        <AppRoutes api={mockApi()} />
      </MemoryRouter>,
    );
    expect((await screen.findAllByText(/Airport parking · JFK/)).length).toBeGreaterThan(0);
    expect(screen.getAllByText("Needs a detail").length).toBeGreaterThan(0);
  });

  it("renders a completed inbox card and A3 inbox recovery", async () => {
    rememberSnapshot(
      rankedSnapshot({
        state: "TRANSACTION_AUTHORIZED_SIMULATED",
        transaction: {
          authorizationId: "ta_01k2m3n4p5q6r7s8t9v0w1x2e1",
          acceptanceId: "ac_01k2m3n4p5q6r7s8t9v0w1x2d1",
          action: "reserve_parking",
          mode: "SIMULATED",
          amountMinor: 14800,
          currency: "USD",
          resultRef: "rr_01k2m3n4p5q6r7s8t9v0w1x2g1",
        },
      }),
    );
    const user = userEvent.setup();
    render(
      <MemoryRouter initialEntries={["/"]}>
        <AppRoutes api={mockApi()} />
      </MemoryRouter>,
    );
    await user.click(await screen.findByRole("tab", { name: "History" }));
    expect(await screen.findByText("Completed")).toBeInTheDocument();
  });

  it("does not show a simulated receipt on the confirmation route before A4", async () => {
    render(
      <MemoryRouter initialEntries={["/intents/pi_01k2m3n4p5q6r7s8t9v0w1x2y3/confirmation"]}>
        <AppRoutes api={mockApi({ getOwnedIntent: async () => rankedSnapshot() })} />
      </MemoryRouter>,
    );
    expect(await screen.findByText("Why this is recommended")).toBeInTheDocument();
    expect(screen.queryByText("SIMULATED RECEIPT")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Confirm offer selection" })).toBeInTheDocument();
  });

  it("renders supplier failure kinds with text, not color only", async () => {
    render(
      <MemoryRouter initialEntries={["/intents/pi_01k2m3n4p5q6r7s8t9v0w1x2y3"]}>
        <AppRoutes
          api={mockApi({
            getOwnedIntent: async () =>
              rankedSnapshot({
                supplierOutcomes: [
                  { supplierToken: LOCKED_SUPPLIER_TOKENS.skyShield, kind: "OFFER", reason: null },
                  {
                    supplierToken: LOCKED_SUPPLIER_TOKENS.parkDirect,
                    kind: "INVALID",
                    reason: "schema",
                  },
                  {
                    supplierToken: LOCKED_SUPPLIER_TOKENS.terminalFlex,
                    kind: "LATE",
                    reason: null,
                  },
                ],
              }),
          })}
        />
      </MemoryRouter>,
    );
    expect(await screen.findByText("Invalid")).toBeInTheDocument();
    expect(screen.getByText("Late")).toBeInTheDocument();
    expect(screen.getByText("Partial results")).toBeInTheDocument();
  });

  it("shows all-unavailable and receipt restart copy", async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter initialEntries={["/intents/pi_01k2m3n4p5q6r7s8t9v0w1x2y3/confirmation"]}>
        <AppRoutes
          api={mockApi({
            getOwnedIntent: async () =>
              rankedSnapshot({
                state: "TRANSACTION_AUTHORIZED_SIMULATED",
                supplierOutcomes: [
                  {
                    supplierToken: LOCKED_SUPPLIER_TOKENS.skyShield,
                    kind: "FAILED",
                    reason: "closed",
                  },
                  {
                    supplierToken: LOCKED_SUPPLIER_TOKENS.parkDirect,
                    kind: "DECLINED",
                    reason: null,
                  },
                  {
                    supplierToken: LOCKED_SUPPLIER_TOKENS.terminalFlex,
                    kind: "TIMED_OUT",
                    reason: null,
                  },
                ],
                transaction: {
                  authorizationId: "ta_01k2m3n4p5q6r7s8t9v0w1x2e1",
                  acceptanceId: "ac_01k2m3n4p5q6r7s8t9v0w1x2d1",
                  action: "reserve_parking",
                  mode: "SIMULATED",
                  amountMinor: 14800,
                  currency: "USD",
                  resultRef: "rr_01k2m3n4p5q6r7s8t9v0w1x2g1",
                },
              }),
          })}
        />
      </MemoryRouter>,
    );
    expect(await screen.findByText("SIMULATED RECEIPT")).toBeInTheDocument();
    expect(screen.getByText(/keeps requests in this browser session/)).toBeInTheDocument();
    await user.click(
      within(document.querySelector(".re-receipt") as HTMLElement).getByRole("button", {
        name: "Back to intents",
      }),
    );
    expect(
      await screen.findByRole("heading", { name: "What are you planning or trying to get done?" }),
    ).toBeInTheDocument();
  });

  it("blocks A3 on an expired snapshot evaluation clock and offers recovery", async () => {
    render(
      <MemoryRouter initialEntries={["/intents/pi_01k2m3n4p5q6r7s8t9v0w1x2y3"]}>
        <AppRoutes
          api={mockApi({
            getOwnedIntent: async () =>
              rankedSnapshot({
                updatedAt: "2026-08-21T16:00:00Z",
                expiresAt: "2026-08-22T15:00:00Z",
              }),
          })}
        />
      </MemoryRouter>,
    );
    expect(await screen.findByText("Acceptance is blocked")).toBeInTheDocument();
    expect(screen.getAllByText(/validity deadline has passed/).length).toBeGreaterThan(0);
    expect(screen.getByText("Select another offer")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Confirm offer selection" })).toBeDisabled();
  });

  it("does not mount the ITAA composer on the public new-intent route", async () => {
    render(
      <MemoryRouter initialEntries={["/intents/new"]}>
        <AppRoutes api={mockApi()} />
      </MemoryRouter>,
    );
    expect(
      await screen.findByRole("heading", { name: "What are you planning or trying to get done?" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Start seeded demonstration" }),
    ).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Analyse requirement" })).not.toBeInTheDocument();
  });
});
