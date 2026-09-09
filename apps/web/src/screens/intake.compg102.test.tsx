import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AppRoutes } from "../App.js";
import { ClosedApiError } from "../api/errors.js";
import * as ids from "../api/ids.js";
import { PortfolioLayout } from "../components/AppShell.js";
import { SAMPLE_JFK_TEXT, NewIntentScreen } from "./NewIntentScreen.js";
import { IntentWorkspace } from "./IntentWorkspace.js";
import { rememberCompetitionIntent } from "../session/memory.js";
import { intakeExtraction, mockApi, rankedSnapshot, snapshot } from "../test/fixtures.js";

afterEach(() => {
  cleanup();
  sessionStorage.clear();
  vi.restoreAllMocks();
});

function renderNew(api = mockApi()) {
  return render(
    <MemoryRouter initialEntries={["/intents/new"]}>
      <Routes>
        <Route element={<PortfolioLayout api={api} />}>
          <Route path="/intents/new" element={<NewIntentScreen api={api} />} />
          <Route path="/intents/:intentId" element={<IntentWorkspace api={api} />} />
          <Route
            path="/intents/:intentId/confirmation"
            element={<IntentWorkspace api={api} confirmationRoute />}
          />
        </Route>
      </Routes>
    </MemoryRouter>,
  );
}

describe("competition intake screens", () => {
  it("walks the NL happy path to the workspace", async () => {
    const user = userEvent.setup();
    const extractIntake = vi.fn(async () => intakeExtraction());
    const confirmIntakeIntent = vi.fn(async () => snapshot());
    renderNew(mockApi({ extractIntake, confirmIntakeIntent, getSnapshot: async () => snapshot() }));
    await user.click(screen.getByRole("button", { name: "Use sample JFK text" }));
    expect(screen.getByLabelText("Parking requirement")).toHaveValue(SAMPLE_JFK_TEXT);
    await user.click(screen.getByRole("button", { name: "Analyse requirement" }));
    expect(await screen.findByText("Confirm extracted fields")).toBeInTheDocument();
    expect(screen.getByText(/Evidence and confidence/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Confirm parking requirement" }));
    await waitFor(() => expect(confirmIntakeIntent).toHaveBeenCalled());
    expect(confirmIntakeIntent).toHaveBeenCalledWith(
      expect.objectContaining({
        airportCode: "JFK",
        vehicleClass: "standard",
        covered: "preferred",
        shuttleMaxMinutes: 20,
        currency: "USD",
      }),
    );
    expect(JSON.stringify(confirmIntakeIntent.mock.calls)).not.toMatch(/"text"/);
    expect(await screen.findByText("Purchase Intent review")).toBeInTheDocument();
  });

  it("shows missing, ambiguous, failure, and retry states", async () => {
    const user = userEvent.setup();
    const extractIntake = vi
      .fn()
      .mockRejectedValueOnce(
        new ClosedApiError({
          status: 500,
          code: "unavailable",
          field: "model",
          correlationId: "cr_01k2m3n4p5q6r7s8t9v0w1x2k2",
        }),
      )
      .mockResolvedValueOnce(
        intakeExtraction({
          missingFields: ["serviceWindow.end"],
          proposal: {
            location: { airportCode: "JFK" },
            serviceWindow: { start: "2026-09-03T13:00:00Z", end: null },
            requirements: { vehicleClass: "standard", covered: "preferred", shuttleMaxMinutes: 20 },
            constraints: { currency: "USD", accessibility: ["ev_charging"] },
          },
        }),
      )
      .mockResolvedValueOnce(
        intakeExtraction({
          ambiguousFields: ["location.airportCode"],
          proposal: {
            location: { airportCode: null },
            serviceWindow: { start: "2026-09-03T13:00:00Z", end: "2026-09-08T22:00:00Z" },
            requirements: { vehicleClass: "standard", covered: "preferred", shuttleMaxMinutes: 20 },
            constraints: { currency: "USD", accessibility: ["ev_charging"] },
          },
        }),
      );
    renderNew(mockApi({ extractIntake }));
    await user.type(screen.getByLabelText("Parking requirement"), "need airport parking");
    await user.click(screen.getByRole("button", { name: "Analyse requirement" }));
    expect(await screen.findByText("Extraction failed")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByRole("heading", { name: "Missing information" })).toBeInTheDocument();
    expect(screen.getByText("serviceWindow.end")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Analyse requirement" }));
    expect(
      await screen.findByRole("heading", { name: "Ambiguous information" }),
    ).toBeInTheDocument();
    expect(screen.getAllByText("location.airportCode").length).toBeGreaterThan(0);
    expect(extractIntake).toHaveBeenCalledTimes(3);
  });

  it("declines confirmation without creating an intent", async () => {
    const user = userEvent.setup();
    const confirmIntakeIntent = vi.fn();
    renderNew(mockApi({ confirmIntakeIntent }));
    await user.click(screen.getByRole("button", { name: "Use sample JFK text" }));
    await user.click(screen.getByRole("button", { name: "Analyse requirement" }));
    expect(await screen.findByText("Confirm extracted fields")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Decline confirmation" }));
    expect(confirmIntakeIntent).not.toHaveBeenCalled();
    expect(screen.queryByText("Confirm extracted fields")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Parking requirement")).toHaveValue(SAMPLE_JFK_TEXT);
  });

  it("uses the buyer-corrected airport instead of the raw proposal", async () => {
    const user = userEvent.setup();
    const confirmIntakeIntent = vi.fn(async () => snapshot({ airport: "LAX" }));
    renderNew(
      mockApi({
        extractIntake: async () =>
          intakeExtraction({
            proposal: {
              location: { airportCode: "EWR" },
              serviceWindow: { start: "2026-09-03T13:00:00Z", end: "2026-09-08T22:00:00Z" },
              requirements: {
                vehicleClass: "standard",
                covered: "preferred",
                shuttleMaxMinutes: 20,
              },
              constraints: { currency: "USD", accessibility: ["ev_charging"] },
            },
          }),
        confirmIntakeIntent,
        getSnapshot: async () => snapshot({ airport: "LAX" }),
      }),
    );
    await user.click(screen.getByRole("button", { name: "Use sample JFK text" }));
    await user.click(screen.getByRole("button", { name: "Analyse requirement" }));
    const airport = await screen.findByLabelText("Airport");
    await user.clear(airport);
    await user.type(airport, "LAX");
    await user.click(screen.getByRole("button", { name: "Confirm parking requirement" }));
    await waitFor(() => expect(confirmIntakeIntent).toHaveBeenCalled());
    expect(confirmIntakeIntent).toHaveBeenCalledWith(
      expect.objectContaining({ airportCode: "LAX" }),
    );
  });

  it("does not call opaqueId or governanceIds on the competition path", async () => {
    const user = userEvent.setup();
    const opaque = vi.spyOn(ids, "opaqueId");
    const governance = vi.spyOn(ids, "governanceIds");
    const confirmRequirement = vi.fn();
    const approveAndDispatch = vi.fn();
    const acceptOffer = vi.fn();
    const authorizeTransaction = vi.fn();
    const intakeConfirm = vi.fn(async () => snapshot({ state: "AWAITING_DISPATCH_APPROVAL" }));
    const intakeDispatch = vi.fn(async () => rankedSnapshot());
    render(
      <MemoryRouter initialEntries={["/intents/new/parking"]}>
        <AppRoutes
          api={mockApi({
            confirmRequirement,
            approveAndDispatch,
            acceptOffer,
            authorizeTransaction,
            intakeConfirm,
            intakeDispatch,
            confirmIntakeIntent: async () => snapshot(),
            getOwnedIntent: async () => snapshot(),
          })}
        />
      </MemoryRouter>,
    );
    opaque.mockClear();
    governance.mockClear();
    await user.click(await screen.findByRole("button", { name: /Use the example/ }));
    await user.click(screen.getByRole("button", { name: "Send to Reservedge" }));
    await user.click(
      await screen.findByRole("button", { name: "Confirm requirement and research" }),
    );
    expect(
      await screen.findByRole("button", { name: /^Confirm requirement$/ }),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /^Confirm requirement$/ }));
    await waitFor(() => expect(intakeConfirm).toHaveBeenCalledTimes(1));
    expect(confirmRequirement).not.toHaveBeenCalled();
    expect(governance).not.toHaveBeenCalled();
    expect(opaque).not.toHaveBeenCalled();
  });

  it("declines A2 on a competition workspace without dispatching", async () => {
    const user = userEvent.setup();
    rememberCompetitionIntent("pi_01k2m3n4p5q6r7s8t9v0w1x2y3");
    const intakeDispatch = vi.fn();
    const approveAndDispatch = vi.fn();
    render(
      <MemoryRouter initialEntries={["/intents/pi_01k2m3n4p5q6r7s8t9v0w1x2y3"]}>
        <Routes>
          <Route
            path="/intents/:intentId"
            element={
              <IntentWorkspace
                api={mockApi({
                  getOwnedIntent: async () => snapshot({ state: "AWAITING_DISPATCH_APPROVAL" }),
                  getSnapshot: async () => snapshot({ state: "AWAITING_DISPATCH_APPROVAL" }),
                  intakeDispatch,
                  approveAndDispatch,
                })}
              />
            }
          />
          <Route path="/" element={<p>Inbox</p>} />
        </Routes>
      </MemoryRouter>,
    );
    await user.click(await screen.findByRole("button", { name: "Decline disclosure" }));
    expect(await screen.findByText("Inbox")).toBeInTheDocument();
    expect(intakeDispatch).not.toHaveBeenCalled();
    expect(approveAndDispatch).not.toHaveBeenCalled();
  });

  it("does not analyse an empty requirement", async () => {
    const extractIntake = vi.fn();
    renderNew(mockApi({ extractIntake }));
    await userEvent.setup().click(screen.getByRole("button", { name: "Analyse requirement" }));
    expect(extractIntake).not.toHaveBeenCalled();
  });

  it("declines extracted confirmation and returns to compose", async () => {
    const user = userEvent.setup();
    const confirmIntakeIntent = vi.fn();
    renderNew(mockApi({ extractIntake: async () => intakeExtraction(), confirmIntakeIntent }));
    await user.click(screen.getByRole("button", { name: "Use sample JFK text" }));
    await user.click(screen.getByRole("button", { name: "Analyse requirement" }));
    await user.click(await screen.findByRole("button", { name: "Decline confirmation" }));
    expect(screen.getByLabelText("Parking requirement")).toBeInTheDocument();
    expect(confirmIntakeIntent).not.toHaveBeenCalled();
  });

  it("blocks confirm until required fields are complete and toggles accessibility", async () => {
    const user = userEvent.setup();
    const confirmIntakeIntent = vi.fn();
    renderNew(mockApi({ extractIntake: async () => intakeExtraction(), confirmIntakeIntent }));
    await user.click(screen.getByRole("button", { name: "Use sample JFK text" }));
    await user.click(screen.getByRole("button", { name: "Analyse requirement" }));
    const airport = await screen.findByLabelText("Airport");
    await user.clear(airport);
    expect(screen.getByRole("button", { name: "Confirm parking requirement" })).toBeDisabled();
    await user.type(airport, "JFK");
    await user.selectOptions(screen.getByLabelText("Vehicle class"), "standard");
    await user.selectOptions(screen.getByLabelText("Covered"), "preferred");
    const ev = screen.getByRole("checkbox", { name: "ev_charging" });
    await user.click(ev);
    await user.click(ev);
    await user.click(screen.getByRole("button", { name: "Confirm parking requirement" }));
    await waitFor(() => expect(confirmIntakeIntent).toHaveBeenCalled());
  });

  it("keeps the seeded demonstration button and flow", async () => {
    const user = userEvent.setup();
    const createIntent = vi.fn(async () => snapshot());
    renderNew(mockApi({ createIntent, getSnapshot: async () => snapshot() }));
    expect(screen.getByRole("button", { name: "Start seeded demonstration" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Start seeded demonstration" }));
    await waitFor(() => expect(createIntent).toHaveBeenCalled());
    expect(await screen.findByText("Purchase Intent review")).toBeInTheDocument();
  });

  it("supports keyboard entry at a 320-wide compose surface", async () => {
    const user = userEvent.setup();
    const extractIntake = vi.fn(async () => intakeExtraction());
    renderNew(mockApi({ extractIntake }));
    const shell = document.querySelector(".itaa-app");
    if (shell instanceof HTMLElement) {
      shell.style.width = "320px";
    }
    const box = screen.getByLabelText("Parking requirement");
    box.focus();
    expect(box).toHaveFocus();
    await user.keyboard("need parking at JFK");
    expect(box).toHaveValue("need parking at JFK");
    await user.tab();
    await user.tab();
    await user.keyboard("{Enter}");
    await waitFor(() => expect(extractIntake).toHaveBeenCalled());
  });
});
