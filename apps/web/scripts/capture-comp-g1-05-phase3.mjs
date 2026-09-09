#!/usr/bin/env node
/**
 * COMP-G1-05 Phase 3: live parking workspace + lifecycle chrome.
 * Does not bind UAT ports 5173/8000. Uses 5184 / 9468 for this evidence pass.
 */
import { spawn } from "node:child_process";
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const repo = join(root, "../..");
const evidence = join(root, "evidence/comp-g1-05/phase-3");
mkdirSync(evidence, { recursive: true });

const chrome = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const debug = 9468;
const profile = mkdtempSync(join(tmpdir(), "comp-g1-05-p3-"));
const port = 5184;

const chromeProc = spawn(
  chrome,
  [
    "--headless=new",
    "--disable-gpu",
    "--no-first-run",
    "--hide-scrollbars",
    `--remote-debugging-port=${debug}`,
    `--user-data-dir=${profile}`,
    "--window-size=1440,940",
    "about:blank",
  ],
  { stdio: ["ignore", "pipe", "pipe"] },
);

async function waitDebug() {
  for (let i = 0; i < 80; i += 1) {
    try {
      const list = await fetch(`http://127.0.0.1:${debug}/json/version`);
      if (list.ok) {
        return;
      }
    } catch {
      // retry
    }
    await new Promise((r) => setTimeout(r, 150));
  }
  throw new Error("chrome debug missing");
}

await waitDebug();
const targets = await fetch(`http://127.0.0.1:${debug}/json`).then((r) => r.json());
const pageTarget = targets.find((item) => item.type === "page") ?? targets[0];
if (!pageTarget?.webSocketDebuggerUrl) {
  throw new Error("no chrome page target");
}

function cdpSession(wsUrl) {
  return new Promise((resolve, reject) => {
    const socket = new WebSocket(wsUrl);
    let nextId = 0;
    socket.addEventListener("open", () =>
      resolve({
        socket,
        nextId: () => ++nextId,
      }),
    );
    socket.addEventListener("error", reject);
  });
}

const pageWs = await cdpSession(pageTarget.webSocketDebuggerUrl);

function cdp(session, method, params = {}) {
  return new Promise((resolve, reject) => {
    const id = session.nextId();
    const onMessage = (event) => {
      const payload = JSON.parse(String(event.data));
      if (payload.id === id) {
        session.socket.removeEventListener("message", onMessage);
        payload.error ? reject(new Error(JSON.stringify(payload.error))) : resolve(payload.result);
      }
    };
    session.socket.addEventListener("message", onMessage);
    session.socket.send(JSON.stringify({ id, method, params }));
  });
}

async function shot(file, width, height, extraEval = null) {
  await cdp(pageWs, "Emulation.setDeviceMetricsOverride", {
    width,
    height,
    deviceScaleFactor: 1,
    mobile: width <= 410,
  });
  await new Promise((r) => setTimeout(r, 450));
  if (extraEval) {
    await cdp(pageWs, "Runtime.evaluate", { expression: extraEval, returnByValue: true });
    await new Promise((r) => setTimeout(r, 400));
  }
  const png = await cdp(pageWs, "Page.captureScreenshot", {
    format: "png",
    captureBeyondViewport: false,
  });
  writeFileSync(join(evidence, file), Buffer.from(png.data, "base64"));
}

async function go(path) {
  await cdp(pageWs, "Page.navigate", { url: `http://127.0.0.1:${port}${path}` });
  await new Promise((r) => setTimeout(r, 1400));
}

async function evalInPage(expression, awaitPromise = false) {
  const result = await cdp(pageWs, "Runtime.evaluate", {
    expression,
    returnByValue: true,
    awaitPromise,
  });
  return result.value ?? result.result?.value;
}

const vite = spawn(
  "pnpm",
  ["--filter", "@itaa/web", "exec", "vite", "--host", "127.0.0.1", "--port", String(port)],
  { cwd: repo, stdio: "pipe" },
);

await new Promise((resolve, reject) => {
  const timer = setTimeout(() => reject(new Error("vite timeout")), 25000);
  const onData = (chunk) => {
    if (String(chunk).includes("Local:")) {
      clearTimeout(timer);
      resolve();
    }
  };
  vite.stdout.on("data", onData);
  vite.stderr.on("data", onData);
});

const VIEWPORTS = [
  { name: "1440x940", width: 1440, height: 940 },
  { name: "410x874", width: 410, height: 874 },
  { name: "390x844", width: 390, height: 844 },
  { name: "320", width: 320, height: 844 },
];

const clickNamed = (label) => `(() => {
  const el = [...document.querySelectorAll("button")].find((item) => (item.textContent || "").trim() === ${JSON.stringify(label)});
  el?.click();
  return Boolean(el);
})()`;

await go("/intents/new/parking");
await evalInPage(`(() => {
  const example = [...document.querySelectorAll("button")].find((el) => (el.textContent || "").includes("Use the example"));
  example?.click();
  return Boolean(example);
})()`);
await new Promise((r) => setTimeout(r, 300));
await evalInPage(clickNamed("Send to Reservedge"));
await new Promise((r) => setTimeout(r, 1800));
const afterSend = await evalInPage(`({
  fail: document.querySelector(".re-fail")?.textContent || null,
  confirm: [...document.querySelectorAll("button")].some((el) => (el.textContent || "").includes("Confirm requirement")),
  text: (document.body.innerText || "").slice(0, 500),
})`);
await shot("composer-after-send-1440x940.png", 1440, 940);

const minted = await evalInPage(
  `(async () => {
  const extract = await fetch("/v1/simulations/airport-parking/intake/extractions", {
    method: "POST",
    credentials: "same-origin",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      text: "I'm flying from JFK on September 3 at 1 PM and returning September 8 at 10 PM. I have a standard EV, prefer covered parking, and don't want a shuttle longer than 20 minutes.",
      category: "airport_parking",
    }),
  });
  const extracted = await extract.json();
  const confirm = await fetch("/v1/simulations/airport-parking/intake/intents", {
    method: "POST",
    credentials: "same-origin",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      intakeId: extracted.intakeId,
      airportCode: "JFK",
      start: "2026-09-03T13:00:00Z",
      end: "2026-09-08T22:00:00Z",
      vehicleClass: "standard",
      covered: "preferred",
      shuttleMaxMinutes: 20,
      currency: "USD",
      accessibility: ["ev_charging"],
    }),
  });
  const snapshot = await confirm.json();
  if (!snapshot.intentId) {
    return { ok: false, extractStatus: extract.status, confirmStatus: confirm.status, snapshot };
  }
  location.assign("/intents/" + snapshot.intentId);
  return { ok: true, intentIdPrefix: String(snapshot.intentId).slice(0, 3), state: snapshot.state };
})()`,
  true,
);
await new Promise((r) => setTimeout(r, 1800));
const notes = { afterSend, minted, url: await evalInPage("location.pathname") };

for (const vp of VIEWPORTS) {
  await shot(`live-request-${vp.name}.png`, vp.width, vp.height);
}

await evalInPage(clickNamed("Modify intent"));
await new Promise((r) => setTimeout(r, 400));
await shot("live-modify-1440x940.png", 1440, 940);
await evalInPage(clickNamed("Never mind"));
await new Promise((r) => setTimeout(r, 300));
await evalInPage(clickNamed("Cancel intent"));
await new Promise((r) => setTimeout(r, 400));
await shot("live-delete-draft-1440x940.png", 1440, 940);
await evalInPage(clickNamed("Keep request"));
await new Promise((r) => setTimeout(r, 300));

await evalInPage(`document.querySelector(".re-status-actions button")?.focus()`);
await shot("live-request-1440x940-focus.png", 1440, 940);

await cdp(pageWs, "Emulation.setEmulatedMedia", {
  features: [{ name: "prefers-reduced-motion", value: "reduce" }],
});
await shot("live-request-1440x940-reduced-motion.png", 1440, 940);

const measured = await evalInPage(`(() => {
  const actions = document.querySelector(".re-status-actions");
  const tabs = document.querySelector(".re-intent-tabs");
  return {
    path: location.pathname,
    hasKeepPending: [...document.querySelectorAll("button")].some((el) => (el.textContent || "").trim() === "Keep pending"),
    hasModify: [...document.querySelectorAll("button")].some((el) => (el.textContent || "").trim() === "Modify intent"),
    itaaReview: (document.body.innerText || "").includes("Purchase Intent review"),
    jetPark: (document.body.innerText || "").includes("JetPark"),
    overflowX: document.documentElement.scrollWidth - document.documentElement.clientWidth,
    actionsHeight: actions ? actions.getBoundingClientRect().height : null,
    tabsWidth: tabs ? tabs.getBoundingClientRect().width : null,
    reduced: matchMedia("(prefers-reduced-motion: reduce)").matches,
  };
})()`);
notes.measured = measured;

writeFileSync(join(evidence, "measurements.json"), JSON.stringify(notes, null, 2));
writeFileSync(
  join(evidence, "compare.html"),
  `<!doctype html><meta charset="utf-8"><title>COMP-G1-05 Phase 3</title>
<style>
  body { margin: 24px; font: 14px/1.45 system-ui; background: #E9E6DF; color: #221F1A; }
  img { width: 100%; border: 1px solid #E6E1D8; background: #fff; }
  .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
  .cap { font: 11px/1.4 ui-monospace, monospace; color: #6C685F; margin: 8px 0; }
</style>
<h1>Phase 3 — live parking workspace and lifecycle</h1>
<p>Reservedge chrome for a confirmed parking intent. No ITAA workspace. No JetPark ranking.</p>
<section><div class="cap">Request 1440</div><img src="live-request-1440x940.png" alt="live request desktop"></section>
<section class="grid">
  <div><div class="cap">410</div><img src="live-request-410x874.png" alt="410"></div>
  <div><div class="cap">390</div><img src="live-request-390x844.png" alt="390"></div>
</section>
<section class="grid">
  <div><div class="cap">320</div><img src="live-request-320.png" alt="320"></div>
  <div><div class="cap">Modify dialog</div><img src="live-modify-1440x940.png" alt="modify"></div>
</section>
<section class="grid">
  <div><div class="cap">Delete draft dialog</div><img src="live-delete-draft-1440x940.png" alt="delete"></div>
  <div><div class="cap">Focus + reduced motion</div><img src="live-request-1440x940-focus.png" alt="focus"></div>
</section>
`,
);

vite.kill("SIGTERM");
chromeProc.kill("SIGTERM");
try {
  rmSync(profile, { recursive: true, force: true });
} catch {
  // Chrome may still hold the profile directory.
}
console.log(`wrote ${evidence}`);
