#!/usr/bin/env node
/**
 * Viewport measurements for the interactive React intent-first composer CSS.
 * Does not measure the inert .dc.html design canvas.
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
const kitCss = readFileSync(join(root, "../../packages/ui-kit/src/itaa-ui-kit.css"), "utf8");
const appCss = readFileSync(join(root, "src/styles.css"), "utf8").replace(
  '@import "@itaa/ui-kit/itaa-ui-kit.css";',
  "",
);
const composerHtml = `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Intent</title><style>${kitCss}\n${appCss}</style></head><body><div class="re-app" data-route="workspace"><main id="main" class="re-detail-body"><div class="re-fade re-intent-compose"><div class="re-eyebrow">NEW INTENT</div><h2 class="re-h2 re-intent-compose-title">What are you planning or trying to get done?</h2><p class="re-lead">Describe it the way you'd say it out loud.</p><div class="re-intent-compose-card"><textarea class="re-intent-compose-field itaa-focus-ring" aria-label="What are you planning or trying to get done?" rows="4"></textarea><div class="re-intent-compose-footer"><p class="re-intent-compose-disclosure">Nothing is sent to any supplier from this step.</p><button type="button" class="re-primary itaa-focus-ring">Start booking</button></div></div><div class="re-intent-suggestions"><button type="button" class="re-chip-btn itaa-focus-ring">Two nights in Edinburgh for a conference</button><button type="button" class="re-chip-btn itaa-focus-ring">Weekend away, driving, dog with us</button><button type="button" class="re-chip-btn itaa-focus-ring">Airport parking for a work trip on Thursday</button></div><div class="re-intent-direct"><div class="re-intent-direct-title">Already know the exact booking?</div><div class="re-intent-direct-row"><button type="button" class="re-intent-direct-btn itaa-focus-ring"><span class="re-code">Pk</span>Airport parking</button><button type="button" class="re-intent-direct-btn itaa-focus-ring"><span class="re-code">Rc</span>Rental car</button><button type="button" class="re-intent-direct-btn itaa-focus-ring"><span class="re-code">En</span>Entertainment booking</button></div></div></div></main><nav class="re-tabs" aria-label="Primary"><a class="re-tab is-on" href="/"><span class="re-tab-bar"></span>Intent</a><a class="re-tab" href="/bookings"><span class="re-tab-bar"></span>Bookings</a><a class="re-tab" href="/activity"><span class="re-tab-bar"></span>Activity</a></nav></div></body></html>`;
writeFileSync(join(evidence, "viewport-intent-composer.html"), composerHtml);
const clarifyHtml = `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Clarify</title><style>${kitCss}\n${appCss}</style></head><body><div class="re-app" data-route="workspace"><main id="main" class="re-detail-body"><div class="re-fade re-clarify"><div class="re-clarify-panes" role="tablist"><button type="button" class="re-clarify-pane is-on">Conversation</button><button type="button" class="re-clarify-pane">Plan · 4 tasks</button></div><section class="re-clarify-chat"><div class="re-clarify-thread"><div class="re-clarify-bubble re-clarify-bubble-user">I'm travelling to Edinburgh for a conference and I'll need a car when I land.</div><div class="re-clarify-card"><fieldset class="re-clarify-fieldset"><legend class="re-clarify-legend">Exact dates</legend><p class="re-clarify-hint">You mentioned Thursday. That is not an exact calendar date yet.</p><div class="re-clarify-dates"><div class="re-clarify-field"><label class="re-clarify-label" for="d1">Start date</label><input id="d1" class="re-clarify-text" type="date" value="2026-10-14"></div><div class="re-clarify-field"><label class="re-clarify-label" for="d2">End date</label><input id="d2" class="re-clarify-text" type="date" value="2026-10-19"></div></div><p class="re-clarify-selected">Selected 14–19 Oct 2026</p></fieldset><div class="re-clarify-choices"><button type="button" class="re-clarify-choice">Morning</button><button type="button" class="re-clarify-choice">Afternoon</button><button type="button" class="re-clarify-choice is-on">Evening</button><button type="button" class="re-clarify-choice">Anytime / Flexible</button></div><button type="button" class="re-primary re-clarify-update">Answer and update plan</button></div></div></section><section class="re-clarify-plan"><div class="re-clarify-plan-head"><span class="re-clarify-kicker">PLAN</span><span class="re-clarify-status">Forming</span></div><h2 class="re-h2 re-clarify-plan-title">Edinburgh conference</h2><article class="re-clarify-task"><span class="re-clarify-task-title">Airport parking · EDI</span><span class="re-clarify-provenance is-inferred">Inferred</span></article><article class="re-clarify-task"><span class="re-clarify-task-title">Rental car · Edinburgh</span><span class="re-clarify-provenance is-explicit">Explicit</span></article><button type="button" class="re-primary re-clarify-confirm">Confirm plan</button></section><div class="re-clarify-mobile-actions"><button type="button" class="re-primary">Confirm plan</button><p>Nothing is sent to any supplier from this step.</p></div></div></main><nav class="re-tabs" aria-label="Primary"><a class="re-tab is-on" href="/"><span class="re-tab-bar"></span>Intent</a><a class="re-tab" href="/bookings"><span class="re-tab-bar"></span>Bookings</a><a class="re-tab" href="/activity"><span class="re-tab-bar"></span>Activity</a></nav></div></body></html>`;
writeFileSync(join(evidence, "viewport-intent-clarify.html"), clarifyHtml);

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

const chrome = findChrome();
if (chrome === null) {
  console.error("FAIL: Chrome is required for recovered intent-first viewport measurement");
  process.exit(1);
}

const server = createServer((req, res) => {
  res.writeHead(200, { "content-type": "text/html; charset=utf-8" });
  res.end(String(req.url ?? "").includes("clarify") ? clarifyHtml : composerHtml);
});

await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
const port = server.address().port;
const base = `http://127.0.0.1:${port}`;

async function cdp(portDebug, method, params = {}) {
  const targets = await fetch(`http://127.0.0.1:${portDebug}/json`).then((item) => item.json());
  const page = targets.find((item) => item.type === "page") ?? targets[0];
  const ws = page.webSocketDebuggerUrl;
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

const cases = [
  { width: 320, height: 900, label: "composer-320" },
  { width: 375, height: 812, label: "composer-375" },
  { width: 390, height: 844, label: "composer-390" },
  { width: 430, height: 932, label: "composer-430" },
  { width: 768, height: 1024, label: "composer-768" },
  { width: 1280, height: 800, label: "composer-1280" },
];

const debugPort = 9460;
const profile = mkdtempSync(join(tmpdir(), "itaa-intent-first-chrome-"));
const chromeProc = startChrome([
  "--headless=new",
  "--disable-gpu",
  "--no-first-run",
  "--no-default-browser-check",
  "--disable-dev-shm-usage",
  `--remote-debugging-port=${debugPort}`,
  `--user-data-dir=${profile}`,
  "--window-size=1280,900",
  `${base}/`,
]);
await waitForDebug(debugPort);

const measurements = [];
let headingMissing = false;
let overflowed = false;
for (const item of cases) {
  await cdp(debugPort, "Page.navigate", { url: `${base}/` });
  await new Promise((resolve) => setTimeout(resolve, 700));
  await cdp(debugPort, "Emulation.setDeviceMetricsOverride", {
    width: item.width,
    height: item.height,
    deviceScaleFactor: 1,
    mobile: item.width < 768,
  });
  await new Promise((resolve) => setTimeout(resolve, 250));
  const result = await cdp(debugPort, "Runtime.evaluate", {
    expression: `({
      innerWidth: window.innerWidth,
      clientWidth: document.documentElement.clientWidth,
      scrollWidth: document.documentElement.scrollWidth,
      heading: Boolean(document.body.innerText.includes("What are you planning or trying to get done?")),
      domainPicker: Boolean(document.body.innerText.includes("What do you need?")),
      secondaryShortcut: Boolean(document.body.innerText.includes("Already know the exact booking?")),
      sim: Boolean(document.body.innerText.includes("SIM")),
    })`,
    returnByValue: true,
  });
  const value = result.result.value;
  if (!value.heading || value.domainPicker) {
    headingMissing = true;
  }
  const shot = await cdp(debugPort, "Page.captureScreenshot", { format: "png", fromSurface: true });
  if (typeof shot.data === "string") {
    writeFileSync(
      join(evidence, `intent-first-${item.label}.png`),
      Buffer.from(shot.data, "base64"),
    );
  }
  measurements.push({
    ...item,
    overflow: value.scrollWidth > value.clientWidth,
    ...value,
  });
  if (value.scrollWidth > value.clientWidth) {
    overflowed = true;
  }
}

const clarifyCases = [
  { width: 320, height: 900, label: "clarify-320" },
  { width: 375, height: 812, label: "clarify-375" },
  { width: 390, height: 844, label: "clarify-390" },
  { width: 430, height: 932, label: "clarify-430" },
  { width: 768, height: 1024, label: "clarify-768" },
  { width: 1280, height: 800, label: "clarify-1280" },
];
let clarifyMissing = false;
for (const item of clarifyCases) {
  await cdp(debugPort, "Page.navigate", { url: `${base}/clarify` });
  await new Promise((resolve) => setTimeout(resolve, 700));
  await cdp(debugPort, "Emulation.setDeviceMetricsOverride", {
    width: item.width,
    height: item.height,
    deviceScaleFactor: 1,
    mobile: item.width < 768,
  });
  await new Promise((resolve) => setTimeout(resolve, 250));
  const result = await cdp(debugPort, "Runtime.evaluate", {
    expression: `({
      innerWidth: window.innerWidth,
      clientWidth: document.documentElement.clientWidth,
      scrollWidth: document.documentElement.scrollWidth,
      heading: Boolean(document.body.innerText.includes("Edinburgh conference")),
      forming: Boolean(document.body.innerText.includes("Forming")),
      confirm: Boolean(document.body.innerText.includes("Confirm plan")),
    })`,
    returnByValue: true,
  });
  const value = result.result.value;
  if (!value.heading || !value.forming || !value.confirm) {
    clarifyMissing = true;
  }
  const shot = await cdp(debugPort, "Page.captureScreenshot", { format: "png", fromSurface: true });
  if (typeof shot.data === "string") {
    writeFileSync(
      join(evidence, `intent-first-${item.label}.png`),
      Buffer.from(shot.data, "base64"),
    );
  }
  measurements.push({
    ...item,
    overflow: value.scrollWidth > value.clientWidth,
    ...value,
  });
  if (value.scrollWidth > value.clientWidth) {
    overflowed = true;
  }
}

chromeProc.kill("SIGTERM");
await new Promise((resolve) => setTimeout(resolve, 400));
try {
  rmSync(profile, { recursive: true, force: true });
} catch {
  // Chrome may still hold profile files after SIGTERM
}
server.close();

const report = {
  measuredAt: new Date().toISOString(),
  chrome,
  note: "Interactive React intent-first composer and Clarify & plan CSS measured at phone, tablet, and desktop widths.",
  measurements,
};

writeFileSync(
  join(evidence, "intent-first-viewport-measurements.json"),
  JSON.stringify(report, null, 2),
);
console.log(JSON.stringify(report, null, 2));

if (headingMissing) {
  console.error(
    "FAIL: recovered compose heading missing, or rejected domain-picker heading present",
  );
  process.exit(1);
}
if (clarifyMissing) {
  console.error("FAIL: Clarify & plan layout missing forming plan or confirm action");
  process.exit(1);
}
if (overflowed) {
  console.error(
    "FAIL: horizontal overflow on the interactive intent-first composer or clarify/plan",
    measurements,
  );
  process.exit(1);
}
console.log(
  "PASS: interactive intent-first composer and Clarify & plan present without overflow at measured viewports",
);
