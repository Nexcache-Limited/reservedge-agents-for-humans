import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AppRoutes } from "../App.js";
import { SAMPLE_JFK_TEXT } from "../reservedge/parking-intake.js";
import { rememberCompetitionIntent } from "../session/memory.js";
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

describe("COMP-G1-05 Phase 3 live parking workspace", () => {
  it("lands a confirmed parking intent on Reservedge chrome, not the ITAA workspace", async () => {
    const user = userEvent.setup();
    const confirmIntakeIntent = vi.fn(async () => snapshot());
    renderApp(
      "/intents/new/parking",
      mockApi({
        extractIntake: async () => intakeExtraction(),
        confirmIntakeIntent,
        getOwnedIntent: async () => snapshot(),
      }),
    );
    await user.click(await screen.findByRole("button", { name: /Use the example/ }));
    await user.click(screen.getByRole("button", { name: "Send to Reservedge" }));
    await user.click(
      await screen.findByRole("button", { name: "Confirm requirement and research" }),
    );
    await waitFor(() => expect(confirmIntakeIntent).toHaveBeenCalledTimes(1));
    const [confirmBody] = confirmIntakeIntent.mock.calls[0] as unknown as [Record<string, unknown>];
    expect(JSON.stringify(confirmBody)).not.toMatch(/flying from JFK|September 3/);
    expect(
      await screen.findByRole("tab", { name: "Request" }, { timeout: 10_000 }),
    ).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Research" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Offers" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Activity" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Keep pending" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Modify intent" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Cancel intent" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Confirm requirement" })).toBeInTheDocument();
    expect(screen.queryByText("Purchase Intent review")).not.toBeInTheDocument();
    expect(screen.queryByText("Return to Intent Inbox")).not.toBeInTheDocument();
    expect(screen.queryByText(/ITAA recommends/)).not.toBeInTheDocument();
    expect(screen.queryByText("JetPark")).not.toBeInTheDocument();
    expect(document.body.textContent ?? "").not.toContain(SAMPLE_JFK_TEXT);
  });

  it("keeps cancel and delete as distinct backend actions", async () => {
    const user = userEvent.setup();
    const deleteDraft = vi.fn(async () => undefined);
    const cancelIntent = vi.fn(async () => snapshot({ state: "CANCELLED" }));
    rememberCompetitionIntent("pi_01k2m3n4p5q6r7s8t9v0w1x2y3");
    renderApp(
      "/intents/pi_01k2m3n4p5q6r7s8t9v0w1x2y3",
      mockApi({ getOwnedIntent: async () => snapshot(), deleteDraft, cancelIntent }),
    );
    await user.click(await screen.findByRole("button", { name: "Cancel intent" }));
    expect(screen.getByRole("dialog", { name: "Delete this draft?" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Delete draft" }));
    await waitFor(() => expect(deleteDraft).toHaveBeenCalledTimes(1));
    expect(cancelIntent).not.toHaveBeenCalled();

    cleanup();
    const disclosedCancel = vi.fn(async () => snapshot({ state: "CANCELLED" }));
    const disclosedDelete = vi.fn(async () => undefined);
    renderApp(
      "/intents/pi_01k2m3n4p5q6r7s8t9v0w1x2y3",
      mockApi({
        getOwnedIntent: async () => snapshot({ state: "AWAITING_DISPATCH_APPROVAL" }),
        cancelIntent: disclosedCancel,
        deleteDraft: disclosedDelete,
      }),
    );
    await user.click(await screen.findByRole("button", { name: "Cancel intent" }));
    expect(screen.getByRole("dialog", { name: "Cancel this request?" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Cancel request" }));
    await waitFor(() => expect(disclosedCancel).toHaveBeenCalledTimes(1));
    expect(disclosedDelete).not.toHaveBeenCalled();
  });

  it("sends replace with a stable idempotency key and ignores a second in-flight confirm", async () => {
    const user = userEvent.setup();
    const replaceIntent = vi.fn(async () => ({
      previous: snapshot({ state: "SUPERSEDED" }),
      draft: snapshot({ intentId: "pi_01k2m3n4p5q6r7s8t9v0w1x2n1" }),
    }));
    renderApp(
      "/intents/pi_01k2m3n4p5q6r7s8t9v0w1x2y3",
      mockApi({
        getOwnedIntent: async (intentId) => snapshot({ intentId }),
        replaceIntent,
      }),
    );
    await user.click(await screen.findByRole("button", { name: "Modify intent" }));
    await user.click(screen.getByRole("button", { name: "Start a revised request" }));
    await user.click(screen.getByRole("button", { name: "Start revised request" }));
    await waitFor(() => expect(replaceIntent).toHaveBeenCalledTimes(1));
    const replaceArgs = replaceIntent.mock.calls[0] as unknown as [string, string];
    expect(replaceArgs[1]).toMatch(/^ik_/);
  });

  it("reads ranked offers from the owned snapshot without JetPark prototype values", async () => {
    renderApp(
      "/intents/pi_01k2m3n4p5q6r7s8t9v0w1x2y3",
      mockApi({ getOwnedIntent: async () => rankedSnapshot() }),
    );
    expect(await screen.findByText("Why this is recommended")).toBeInTheDocument();
    expect(screen.getByText("Confirm selected offer")).toBeInTheDocument();
    expect(screen.queryByText("JetPark")).not.toBeInTheDocument();
    expect(screen.queryByText("$71.40")).not.toBeInTheDocument();
    expect(document.body.textContent ?? "").not.toMatch(/\bA[1-4]\b/);
    expect(document.body.textContent ?? "").not.toContain("pi_01k2m3n4p5q6r7s8t9v0w1x2y3");
  });

  it("lists the owned intent in the inbox from the backend, not seed fixtures", async () => {
    const user = userEvent.setup();
    const remote = snapshot();
    renderApp(
      "/",
      mockApi({
        listIntents: async () => ({ needsYou: [remote], running: [], saved: [], history: [] }),
        getOwnedIntent: async () => remote,
      }),
    );
    const inboxRow = await screen.findByRole("button", {
      name: /Needs a confirmation before research/,
    });
    expect(inboxRow).toBeInTheDocument();
    expect(screen.queryByText("JetPark JFK")).not.toBeInTheDocument();
    await user.click(inboxRow);
    expect(await screen.findByRole("button", { name: "Keep pending" })).toBeInTheDocument();
  });

  it("closes the draft-delete dialog with Escape, Keep request, and the overlay backdrop", async () => {
    const user = userEvent.setup();
    rememberCompetitionIntent("pi_01k2m3n4p5q6r7s8t9v0w1x2y3");
    renderApp(
      "/intents/pi_01k2m3n4p5q6r7s8t9v0w1x2y3",
      mockApi({ getOwnedIntent: async () => snapshot() }),
    );
    await user.click(await screen.findByRole("button", { name: "Cancel intent" }));
    expect(screen.getByRole("dialog", { name: "Delete this draft?" })).toBeInTheDocument();
    fireEvent.keyDown(document.querySelector(".re-overlay")!, { key: "Escape" });
    expect(screen.queryByRole("dialog")).toBeNull();
    await user.click(screen.getByRole("button", { name: "Cancel intent" }));
    await user.click(screen.getByRole("button", { name: "Keep request" }));
    expect(screen.queryByRole("dialog")).toBeNull();
    await user.click(screen.getByRole("button", { name: "Cancel intent" }));
    fireEvent.click(document.querySelector(".re-overlay")!);
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("deletes a live inbox draft through the list without cancelling", async () => {
    const user = userEvent.setup();
    const remote = snapshot();
    const deleteDraft = vi.fn(async () => undefined);
    renderApp(
      "/",
      mockApi({
        listIntents: async () => ({ needsYou: [remote], running: [], saved: [], history: [] }),
        getOwnedIntent: async () => remote,
        deleteDraft,
      }),
    );
    await screen.findByRole("button", { name: /Needs a confirmation before research/ });
    await user.click(screen.getByRole("button", { name: /Delete Airport parking/ }));
    await waitFor(() => expect(deleteDraft).toHaveBeenCalledTimes(1));
  });
});
