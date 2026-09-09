import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it } from "vitest";
import { AppRoutes } from "../App.js";
import { mockApi } from "../test/fixtures.js";

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

describe("COMP-G1-05 Reservedge workspace", () => {
  it("opens on a blank competition start instead of the JetPark seed", async () => {
    renderApp("/");
    const main = screen.getByRole("main");
    expect(
      await within(main).findByRole("heading", {
        name: "What are you planning or trying to get done?",
      }),
    ).toBeInTheDocument();
    expect(within(main).queryByText("JetPark JFK")).not.toBeInTheDocument();
    expect(within(main).queryByText("$71.40")).not.toBeInTheDocument();
  });

  it("still opens the JetPark seed when that sample is selected", async () => {
    const user = userEvent.setup();
    renderApp("/");
    await user.click(await screen.findByRole("button", { name: /recommended \$71\.40/ }));
    expect(await screen.findByText("JetPark JFK")).toBeInTheDocument();
    expect(screen.getByText("$71.40")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Take this one" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Compare all three" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Recommendation" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Compare offers" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Disclosure record" })).toBeInTheDocument();
    expect(screen.getByText("WHY THIS ONE")).toBeInTheDocument();
  });

  it("shows the simulated receipt for the July history intent", async () => {
    const user = userEvent.setup();
    renderApp("/");
    await user.click(await screen.findByRole("tab", { name: "History" }));
    await user.click(screen.getByRole("button", { name: /JFK parking · Jul 2–6/ }));
    expect(await screen.findByText("Authorization recorded")).toBeInTheDocument();
    expect(screen.getByText("SIMULATED")).toBeInTheDocument();
    expect(screen.getByText("SIM-3B77")).toBeInTheDocument();
    expect(screen.getByText("$44.10")).toBeInTheDocument();
  });

  it("opens the intent-first composer instead of the ITAA composer", async () => {
    renderApp("/intents/new");
    expect(
      await screen.findByRole("heading", { name: "What are you planning or trying to get done?" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Pk Airport parking" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Rc Rental car" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "En Entertainment booking" })).toBeInTheDocument();
    expect(screen.queryByText(/Spa is next/i)).not.toBeInTheDocument();
    expect(screen.queryByText("Analyse requirement")).not.toBeInTheDocument();
    expect(screen.queryByText(/ITAA extracts/i)).not.toBeInTheDocument();
  });

  it("walks the same composer for parking, rental, and entertainment", async () => {
    const user = userEvent.setup();
    const parking = renderApp("/intents/new/parking");
    expect(await screen.findByText("Send to Reservedge")).toBeInTheDocument();
    expect(screen.getByText("REQUIREMENT · BUILDING")).toBeInTheDocument();
    expect(screen.getByText("Live competition path")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Use the example/ }));
    await user.click(screen.getByRole("button", { name: "Send to Reservedge" }));
    expect(await screen.findByText(/No extra questions were needed/)).toBeInTheDocument();
    parking.unmount();

    const rental = renderApp("/intents/new/rental");
    await user.click(await screen.findByRole("button", { name: /Use the example/ }));
    await user.click(screen.getByRole("button", { name: "Send to Reservedge" }));
    await user.click(screen.getByRole("button", { name: /Match flight/ }));
    await user.click(screen.getByRole("button", { name: "Mid-size SUV" }));
    expect(screen.getByText(/QUESTION 3 OF 3/)).toBeInTheDocument();
    expect(
      screen.getByText(/Required — suppliers in this domain cannot price without it/),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Skip this" })).not.toBeInTheDocument();
    rental.unmount();

    renderApp("/intents/new/ents");
    expect(
      await screen.findByRole("heading", { name: "Entertainment booking" }),
    ).toBeInTheDocument();
    expect(screen.getAllByText(/Simulated demonstration/).length).toBeGreaterThan(0);
  });

  it("opens the authorization modal from Take this one", async () => {
    const user = userEvent.setup();
    renderApp("/");
    await user.click(await screen.findByRole("button", { name: /recommended \$71\.40/ }));
    await user.click(await screen.findByRole("button", { name: "Take this one" }));
    expect(screen.getByRole("dialog")).toHaveTextContent("Authorize this purchase");
    expect(screen.getByText(/APPROVAL 2 OF 2/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Authorize $71.40" })).toBeInTheDocument();
  });

  it("walks seed compare, disclosure, research, activity, and cancel", async () => {
    const user = userEvent.setup();
    renderApp("/");
    await user.click(await screen.findByRole("button", { name: /recommended \$71\.40/ }));
    await user.click(await screen.findByRole("button", { name: "Compare all three" }));
    expect(screen.getByText("DIMENSION")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Disclosure record" }));
    expect(screen.getByRole("heading", { name: /What was sent/ })).toBeInTheDocument();
    await user.click(screen.getByRole("tab", { name: "Research" }));
    expect(screen.getByText(/PUBLIC RESEARCH/)).toBeInTheDocument();
    await user.click(screen.getByRole("tab", { name: "Request" }));
    expect(screen.getAllByText(/Airport parking|REQUIREMENT/).length).toBeGreaterThan(0);
    await user.click(screen.getByRole("tab", { name: "Activity" }));
    expect(document.querySelector(".re-audit")).not.toBeNull();
    await user.click(screen.getByRole("button", { name: "Cancel intent" }));
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it("opens the rental incomplete-offer re-ask from compare", async () => {
    const user = userEvent.setup();
    renderApp("/");
    await user.click((await screen.findAllByRole("button", { name: /Rental car from JFK/ }))[0]!);
    await user.click(await screen.findByRole("button", { name: "Compare offers" }));
    expect(await screen.findByRole("button", { name: "Answer and re-ask" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Answer and re-ask" }));
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it("resumes the Boston disclosure gate and walks supplier progress", async () => {
    const user = userEvent.setup();
    renderApp("/");
    await user.click(await screen.findByRole("tab", { name: "Pending" }));
    await user.click(screen.getAllByRole("button", { name: /Rental car · Boston/ })[0]!);
    await user.click(await screen.findByRole("button", { name: "Resume" }));
    await user.click(await screen.findByRole("button", { name: "Send this request" }));
    await user.click(await screen.findByRole("button", { name: "See the recommendation" }));
    expect(screen.getAllByText(/Recommended|WHY THIS ONE/i).length).toBeGreaterThan(0);
  });

  it("keeps a seed pending, opens modify, and sends a rental re-ask", async () => {
    const user = userEvent.setup();
    renderApp("/");
    await user.click(await screen.findByRole("button", { name: /recommended \$71\.40/ }));
    await user.click(await screen.findByRole("button", { name: "Keep pending" }));
    expect(await screen.findByText(/Paused by you at/i)).toBeInTheDocument();
    await user.click(screen.getAllByRole("button", { name: /Rental car from JFK/ })[0]!);
    await user.click(await screen.findByRole("button", { name: "Modify intent" }));
    expect(screen.getByRole("heading", { name: "Modify this intent?" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Never mind" }));
    await user.click(screen.getByRole("button", { name: "Compare offers" }));
    await user.click(await screen.findByRole("button", { name: "Answer and re-ask" }));
    await user.click(screen.getByRole("button", { name: "Review the new disclosure" }));
    await user.click(await screen.findByRole("button", { name: "Send this one field" }));
    expect(screen.getAllByText(/complete/i).length).toBeGreaterThan(0);
  });

  it("opens a seed intent by route, dismisses overlays, and shows July activity", async () => {
    const user = userEvent.setup();
    renderApp("/intents/jfk");
    expect(await screen.findByText("JetPark JFK")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Take this one" }));
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    fireEvent.keyDown(document.querySelector(".re-overlay")!, { key: "Escape" });
    expect(screen.queryByRole("dialog")).toBeNull();
    await user.click(screen.getByRole("button", { name: "Take this one" }));
    fireEvent.click(document.querySelector(".re-overlay")!);
    expect(screen.queryByRole("dialog")).toBeNull();
    cleanup();
    renderApp("/intents/jfkjul");
    expect(await screen.findByText("Authorization recorded")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "View this intent's activity" }));
    expect(document.querySelector(".re-audit")).not.toBeNull();
  });
});
