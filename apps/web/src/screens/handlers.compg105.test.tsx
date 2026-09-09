import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AppRoutes } from "../App.js";
import { ClosedApiError } from "../api/errors.js";
import type { ProgressEventPayload, ProgressHandlers } from "../api/types.js";
import { LOCKED_OFFER_IDS, LOCKED_SUPPLIER_TOKENS } from "../fixtures/golden.js";
import { rememberSnapshot } from "../session/memory.js";
import { intakeExtraction, mockApi, rankedSnapshot, snapshot } from "../test/fixtures.js";

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

function headerNewIntent(): HTMLElement {
  return document.querySelector(".re-new:not(.re-new-empty)") as HTMLElement;
}

function mobileNewIntent(): HTMLElement {
  return document.querySelector(".re-new-mobile") as HTMLElement;
}

describe("COMP-G1-05 inbox, routing, and recovery handlers", () => {
  it("opens the domain picker from the inbox header, empty filter, and mobile new-intent actions", async () => {
    const user = userEvent.setup();
    renderApp("/");
    await screen.findByRole("heading", { name: "Bookings" });
    await user.click(headerNewIntent());
    expect(
      await screen.findByRole("heading", { name: "What are you planning or trying to get done?" }),
    ).toBeInTheDocument();
    expect(screen.queryByText("Analyse requirement")).not.toBeInTheDocument();

    cleanup();
    renderApp("/");
    await screen.findByRole("heading", { name: "Bookings" });
    await user.click(screen.getByRole("tab", { name: "Running" }));
    await user.click(screen.getByRole("button", { name: "Delete LGA parking · Oct 2–4" }));
    expect(screen.getByText("Nothing here.")).toBeInTheDocument();
    await user.click(document.querySelector(".re-new-empty") as HTMLElement);
    expect(
      await screen.findByRole("heading", { name: "What are you planning or trying to get done?" }),
    ).toBeInTheDocument();

    cleanup();
    renderApp("/");
    await screen.findByRole("heading", {
      name: "What are you planning or trying to get done?",
    });
    await user.click(mobileNewIntent());
    expect(
      await screen.findByRole("heading", { name: "What are you planning or trying to get done?" }),
    ).toBeInTheDocument();
  });

  it("falls back to the remembered session inbox when listIntents fails", async () => {
    rememberSnapshot(snapshot());
    renderApp(
      "/",
      mockApi({
        listIntents: async () => {
          throw new ClosedApiError({
            status: 500,
            code: "unavailable",
            field: "request",
            correlationId: "cr_01k2m3n4p5q6r7s8t9v0w1x2k2",
          });
        },
      }),
    );
    expect(
      await screen.findByRole("button", { name: /Needs a confirmation before research/ }),
    ).toBeInTheDocument();
    expect(document.querySelector("[data-source='seed']")).not.toBeNull();
    expect(screen.queryByText("JetPark JFK")).not.toBeInTheDocument();
  });

  it("returns unknown routes to Intents without creating a request", async () => {
    const user = userEvent.setup();
    renderApp("/no-such-route");
    expect(
      await screen.findByRole("heading", { name: "This page is not part of the demo" }),
    ).toBeInTheDocument();
    expect(screen.getByText(/Unknown routes do not create intents/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Return to Intents" }));
    expect(
      await screen.findByRole("heading", {
        name: "What are you planning or trying to get done?",
      }),
    ).toBeInTheDocument();
  });

  it("sends an unknown live intent back to the inbox and announces the miss", async () => {
    const user = userEvent.setup();
    renderApp(
      "/intents/pi_01k2m3n4p5q6r7s8t9v0w1x2y3",
      mockApi({
        getOwnedIntent: async () => {
          throw new ClosedApiError({
            status: 404,
            code: "unknown_resource",
            field: "intentId",
            correlationId: "cr_01k2m3n4p5q6r7s8t9v0w1x2k2",
          });
        },
      }),
    );
    expect(await screen.findByRole("heading", { name: "Unknown intent" })).toBeInTheDocument();
    expect(
      screen.getAllByText("This request is not available in this browser session.").length,
    ).toBeGreaterThan(0);
    expect(document.querySelector(".itaa-live-region")).toHaveTextContent(
      "This request is not available in this browser session.",
    );
    await user.click(document.querySelector(".re-card .re-primary") as HTMLElement);
    expect(
      await screen.findByRole("heading", {
        name: "What are you planning or trying to get done?",
      }),
    ).toBeInTheDocument();
  });

  it("uses the mobile back control to leave a global view", async () => {
    const user = userEvent.setup();
    renderApp("/activity");
    expect(await screen.findByRole("heading", { name: "Activity" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Back to intents" }));
    expect(await screen.findByRole("heading", { name: "Bookings" })).toBeInTheDocument();
  });

  it("opens a seed intent on the mobile route when the viewport is narrow", async () => {
    const user = userEvent.setup();
    const matchMedia = window.matchMedia;
    window.matchMedia = ((query: string) => ({
      matches: query.includes("max-width: 1179px"),
      media: query,
      onchange: null,
      addListener: () => undefined,
      removeListener: () => undefined,
      addEventListener: () => undefined,
      removeEventListener: () => undefined,
      dispatchEvent: () => false,
    })) as typeof window.matchMedia;
    try {
      renderApp("/");
      await user.click(await screen.findByRole("button", { name: /recommended \$71\.40/ }));
      expect(await screen.findByText("JetPark JFK")).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Back to intents" })).toBeInTheDocument();
      await user.click(screen.getByRole("button", { name: "Back to intents" }));
      expect(await screen.findByRole("heading", { name: "Bookings" })).toBeInTheDocument();
    } finally {
      window.matchMedia = matchMedia;
    }
  });
});

describe("COMP-G1-05 composer typed, skip, correction, and confirm handlers", () => {
  it("accepts a typed own answer on Enter and skips an optional rental question", async () => {
    const user = userEvent.setup();
    renderApp("/intents/new/rental");
    await user.click(await screen.findByRole("button", { name: /Use the example/ }));
    await user.click(screen.getByRole("button", { name: "Send to Reservedge" }));
    expect(screen.getByText(/QUESTION 1 OF 3/)).toBeInTheDocument();
    await user.type(screen.getByLabelText("Your own answer"), "Match the inbound flight{enter}");
    expect(screen.getByText("Match the inbound flight")).toBeInTheDocument();
    expect(screen.getByText(/QUESTION 2 OF 3/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Skip this" }));
    expect(screen.getByText(/QUESTION 3 OF 3/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Skip this" })).not.toBeInTheDocument();
    expect(screen.getByText("Assumed — you skipped this")).toBeInTheDocument();
  });

  it("blocks confirm until the required driver question is answered, then uses what you have", async () => {
    const user = userEvent.setup();
    renderApp("/intents/new/rental");
    await user.click(await screen.findByRole("button", { name: /Use the example/ }));
    await user.click(screen.getByRole("button", { name: "Send to Reservedge" }));
    await user.click(screen.getByRole("button", { name: "Skip this" }));
    await user.click(screen.getByRole("button", { name: "Skip this" }));
    await user.click(screen.getByRole("button", { name: "Use what you have" }));
    expect(
      screen.getAllByText("Answer the required question before confirming.").length,
    ).toBeGreaterThan(0);
    expect(document.querySelector(".itaa-live-region")).toHaveTextContent(
      "Answer the required question before confirming.",
    );
    await user.click(screen.getByRole("button", { name: /30–65/ }));
    await user.click(screen.getByRole("button", { name: "Use what you have" }));
    expect(
      screen.getAllByText("Complete the required parking fields before confirming.").length,
    ).toBeGreaterThan(0);
    await user.type(screen.getByLabelText("Correct PICKUP AND RETURN"), "Match flight{enter}");
    await user.type(screen.getByLabelText("Correct VEHICLE CLASS"), "Mid-size SUV{enter}");
    await user.click(screen.getByRole("button", { name: "Use what you have" }));
    await waitFor(() =>
      expect(document.querySelector(".re-app")).toHaveAttribute("data-route", "inbox"),
    );
    expect(screen.queryByText("Answer the required question before confirming.")).toBeNull();
  });

  it("returns to a skipped required window from Answer it after an unparseable typed answer", async () => {
    const user = userEvent.setup();
    renderApp(
      "/intents/new/parking",
      mockApi({
        extractIntake: async () =>
          intakeExtraction({
            missingFields: ["serviceWindow.start", "serviceWindow.end"],
            proposal: {
              location: { airportCode: "JFK" },
              serviceWindow: { start: null, end: null },
              requirements: {
                vehicleClass: "standard",
                covered: "preferred",
                shuttleMaxMinutes: 20,
              },
              constraints: { currency: "USD", accessibility: ["ev_charging"] },
            },
          }),
      }),
    );
    await user.type(
      await screen.findByLabelText("What you need"),
      "Need JFK parking later this week",
    );
    await user.click(screen.getByRole("button", { name: "Send to Reservedge" }));
    expect(await screen.findByText("When do you need the space?")).toBeInTheDocument();
    await user.type(screen.getByLabelText("Your own answer"), "sometime soon{enter}");
    expect(screen.getByText(/required answer left/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Answer it" }));
    expect(screen.getByText("When do you need the space?")).toBeInTheDocument();
    await user.type(screen.getByLabelText("Window start"), "2026-09-04T14:00");
    await user.type(screen.getByLabelText("Window end"), "2026-09-09T22:00");
    await user.click(screen.getByRole("button", { name: "Continue with these times" }));
    expect(screen.queryByText(/required answer left/)).not.toBeInTheDocument();
    expect(screen.getByText(/All questions done|No extra questions/)).toBeInTheDocument();
  });

  it("canonicalizes a typed parking-prefs answer and surfaces extraction failure without raw secrets", async () => {
    const user = userEvent.setup();
    const confirmIntakeIntent = vi.fn(async () => snapshot());
    renderApp(
      "/intents/new/parking",
      mockApi({
        extractIntake: async () =>
          intakeExtraction({
            missingFields: [
              "requirements.covered",
              "requirements.shuttleMaxMinutes",
              "requirements.vehicleClass",
              "constraints.accessibility",
            ],
            proposal: {
              location: { airportCode: "JFK" },
              serviceWindow: { start: "2026-09-03T13:00:00Z", end: "2026-09-08T22:00:00Z" },
              requirements: { vehicleClass: null, covered: null, shuttleMaxMinutes: null },
              constraints: { currency: "USD", accessibility: [] },
            },
          }),
        confirmIntakeIntent,
      }),
    );
    await user.type(
      await screen.findByLabelText("What you need"),
      "JFK parking 2026-09-03T13:00:00Z to 2026-09-08T22:00:00Z",
    );
    await user.click(screen.getByRole("button", { name: "Send to Reservedge" }));
    expect(await screen.findByText("What matters most this trip?")).toBeInTheDocument();
    await user.type(
      screen.getByLabelText("Your own answer"),
      "covered shuttle 20 suv ev charging{enter}",
    );
    expect(screen.getByText("suv")).toBeInTheDocument();
    expect(screen.getByText("EV charging")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Confirm requirement and research" }));
    await waitFor(() => expect(confirmIntakeIntent).toHaveBeenCalledTimes(1));
    const [body] = confirmIntakeIntent.mock.calls[0] as unknown as [Record<string, unknown>];
    expect(body).toEqual(
      expect.objectContaining({
        vehicleClass: "suv",
        covered: "preferred",
        shuttleMaxMinutes: 20,
        accessibility: ["ev_charging"],
      }),
    );

    cleanup();
    const extractIntake = vi.fn(async () => {
      throw new ClosedApiError({
        status: 503,
        code: "unavailable",
        field: "model",
        correlationId: "cr_01k2m3n4p5q6r7s8t9v0w1x2k2",
      });
    });
    renderApp("/intents/new/parking", mockApi({ extractIntake }));
    await user.click(await screen.findByRole("button", { name: /Use the example/ }));
    await user.click(screen.getByRole("button", { name: "Send to Reservedge" }));
    expect(
      await screen.findByText("The extraction service is not available. Try again in a moment."),
    ).toBeInTheDocument();
    expect(document.querySelector(".itaa-live-region")).toHaveTextContent(
      "The requirement could not be read.",
    );
    expect(screen.queryByText("cr_01k2m3n4p5q6r7s8t9v0w1x2k2")).not.toBeInTheDocument();
  });
});

describe("COMP-G1-05 live parking pause, modify, receipt, and offer handlers", () => {
  it("resumes a saved intent and refreshes after an ambiguous confirm failure", async () => {
    const user = userEvent.setup();
    const unsaveIntent = vi.fn(async () => snapshot({ saved: false }));
    renderApp(
      "/intents/pi_01k2m3n4p5q6r7s8t9v0w1x2y3",
      mockApi({
        getOwnedIntent: async () => snapshot({ saved: true, savedAt: "2026-08-20T16:00:00Z" }),
        unsaveIntent,
      }),
    );
    await user.click(await screen.findByRole("button", { name: "Resume" }));
    await waitFor(() => expect(unsaveIntent).toHaveBeenCalledTimes(1));
    expect(screen.queryByRole("button", { name: "Resume" })).not.toBeInTheDocument();

    cleanup();
    const getOwnedIntent = vi.fn(async () => snapshot());
    const intakeConfirm = vi.fn(async () => {
      throw new ClosedApiError({
        status: 500,
        code: "closed",
        field: "request",
        correlationId: "cr_01k2m3n4p5q6r7s8t9v0w1x2k2",
        retryable: true,
        ambiguous: true,
      });
    });
    renderApp("/intents/pi_01k2m3n4p5q6r7s8t9v0w1x2y3", mockApi({ getOwnedIntent, intakeConfirm }));
    await user.click(await screen.findByRole("button", { name: "Confirm requirement" }));
    expect(
      await screen.findByText(
        "The service did not confirm the last action. Refresh status before trying again.",
      ),
    ).toBeInTheDocument();
    const beforeRefresh = getOwnedIntent.mock.calls.length;
    await user.click(screen.getByRole("button", { name: "Refresh status" }));
    await waitFor(() => expect(getOwnedIntent.mock.calls.length).toBeGreaterThan(beforeRefresh));
    expect(screen.queryByText("cr_01k2m3n4p5q6r7s8t9v0w1x2k2")).not.toBeInTheDocument();
  });

  it("edits, keeps pending, and discards from modify without copying offers", async () => {
    const user = userEvent.setup();
    const saveIntent = vi.fn(async () =>
      snapshot({ saved: true, savedAt: "2026-08-20T16:00:00Z" }),
    );
    renderApp(
      "/intents/pi_01k2m3n4p5q6r7s8t9v0w1x2y3",
      mockApi({ getOwnedIntent: async () => snapshot(), saveIntent }),
    );
    await user.click(await screen.findByRole("button", { name: "Modify intent" }));
    await user.click(screen.getByRole("button", { name: "Review the requirement instead" }));
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(screen.getByRole("tab", { name: "Request" })).toHaveAttribute("aria-selected", "true");

    await user.click(screen.getByRole("button", { name: "Modify intent" }));
    await user.click(screen.getByRole("button", { name: "Keep it pending and start a new one" }));
    await waitFor(() => expect(saveIntent).toHaveBeenCalledTimes(1));
    expect(
      await screen.findByRole("heading", { name: "What are you planning or trying to get done?" }),
    ).toBeInTheDocument();

    cleanup();
    const deleteDraft = vi.fn(async () => undefined);
    renderApp(
      "/intents/pi_01k2m3n4p5q6r7s8t9v0w1x2y3",
      mockApi({ getOwnedIntent: async () => snapshot(), deleteDraft }),
    );
    await user.click(await screen.findByRole("button", { name: "Modify intent" }));
    await user.click(screen.getByRole("button", { name: "Discard this one and start fresh" }));
    await waitFor(() => expect(deleteDraft).toHaveBeenCalledTimes(1));
    expect(await screen.findByRole("button", { name: "Send to Reservedge" })).toBeInTheDocument();
    expect(screen.getByText("REQUIREMENT · BUILDING")).toBeInTheDocument();
  });

  it("selects a non-recommended offer, then walks receipt activity and inbox return", async () => {
    const user = userEvent.setup();
    const intakeAccept = vi.fn(async () =>
      rankedSnapshot({
        state: "ACCEPTANCE_RECORDED",
        acceptance: {
          acceptanceId: "ac_01k2m3n4p5q6r7s8t9v0w1x2d1",
          offerId: LOCKED_OFFER_IDS.parkDirect,
          offerVersion: 1,
          status: "recorded",
        },
      }),
    );
    renderApp(
      "/intents/pi_01k2m3n4p5q6r7s8t9v0w1x2y3",
      mockApi({ getOwnedIntent: async () => rankedSnapshot(), intakeAccept }),
    );
    await user.click(await screen.findByRole("button", { name: "Select ParkDirect" }));
    expect(screen.getByLabelText("Selected offer acceptance")).toHaveTextContent("ParkDirect");
    await user.click(screen.getByRole("button", { name: "Confirm offer selection" }));
    await waitFor(() => expect(intakeAccept).toHaveBeenCalledTimes(1));
    expect(intakeAccept).toHaveBeenCalledWith("pi_01k2m3n4p5q6r7s8t9v0w1x2y3", {
      offerId: LOCKED_OFFER_IDS.parkDirect,
      offerVersion: 1,
    });
    expect(screen.getByRole("dialog", { name: "Authorize this purchase" })).toBeInTheDocument();

    cleanup();
    renderApp(
      "/intents/pi_01k2m3n4p5q6r7s8t9v0w1x2y3/confirmation",
      mockApi({
        getOwnedIntent: async () =>
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
        intentActivity: async () => [
          { occurredAt: "2026-08-20T16:05:00Z", label: "Simulated authorization recorded" },
        ],
      }),
    );
    expect(await screen.findByText("SIMULATED RECEIPT")).toBeInTheDocument();
    expect(screen.getByText(/keeps requests in this browser session/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "View this intent's activity" }));
    expect(screen.getByRole("tab", { name: "Activity" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getAllByText("Booking confirmed for SkyShield offer").length).toBeGreaterThan(0);
    await user.click(screen.getByRole("tab", { name: "Offers" }));
    await user.click(
      within(document.querySelector(".re-receipt") as HTMLElement).getByRole("button", {
        name: "Back to intents",
      }),
    );
    expect(document.querySelector(".re-app")).toHaveAttribute("data-route", "workspace");
    expect(
      screen.getByRole("heading", { name: "What are you planning or trying to get done?" }),
    ).toBeInTheDocument();
  });

  it("closes the progress stream on error and still applies the ranked snapshot", async () => {
    const user = userEvent.setup();
    const closer = vi.fn();
    const subscribeProgress = vi.fn((_intent: string, handlers: ProgressHandlers) => {
      queueMicrotask(() => handlers.onError());
      return { close: closer };
    });
    const intakeDispatch = vi.fn(async () => rankedSnapshot());
    renderApp(
      "/intents/pi_01k2m3n4p5q6r7s8t9v0w1x2y3",
      mockApi({
        getOwnedIntent: async () => snapshot({ state: "AWAITING_DISPATCH_APPROVAL" }),
        subscribeProgress,
        intakeDispatch,
      }),
    );
    await user.click(await screen.findByRole("button", { name: "Send this request" }));
    await waitFor(() => expect(intakeDispatch).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(closer).toHaveBeenCalled());
    await user.click(await screen.findByRole("button", { name: "See the recommendation" }));
    expect(screen.getByText("Why this is recommended")).toBeInTheDocument();
    expect(screen.queryByText("JetPark")).not.toBeInTheDocument();
  });

  it("dedupes progress events and ignores a later generation", async () => {
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
    const first: ProgressEventPayload = {
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
    };
    send?.(first);
    send?.(first);
    send?.({ ...first, generationId: "pg_01k2m3n4p5q6r7s8t9v0w1x2g2", sequence: 1 });
    expect(await screen.findAllByText("SkyShield")).toHaveLength(1);
    expect(screen.getByText("Offer received")).toBeInTheDocument();
    release(rankedSnapshot());
    expect(await screen.findByText("Suppliers answered")).toBeInTheDocument();
  });
});

describe("COMP-G1-05 seed demonstration handlers", () => {
  it("starts on the intent-first composer without a domain picker", async () => {
    renderApp("/");
    const main = await screen.findByRole("main");
    expect(
      within(main).getByRole("heading", { name: "What are you planning or trying to get done?" }),
    ).toBeInTheDocument();
    expect(within(main).queryByRole("button", { name: "New intent" })).toBeNull();
  });

  it("continues research to offers and keeps a disclosure gate pending", async () => {
    const user = userEvent.setup();
    renderApp("/");
    await user.click(await screen.findByRole("tab", { name: "Running" }));
    await user.click(screen.getByRole("button", { name: /Public listings only/ }));
    expect(await screen.findByText(/PUBLIC RESEARCH/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Continue to the offers tab" }));
    expect(screen.getByRole("tab", { name: "Offers" })).toHaveAttribute("aria-selected", "true");

    await user.click(screen.getByRole("tab", { name: "Pending" }));
    await user.click(screen.getAllByRole("button", { name: /Rental car · Boston/ })[0]!);
    expect(await screen.findByText("What suppliers will see")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Not now — keep pending" }));
    expect(screen.getByText(/Paused. Nothing further was shared/)).toBeInTheDocument();
  });

  it("leaves a rental re-ask incomplete and closes authorization without charging", async () => {
    const user = userEvent.setup();
    renderApp("/");
    await user.click((await screen.findAllByRole("button", { name: /Rental car from JFK/ }))[0]!);
    await user.click(await screen.findByRole("button", { name: "Compare offers" }));
    await user.click(screen.getByRole("button", { name: "Answer and re-ask" }));
    await user.click(screen.getByRole("button", { name: "Leave it incomplete" }));
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(screen.getByRole("button", { name: "Answer and re-ask" })).toBeInTheDocument();

    cleanup();
    renderApp("/");
    await user.click(await screen.findByRole("button", { name: /recommended \$71\.40/ }));
    await user.click(await screen.findByRole("button", { name: "Take this one" }));
    await user.click(screen.getByRole("button", { name: "Not now" }));
    expect(screen.queryByRole("dialog")).toBeNull();
    await user.click(screen.getByRole("button", { name: "Take this one" }));
    await user.click(screen.getByRole("button", { name: "Authorize $71.40" }));
    expect(await screen.findByText("Authorization recorded")).toBeInTheDocument();
    expect(screen.getByText(/No card charged, nothing reserved/)).toBeInTheDocument();
  });

  it("edits, discards, or deletes a seed intent from modify and cancel", async () => {
    const user = userEvent.setup();
    renderApp("/");
    await user.click(await screen.findByRole("button", { name: /recommended \$71\.40/ }));
    await user.click(await screen.findByRole("button", { name: "Modify intent" }));
    await user.click(screen.getByRole("button", { name: "Edit the requirement instead" }));
    expect(screen.getByRole("tab", { name: "Request" })).toHaveAttribute("aria-selected", "true");
    expect(screen.queryByRole("dialog")).toBeNull();

    await user.click(screen.getByRole("button", { name: "Modify intent" }));
    await user.click(screen.getByRole("button", { name: "Keep it pending and start a new one" }));
    expect(
      await screen.findByRole("heading", { name: "What are you planning or trying to get done?" }),
    ).toBeInTheDocument();

    cleanup();
    renderApp("/");
    await user.click(await screen.findByRole("button", { name: /recommended \$71\.40/ }));
    await user.click(await screen.findByRole("button", { name: "Modify intent" }));
    await user.click(screen.getByRole("button", { name: "Discard this one and start fresh" }));
    expect(await screen.findByRole("button", { name: "Send to Reservedge" })).toBeInTheDocument();
    expect(screen.getByText("REQUIREMENT · BUILDING")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /recommended \$71\.40/ })).toBeNull();

    cleanup();
    renderApp("/");
    await user.click((await screen.findAllByRole("button", { name: /Rental car from JFK/ }))[0]!);
    await user.click(await screen.findByRole("button", { name: "Cancel intent" }));
    await user.click(screen.getByRole("button", { name: "Keep it" }));
    expect(screen.queryByRole("dialog")).toBeNull();
    await user.click(screen.getByRole("button", { name: "Cancel intent" }));
    await user.click(screen.getByRole("button", { name: "Delete intent" }));
    expect(
      await screen.findByRole("heading", {
        name: "What are you planning or trying to get done?",
      }),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Rental car from JFK/ })).toBeNull();
  });
});
