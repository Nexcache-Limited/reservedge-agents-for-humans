import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it } from "vitest";
import { AppRoutes } from "./App.js";
import { intakeExtraction, mockApi } from "./test/fixtures.js";

afterEach(() => {
  cleanup();
  sessionStorage.clear();
});

const EDINBURGH = "I'm travelling to Edinburgh for a conference and I'll need a car when I land.";
const JFK = "Airport parking at JFK next Thursday";

function renderApp(path = "/") {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AppRoutes api={mockApi()} />
    </MemoryRouter>,
  );
}

async function startObjective(text: string) {
  const user = userEvent.setup();
  renderApp("/");
  const field = await screen.findByRole("textbox", {
    name: "What are you planning or trying to get done?",
  });
  fireEvent.change(field, { target: { value: text } });
  const start = screen.getByRole("button", { name: "Start booking" });
  expect(start).toBeEnabled();
  await user.click(start);
  expect(
    await screen.findByRole("button", { name: "Answer and update plan" }, { timeout: 8000 }),
  ).toBeEnabled();
  return user;
}

async function submitAnswers(user: Awaited<ReturnType<typeof startObjective>>) {
  await user.click(screen.getByRole("button", { name: "Answer and update plan" }));
}

function planRoot(): HTMLElement {
  return document.querySelector(".re-clarify") as HTMLElement;
}

describe("intent-first Clarify & plan", () => {
  it("preserves the full objective after Start booking and does not jump to a domain form", async () => {
    await startObjective(EDINBURGH);
    expect(await screen.findByText(EDINBURGH)).toBeInTheDocument();
    expect((await screen.findAllByText("Clarify & plan")).length).toBeGreaterThan(0);
    expect(screen.getByText("Gathering")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Send to Reservedge" })).toBeNull();
    expect(screen.queryByRole("heading", { name: "Airport parking" })).toBeNull();
  });

  it("does not re-ask facts already supplied in the objective", async () => {
    await startObjective(EDINBURGH);
    expect(await screen.findByRole("group", { name: "Exact dates" })).toBeInTheDocument();
    expect(screen.getByLabelText("Start date")).toBeInTheDocument();
    expect(screen.getByLabelText("Departing from")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Yes" })).toBeNull();
    expect(screen.queryByText(/Will you need a car/i)).toBeNull();
  });

  it("invites hotels, cars, and parking in chat for a dated city trip without inventing airport parking", async () => {
    const user = userEvent.setup();
    renderApp("/");
    const field = await screen.findByRole("textbox", {
      name: "What are you planning or trying to get done?",
    });
    fireEvent.change(field, {
      target: { value: "I'm travelling to Edinburgh from 14 to 19 October 2026." },
    });
    await user.click(screen.getByRole("button", { name: "Start booking" }));
    expect(
      await screen.findByText(/I can help with hotels, airport parking, and things to do/i),
    ).toBeInTheDocument();
    expect(screen.queryByRole("group", { name: "What should I help book?" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Answer and update plan" })).toBeNull();
    expect(screen.getByRole("button", { name: "Confirm plan" })).toBeInTheDocument();
    expect(screen.queryByText("Airport parking · EDI")).toBeNull();
    expect(screen.queryByText("Airport parking · Edinburgh")).toBeNull();
    expect(screen.queryByText("JFK")).toBeNull();
  });

  it("does not show a date card for a named city trip and asks when in chat", async () => {
    const user = userEvent.setup();
    renderApp("/");
    const field = await screen.findByRole("textbox", {
      name: "What are you planning or trying to get done?",
    });
    fireEvent.change(field, { target: { value: "travelling to London" } });
    await user.click(screen.getByRole("button", { name: "Start booking" }));
    expect(await screen.findByText(/I have London\. When are you travelling/i)).toBeInTheDocument();
    expect(screen.queryByText(/Where and when are you travelling/i)).toBeNull();
    expect(screen.queryByLabelText("Start date")).toBeNull();
    expect(screen.queryByRole("button", { name: "Answer and update plan" })).toBeNull();
    expect(screen.getByText(/Reply with your dates in the chat/i)).toBeInTheDocument();
  });

  it("asks only missing blocking questions and keeps an explicit rental-car task", async () => {
    const user = await startObjective(EDINBURGH);
    const plan = within(planRoot());
    expect(await plan.findByRole("group", { name: "Exact dates" })).toBeInTheDocument();
    await submitAnswers(user);
    expect(plan.getByText("Rental car · Edinburgh")).toBeInTheDocument();
    expect(plan.getByText("Explicit")).toBeInTheDocument();
    expect(plan.getByText("You asked for this.")).toBeInTheDocument();
  });

  it("produces more than one task from a multi-need objective", async () => {
    const user = await startObjective(EDINBURGH);
    await submitAnswers(user);
    const plan = within(planRoot());
    expect(await plan.findByText("Rental car · Edinburgh")).toBeInTheDocument();
    expect(plan.getByText("Airport parking · EDI")).toBeInTheDocument();
    expect(planRoot().querySelectorAll(".re-clarify-task").length).toBeGreaterThan(1);
  });

  it("preserves explicit, inferred, and proposed provenance", async () => {
    const user = await startObjective(EDINBURGH);
    await submitAnswers(user);
    await screen.findByText("Inferred");
    expect(screen.getByText("Explicit")).toBeInTheDocument();
    expect(screen.getAllByText("Proposed").length).toBeGreaterThan(0);
    expect(screen.getByText(/Not an explicit parking request/)).toBeInTheDocument();
    expect(screen.getByText(/not something you requested/i)).toBeInTheDocument();
  });

  it("lets the user remove a proposed task", async () => {
    const user = await startObjective(EDINBURGH);
    await submitAnswers(user);
    const plan = within(planRoot());
    const flight = (await plan.findByText("Flight")).closest("article");
    expect(flight).not.toBeNull();
    await user.click(within(flight as HTMLElement).getByRole("button", { name: "Not needed" }));
    expect(plan.queryByText("Flight")).toBeNull();
    expect(plan.getByText("Rental car · Edinburgh")).toBeInTheDocument();
  });

  it("confirms the plan only after clarification, then allows execution", async () => {
    const user = await startObjective(EDINBURGH);
    fireEvent.change(screen.getByLabelText("Start date"), { target: { value: "2026-10-14" } });
    fireEvent.change(screen.getByLabelText("End date"), { target: { value: "2026-10-19" } });
    await user.type(screen.getByLabelText("Departing from"), "Manchester (MAN)");
    expect(screen.queryByRole("button", { name: "Confirm plan" })).toBeNull();
    await user.click(screen.getByRole("button", { name: "Answer and update plan" }));
    await user.click(screen.getByRole("button", { name: "Confirm plan" }));
    expect(screen.getByRole("status")).toHaveTextContent(/Plan confirmed/);
    expect(screen.queryByRole("button", { name: "Send to Reservedge" })).toBeNull();
    expect(screen.getByRole("button", { name: "Begin parking requirement" })).toBeInTheDocument();
  });

  it("starts parking execution only after plan confirmation and prefills known facts", async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter initialEntries={["/"]}>
        <AppRoutes
          api={mockApi({
            extractIntake: async () =>
              intakeExtraction({
                missingFields: ["location.airportCode"],
                proposal: {
                  location: { airportCode: null },
                  serviceWindow: { start: null, end: null },
                  requirements: {
                    vehicleClass: "standard",
                    covered: "preferred",
                    shuttleMaxMinutes: 20,
                  },
                  constraints: { currency: "USD", accessibility: [] },
                },
              }),
          })}
        />
      </MemoryRouter>,
    );
    await user.type(
      await screen.findByRole("textbox", {
        name: "What are you planning or trying to get done?",
      }),
      EDINBURGH,
    );
    await user.click(screen.getByRole("button", { name: "Start booking" }));
    fireEvent.change(await screen.findByLabelText("Start date"), {
      target: { value: "2026-10-14" },
    });
    fireEvent.change(screen.getByLabelText("End date"), { target: { value: "2026-10-19" } });
    await user.type(screen.getByLabelText("Departing from"), "MAN");
    await user.click(screen.getByRole("button", { name: "Answer and update plan" }));
    await user.click(screen.getByRole("button", { name: "Confirm plan" }));
    await user.click(screen.getByRole("button", { name: "Begin parking requirement" }));
    expect(screen.queryByRole("button", { name: "Send to Reservedge" })).toBeNull();
    expect(screen.queryByRole("button", { name: /Use the example/ })).toBeNull();
    expect(screen.queryByRole("textbox", { name: "What you need" })).toBeNull();
    expect(
      await screen.findByRole("button", { name: "Confirm requirement and research" }),
    ).toBeInTheDocument();
    expect(await screen.findByText("AIRPORT")).toBeInTheDocument();
    expect(screen.getAllByText("EDI").length).toBeGreaterThan(0);
    expect(screen.getByText("Live competition path")).toBeInTheDocument();
  });

  it("keeps the JFK parking case on the existing simulated A1–A4 path after plan confirm", async () => {
    const user = await startObjective(JFK);
    expect(await screen.findByText(JFK)).toBeInTheDocument();
    expect(screen.getByLabelText("Start date")).toHaveValue("");
    fireEvent.change(screen.getByLabelText("Start date"), { target: { value: "2026-10-16" } });
    fireEvent.change(screen.getByLabelText("End date"), { target: { value: "2026-10-20" } });
    await user.click(screen.getByRole("button", { name: "Answer and update plan" }));
    expect(screen.queryByLabelText("Start date")).toBeNull();
    expect(screen.getAllByText("Airport parking · JFK").length).toBeGreaterThan(0);
    expect(screen.queryByRole("button", { name: "Not needed" })).toBeNull();
    await user.click(screen.getByRole("button", { name: "Confirm plan" }));
    await user.click(screen.getByRole("button", { name: "Begin parking requirement" }));
    expect(screen.queryByRole("button", { name: "Send to Reservedge" })).toBeNull();
    expect(screen.queryByRole("button", { name: /Use the example/ })).toBeNull();
    expect(
      await screen.findByRole("button", { name: "Confirm requirement and research" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Live competition path")).toBeInTheDocument();
    expect(screen.getAllByText("JFK").length).toBeGreaterThan(0);
  });

  it("preserves composer, clarification, and plan state across Intent / Bookings / Activity", async () => {
    const user = await startObjective(EDINBURGH);
    fireEvent.change(screen.getByLabelText("Start date"), { target: { value: "2026-10-14" } });
    fireEvent.change(screen.getByLabelText("End date"), { target: { value: "2026-10-19" } });
    await user.click(document.querySelector(".re-tabs a[href='/bookings']") as HTMLAnchorElement);
    expect(await screen.findByRole("heading", { name: "Booking Chats" })).toBeInTheDocument();
    await user.click(document.querySelector(".re-tabs a[href='/activity']") as HTMLAnchorElement);
    expect(await screen.findByRole("heading", { name: "Activity" })).toBeInTheDocument();
    await user.click(
      document.querySelector(".re-tabs a[href='/intents/clarify']") as HTMLAnchorElement,
    );
    expect(await screen.findByText(EDINBURGH)).toBeInTheDocument();
    expect(screen.getByLabelText("Start date")).toHaveValue("2026-10-14");
    expect(screen.getByLabelText("End date")).toHaveValue("2026-10-19");
    await user.click(screen.getByRole("button", { name: "Answer and update plan" }));
    expect(within(planRoot()).getByText("Rental car · Edinburgh")).toBeInTheDocument();
  });

  it("does not pretend unsupported tasks are live", async () => {
    const user = await startObjective(EDINBURGH);
    await user.click(await screen.findByRole("button", { name: "Answer and update plan" }));
    await user.click(screen.getByRole("button", { name: "Confirm plan" }));
    expect(screen.getAllByText("Unsupported in this build").length).toBeGreaterThan(0);
    expect(screen.getAllByText("No supplier execution in this build.").length).toBeGreaterThan(0);
    expect(screen.queryByRole("button", { name: /Begin flight/i })).toBeNull();
    expect(screen.getByRole("button", { name: "Open rental demonstration" })).toBeInTheDocument();
  });

  it("can add a supported demonstration task during review", async () => {
    const user = await startObjective(JFK);
    await submitAnswers(user);
    await user.click(await screen.findByRole("button", { name: "Add entertainment" }));
    expect(within(planRoot()).getByText("Entertainment")).toBeInTheDocument();
    expect(within(planRoot()).getByText("Demonstration task")).toBeInTheDocument();
  });

  it("explains that Clarify & plan is session-local when opened with no plan", async () => {
    renderApp("/intents/clarify");
    expect(
      await screen.findByRole("heading", { name: "No plan in this session" }),
    ).toBeInTheDocument();
    expect(screen.getByText(/lives in this browser session only/i)).toBeInTheDocument();
    await userEvent.setup().click(screen.getByRole("button", { name: "Start from an objective" }));
    expect(
      await screen.findByRole("heading", { name: "What are you planning or trying to get done?" }),
    ).toBeInTheDocument();
  });

  it("accepts a proposed task, stores an extra note, and opens the rental demonstration", async () => {
    const user = await startObjective(EDINBURGH);
    await user.type(
      screen.getByLabelText("Add anything else about this trip"),
      "Window seat if possible",
    );
    await user.click(screen.getByRole("button", { name: "Add note" }));
    await submitAnswers(user);
    expect(screen.getAllByText("Window seat if possible").length).toBeGreaterThan(0);
    const hotel = (await within(planRoot()).findByText("Hotel")).closest("article") as HTMLElement;
    await user.click(within(hotel).getByRole("button", { name: "Add to plan" }));
    await user.click(screen.getByRole("button", { name: "Confirm plan" }));
    await user.click(screen.getByRole("button", { name: "Open rental demonstration" }));
    expect(await screen.findByText("Simulated demonstration")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Send to Reservedge" })).toBeInTheDocument();
  });

  it("does not force a car question for a New York stay trip", async () => {
    const user = userEvent.setup();
    renderApp("/");
    const field = await screen.findByRole("textbox", {
      name: "What are you planning or trying to get done?",
    });
    fireEvent.change(field, {
      target: { value: "I'm planning a five-day trip to New York in October." },
    });
    await user.click(screen.getByRole("button", { name: "Start booking" }));
    expect(await screen.findByText(/When are you travelling/i)).toBeInTheDocument();
    expect(screen.queryByLabelText("Start date")).toBeNull();
    expect(screen.queryByRole("button", { name: "Answer and update plan" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Yes" })).toBeNull();
    expect(screen.queryByText(/Will you need a car/i)).toBeNull();
    expect(screen.queryByText("JFK")).toBeNull();
  });
});
