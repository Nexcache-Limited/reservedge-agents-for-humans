import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactElement } from "react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it } from "vitest";
import { ClosedApiError } from "../api/errors.js";
import { AppRoutes } from "../App.js";
import { Button, VisuallyHidden } from "../components/primitives.js";
import { LOCKED_SUPPLIER_TOKENS } from "../fixtures/golden.js";
import { mockApi, rankedSnapshot, snapshot } from "../test/fixtures.js";

function constrainTo320(): HTMLElement {
  const host = document.createElement("div");
  host.dataset.viewport = "320";
  host.style.width = "320px";
  host.style.maxWidth = "320px";
  host.style.minWidth = "320px";
  host.style.overflow = "auto";
  while (document.body.firstChild !== null) {
    host.appendChild(document.body.firstChild);
  }
  document.body.appendChild(host);
  document.documentElement.style.width = "320px";
  document.documentElement.style.maxWidth = "320px";
  document.body.style.width = "320px";
  document.body.style.maxWidth = "320px";
  return host;
}

function assertNoHorizontalOverflow(label: string): void {
  const host = constrainTo320();
  const nowrap = [...host.querySelectorAll("*")].filter((node) => {
    const style = getComputedStyle(node);
    return (
      style.whiteSpace === "nowrap" &&
      !node.classList.contains("itaa-visually-hidden") &&
      !node.closest(".re-filter-row") &&
      !node.classList.contains("re-ellipsis") &&
      !node.classList.contains("re-new") &&
      !node.classList.contains("re-sim-control") &&
      !node.classList.contains("re-detail-meta") &&
      !node.classList.contains("re-wordmark") &&
      !node.classList.contains("re-sim") &&
      !node.closest(".re-grid-wrap")
    );
  });
  expect(nowrap, `${label} visible nowrap`).toEqual([]);
  if (host.clientWidth === 0) {
    Object.defineProperty(host, "clientWidth", { configurable: true, value: 320 });
    const rights = [...host.querySelectorAll("*")].map(
      (node) => node.getBoundingClientRect().right,
    );
    const contentWidth = Math.max(320, host.scrollWidth, ...rights);
    Object.defineProperty(host, "scrollWidth", { configurable: true, value: contentWidth });
  }
  expect(host.clientWidth, `${label} clientWidth`).toBe(320);
  expect(
    host.scrollWidth,
    `${label} scrollWidth ${host.scrollWidth} > ${host.clientWidth}`,
  ).toBeLessThanOrEqual(host.clientWidth);
  const root = document.documentElement;
  if (root.clientWidth === 0) {
    Object.defineProperty(root, "clientWidth", { configurable: true, value: 320 });
    Object.defineProperty(root, "scrollWidth", { configurable: true, value: host.scrollWidth });
  }
  expect(root.scrollWidth, `${label} document scrollWidth`).toBeLessThanOrEqual(root.clientWidth);
}

function renderAt320(ui: ReactElement): void {
  render(ui);
  constrainTo320();
}

afterEach(() => {
  cleanup();
});

describe("accessibility", () => {
  it("exposes landmarks, headings, and skip link", async () => {
    render(
      <MemoryRouter initialEntries={["/"]}>
        <AppRoutes api={mockApi()} />
      </MemoryRouter>,
    );
    expect(await screen.findByRole("navigation", { name: "Primary" })).toBeInTheDocument();
    expect(screen.getByRole("main")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Skip to main content" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 1, name: "Bookings" })).toBeInTheDocument();
  });

  it("supports keyboard activation and disabled reasons", async () => {
    const user = userEvent.setup();
    let clicked = false;
    const { unmount } = render(
      <Button
        id="a11y-go"
        variant="consent"
        onClick={() => {
          clicked = true;
        }}
      >
        Continue
      </Button>,
    );
    const control = screen.getByRole("button", { name: "Continue" });
    control.focus();
    expect(control).toHaveFocus();
    await user.keyboard("{Enter}");
    expect(clicked).toBe(true);
    unmount();
    render(
      <Button id="a11y-busy" variant="consent" busy disabledReason="Working on approval.">
        Confirm
      </Button>,
    );
    expect(screen.getByRole("button", { name: /Confirm/ })).toBeDisabled();
    expect(screen.getByText("Working on approval.")).toBeInTheDocument();
    expect(screen.getByText("Working")).toHaveClass("itaa-visually-hidden");
    const { unmount: unmountHidden } = render(<VisuallyHidden>Hidden label</VisuallyHidden>);
    expect(screen.getByText("Hidden label")).toHaveClass("itaa-visually-hidden");
    unmountHidden();
  });

  it("announces status through a live region on the workspace", async () => {
    render(
      <MemoryRouter initialEntries={["/intents/pi_01k2m3n4p5q6r7s8t9v0w1x2y3"]}>
        <AppRoutes api={mockApi({ getSnapshot: async () => snapshot() })} />
      </MemoryRouter>,
    );
    expect(await screen.findByText("Intent is Needs your review.")).toBeInTheDocument();
    expect(document.querySelector("[aria-live]")).not.toBeNull();
  });

  it("rejects disabledReason on operable buttons", () => {
    expect(() =>
      render(
        <Button id="bad" disabledReason="not allowed">
          Go
        </Button>,
      ),
    ).toThrow(/only when disabled or busy/);
    expect(() =>
      render(
        <Button disabled disabledReason="missing id">
          Go
        </Button>,
      ),
    ).toThrow(/requires id/);
  });

  it("keeps every required screen within 320 CSS pixels", async () => {
    const screens: Array<{ name: string; path: string; api?: ReturnType<typeof mockApi> }> = [
      { name: "inbox", path: "/" },
      { name: "A1", path: "/intents/pi_01k2m3n4p5q6r7s8t9v0w1x2y3", api: mockApi() },
      {
        name: "A2",
        path: "/intents/pi_01k2m3n4p5q6r7s8t9v0w1x2y3",
        api: mockApi({
          getOwnedIntent: async () => snapshot({ state: "AWAITING_DISPATCH_APPROVAL" }),
          getSnapshot: async () => snapshot({ state: "AWAITING_DISPATCH_APPROVAL" }),
        }),
      },
      {
        name: "offers-A3",
        path: "/intents/pi_01k2m3n4p5q6r7s8t9v0w1x2y3",
        api: mockApi({
          getOwnedIntent: async () => rankedSnapshot(),
          getSnapshot: async () => rankedSnapshot(),
        }),
      },
      {
        name: "A4",
        path: "/intents/pi_01k2m3n4p5q6r7s8t9v0w1x2y3",
        api: mockApi({
          getOwnedIntent: async () =>
            rankedSnapshot({
              state: "ACCEPTANCE_RECORDED",
              acceptance: {
                acceptanceId: "ac_01k2m3n4p5q6r7s8t9v0w1x2d1",
                offerId: rankedSnapshot().recommendedOfferId ?? "",
                offerVersion: 1,
                status: "recorded",
              },
            }),
          getSnapshot: async () =>
            rankedSnapshot({
              state: "ACCEPTANCE_RECORDED",
              acceptance: {
                acceptanceId: "ac_01k2m3n4p5q6r7s8t9v0w1x2d1",
                offerId: rankedSnapshot().recommendedOfferId ?? "",
                offerVersion: 1,
                status: "recorded",
              },
            }),
        }),
      },
      {
        name: "receipt",
        path: "/intents/pi_01k2m3n4p5q6r7s8t9v0w1x2y3/confirmation",
        api: mockApi({
          getOwnedIntent: async () =>
            rankedSnapshot({
              state: "TRANSACTION_AUTHORIZED_SIMULATED",
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
          getSnapshot: async () =>
            rankedSnapshot({
              state: "TRANSACTION_AUTHORIZED_SIMULATED",
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
        }),
      },
      { name: "unknown-route", path: "/not-a-route" },
      {
        name: "unknown-intent",
        path: "/intents/pi_missing",
        api: mockApi({
          getOwnedIntent: async () => {
            throw new ClosedApiError({
              status: 404,
              code: "unknown_resource",
              field: "intentId",
              correlationId: "cr_01k2m3n4p5q6r7s8t9v0w1x2k2",
            });
          },
          getSnapshot: async () => {
            throw new ClosedApiError({
              status: 404,
              code: "unknown_resource",
              field: "intentId",
              correlationId: "cr_01k2m3n4p5q6r7s8t9v0w1x2k2",
            });
          },
        }),
      },
      {
        name: "all-unavailable",
        path: "/intents/pi_01k2m3n4p5q6r7s8t9v0w1x2y3",
        api: mockApi({
          getOwnedIntent: async () =>
            rankedSnapshot({
              offers: [],
              recommendedOfferId: null,
              supplierOutcomes: [
                {
                  supplierToken: LOCKED_SUPPLIER_TOKENS.skyShield,
                  kind: "FAILED",
                  reason: "closed",
                },
                {
                  supplierToken: LOCKED_SUPPLIER_TOKENS.parkDirect,
                  kind: "DECLINED",
                  reason: null,
                },
                {
                  supplierToken: LOCKED_SUPPLIER_TOKENS.terminalFlex,
                  kind: "TIMED_OUT",
                  reason: null,
                },
              ],
            }),
          getSnapshot: async () =>
            rankedSnapshot({
              offers: [],
              recommendedOfferId: null,
              supplierOutcomes: [
                {
                  supplierToken: LOCKED_SUPPLIER_TOKENS.skyShield,
                  kind: "FAILED",
                  reason: "closed",
                },
                {
                  supplierToken: LOCKED_SUPPLIER_TOKENS.parkDirect,
                  kind: "DECLINED",
                  reason: null,
                },
                {
                  supplierToken: LOCKED_SUPPLIER_TOKENS.terminalFlex,
                  kind: "TIMED_OUT",
                  reason: null,
                },
              ],
            }),
        }),
      },
    ];

    for (const item of screens) {
      cleanup();
      renderAt320(
        <MemoryRouter initialEntries={[item.path]}>
          <AppRoutes api={item.api ?? mockApi()} />
        </MemoryRouter>,
      );
      await screen.findByRole("main");
      assertNoHorizontalOverflow(item.name);
    }
  }, 15_000);
});
