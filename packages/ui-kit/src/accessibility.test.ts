import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import {
  FOCUS_RING_CLASS,
  buttonHtml,
  liveRegionHtml,
  renderStylesheet,
  shouldAnnounce,
  simulationBannerHtml,
  statusIndicatorHtml,
  visuallyHiddenHtml,
  withFocusRing,
} from "./index.js";

const harness = readFileSync(
  join(dirname(fileURLToPath(import.meta.url)), "..", "harness", "index.html"),
  "utf8",
);

test("visually hidden helper keeps text for assistive technology", () => {
  const html = visuallyHiddenHtml("Working", "busy-note");
  assert.match(html, /itaa-visually-hidden/);
  assert.match(html, /id="busy-note"/);
  assert.match(html, /Working/);
});

test("live region avoids duplicate announcements and defaults to polite", () => {
  assert.equal(shouldAnnounce("", "Saved"), true);
  assert.equal(shouldAnnounce("Saved", "Saved"), false);
  assert.equal(shouldAnnounce("Saved", ""), false);
  const polite = liveRegionHtml({ message: "Status updated" });
  assert.match(polite, /aria-live="polite"/);
  assert.match(polite, /role="status"/);
  assert.match(polite, /itaa-visually-hidden/);
  const assertive = liveRegionHtml({ message: "Failed", politeness: "assertive", visible: true });
  assert.match(assertive, /role="alert"/);
  assert.match(assertive, /aria-live="assertive"/);
  assert.doesNotMatch(assertive, /itaa-visually-hidden/);
});

test("focus treatment is visible and shared", () => {
  assert.equal(withFocusRing("itaa-button"), `itaa-button ${FOCUS_RING_CLASS}`);
  const css = renderStylesheet();
  assert.match(css, /\.itaa-focus-ring:focus-visible/);
  assert.match(css, /outline:\s*var\(--itaa-focus-width\) solid var\(--itaa-color-focus\)/);
});

test("reduced motion disables nonessential transitions", () => {
  const css = renderStylesheet();
  assert.match(css, /prefers-reduced-motion:\s*reduce/);
  assert.match(css, /--itaa-motion-duration:\s*0ms/);
  assert.doesNotMatch(css, /@keyframes/);
  assert.doesNotMatch(css, /bounce|spring|confetti|pulse/i);
  assert.match(harness, /id="reduced-motion"/);
});

test("interactive primitives meet the 44px target and remain unclipped at large text", () => {
  const css = renderStylesheet();
  assert.match(css, /\.itaa-button[^{]*\{[^}]*min-height:\s*var\(--itaa-touch-min\)/);
  assert.match(css, /\.itaa-button[^{]*\{[^}]*min-width:\s*var\(--itaa-touch-min\)/);
  assert.match(css, /\.itaa-button[^{]*\{[^}]*font-size:\s*var\(--itaa-font-size-body\)/);
  assert.match(css, /\.itaa-status[^{]*\{[^}]*font-size:\s*var\(--itaa-font-size-body\)/);
  assert.match(
    css,
    /\.itaa-simulation-banner[^{]*\{[^}]*font-size:\s*var\(--itaa-font-size-body\)/,
  );
  assert.doesNotMatch(css, /\.itaa-button[^{]*\{[^}]*overflow:\s*hidden/);
  assert.doesNotMatch(css, /\.itaa-status[^{]*\{[^}]*overflow:\s*hidden/);
  assert.match(harness, /id="zoom-200"/);

  const button = buttonHtml({ label: "Continue" });
  const status = statusIndicatorHtml({ variant: "working", label: "Working" });
  const banner = simulationBannerHtml({ density: "compact" });
  assert.match(button, /itaa-button__label/);
  assert.match(status, /Working/);
  assert.match(banner, /SIMULATED - NO REAL CHARGES OR RESERVATIONS/);
});

test("harness includes a keyboard focus sequence", () => {
  assert.match(harness, /id="focus-sequence"/);
  assert.match(harness, /tabindex="0"|itaa-button/i);
});
