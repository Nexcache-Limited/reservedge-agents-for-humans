#!/usr/bin/env node
/**
 * COMP-G1-05 Phase 2: domain picker + composer screenshots.
 * Does not bind UAT ports 5173/8000. Uses 5181 for this evidence pass.
 */
import { spawn } from "node:child_process";
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const repo = join(root, "../..");
const evidence = join(root, "evidence/comp-g1-05/phase-2");
mkdirSync(evidence, { recursive: true });

const chrome = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const debug = 9467;
const profile = mkdtempSync(join(tmpdir(), "comp-g1-05-p2-"));
const port = 5183;

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
const pageWs = await cdpSession(pageTarget.webSocketDebuggerUrl);

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
  await new Promise((r) => setTimeout(r, 400));
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
  await new Promise((r) => setTimeout(r, 1200));
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
  { name: "1280x800", width: 1280, height: 800 },
  { name: "410x874", width: 410, height: 874 },
  { name: "390x844", width: 390, height: 844 },
  { name: "320", width: 320, height: 844 },
];

const CLICK_PARKING = `document.querySelector("button.re-domain-card")?.click()`;
const ANSWER_Q1 = `(() => {
  const chip = document.querySelector(".re-chips button");
  chip?.click();
  return chip ? chip.textContent : "none";
})()`;

const measures = {};
for (const vp of VIEWPORTS) {
  await go("/intents/new");
  await shot(`picker-${vp.name}.png`, vp.width, vp.height);
  const measured = await cdp(pageWs, "Runtime.evaluate", {
    expression: `(() => {
      const app = document.querySelector(".re-app");
      const grid = document.querySelector(".re-domain-grid");
      const cards = [...document.querySelectorAll(".re-domain-card")];
      return {
        body: getComputedStyle(document.body).backgroundColor,
        app: app ? getComputedStyle(app).backgroundColor : null,
        font: app ? getComputedStyle(app).fontFamily : null,
        gridOverflow: grid ? grid.scrollWidth - grid.clientWidth : 0,
        overflowX: document.documentElement.scrollWidth - document.documentElement.clientWidth,
        cardCount: cards.length,
        cardRadius: cards[0] ? getComputedStyle(cards[0]).borderRadius : null,
        spa: (document.body.innerText || "").includes("Spa is next"),
        flags: cards.map((el) => ({
          name: el.querySelector(".re-domain-card-name")?.textContent,
          flag: el.querySelector(".re-demo-flag, .re-path-flag")?.textContent,
        })),
      };
    })()`,
    returnByValue: true,
  });
  measures[vp.name] = measured.value ?? measured.result?.value;
}

await go("/intents/new");
await cdp(pageWs, "Emulation.setDeviceMetricsOverride", {
  width: 1440,
  height: 940,
  deviceScaleFactor: 1,
  mobile: false,
});
await cdp(pageWs, "Runtime.evaluate", { expression: CLICK_PARKING, returnByValue: true });
await new Promise((r) => setTimeout(r, 600));
await shot("composer-parking-step1-1440x940.png", 1440, 940);

await go("/intents/new/rental");
await shot("composer-rental-step1-1440x940.png", 1440, 940);
await cdp(pageWs, "Runtime.evaluate", {
  expression: `(() => {
    const example = [...document.querySelectorAll("button")].find((el) => (el.textContent || "").includes("Use the example"));
    example?.click();
    return Boolean(example);
  })()`,
  returnByValue: true,
});
await new Promise((r) => setTimeout(r, 400));
await cdp(pageWs, "Runtime.evaluate", {
  expression: `(() => {
    const send = [...document.querySelectorAll("button")].find((el) => (el.textContent || "").trim() === "Send to Reservedge");
    send?.click();
    return send ? send.disabled : "missing";
  })()`,
  returnByValue: true,
});
await new Promise((r) => setTimeout(r, 700));
await shot("composer-rental-q1-1440x940.png", 1440, 940);
const q1 = await cdp(pageWs, "Runtime.evaluate", { expression: ANSWER_Q1, returnByValue: true });
await new Promise((r) => setTimeout(r, 400));
await shot("composer-rental-requirement-1440x940.png", 1440, 940);

await go("/intents/new/ents");
await shot("composer-ents-step1-1440x940.png", 1440, 940);

await go("/intents/new");
await cdp(pageWs, "Emulation.setDeviceMetricsOverride", {
  width: 410,
  height: 874,
  deviceScaleFactor: 1,
  mobile: true,
});
await new Promise((r) => setTimeout(r, 400));
await shot("picker-mobile-410x874.png", 410, 874);
await cdp(pageWs, "Runtime.evaluate", { expression: CLICK_PARKING, returnByValue: true });
await new Promise((r) => setTimeout(r, 600));
await shot("composer-mobile-410x874.png", 410, 874);

await cdp(pageWs, "Emulation.setDeviceMetricsOverride", {
  width: 1440,
  height: 940,
  deviceScaleFactor: 1,
  mobile: false,
});
await go("/intents/new");
await cdp(pageWs, "Runtime.evaluate", {
  expression: `document.querySelector(".re-domain-card")?.focus()`,
});
await new Promise((r) => setTimeout(r, 200));
await shot("picker-1440x940-focus.png", 1440, 940);

await cdp(pageWs, "Emulation.setEmulatedMedia", {
  features: [{ name: "prefers-reduced-motion", value: "reduce" }],
});
await go("/intents/new");
await shot("picker-1440x940-reduced-motion.png", 1440, 940);

writeFileSync(
  join(evidence, "measurements.json"),
  JSON.stringify({ measures, rentalQ1: q1.value ?? q1.result?.value }, null, 2),
);
writeFileSync(
  join(evidence, "compare.html"),
  `<!doctype html><meta charset="utf-8"><title>COMP-G1-05 Phase 2</title>
<style>
  body { margin: 24px; font: 14px/1.45 system-ui; background: #E9E6DF; color: #221F1A; }
  img { width: 100%; border: 1px solid #E6E1D8; background: #fff; }
  .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
  .cap { font: 11px/1.4 ui-monospace, monospace; color: #6C685F; margin: 8px 0; }
</style>
<h1>Phase 2 — domain picker and bounded composer</h1>
<p>Implementation only (design HTML has no isolated composer route). Spa copy must be absent.</p>
<section><div class="cap">Picker 1440</div><img src="picker-1440x940.png" alt="picker desktop"></section>
<section><div class="cap">Picker 410</div><img src="picker-410x874.png" alt="picker mobile"></section>
<section class="grid">
  <div><div class="cap">Parking step 1</div><img src="composer-parking-step1-1440x940.png" alt="parking composer"></div>
  <div><div class="cap">Rental question 1 + requirement</div><img src="composer-rental-q1-1440x940.png" alt="rental q1"></div>
</section>
<section class="grid">
  <div><div class="cap">Rental after first answer</div><img src="composer-rental-requirement-1440x940.png" alt="rental requirement"></div>
  <div><div class="cap">Entertainment step 1</div><img src="composer-ents-step1-1440x940.png" alt="ents composer"></div>
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
