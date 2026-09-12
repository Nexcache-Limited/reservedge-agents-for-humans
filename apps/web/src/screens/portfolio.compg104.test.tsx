import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ClosedApiError } from "../api/errors.js";
import { AppRoutes } from "../App.js";
import { rememberCompetitionIntent, rememberSnapshot } from "../session/memory.js";
import { mockApi, rankedSnapshot, snapshot } from "../test/fixtures.js";
import { STATE_LABEL, STATE_TO_STAGE } from "../view-models/workspace.js";

afterEach(() => {
  cleanup();
  sessionStorage.clear();
});

describe("COMP-G1-04 portfolio UI", () => {
  it("maps cancelled and superseded as distinct buyer outcomes", () => {
    expect(STATE_LABEL.CANCELLED).toBe("Cancelled");
    expect(STATE_LABEL.SUPERSEDED).toBe("Replaced");
    expect(STATE_LABEL.TRANSACTION_AUTHORIZED_SIMULATED).toBe("Completed");
    expect(STATE_TO_STAGE.CANCELLED).toBe("requirement");
    expect(STATE_TO_STAGE.SUPERSEDED).toBe("requirement");
  });

  it("filters ten requests across Needs you, Saved, and History without showing opaque ids", async () => {
    const user = userEvent.setup();
    const needsYou = Array.from({ length: 6 }, (_, index) =>
      snapshot({
        intentId: `pi_01k2m3n4p5q6r7s8t9v0w1x2n${index}`,
        airport: "JFK",
        updatedAt: `2026-08-2${index}T15:00:00Z`,
      }),
    );
    const saved = [
      snapshot({
        intentId: "pi_01k2m3n4p5q6r7s8t9v0w1x2s1",
        state: "AWAITING_DISPATCH_APPROVAL",
        saved: true,
        savedAt: "2026-08-21T16:00:00Z",
      }),
    ];
    const history = [
      snapshot({
        intentId: "pi_01k2m3n4p5q6r7s8t9v0w1x2h1",
        state: "TRANSACTION_AUTHORIZED_SIMULATED",
        updatedAt: "2026-08-22T15:00:00Z",
      }),
      snapshot({
        intentId: "pi_01k2m3n4p5q6r7s8t9v0w1x2h2",
        state: "CANCELLED",
        updatedAt: "2026-08-22T14:00:00Z",
      }),
      snapshot({
        intentId: "pi_01k2m3n4p5q6r7s8t9v0w1x2h3",
        state: "SUPERSEDED",
        updatedAt: "2026-08-22T13:00:00Z",
      }),
    ];
    render(
      <MemoryRouter initialEntries={["/"]}>
        <AppRoutes
          api={mockApi({
            listIntents: async () => ({ needsYou, running: [], saved, history }),
          })}
        />
      </MemoryRouter>,
    );
    await user.click(await screen.findByRole("tab", { name: "Needs you" }));
    expect(
      within(screen.getByLabelText("Your booking chats")).getAllByText(/Airport parking · JFK/),
    ).toHaveLength(6);
    expect(document.body.textContent ?? "").not.toMatch(/pi_/);
    await user.click(screen.getByRole("tab", { name: "Pending" }));
    expect(await screen.findByText("Paused before disclosure.")).toBeInTheDocument();
    await user.click(screen.getByRole("tab", { name: "History" }));
    expect(await screen.findByText("Completed")).toBeInTheDocument();
    expect(screen.getAllByText("Cancelled by you").length).toBeGreaterThan(0);
    expect(screen.getByText("Replaced")).toBeInTheDocument();
    await user.click(screen.getByRole("tab", { name: "Running" }));
    expect(await screen.findByText("Nothing here.")).toBeInTheDocument();
  });

  it("confirms cancel, delete, replace, and save-for-later from the workspace", async () => {
    const user = userEvent.setup();
    const cancelIntent = vi.fn(async () => snapshot({ state: "CANCELLED" }));
    const deleteDraft = vi.fn(async () => undefined);
    const replaceIntent = vi.fn(async (intentId: string, idempotencyKey: string) => {
      expect(intentId).toMatch(/^pi_/);
      expect(idempotencyKey).toMatch(/^ik_/);
      return {
        previous: snapshot({ state: "SUPERSEDED" }),
        draft: snapshot({ intentId: "pi_01k2m3n4p5q6r7s8t9v0w1x2n1" }),
      };
    });
    const saveIntent = vi.fn(async () =>
      snapshot({ saved: true, savedAt: "2026-08-20T16:00:00Z" }),
    );
    rememberCompetitionIntent("pi_01k2m3n4p5q6r7s8t9v0w1x2y3");
    render(
      <MemoryRouter initialEntries={["/intents/pi_01k2m3n4p5q6r7s8t9v0w1x2y3"]}>
        <AppRoutes
          api={mockApi({
            getOwnedIntent: async () => snapshot(),
            getSnapshot: async () => snapshot(),
            cancelIntent,
            deleteDraft,
            replaceIntent,
            saveIntent,
            intentActivity: async () => [
              { occurredAt: "2026-08-20T15:00:00Z", label: "Request created" },
              { occurredAt: "2026-08-21T09:00:00Z", label: "Request cancelled" },
            ],
          })}
        />
      </MemoryRouter>,
    );
    expect(await screen.findByText("Request created for JFK parking")).toBeInTheDocument();
    expect(screen.getByText("20 Aug 2026 15:00")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Keep pending" }));
    await waitFor(() => expect(saveIntent).toHaveBeenCalled());
    await user.click(screen.getByRole("button", { name: "Cancel intent" }));
    expect(screen.getByRole("dialog", { name: "Delete this draft?" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Keep request" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Modify intent" }));
    await user.click(screen.getByRole("button", { name: "Start a revised request" }));
    await user.click(screen.getByRole("button", { name: "Start revised request" }));
    await waitFor(() => expect(replaceIntent).toHaveBeenCalled());
    expect(replaceIntent.mock.calls[0]?.[1]).toMatch(/^ik_/);
  });

  it("keeps a single simulation disclosure on inbox and workspace routes", async () => {
    render(
      <MemoryRouter initialEntries={["/"]}>
        <AppRoutes api={mockApi()} />
      </MemoryRouter>,
    );
    expect((await screen.findAllByText("Simulation mode")).length).toBeGreaterThan(0);
    expect(screen.getAllByText("SIM").length).toBeGreaterThan(0);
  });

  it("does not print A1–A4, Gate, WP, process-memory, or opaque ids in customer copy", async () => {
    rememberSnapshot(snapshot());
    render(
      <MemoryRouter initialEntries={["/intents/pi_01k2m3n4p5q6r7s8t9v0w1x2y3"]}>
        <AppRoutes
          api={mockApi({
            getOwnedIntent: async () => rankedSnapshot(),
            intentActivity: async () => [
              { occurredAt: "2026-08-20T15:00:00Z", label: "Three simulated suppliers contacted" },
            ],
          })}
        />
      </MemoryRouter>,
    );
    expect(await screen.findByText("Why this is recommended")).toBeInTheDocument();
    expect(await screen.findByText("Three simulated suppliers contacted")).toBeInTheDocument();
    const visible = document.body.textContent ?? "";
    expect(visible).not.toMatch(/\bA[1-4]\b/);
    expect(visible).not.toMatch(/\bGate\b/);
    expect(visible).not.toMatch(/\bWP-0/);
    expect(visible).not.toMatch(/process-memory/);
    expect(visible).not.toMatch(/schema paths/i);
    expect(visible).not.toContain("pi_01k2m3n4p5q6r7s8t9v0w1x2y3");
    expect(visible).toContain("Confirm selected offer");
  });

  it("treats a foreign or unknown request as the same closed recovery", async () => {
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
    expect(document.body.textContent ?? "").not.toMatch(/does not exist|not found for owner/i);
  });
});
