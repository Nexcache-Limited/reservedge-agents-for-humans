import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it } from "vitest";
import { AppRoutes } from "./App.js";
import { inferDomain } from "./intent-first/objective.js";
import { mockApi } from "./test/fixtures.js";

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

describe("intent-first React composer", () => {
  it("opens on an editable objective composer, not a domain-card picker", async () => {
    renderApp("/");
    const heading = await screen.findByRole("heading", {
      name: "What are you planning or trying to get done?",
    });
    expect(heading).toBeInTheDocument();
    expect(screen.getByText("Nothing is sent to any supplier from this step.")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "What do you need?" })).toBeNull();
    const field = screen.getByRole("textbox", {
      name: "What are you planning or trying to get done?",
    });
    field.focus();
    expect(field).toHaveFocus();
    expect(screen.getByRole("button", { name: "Start booking" })).toBeDisabled();
  });

  it("accepts typed text and keeps Start booking disabled until there is content", async () => {
    const user = userEvent.setup();
    renderApp("/");
    const field = await screen.findByRole("textbox", {
      name: "What are you planning or trying to get done?",
    });
    expect(screen.getByRole("button", { name: "Start booking" })).toBeDisabled();
    await user.type(field, "Airport parking at JFK next Thursday");
    expect(field).toHaveValue("Airport parking at JFK next Thursday");
    expect(screen.getByRole("button", { name: "Start booking" })).toBeEnabled();
  });

  it("applies a suggestion chip and leaves the text editable", async () => {
    const user = userEvent.setup();
    renderApp("/");
    await user.click(
      await screen.findByRole("button", { name: "Airport parking for a work trip on Thursday" }),
    );
    const field = screen.getByRole("textbox", {
      name: "What are you planning or trying to get done?",
    });
    expect(field).toHaveValue("Airport parking for a work trip on Thursday");
    expect(field).toHaveFocus();
    await user.type(field, " plus a compact");
    expect(field).toHaveValue("Airport parking for a work trip on Thursday plus a compact");
    expect(
      screen.getByText("Suggestion applied. You can edit it before starting."),
    ).toBeInTheDocument();
  });

  it("opens Clarify & plan from Start booking instead of a domain form", async () => {
    const user = userEvent.setup();
    renderApp("/");
    await user.type(
      await screen.findByRole("textbox", {
        name: "What are you planning or trying to get done?",
      }),
      "Airport parking at JFK next Thursday",
    );
    await user.click(screen.getByRole("button", { name: "Start booking" }));
    expect(await screen.findAllByText("Clarify & plan")).not.toHaveLength(0);
    expect(screen.getByText("Airport parking at JFK next Thursday")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Send to Reservedge" })).toBeNull();
  });

  it("uses a domain shortcut as a secondary one-task start", async () => {
    const user = userEvent.setup();
    renderApp("/intents/new");
    expect(
      await screen.findByRole("heading", { name: "What are you planning or trying to get done?" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Already know the exact booking?")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Pk Airport parking" }));
    expect(await screen.findByRole("button", { name: "Send to Reservedge" })).toBeInTheDocument();
    expect(screen.getByText("Live competition path")).toBeInTheDocument();
  });

  it("opens an existing booking from the list", async () => {
    const user = userEvent.setup();
    renderApp("/");
    await user.click(await screen.findByRole("button", { name: /recommended \$71\.40/ }));
    expect(await screen.findByText("JetPark JFK")).toBeInTheDocument();
    expect(screen.getAllByText("Demonstration").length).toBeGreaterThan(0);
  });

  it("switches Intent, Bookings, and Activity tabs without losing composer text", async () => {
    const user = userEvent.setup();
    renderApp("/");
    const field = await screen.findByRole("textbox", {
      name: "What are you planning or trying to get done?",
    });
    await user.type(field, "Keep this objective");
    await user.click(document.querySelector(".re-tabs a[href='/bookings']") as HTMLAnchorElement);
    expect(await screen.findByRole("heading", { name: "Bookings" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /recommended \$71\.40/ })).toBeInTheDocument();
    await user.click(document.querySelector(".re-tabs a[href='/activity']") as HTMLAnchorElement);
    expect(await screen.findByRole("heading", { name: "Activity" })).toBeInTheDocument();
    await user.click(document.querySelector(".re-tabs a[href='/']") as HTMLAnchorElement);
    expect(
      await screen.findByRole("textbox", {
        name: "What are you planning or trying to get done?",
      }),
    ).toHaveValue("Keep this objective");
  });

  it("supports keyboard focus on the composer and Start booking", async () => {
    const user = userEvent.setup();
    renderApp("/");
    const field = await screen.findByRole("textbox", {
      name: "What are you planning or trying to get done?",
    });
    await user.click(field);
    await user.keyboard("Need airport parking at LGA");
    expect(field).toHaveValue("Need airport parking at LGA");
    const start = screen.getByRole("button", { name: "Start booking" });
    start.focus();
    expect(start).toHaveFocus();
    await user.keyboard("{Enter}");
    expect(await screen.findAllByText("Clarify & plan")).not.toHaveLength(0);
    expect(screen.queryByRole("button", { name: "Send to Reservedge" })).toBeNull();
  });
});

describe("intent-first domain inference", () => {
  it("routes parking, rental, and entertainment language to the matching one-task path", () => {
    expect(inferDomain("Airport parking for a work trip on Thursday")).toBe("parking");
    expect(inferDomain("Weekend away, driving, dog with us")).toBe("rental");
    expect(inferDomain("Two tickets for a concert")).toBe("ents");
    expect(inferDomain("Two nights in Edinburgh for a conference")).toBe("parking");
  });
});

describe("intent-first shell copy", () => {
  it("labels the list Bookings and keeps domain shortcuts out of the first heading", async () => {
    renderApp("/");
    expect(await screen.findByRole("heading", { name: "Bookings" })).toBeInTheDocument();
    const main = screen.getByRole("main");
    expect(within(main).queryByRole("heading", { name: "What do you need?" })).toBeNull();
    expect(screen.getAllByRole("link", { name: "Intent" }).length).toBeGreaterThan(0);
    expect(screen.getAllByRole("link", { name: "Bookings" }).length).toBeGreaterThan(0);
    expect(screen.getAllByRole("link", { name: "Activity" }).length).toBeGreaterThan(0);
  });
});
