import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it } from "vitest";
import { AppRoutes } from "../App.js";
import { SEED_INTENTS } from "../reservedge/inbox.js";
import { mockApi } from "../test/fixtures.js";
import { InboxWelcome } from "./InboxScreen.js";

afterEach(() => {
  cleanup();
});

function renderApp(path = "/") {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AppRoutes api={mockApi()} />
    </MemoryRouter>,
  );
}

describe("COMP-G1-05 Phase 1 Reservedge shell", () => {
  it("renders the Reservedge rail wordmark, SIM chip, and inbox filters", async () => {
    renderApp("/");
    expect(await screen.findByRole("heading", { name: "Bookings" })).toBeInTheDocument();
    expect(screen.getAllByText("Reservedge").length).toBeGreaterThan(0);
    expect(screen.getAllByText("SIM").length).toBeGreaterThan(0);
    expect(screen.getByText("Simulation mode")).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "All" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Needs you" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Pending" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "History" })).toBeInTheDocument();
    expect(screen.getAllByText("JFK airport parking · Sep 4–8").length).toBeGreaterThan(0);
    expect(screen.getByText("TODAY · 29 AUG")).toBeInTheDocument();
    expect(document.body.textContent ?? "").not.toMatch(/Gate 1/);
    expect(document.body.textContent ?? "").not.toMatch(/\bA1\b/);
    expect(document.body.textContent ?? "").not.toMatch(/process-memory/i);
  });

  it("keeps one public wordmark and does not show the giant simulation banner", async () => {
    const { container } = renderApp("/");
    await screen.findByRole("heading", { name: "Bookings" });
    expect(container.querySelectorAll(".re-wordmark")).toHaveLength(1);
    expect(container.querySelector(".itaa-simulation-banner")).toBeNull();
    expect(container.querySelector(".itaa-stage-track")).toBeNull();
  });

  it("renders Activity, Preferences, Privacy & data, and Account & plan", async () => {
    const user = userEvent.setup();
    renderApp("/");
    await user.click((await screen.findAllByRole("link", { name: "Activity" }))[0]!);
    expect(await screen.findByRole("heading", { name: "Activity" })).toBeInTheDocument();
    expect(screen.getByText(/You authorized \$71\.40/)).toBeInTheDocument();
    await user.click(screen.getAllByRole("link", { name: "Preferences" })[0]!);
    expect(await screen.findByRole("heading", { name: "Preferences" })).toBeInTheDocument();
    expect(screen.getByText(/never sent to a supplier/i)).toBeInTheDocument();
    await user.click(screen.getAllByRole("link", { name: "Privacy & data" })[0]!);
    expect(await screen.findByRole("heading", { name: "Your data" })).toBeInTheDocument();
    await user.click(screen.getAllByRole("link", { name: "Account & plan" })[0]!);
    expect(await screen.findByRole("heading", { name: "Reservedge Plus" })).toBeInTheDocument();
    expect(screen.getByText(/No subscription is charged/)).toBeInTheDocument();
  });

  it("filters the inbox, deletes a seed draft, and redirects /inbox", async () => {
    const user = userEvent.setup();
    renderApp("/inbox");
    expect(await screen.findByRole("heading", { name: "Bookings" })).toBeInTheDocument();
    await user.click(screen.getByRole("tab", { name: "Pending" }));
    expect(screen.getByText(/paused by you/i)).toBeInTheDocument();
    await user.click(screen.getByRole("tab", { name: "Running" }));
    expect(screen.getByText(/LGA parking/i)).toBeInTheDocument();
    await user.click(screen.getByRole("tab", { name: "Needs you" }));
    await user.click(screen.getByRole("button", { name: "Delete JFK airport parking · Sep 4–8" }));
    expect(screen.queryByRole("button", { name: /JFK airport parking · Sep 4–8/ })).toBeNull();
  });

  it("shows the not-found screen for an unknown route", async () => {
    renderApp("/no-such-route");
    expect(
      await screen.findByRole("heading", { name: "This page is not part of the demo" }),
    ).toBeInTheDocument();
  });

  it("renders InboxWelcome for selected, pending, and empty states", () => {
    const decision = SEED_INTENTS.find((row) => row.status === "decision")!;
    const pending = SEED_INTENTS.find((row) => row.status === "pending")!;
    const done = SEED_INTENTS.find((row) => row.status === "done")!;
    const empty = render(<InboxWelcome selected={null} />);
    expect(screen.getByText(/Select an intent from the list/)).toBeInTheDocument();
    empty.unmount();
    const live = render(<InboxWelcome selected={decision} />);
    expect(screen.getByRole("button", { name: "Keep pending" })).toBeInTheDocument();
    live.unmount();
    const paused = render(<InboxWelcome selected={pending} />);
    expect(screen.getByRole("button", { name: "Resume" })).toBeInTheDocument();
    paused.unmount();
    render(<InboxWelcome selected={done} />);
    expect(screen.getByText(/Kept in history/)).toBeInTheDocument();
  });
});
