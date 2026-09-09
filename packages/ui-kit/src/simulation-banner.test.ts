import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import {
  SIMULATION_BANNER_LABEL,
  SIMULATION_BANNER_PLACEMENTS,
  renderStylesheet,
  simulationBannerHtml,
} from "./index.js";

const harness = readFileSync(
  join(dirname(fileURLToPath(import.meta.url)), "..", "harness", "index.html"),
  "utf8",
);
const compactFixture = readFileSync(
  join(
    dirname(fileURLToPath(import.meta.url)),
    "..",
    "harness",
    "fixtures",
    "simulation-banner-compact.html",
  ),
  "utf8",
);
const wideFixture = readFileSync(
  join(
    dirname(fileURLToPath(import.meta.url)),
    "..",
    "harness",
    "fixtures",
    "simulation-banner-wide.html",
  ),
  "utf8",
);

test("SimulationBanner uses the exact default label and matching accessible name", () => {
  assert.equal(SIMULATION_BANNER_LABEL, "SIMULATED - NO REAL CHARGES OR RESERVATIONS");
  const html = simulationBannerHtml();
  assert.match(html, new RegExp(`>${SIMULATION_BANNER_LABEL}<`));
  assert.match(html, new RegExp(`aria-label="${SIMULATION_BANNER_LABEL}"`));
  assert.match(html, /role="status"/);
  assert.match(html, /data-itaa-simulation="true"/);
});

test("SimulationBanner is not dismissible", () => {
  const html = simulationBannerHtml();
  assert.doesNotMatch(html, /button/i);
  assert.doesNotMatch(html, /dismiss|close|aria-modal/i);
});

test("SimulationBanner supports required placements and compact/wide densities", () => {
  assert.deepEqual(
    [...SIMULATION_BANNER_PLACEMENTS],
    ["offers", "authorization", "receipt", "demo-shell"],
  );
  const compact = simulationBannerHtml({ density: "compact", placement: "offers" });
  const wide = simulationBannerHtml({ density: "wide", placement: "receipt" });
  assert.match(compact, /itaa-simulation-banner--compact/);
  assert.match(compact, /data-placement="offers"/);
  assert.match(wide, /itaa-simulation-banner--wide/);
  assert.match(wide, /data-placement="receipt"/);
  const normalize = (value: string): string =>
    value.replace(/\s+/g, " ").replace(/ >/g, ">").replace(/> </g, "><").trim();
  assert.equal(normalize(compact), normalize(compactFixture));
  assert.equal(normalize(wide), normalize(wideFixture));
});

test("harness shows compact and wide SimulationBanner examples", () => {
  assert.match(harness, /id="simulation-compact"/);
  assert.match(harness, /id="simulation-wide"/);
  assert.match(harness, /SIMULATED - NO REAL CHARGES OR RESERVATIONS/g);
});

test("SimulationBanner stays readable at large text and avoids failure styling", () => {
  const css = renderStylesheet();
  assert.match(css, /\.itaa-simulation-banner[^{]*\{[^}]*overflow:\s*visible/);
  assert.match(css, /\.itaa-simulation-banner[^{]*\{[^}]*overflow-wrap:\s*anywhere/);
  assert.doesNotMatch(css, /\.itaa-simulation-banner[^{]*\{[^}]*white-space:\s*nowrap/);
  assert.doesNotMatch(css, /\.itaa-simulation-banner[^{]*\{[^}]*overflow:\s*hidden/);
  assert.match(
    css,
    /\.itaa-simulation-banner[^{]*\{[^}]*background:\s*var\(--itaa-color-surface-simulation\)/,
  );
  assert.doesNotMatch(css, /\.itaa-simulation-banner[^{]*\{[^}]*--itaa-color-status-denial/);
});
