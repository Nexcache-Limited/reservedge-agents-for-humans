#!/usr/bin/env node
/**
 * Genuine 320 CSS-pixel overflow and 200% browser-zoom measurements.
 * Uses headed/headless Chromium with a Preferences default_zoom_level of 200%
 * (not deviceScaleFactor). Writes JSON under apps/web/evidence/.
 */
import { spawn, spawnSync } from "node:child_process";
import { createServer } from "node:http";
import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const evidence = join(root, "evidence");
mkdirSync(evidence, { recursive: true });

const chromeCandidates = [
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
  "/Applications/Chromium.app/Contents/MacOS/Chromium",
  "google-chrome",
  "chromium",
];

function findChrome() {
  for (const candidate of chromeCandidates) {
    if (candidate.includes("/")) {
      if (existsSync(candidate)) {
        return candidate;
      }
      continue;
    }
    const found = spawnSync("which", [candidate], { encoding: "utf8" });
    if (found.status === 0) {
      const resolved = found.stdout.trim().split("\n")[0];
      if (resolved) {
        return resolved;
      }
    }
  }
  return null;
}

const kitCss = readFileSync(join(root, "../../packages/ui-kit/src/itaa-ui-kit.css"), "utf8");
const appCss = readFileSync(join(root, "src/styles.css"), "utf8").replace(
  '@import "@itaa/ui-kit/itaa-ui-kit.css";',
  "",
);

const screens = [
  ["inbox", inboxHtml()],
  ["a1", workspaceHtml("A1 confirm", requirementHtml())],
  ["a2", workspaceHtml("A2 disclosure", disclosureHtml())],
  ["offers-a3", workspaceHtml("Compare", offersHtml())],
  ["a4", workspaceHtml("A4 authorize", authorizeHtml())],
  ["receipt", workspaceHtml("Receipt", receiptHtml())],
  ["error", workspaceHtml("Recovery", errorHtml())],
];

function banner() {
  return `<div class="itaa-simulation-banner itaa-simulation-banner--wide" role="status"><p class="itaa-simulation-banner__label">SIMULATED - NO REAL CHARGES OR RESERVATIONS</p></div>`;
}

function shell(title, body) {
  return `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>${title}</title><style>${kitCss}\n${appCss}</style></head><body><div id="root" class="itaa-app"><a class="itaa-skip itaa-focus-ring" href="#main">Skip to main content</a><header class="itaa-topbar">${banner()}</header><div class="itaa-shell"><nav class="itaa-rail" aria-label="Primary"><p class="itaa-text itaa-text--label">ITAA</p><p class="itaa-text itaa-text--meta">You do not search. You decide.</p><ul><li><a class="itaa-nav itaa-focus-ring" href="/">Intent Inbox</a></li><li><a class="itaa-nav itaa-focus-ring" href="/new">New airport-parking demo</a></li></ul></nav><div class="itaa-workspace"><main id="main" tabindex="-1"><h1 class="itaa-text itaa-text--display">${title}</h1>${body}</main></div></div></div></body></html>`;
}

function inboxHtml() {
  return shell(
    "Intent Inbox",
    `${banner()}<p class="itaa-text itaa-text--body">ITAA turns a need into a private, evidence-backed decision. Nothing is disclosed or reserved until you approve the exact step.</p><div class="itaa-actions"><button class="itaa-button itaa-button--primary" type="button"><span class="itaa-button__label">Share or describe a requirement</span></button><button class="itaa-button itaa-button--consent" type="button"><span class="itaa-button__label">Start JFK airport-parking demo</span></button></div><section class="itaa-surface itaa-surface--pad-lg"><h2 class="itaa-text itaa-text--heading">No intents in this browser session</h2><p class="itaa-text itaa-text--body">This demo does not monitor email or live supplier connections. Start the seeded airport-parking demonstration to create a local session.</p></section>`,
  );
}

function workspaceHtml(title, inner) {
  return shell(
    title,
    `<ol class="itaa-stage-track">${["Purchase Intent", "A1 confirm", "A2 disclosure", "Supplier responses", "Compare", "A3 accept", "A4 authorize", "Receipt"].map((item) => `<li>${item}</li>`).join("")}</ol>${inner}`,
  );
}

function requirementHtml() {
  return `<div class="itaa-stack">${banner()}<section class="itaa-surface itaa-surface--raised itaa-surface--pad-lg"><h2 class="itaa-text itaa-text--heading">Purchase Intent review</h2><dl class="itaa-fields"><div><dt class="itaa-text itaa-text--meta">Airport</dt><dd class="itaa-text itaa-text--body">JFK (John F. Kennedy)</dd></div><div><dt class="itaa-text itaa-text--meta">Parking dates</dt><dd class="itaa-text itaa-text--body">3 Sep 2026 13:00Z to 8 Sep 2026 22:00Z</dd></div></dl></section><section class="itaa-surface itaa-surface--pad-lg"><h2 class="itaa-text itaa-text--heading">Confirm requirement — A1</h2><button class="itaa-button itaa-button--consent" type="button"><span class="itaa-button__label">Confirm requirement</span></button></section></div>`;
}

function disclosureHtml() {
  return `<div class="itaa-stack">${banner()}<section class="itaa-surface itaa-surface--raised itaa-surface--pad-lg"><h2 class="itaa-text itaa-text--heading">Minimum disclosure — Gate 1 / A2</h2><p class="itaa-text itaa-text--body">Authorize disclosure to 3 isolated simulated suppliers. This shares only the fields below. It does not reserve, buy, or charge anything.</p><button class="itaa-button itaa-button--consent" type="button"><span class="itaa-button__label">Authorize disclosure to 3 suppliers</span></button></section></div>`;
}

function offersHtml() {
  const card = (name, rec, total) =>
    `<article class="itaa-offer-card itaa-surface itaa-surface--pad-lg" data-recommended="${rec}"><header><h3 class="itaa-text itaa-text--heading">${name}</h3><span class="itaa-status itaa-status--neutral"><span class="itaa-status__swatch"></span><span class="itaa-status__label">Private simulated offer</span></span></header><dl class="itaa-fields"><div><dt class="itaa-text itaa-text--meta">All-in total</dt><dd class="itaa-text itaa-text--fact">${total}</dd></div><div><dt class="itaa-text itaa-text--meta">Cancellation</dt><dd class="itaa-text itaa-text--body">free until 24 hours before arrival</dd></div><div><dt class="itaa-text itaa-text--meta">Refund</dt><dd class="itaa-text itaa-text--body">original method</dd></div><div><dt class="itaa-text itaa-text--meta">Add-ons</dt><dd class="itaa-text itaa-text--body">${name === "SkyShield" ? "EV charging" : "None"}</dd></div></dl><button class="itaa-button itaa-button--ghost" type="button"><span class="itaa-button__label">Select ${name}</span></button></article>`;
  return `<div class="itaa-stack">${banner()}<section class="itaa-surface itaa-surface--raised itaa-surface--pad-lg"><h2 class="itaa-text itaa-text--heading">Recommendation and comparison</h2><div class="itaa-recommend"><h3 class="itaa-text itaa-text--heading">Why this is recommended</h3><ul><li>SkyShield is covered parking with EV charging.</li><li>Shuttle time 8 minutes is within the 20-minute preference.</li></ul></div><div class="itaa-compare">${card("SkyShield", "true", "USD 148.00")}${card("ParkDirect", "false", "USD 119.00")}${card("TerminalFlex", "false", "USD 169.00")}</div><section class="itaa-surface itaa-surface--pad-md"><h3 class="itaa-text itaa-text--heading">Accept selected offer — A3</h3><dl class="itaa-fields" aria-label="Selected offer acceptance"><div><dt class="itaa-text itaa-text--meta">Supplier</dt><dd class="itaa-text itaa-text--body">SkyShield</dd></div><div><dt class="itaa-text itaa-text--meta">Offer version</dt><dd class="itaa-text itaa-text--fact">1</dd></div><div><dt class="itaa-text itaa-text--meta">Amount</dt><dd class="itaa-text itaa-text--fact">USD 148.00</dd></div><div><dt class="itaa-text itaa-text--meta">Currency</dt><dd class="itaa-text itaa-text--fact">USD</dd></div><div><dt class="itaa-text itaa-text--meta">Cancellation</dt><dd class="itaa-text itaa-text--body">free until 24 hours before arrival</dd></div><div><dt class="itaa-text itaa-text--meta">Refund</dt><dd class="itaa-text itaa-text--body">original method</dd></div><div><dt class="itaa-text itaa-text--meta">Add-ons</dt><dd class="itaa-text itaa-text--body">EV charging</dd></div><div><dt class="itaa-text itaa-text--meta">Validity deadline</dt><dd class="itaa-text itaa-text--fact">2026-08-21T16:00:00Z</dd></div><div><dt class="itaa-text itaa-text--meta">Simulation status</dt><dd class="itaa-text itaa-text--body">SIMULATED — no real reservation or charge</dd></div></dl><button class="itaa-button itaa-button--consent" type="button"><span class="itaa-button__label">Confirm offer selection</span></button></section></section></div>`;
}

function authorizeHtml() {
  return `<div class="itaa-stack">${banner()}<section class="itaa-surface itaa-surface--raised itaa-surface--pad-lg"><h2 class="itaa-text itaa-text--heading">Authorize simulated reservation — Gate 2 / A4</h2><button class="itaa-button itaa-button--consent" type="button"><span class="itaa-button__label">Authorize simulated reservation</span></button></section></div>`;
}

function receiptHtml() {
  return `<div class="itaa-stack">${banner()}<section class="itaa-surface itaa-surface--raised itaa-surface--pad-lg"><h2 class="itaa-text itaa-text--display">SIMULATED RECEIPT</h2><p class="itaa-text itaa-text--body">No card was charged. No supplier reservation was created.</p><button class="itaa-button itaa-button--primary" type="button"><span class="itaa-button__label">Return to Intent Inbox</span></button></section></div>`;
}

function errorHtml() {
  return `<div class="itaa-error" role="alert"><p class="itaa-text itaa-text--label">Could not complete that action</p><p class="itaa-text itaa-text--body">This intent was not found. Local simulation state is lost when the API restarts.</p><button class="itaa-button itaa-button--primary" type="button"><span class="itaa-button__label">Return to Intent Inbox</span></button></div>`;
}

const files = {};
for (const [name, html] of screens) {
  const path = join(evidence, `viewport-${name}.html`);
  writeFileSync(path, html);
  files[name] = path;
}

const chrome = findChrome();
if (chrome === null) {
  console.error("FAIL: Chrome is required for test:viewport");
  process.exit(1);
}

const server = createServer((req, res) => {
  const name = new URL(req.url ?? "/", "http://127.0.0.1").pathname.replace(/^\//, "") || "inbox";
  const path = files[name];
  if (path === undefined) {
    res.writeHead(404);
    res.end("missing");
    return;
  }
  res.writeHead(200, { "content-type": "text/html; charset=utf-8" });
  res.end(readFileSync(path));
});

await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
const port = server.address().port;
const base = `http://127.0.0.1:${port}`;

async function cdp(portDebug, method, params = {}) {
  const targets = await fetch(`http://127.0.0.1:${portDebug}/json`).then((item) => item.json());
  const page = targets.find((item) => item.type === "page") ?? targets[0];
  const ws = page.webSocketDebuggerUrl;
  const { WebSocket } = await import("node:http").then(() => ({ WebSocket: globalThis.WebSocket }));
  if (typeof WebSocket !== "function") {
    throw new Error("WebSocket is required (Node 22+)");
  }
  return await new Promise((resolve, reject) => {
    const socket = new WebSocket(ws);
    let id = 0;
    socket.addEventListener("open", () => {
      id += 1;
      socket.send(JSON.stringify({ id, method, params }));
    });
    socket.addEventListener("message", (event) => {
      const payload = JSON.parse(String(event.data));
      if (payload.id === id) {
        socket.close();
        if (payload.error !== undefined) {
          reject(new Error(JSON.stringify(payload.error)));
        } else {
          resolve(payload.result);
        }
      }
    });
    socket.addEventListener("error", reject);
  });
}

function startChrome(args) {
  const child = spawn(chrome, args, { stdio: ["ignore", "pipe", "pipe"] });
  child.stderr.on("data", () => undefined);
  return child;
}

async function waitForDebug(portDebug) {
  for (let attempt = 0; attempt < 80; attempt += 1) {
    try {
      const list = await fetch(`http://127.0.0.1:${portDebug}/json/version`);
      if (list.ok) {
        return;
      }
    } catch {
      // retry
    }
    await new Promise((resolve) => setTimeout(resolve, 200));
  }
  throw new Error(`Chrome debug port ${portDebug} did not open`);
}

const debug320 = 9455;
const profile320 = mkdtempSync(join(tmpdir(), "itaa-ui01-chrome-320-"));
const chrome320 = startChrome([
  "--headless=new",
  "--disable-gpu",
  "--no-first-run",
  "--no-default-browser-check",
  "--disable-dev-shm-usage",
  `--remote-debugging-port=${debug320}`,
  `--user-data-dir=${profile320}`,
  `--window-size=320,4000`,
  `${base}/inbox`,
]);
await waitForDebug(debug320);

const measurements = [];
for (const [name] of screens) {
  await cdp(debug320, "Page.navigate", { url: `${base}/${name}` });
  await new Promise((resolve) => setTimeout(resolve, 250));
  await cdp(debug320, "Emulation.setDeviceMetricsOverride", {
    width: 320,
    height: 4000,
    deviceScaleFactor: 1,
    mobile: false,
  });
  const result = await cdp(debug320, "Runtime.evaluate", {
    expression:
      "({innerWidth, clientWidth: document.documentElement.clientWidth, scrollWidth: document.documentElement.scrollWidth, bodyScroll: document.body.scrollWidth, dpr: window.devicePixelRatio})",
    returnByValue: true,
  });
  const shot = await cdp(debug320, "Page.captureScreenshot", { format: "png", fromSurface: true });
  if (typeof shot.data === "string") {
    writeFileSync(join(evidence, `${name}-narrow-320.png`), Buffer.from(shot.data, "base64"));
  }
  measurements.push({
    screen: name,
    cssViewport: 320,
    mechanism: "Emulation.setDeviceMetricsOverride width=320 DSF=1",
    ...result.result.value,
  });
}

chrome320.kill("SIGTERM");
await new Promise((resolve) => setTimeout(resolve, 400));
try {
  rmSync(profile320, { recursive: true, force: true });
} catch {
  // Chrome may still hold profile files after SIGTERM
}

const zoomLevel = Math.log(2) / Math.log(1.2);
const profileZoom = mkdtempSync(join(tmpdir(), "itaa-ui01-chrome-zoom-"));
mkdirSync(join(profileZoom, "Default"), { recursive: true });
writeFileSync(
  join(profileZoom, "Default", "Preferences"),
  JSON.stringify({
    default_zoom_level: { x: zoomLevel },
    partition: { default_zoom_level: { x: zoomLevel } },
    profile: { default_content_setting_values: {} },
  }),
);

const debugZoom = 9456;
const chromeZoom = startChrome([
  "--headless=new",
  "--disable-gpu",
  "--no-first-run",
  "--no-default-browser-check",
  "--disable-dev-shm-usage",
  `--remote-debugging-port=${debugZoom}`,
  `--user-data-dir=${profileZoom}`,
  "--window-size=1280,900",
  `${base}/offers-a3`,
]);
await waitForDebug(debugZoom);
await cdp(debugZoom, "Page.navigate", { url: `${base}/offers-a3` });
await new Promise((resolve) => setTimeout(resolve, 400));
const zoomBefore = await cdp(debugZoom, "Runtime.evaluate", {
  expression:
    "({innerWidth: window.innerWidth, clientWidth: document.documentElement.clientWidth, scrollWidth: document.documentElement.scrollWidth, dpr: window.devicePixelRatio, visualScale: window.visualViewport?.scale ?? null})",
  returnByValue: true,
});
const zoomPageShot = await cdp(debugZoom, "Page.captureScreenshot", {
  format: "png",
  fromSurface: true,
});
if (typeof zoomPageShot.data === "string") {
  writeFileSync(join(evidence, "offers-200pct.png"), Buffer.from(zoomPageShot.data, "base64"));
}

const scale = await cdp(debugZoom, "Emulation.setPageScaleFactor", { pageScaleFactor: 2 }).catch(
  (error) => ({ error: String(error) }),
);
const zoomAfterScale = await cdp(debugZoom, "Runtime.evaluate", {
  expression:
    "({innerWidth: window.innerWidth, clientWidth: document.documentElement.clientWidth, scrollWidth: document.documentElement.scrollWidth, dpr: window.devicePixelRatio, visualScale: window.visualViewport?.scale ?? null, active: document.activeElement?.tagName})",
  returnByValue: true,
});
await cdp(debugZoom, "Runtime.evaluate", {
  expression: "document.querySelector('button')?.focus(); document.activeElement?.className",
  returnByValue: true,
});
const focus = await cdp(debugZoom, "Runtime.evaluate", {
  expression:
    "({focused: document.activeElement?.textContent, outline: getComputedStyle(document.activeElement).outline})",
  returnByValue: true,
});
const zoomShot = await cdp(debugZoom, "Page.captureScreenshot", {
  format: "png",
  fromSurface: true,
});
if (typeof zoomShot.data === "string") {
  writeFileSync(join(evidence, "offers-200pct-pinch.png"), Buffer.from(zoomShot.data, "base64"));
}
chromeZoom.kill("SIGTERM");
await new Promise((resolve) => setTimeout(resolve, 400));
try {
  rmSync(profileZoom, { recursive: true, force: true });
} catch {
  // Chrome may still hold profile files after SIGTERM
}
server.close();

const report = {
  measuredAt: new Date().toISOString(),
  chrome,
  overflow320: measurements,
  zoom: {
    mechanism:
      "Chrome Preferences default_zoom_level = log(2)/log(1.2) (~200%) plus CDP Emulation.setPageScaleFactor(2). Not deviceScaleFactor.",
    preferencesZoomLevel: zoomLevel,
    beforeScale: zoomBefore.result.value,
    setPageScaleFactor: scale,
    afterScale: zoomAfterScale.result.value,
    focus,
  },
};

writeFileSync(join(evidence, "viewport-measurements.json"), JSON.stringify(report, null, 2));
const overflow = measurements.filter((item) => item.scrollWidth > item.clientWidth);
if (overflow.length > 0) {
  console.error("FAIL: horizontal overflow at 320 CSS px", overflow);
  process.exit(1);
}
console.log(JSON.stringify(report, null, 2));
console.log("PASS: 320 CSS px overflow assertions");
