import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ClosedApiError } from "../api/errors.js";
import { LOCKED_OFFER_IDS, LOCKED_SUPPLIER_TOKENS } from "../fixtures/golden.js";
import { peekIdempotencyKey } from "../session/memory.js";
import { mockApi, rankedSnapshot, snapshot } from "../test/fixtures.js";
import { IntentWorkspace } from "./IntentWorkspace.js";

function renderWorkspace(api = mockApi(), path = "/intents/pi_01k2m3n4p5q6r7s8t9v0w1x2y3") {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/intents/:intentId" element={<IntentWorkspace api={api} />} />
        <Route
          path="/intents/:intentId/confirmation"
          element={<IntentWorkspace api={api} confirmationRoute />}
        />
        <Route path="/" element={<p>Inbox</p>} />
      </Routes>
    </MemoryRouter>,
  );
}

afterEach(() => {
  cleanup();
});

describe("A1-A4 approval boundaries", () => {
  it("requires explicit A1 confirmation and waits for the API", async () => {
    const user = userEvent.setup();
    const confirmRequirement = vi.fn(async () => snapshot({ state: "AWAITING_DISPATCH_APPROVAL" }));
    renderWorkspace(mockApi({ confirmRequirement }));
    const button = await screen.findByRole("button", { name: "Confirm requirement" });
    expect(screen.getByText(/No supplier has been contacted yet/)).toBeInTheDocument();
    await user.click(button);
    await waitFor(() => expect(confirmRequirement).toHaveBeenCalledTimes(1));
    expect(
      await screen.findByRole("button", { name: "Authorize disclosure to 3 suppliers" }),
    ).toBeInTheDocument();
  });

  it("disables A2 while in flight and shows simulation copy", async () => {
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
        approveAndDispatch,
      }),
    );
    const button = await screen.findByRole("button", {
      name: "Authorize disclosure to 3 suppliers",
    });
    expect(screen.getByText(/does not reserve, buy, or charge/i)).toBeInTheDocument();
    fireEvent.click(button);
    fireEvent.click(button);
    await waitFor(() => expect(approveAndDispatch).toHaveBeenCalledTimes(1));
    expect(screen.getByRole("button", { name: /Authorize disclosure/ })).toHaveAttribute(
      "aria-busy",
      "true",
    );
    release(rankedSnapshot());
    expect(await screen.findByText("Why this is recommended")).toBeInTheDocument();
  });

  it("allows selecting a non-recommended offer before A3", async () => {
    const user = userEvent.setup();
    const acceptOffer = vi.fn(async (_intent: string, body: { offerId: string }) =>
      rankedSnapshot({
        state: "ACCEPTANCE_RECORDED",
        acceptance: {
          acceptanceId: "ac_01k2m3n4p5q6r7s8t9v0w1x2d1",
          offerId: body.offerId,
          offerVersion: 1,
          status: "recorded",
        },
      }),
    );
    renderWorkspace(mockApi({ getSnapshot: async () => rankedSnapshot(), acceptOffer }));
    const selectParkDirect = await screen.findAllByRole("button", { name: "Select ParkDirect" });
    await user.click(selectParkDirect[0]!);
    const acceptance = await screen.findByLabelText("Selected offer acceptance");
    expect(acceptance).toHaveTextContent("ParkDirect");
    expect(acceptance).toHaveTextContent("USD 119.00");
    expect(acceptance).toHaveTextContent("None");
    expect(acceptance).not.toHaveTextContent("EV charging");
    expect(acceptance).toHaveTextContent("SIMULATED");
    expect(acceptance).toHaveTextContent("2026-08-21T16:00:00Z");
    await user.click(screen.getByRole("button", { name: "Confirm offer selection" }));
    await waitFor(() =>
      expect(acceptOffer.mock.calls[0]?.[1]).toMatchObject({
        offerId: LOCKED_OFFER_IDS.parkDirect,
      }),
    );
  });

  it("shows the selected snapshot totals on A3 even when they differ from the catalog", async () => {
    renderWorkspace(
      mockApi({
        getSnapshot: async () =>
          rankedSnapshot({
            updatedAt: "2026-08-20T16:00:00Z",
            offers: rankedSnapshot().offers.map((offer) =>
              offer.offerId === LOCKED_OFFER_IDS.skyShield
                ? { ...offer, totalMinor: 545127, version: 2 }
                : offer,
            ),
          }),
      }),
    );
    const acceptance = await screen.findByLabelText("Selected offer acceptance");
    expect(acceptance).toHaveTextContent("SkyShield");
    expect(acceptance).toHaveTextContent("USD 5451.27");
    expect(acceptance).toHaveTextContent("2");
    expect(acceptance).toHaveTextContent("EV charging");
    expect(acceptance).toHaveTextContent("free until 24 hours before arrival");
  });

  it("blocks A3 when the snapshot evaluation time has expired the offer", async () => {
    const acceptOffer = vi.fn();
    renderWorkspace(
      mockApi({
        getSnapshot: async () =>
          rankedSnapshot({
            updatedAt: "2026-08-21T16:00:00Z",
            expiresAt: "2026-08-22T15:00:00Z",
          }),
        acceptOffer,
      }),
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(/validity deadline has passed/i);
    expect(screen.getByRole("button", { name: "Confirm offer selection" })).toBeDisabled();
    expect(acceptOffer).not.toHaveBeenCalled();
  });

  it("offers inbox recovery when every supplier is unavailable", async () => {
    const user = userEvent.setup();
    renderWorkspace(
      mockApi({
        getSnapshot: async () =>
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
    await user.click(screen.getByRole("button", { name: "Return to Intent Inbox" }));
    expect(await screen.findByText("Inbox")).toBeInTheDocument();
  });

  it("reuses one A4 idempotency key and never uses Pay or Book now", async () => {
    const user = userEvent.setup();
    const authorizeTransaction = vi.fn(async () =>
      rankedSnapshot({
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
      }),
    );
    const accepted = rankedSnapshot({
      state: "ACCEPTANCE_RECORDED",
      acceptance: {
        acceptanceId: "ac_01k2m3n4p5q6r7s8t9v0w1x2d1",
        offerId: LOCKED_OFFER_IDS.skyShield,
        offerVersion: 1,
        status: "recorded",
      },
    });
    renderWorkspace(mockApi({ getSnapshot: async () => accepted, authorizeTransaction }));
    expect(screen.queryByRole("button", { name: /Pay|Book now/i })).not.toBeInTheDocument();
    await user.click(
      await screen.findByRole("button", { name: "Authorize simulated reservation" }),
    );
    await waitFor(() => expect(authorizeTransaction).toHaveBeenCalled());
    const [intentArg, bodyArg, keyArg] = authorizeTransaction.mock.calls[0] as unknown as [
      string,
      { idempotencyKey: string; action: string; mode: string },
      string,
    ];
    expect(intentArg).toMatch(/^pi_/);
    expect(keyArg).toMatch(/^ik_/);
    expect(bodyArg).toMatchObject({
      idempotencyKey: keyArg,
      action: "reserve_parking",
      mode: "SIMULATED",
    });
    expect(peekIdempotencyKey("pi_01k2m3n4p5q6r7s8t9v0w1x2y3")).toBe(keyArg);
    expect(await screen.findByText("SIMULATED RECEIPT")).toBeInTheDocument();
    expect(screen.queryByText("rr_01k2m3n4p5q6r7s8t9v0w1x2g1")).not.toBeInTheDocument();
  });

  it("refreshes the snapshot after an ambiguous failure before another action", async () => {
    const getSnapshot = vi
      .fn()
      .mockResolvedValueOnce(snapshot({ state: "AWAITING_REQUIREMENT_CONFIRMATION" }))
      .mockResolvedValue(snapshot({ state: "AWAITING_DISPATCH_APPROVAL" }));
    const confirmRequirement = vi.fn(async () => {
      throw new ClosedApiError({
        status: 500,
        code: "closed",
        field: "internal",
        correlationId: "unavailable",
        retryable: true,
        ambiguous: true,
      });
    });
    const user = userEvent.setup();
    renderWorkspace(mockApi({ getSnapshot, confirmRequirement }));
    await user.click(await screen.findByRole("button", { name: "Confirm requirement" }));
    expect(await screen.findByText(/did not confirm the last action/)).toBeInTheDocument();
    expect(getSnapshot).toHaveBeenCalledTimes(2);
    expect(screen.getByRole("button", { name: "Refresh status" })).toBeInTheDocument();
  });

  it("disables A4 when the accepted offer is missing from the snapshot", async () => {
    renderWorkspace(
      mockApi({
        getSnapshot: async () =>
          rankedSnapshot({
            state: "ACCEPTANCE_RECORDED",
            acceptance: {
              acceptanceId: "ac_01k2m3n4p5q6r7s8t9v0w1x2d1",
              offerId: "of_missing",
              offerVersion: 1,
              status: "recorded",
            },
            offers: [],
          }),
      }),
    );
    expect(await screen.findByText("Selected offer is no longer available")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Authorize simulated reservation" })).toBeDisabled();
  });
});
