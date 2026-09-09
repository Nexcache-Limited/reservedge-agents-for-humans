#!/usr/bin/env node
/**
 * COMP-G1-05 Phase 4: disclosure gate, progress, locked reco, compare, auth, receipt.
 * Does not bind UAT ports 5173/8000. Uses 5185 / 9469 for this evidence pass.
 */
import { spawn } from "node:child_process";
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const repo = join(root, "../..");
const evidence = join(root, "evidence/comp-g1-05/phase-4");
mkdirSync(evidence, { recursive: true });

const chrome = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const debug = 9469;
const profile = mkdtempSync(join(tmpdir(), "comp-g1-05-p4-"));
const port = 5185;

const TOKENS = {
  parkDirect: "sp_01k2m3n4p5q6r7s8t9v0w1x2b1",
  skyShield: "sp_01k2m3n4p5q6r7s8t9v0w1x2b2",
  terminalFlex: "sp_01k2m3n4p5q6r7s8t9v0w1x2b3",
};
const OFFERS = {
  skyShield: "of_01k2m3n4p5q6r7s8t9v0w1x2a2",
  parkDirect: "of_01k2m3n4p5q6r7s8t9v0w1x2a1",
  terminalFlex: "of_01k2m3n4p5q6r7s8t9v0w1x2a3",
};

const rankedOffers = [
  {
    offerId: OFFERS.skyShield,
    supplierToken: TOKENS.skyShield,
    version: 1,
    rank: 1,
    scoreMicros: 671000,
    totalMinor: 14800,
    currency: "USD",
    recommended: true,
    simulation: true,
  },
  {
    offerId: OFFERS.parkDirect,
    supplierToken: TOKENS.parkDirect,
    version: 1,
    rank: 2,
    scoreMicros: 660000,
    totalMinor: 11900,
    currency: "USD",
    recommended: false,
    simulation: true,
  },
  {
    offerId: OFFERS.terminalFlex,
    supplierToken: TOKENS.terminalFlex,
    version: 1,
    rank: 3,
    scoreMicros: 535000,
    totalMinor: 16900,
    currency: "USD",
    recommended: false,
    simulation: true,
  },
];

const outcomes = [
  { supplierToken: TOKENS.parkDirect, kind: "OFFER", reason: null },
  { supplierToken: TOKENS.skyShield, kind: "OFFER", reason: null },
  { supplierToken: TOKENS.terminalFlex, kind: "OFFER", reason: null },
];

function snap(overrides) {
  return {
    environment: "local_simulation",
    simulation: true,
    intentId: "pi_01k2m3n4p5q6r7s8t9v0w1x2y3",
    state: "AWAITING_REQUIREMENT_CONFIRMATION",
    airport: "JFK",
    category: "airport_parking",
    createdAt: "2026-08-20T15:00:00Z",
    updatedAt: "2026-08-20T15:00:00Z",
    expiresAt: "2026-08-22T15:00:00Z",
    windowStart: "2026-09-03T13:00:00Z",
    windowEnd: "2026-09-08T22:00:00Z",
    marketEvidence: [],
    supplierOutcomes: [],
    offers: [],
    recommendedOfferId: null,
    downside: null,
    acceptance: null,
    transaction: null,
    ...overrides,
  };
}

const VIEWS = {
  confirm: snap(),
  gate: snap({ state: "AWAITING_DISPATCH_APPROVAL" }),
  reco: snap({
    state: "OFFERS_RANKED",
    offers: rankedOffers,
    recommendedOfferId: OFFERS.skyShield,
    downside: { dimension: "total_minor", delta: 2900, versusOfferId: OFFERS.parkDirect },
    supplierOutcomes: outcomes,
  }),
  auth: snap({
    state: "ACCEPTANCE_RECORDED",
    offers: rankedOffers,
    recommendedOfferId: OFFERS.skyShield,
    downside: { dimension: "total_minor", delta: 2900, versusOfferId: OFFERS.parkDirect },
    supplierOutcomes: outcomes,
    acceptance: {
      acceptanceId: "ac_01k2m3n4p5q6r7s8t9v0w1x2d1",
      offerId: OFFERS.skyShield,
      offerVersion: 1,
      status: "recorded",
    },
  }),
  receipt: snap({
    state: "TRANSACTION_AUTHORIZED_SIMULATED",
    offers: rankedOffers,
    recommendedOfferId: OFFERS.skyShield,
    downside: { dimension: "total_minor", delta: 2900, versusOfferId: OFFERS.parkDirect },
    supplierOutcomes: outcomes,
    acceptance: {
      acceptanceId: "ac_01k2m3n4p5q6r7s8t9v0w1x2d1",
      offerId: OFFERS.skyShield,
      offerVersion: 1,
      status: "recorded",
    },
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
};

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

let currentView = "reco";
let hangDispatch = false;

await cdp(pageWs, "Page.enable");
await cdp(pageWs, "Runtime.enable");
await cdp(pageWs, "Fetch.enable", {
  patterns: [{ urlPattern: "*://127.0.0.1:*/v1/*", requestStage: "Request" }],
});

pageWs.socket.addEventListener("message", (event) => {
  const payload = JSON.parse(String(event.data));
  if (payload.method !== "Fetch.requestPaused") {
    return;
  }
  const { requestId, request } = payload.params;
  const pathname = new URL(request.url).pathname;
  if (pathname.includes("/dispatch") && hangDispatch) {
    return;
  }
  let body = null;
  if (pathname.endsWith("/intake/intents")) {
    body = { needsYou: [], running: [], saved: [], history: [] };
  } else if (pathname.endsWith("/activity")) {
    body = { activity: [] };
  } else if (pathname.includes("/intake/intents/")) {
    body = VIEWS[currentView] ?? VIEWS.reco;
  }
  if (body === null) {
    void cdp(pageWs, "Fetch.continueRequest", { requestId });
    return;
  }
  void cdp(pageWs, "Fetch.fulfillRequest", {
    requestId,
    responseCode: 200,
    responseHeaders: [{ name: "Content-Type", value: "application/json" }],
    body: Buffer.from(JSON.stringify(body)).toString("base64"),
  });
});

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
  await new Promise((r) => setTimeout(r, 1600));
  for (let i = 0; i < 12; i += 1) {
    const loading = await evalInPage(
      `(document.body.innerText || "").includes("Loading this parking request")`,
    );
    if (!loading) {
      break;
    }
    await new Promise((r) => setTimeout(r, 250));
  }
}

async function evalInPage(expression, awaitPromise = false) {
  const result = await cdp(pageWs, "Runtime.evaluate", {
    expression,
    returnByValue: true,
    awaitPromise,
  });
  return result.value ?? result.result?.value;
}

const clickNamed = (label) => `(() => {
  const el = [...document.querySelectorAll("button")].find((item) => (item.textContent || "").trim() === ${JSON.stringify(label)});
  el?.click();
  return Boolean(el);
})()`;

async function loadView(view, path = "/intents/pi_01k2m3n4p5q6r7s8t9v0w1x2y3") {
  currentView = view;
  hangDispatch = false;
  await go(path);
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

const notes = {};

await loadView("gate");
notes.gate = await evalInPage(`(() => {
  const main = document.querySelector("#main")?.innerText || "";
  return {
    hold: [...document.querySelectorAll("button")].some((el) => (el.textContent || "").trim() === "Send this request"),
    jetPark: main.includes("JetPark"),
    prototypePrice: main.includes("$71.40"),
    gateWord: /\\bGate\\b/.test(main),
  };
})()`);
for (const vp of VIEWPORTS) {
  await shot(`gate-${vp.name}.png`, vp.width, vp.height);
}

hangDispatch = true;
await evalInPage(clickNamed("Send this request"));
await new Promise((r) => setTimeout(r, 700));
notes.progress = await evalInPage(`({
  answering: (document.body.innerText || "").includes("Suppliers are answering"),
  jetPark: (document.body.innerText || "").includes("JetPark"),
})`);
await shot("progress-1440x940.png", 1440, 940);

await loadView("reco");
notes.reco = await evalInPage(`(() => {
  const main = document.querySelector("#main")?.innerText || "";
  return {
    sky: main.includes("SkyShield"),
    score: main.includes("671,000"),
    downside: main.includes("USD 29.00"),
    take: [...document.querySelectorAll("button")].some((el) => (el.textContent || "").trim() === "Take this one"),
    jetPark: main.includes("JetPark"),
    prototypePrice: main.includes("$71.40"),
  };
})()`);
for (const vp of VIEWPORTS) {
  await shot(`reco-${vp.name}.png`, vp.width, vp.height);
}

await evalInPage(clickNamed("Compare all three"));
await new Promise((r) => setTimeout(r, 400));
notes.compare = await evalInPage(`({
  park: (document.body.innerText || "").includes("ParkDirect"),
  flex: (document.body.innerText || "").includes("TerminalFlex"),
  scores: ["671,000", "660,000", "535,000"].every((item) => (document.body.innerText || "").includes(item)),
})`);
for (const vp of VIEWPORTS) {
  await shot(`compare-${vp.name}.png`, vp.width, vp.height);
}

await loadView("auth");
await evalInPage(clickNamed("Continue to authorization"));
await new Promise((r) => setTimeout(r, 400));
notes.auth = await evalInPage(`({
  dialog: Boolean(document.querySelector("[role=dialog]")),
  hold: [...document.querySelectorAll("button")].some((el) => (el.textContent || "").includes("Authorize")),
  amount: (document.body.innerText || "").includes("USD 148.00"),
})`);
await shot("auth-1440x940.png", 1440, 940);
await shot("auth-390x844.png", 390, 844);

await loadView("receipt", "/intents/pi_01k2m3n4p5q6r7s8t9v0w1x2y3/confirmation");
notes.receipt = await evalInPage(`({
  stamp: (document.body.innerText || "").includes("SIMULATED RECEIPT"),
  session: (document.body.innerText || "").includes("browser session"),
  jetPark: (document.body.innerText || "").includes("JetPark"),
})`);
for (const vp of VIEWPORTS) {
  await shot(`receipt-${vp.name}.png`, vp.width, vp.height);
}

await loadView("reco");
await evalInPage(`document.querySelector(".re-intent-tab")?.focus()`);
await shot("reco-1440x940-focus.png", 1440, 940);
await cdp(pageWs, "Emulation.setEmulatedMedia", {
  features: [{ name: "prefers-reduced-motion", value: "reduce" }],
});
await shot("reco-1440x940-reduced-motion.png", 1440, 940);

notes.measured = await evalInPage(`(() => {
  const reco = document.querySelector(".re-reco");
  return {
    path: location.pathname,
    overflowX: document.documentElement.scrollWidth - document.documentElement.clientWidth,
    recoWidth: reco ? reco.getBoundingClientRect().width : null,
    reduced: matchMedia("(prefers-reduced-motion: reduce)").matches,
    jetPark: (document.body.innerText || "").includes("JetPark"),
    prototypePrice: (document.body.innerText || "").includes("$71.40"),
    gateWord: /\\bGate\\b/.test(document.body.innerText || ""),
  };
})()`);

writeFileSync(join(evidence, "measurements.json"), JSON.stringify(notes, null, 2));
writeFileSync(
  join(evidence, "compare.html"),
  `<!doctype html><meta charset="utf-8"><title>COMP-G1-05 Phase 4</title>
<style>
  body { margin: 24px; font: 14px/1.45 system-ui; background: #E9E6DF; color: #221F1A; }
  img { width: 100%; border: 1px solid #E6E1D8; background: #fff; }
  .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
  .cap { font: 11px/1.4 ui-monospace, monospace; color: #6C685F; margin: 8px 0; }
</style>
<h1>Phase 4 — disclosure, ranking, authorization</h1>
<p>Locked JFK vector: SkyShield 671,000 · ParkDirect 660,000 · TerminalFlex 535,000 · downside USD 29.00. No JetPark / $71.40.</p>
<section><div class="cap">Disclosure gate 1440</div><img src="gate-1440x940.png" alt="disclosure gate"></section>
<section class="grid">
  <div><div class="cap">Progress</div><img src="progress-1440x940.png" alt="supplier progress"></div>
  <div><div class="cap">Recommendation 1440</div><img src="reco-1440x940.png" alt="recommendation"></div>
</section>
<section class="grid">
  <div><div class="cap">Compare 1440</div><img src="compare-1440x940.png" alt="compare"></div>
  <div><div class="cap">Authorization</div><img src="auth-1440x940.png" alt="authorization"></div>
</section>
<section class="grid">
  <div><div class="cap">Receipt 1440</div><img src="receipt-1440x940.png" alt="receipt"></div>
  <div><div class="cap">Reco 390</div><img src="reco-390x844.png" alt="reco 390"></div>
</section>
<section class="grid">
  <div><div class="cap">Gate 320</div><img src="gate-320.png" alt="gate 320"></div>
  <div><div class="cap">Focus + reduced motion</div><img src="reco-1440x940-focus.png" alt="focus"></div>
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
