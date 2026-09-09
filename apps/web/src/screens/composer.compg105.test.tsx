import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AppRoutes } from "../App.js";
import { SAMPLE_JFK_TEXT } from "../reservedge/parking-intake.js";
import { intakeExtraction, mockApi, snapshot } from "../test/fixtures.js";

afterEach(() => {
  cleanup();
});

function renderApp(path: string, api = mockApi()) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AppRoutes api={api} />
    </MemoryRouter>,
  );
}

describe("COMP-G1-05 Phase 2 composer", () => {
  it("renders all three domains through secondary shortcuts and the same composer", async () => {
    const user = userEvent.setup();
    renderApp("/intents/new");
    expect(
      await screen.findByRole("heading", { name: "What are you planning or trying to get done?" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Pk Airport parking" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Rc Rental car" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "En Entertainment booking" })).toBeInTheDocument();
    expect(screen.queryByText(/Spa is next/i)).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Rc Rental car" }));
    expect(await screen.findByRole("button", { name: "Send to Reservedge" })).toBeInTheDocument();
    expect(screen.getByText("REQUIREMENT · BUILDING")).toBeInTheDocument();
    expect(screen.getByText("Simulated demonstration")).toBeInTheDocument();
  });

  it("sends parking to extraction and confirms canonical fields without raw text", async () => {
    const user = userEvent.setup();
    const extractIntake = vi.fn(async () => intakeExtraction());
    const confirmIntakeIntent = vi.fn(async () => snapshot());
    renderApp("/intents/new/parking", mockApi({ extractIntake, confirmIntakeIntent }));
    await user.click(await screen.findByRole("button", { name: /Use the example/ }));
    await user.click(screen.getByRole("button", { name: "Send to Reservedge" }));
    await waitFor(() => expect(extractIntake).toHaveBeenCalledTimes(1));
    expect(extractIntake).toHaveBeenCalledWith(SAMPLE_JFK_TEXT, "airport_parking");
    expect(await screen.findByText(/WHAT YOU TYPED/)).toBeInTheDocument();
    expect(screen.queryByText(/QUESTION 1 OF/)).not.toBeInTheDocument();
    expect(screen.getByText(/No extra questions were needed/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Confirm requirement and research" }));
    await waitFor(() => expect(confirmIntakeIntent).toHaveBeenCalledTimes(1));
    const [body] = confirmIntakeIntent.mock.calls[0] as unknown as [Record<string, unknown>];
    expect(body).not.toHaveProperty("text");
    expect(JSON.stringify(body)).not.toMatch(/flying from JFK|September 3 at 1 PM/);
    expect(body).toEqual(
      expect.objectContaining({
        airportCode: "JFK",
        vehicleClass: "standard",
        covered: "preferred",
        shuttleMaxMinutes: 20,
        currency: "USD",
        accessibility: ["ev_charging"],
      }),
    );
  });

  it("asks only missing parking questions and refuses to skip a required airport", async () => {
    const user = userEvent.setup();
    renderApp(
      "/intents/new/parking",
      mockApi({
        extractIntake: async () =>
          intakeExtraction({
            missingFields: ["location.airportCode"],
            proposal: {
              location: { airportCode: null },
              serviceWindow: { start: "2026-09-03T13:00:00Z", end: "2026-09-08T22:00:00Z" },
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
    await user.type(await screen.findByLabelText("What you need"), "need parking later this week");
    await user.click(screen.getByRole("button", { name: "Send to Reservedge" }));
    expect(await screen.findByText(/QUESTION 1 OF 1/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Skip this" })).not.toBeInTheDocument();
    expect(
      screen.getByText(/Required — suppliers in this domain cannot price without it/),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "JFK · Terminal 8" }));
    expect(screen.queryByText(/QUESTION 2 OF/)).not.toBeInTheDocument();
    expect(screen.getByText("JFK")).toBeInTheDocument();
  });

  it("keeps parking window times from the typed sentence without a wasted question", async () => {
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
    await user.click(await screen.findByRole("button", { name: /Use the example/ }));
    await user.click(screen.getByRole("button", { name: "Send to Reservedge" }));
    expect(await screen.findByText("2026-09-03T13:00:00Z")).toBeInTheDocument();
    expect(screen.getByText("2026-09-08T22:00:00Z")).toBeInTheDocument();
    expect(screen.queryByText(/QUESTION 1 OF/)).not.toBeInTheDocument();
    expect(screen.getByText(/No extra questions were needed/)).toBeInTheDocument();
  });

  it("still offers window inputs when the typed sentence has no parseable times", async () => {
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
    expect(screen.getByLabelText("Window start")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Continue with these times" })).toBeInTheDocument();
    await user.type(screen.getByLabelText("Window start"), "2026-09-04T14:00");
    await user.type(screen.getByLabelText("Window end"), "2026-09-09T22:00");
    await user.click(screen.getByRole("button", { name: "Continue with these times" }));
    expect(screen.queryByText("When do you need the space?")).not.toBeInTheDocument();
  });

  it("caps rental at three questions and blocks skip on the required driver field", async () => {
    const user = userEvent.setup();
    renderApp("/intents/new/rental");
    await user.click(await screen.findByRole("button", { name: /Use the example/ }));
    await user.click(screen.getByRole("button", { name: "Send to Reservedge" }));
    expect(screen.getByText(/QUESTION 1 OF 3/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Match flight/ }));
    await user.click(screen.getByRole("button", { name: "Mid-size SUV" }));
    expect(screen.getByText(/QUESTION 3 OF 3/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Skip this" })).not.toBeInTheDocument();
    expect(screen.queryByText(/QUESTION 4 OF/)).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /30–65/ }));
    expect(screen.queryByText(/QUESTION 3 OF 3/)).not.toBeInTheDocument();
    expect(screen.getByText(/All questions done/)).toBeInTheDocument();
  });

  it("does not call parking intake APIs for entertainment", async () => {
    const user = userEvent.setup();
    const extractIntake = vi.fn(async () => intakeExtraction());
    const confirmIntakeIntent = vi.fn(async () => snapshot());
    renderApp("/intents/new/ents", mockApi({ extractIntake, confirmIntakeIntent }));
    await user.click(await screen.findByRole("button", { name: /Use the example/ }));
    await user.click(screen.getByRole("button", { name: "Send to Reservedge" }));
    expect(extractIntake).not.toHaveBeenCalled();
    expect(screen.getAllByText(/Simulated demonstration/).length).toBeGreaterThan(0);
    await user.click(screen.getByRole("button", { name: "Live music" }));
    await user.click(screen.getByRole("button", { name: /Fri 12 Sep/ }));
    await user.click(screen.getByRole("button", { name: /2 seats · must be together/ }));
    await user.click(screen.getByRole("button", { name: "Confirm requirement and research" }));
    expect(confirmIntakeIntent).not.toHaveBeenCalled();
  });

  it("canonicalizes EV language even when extraction omits accessibility", async () => {
    const user = userEvent.setup();
    const confirmIntakeIntent = vi.fn(async () => snapshot());
    renderApp(
      "/intents/new/parking",
      mockApi({
        extractIntake: async () =>
          intakeExtraction({
            proposal: {
              location: { airportCode: "JFK" },
              serviceWindow: { start: "2026-09-03T13:00:00Z", end: "2026-09-08T22:00:00Z" },
              requirements: {
                vehicleClass: "standard",
                covered: "preferred",
                shuttleMaxMinutes: 20,
              },
              constraints: { currency: "USD", accessibility: [] },
            },
          }),
        confirmIntakeIntent,
      }),
    );
    await user.click(await screen.findByRole("button", { name: /Use the example/ }));
    await user.click(screen.getByRole("button", { name: "Send to Reservedge" }));
    expect(await screen.findByText("EV charging")).toBeInTheDocument();
    expect(screen.queryByText("All questions done.")).not.toBeInTheDocument();
    expect(screen.getByText(/No extra questions were needed/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Confirm requirement and research" }));
    await waitFor(() => expect(confirmIntakeIntent).toHaveBeenCalledTimes(1));
    const [evBody] = confirmIntakeIntent.mock.calls[0] as unknown as [Record<string, unknown>];
    expect(evBody).toEqual(expect.objectContaining({ accessibility: ["ev_charging"] }));
  });

  it("asks for accessibility within three questions instead of declaring the card complete", async () => {
    const user = userEvent.setup();
    renderApp(
      "/intents/new/parking",
      mockApi({
        extractIntake: async () =>
          intakeExtraction({
            missingFields: ["constraints.accessibility"],
            proposal: {
              location: { airportCode: "JFK" },
              serviceWindow: { start: "2026-09-03T13:00:00Z", end: "2026-09-08T22:00:00Z" },
              requirements: {
                vehicleClass: "standard",
                covered: "preferred",
                shuttleMaxMinutes: 20,
              },
              constraints: { currency: "USD", accessibility: [] },
            },
          }),
      }),
    );
    await user.type(
      await screen.findByLabelText("What you need"),
      "JFK parking 2026-09-03T13:00:00Z to 2026-09-08T22:00:00Z standard covered shuttle 20 minutes USD",
    );
    await user.click(screen.getByRole("button", { name: "Send to Reservedge" }));
    expect(await screen.findByText(/QUESTION 1 OF 1/)).toBeInTheDocument();
    expect(screen.queryByText("All questions done.")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "EV charging" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Skip this" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "EV charging" }));
    expect(screen.getByText("EV charging")).toBeInTheDocument();
    expect(screen.getByText(/All questions done/)).toBeInTheDocument();
  });

  it("rejects an invalid vehicle enum with visible choices and lets a filled field be edited", async () => {
    const user = userEvent.setup();
    renderApp("/intents/new/parking", mockApi());
    await user.click(await screen.findByRole("button", { name: /Use the example/ }));
    await user.click(screen.getByRole("button", { name: "Send to Reservedge" }));
    expect(await screen.findByText("standard")).toBeInTheDocument();
    const vehicle = screen.getByLabelText("Correct VEHICLE CLASS");
    await user.type(vehicle, "Standard EV{enter}");
    expect(
      await screen.findAllByText(
        "Vehicle class must be one of: standard, compact, suv, oversized.",
      ),
    ).not.toHaveLength(0);
    await user.clear(vehicle);
    await user.type(vehicle, "suv{enter}");
    expect(await screen.findByText("suv")).toBeInTheDocument();
    const covered = screen.getByLabelText("Correct COVERED");
    await user.type(covered, "required");
    await user.tab();
    expect(await screen.findByText("required")).toBeInTheDocument();
  });

  it("surfaces a missing intake session instead of silently ignoring confirm", async () => {
    const user = userEvent.setup();
    const confirmIntakeIntent = vi.fn(async () => snapshot());
    renderApp(
      "/intents/new/parking",
      mockApi({
        extractIntake: async () => intakeExtraction({ intakeId: "" }),
        confirmIntakeIntent,
      }),
    );
    await user.click(await screen.findByRole("button", { name: /Use the example/ }));
    await user.click(screen.getByRole("button", { name: "Send to Reservedge" }));
    await user.click(
      await screen.findByRole("button", { name: "Confirm requirement and research" }),
    );
    expect(confirmIntakeIntent).not.toHaveBeenCalled();
    expect(
      screen.getByText(
        "This requirement is not linked to an intake session. Send the line again before confirming.",
      ),
    ).toBeInTheDocument();
    expect(screen.queryByText("That's enough to work with.")).not.toBeInTheDocument();
  });

  it("rebuilds ranking-relevant fields from a spoken line when extraction returns no proposal", async () => {
    const user = userEvent.setup();
    const confirmIntakeIntent = vi.fn(async () => snapshot());
    renderApp(
      "/intents/new/parking",
      mockApi({
        extractIntake: async () =>
          intakeExtraction({
            proposal: null,
            missingFields: [
              "location.airportCode",
              "serviceWindow.start",
              "serviceWindow.end",
              "requirements.vehicleClass",
              "requirements.covered",
              "requirements.shuttleMaxMinutes",
              "constraints.currency",
            ],
          }),
        confirmIntakeIntent,
      }),
    );
    await user.click(await screen.findByRole("button", { name: /Use the example/ }));
    await user.click(screen.getByRole("button", { name: "Send to Reservedge" }));
    expect(await screen.findByText("EV charging")).toBeInTheDocument();
    expect(screen.getByText("JFK")).toBeInTheDocument();
    expect(screen.getByText("standard")).toBeInTheDocument();
    expect(screen.queryByText("All questions done.")).not.toBeInTheDocument();
    expect(screen.getByText(/No extra questions were needed/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Confirm requirement and research" }));
    await waitFor(() => expect(confirmIntakeIntent).toHaveBeenCalledTimes(1));
    const [confirmed] = confirmIntakeIntent.mock.calls[0] as unknown as [Record<string, unknown>];
    expect(confirmed).toEqual(
      expect.objectContaining({
        airportCode: "JFK",
        vehicleClass: "standard",
        covered: "preferred",
        shuttleMaxMinutes: 20,
        currency: "USD",
        accessibility: ["ev_charging"],
      }),
    );
  });

  it("confirms a rental design-fixture without calling parking intake", async () => {
    const user = userEvent.setup();
    const confirmIntakeIntent = vi.fn();
    renderApp("/intents/new/rental", mockApi({ confirmIntakeIntent }));
    await user.click(await screen.findByRole("button", { name: /Use the example/ }));
    await user.click(screen.getByRole("button", { name: "Send to Reservedge" }));
    await user.click(screen.getByRole("button", { name: /Match flight/ }));
    await user.click(screen.getByRole("button", { name: "Mid-size SUV" }));
    await user.click(screen.getByRole("button", { name: /30–65/ }));
    await user.click(screen.getByRole("button", { name: "Confirm requirement and research" }));
    expect(confirmIntakeIntent).not.toHaveBeenCalled();
    await waitFor(() =>
      expect(document.querySelector(".re-app")).toHaveAttribute("data-route", "inbox"),
    );
    expect(
      screen.queryByRole("button", { name: "Confirm requirement and research" }),
    ).not.toBeInTheDocument();
  });
});
