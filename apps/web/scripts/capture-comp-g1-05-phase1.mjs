#!/usr/bin/env node
/**
 * COMP-G1-05 Phase 1: reference HTML vs implementation screenshots + measurements.
 * Does not bind UAT ports 5173/8000.
 */
import { spawn } from "node:child_process";
import { createServer } from "node:http";
import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, extname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const repo = join(root, "../..");
const evidence = join(root, "evidence/comp-g1-05/phase-1");
const handoff = join(repo, "docs/design/source-of-truth/reservedge-v1");
mkdirSync(evidence, { recursive: true });

const chrome = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const debug = 9465;
const profile = mkdtempSync(join(tmpdir(), "comp-g1-05-"));

const MIME = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".svg": "image/svg+xml",
  ".woff2": "font/woff2",
};

const server = createServer((req, res) => {
  const raw = decodeURIComponent((req.url ?? "/").split("?")[0] ?? "/");
  let rel = raw === "/" ? "Reservedge Web.dc.html" : raw.replace(/^\//, "");
  if (rel.startsWith("_ds/") && rel.includes("/tokens/")) {
    rel = `tokens/${rel.split("/tokens/")[1]}`;
  }
  if (rel.startsWith("_ds/") && rel.endsWith("styles.css")) {
    res.setHeader("content-type", "text/css");
    res.end("/* design-system styles omitted; tokens loaded separately */");
    return;
  }
  if (rel.startsWith("_ds/") && rel.endsWith("_ds_bundle.js")) {
    res.setHeader("content-type", "text/javascript");
    res.end("/* design-system bundle omitted */");
    return;
  }
  const file = join(handoff, rel);
  if (!file.startsWith(handoff) || !existsSync(file)) {
    res.statusCode = 404;
    res.end("not found");
    return;
  }
  res.setHeader("content-type", MIME[extname(file)] ?? "application/octet-stream");
  res.end(readFileSync(file));
});

await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
const refPort = server.address().port;
const refWeb = `http://127.0.0.1:${refPort}/Reservedge%20Web.dc.html`;
const refMobile = `http://127.0.0.1:${refPort}/Reservedge%20Mobile.dc.html`;

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

const version = await fetch(`http://127.0.0.1:${debug}/json/version`).then((r) => r.json());
const browserWs = version.webSocketDebuggerUrl;

function cdpSession(wsUrl) {
  return new Promise((resolve, reject) => {
    const socket = new WebSocket(wsUrl);
    let nextId = 0;
    const pending = new Map();
    socket.addEventListener("open", () => resolve({ socket, pending, nextId: () => ++nextId }));
    socket.addEventListener("error", reject);
  });
}

const browser = await cdpSession(browserWs);

function send(session, method, params = {}) {
  return new Promise((resolve, reject) => {
    const id = session.nextId();
    session.pending.set(id, { resolve, reject });
    session.socket.send(JSON.stringify({ id, method, params }));
    const onMessage = (event) => {
      const payload = JSON.parse(String(event.data));
      if (payload.id === id) {
        session.socket.removeEventListener("message", onMessage);
        payload.error ? reject(new Error(JSON.stringify(payload.error))) : resolve(payload.result);
      }
    };
    session.socket.addEventListener("message", onMessage);
  });
}

async function pageSession() {
  const created = await send(browser, "Target.createTarget", { url: "about:blank" });
  const attached = await send(browser, "Target.attachToTarget", {
    targetId: created.targetId,
    flatten: true,
  });
  const page = {
    sessionId: attached.sessionId,
    call(method, params = {}) {
      return new Promise((resolve, reject) => {
        const id = browser.nextId();
        browser.pending.set(id, { resolve, reject });
        browser.socket.send(
          JSON.stringify({
            id,
            method: "Target.sendMessageToTarget",
            params: {
              sessionId: attached.sessionId,
              message: JSON.stringify({ id, method, params }),
            },
          }),
        );
      });
    },
  };
  browser.socket.addEventListener("message", (event) => {
    const outer = JSON.parse(String(event.data));
    if (outer.method === "Target.receivedMessageFromTarget") {
      const inner = JSON.parse(outer.params.message);
      const waiter = browser.pending.get(inner.id);
      if (waiter) {
        browser.pending.delete(inner.id);
        inner.error
          ? waiter.reject(new Error(JSON.stringify(inner.error)))
          : waiter.resolve(inner.result);
      }
    }
    const waiter = browser.pending.get(outer.id);
    if (waiter && outer.method === undefined) {
      browser.pending.delete(outer.id);
      outer.error
        ? waiter.reject(new Error(JSON.stringify(outer.error)))
        : waiter.resolve(outer.result);
    }
  });
  return page;
}

async function capture(page, url, path, width, height, scale = 1, settleMs = 2500) {
  await send(browser, "Target.sendMessageToTarget", {
    sessionId: page.sessionId,
    message: JSON.stringify({
      id: 1,
      method: "Emulation.setDeviceMetricsOverride",
      params: {
        width,
        height,
        deviceScaleFactor: scale,
        mobile: width <= 410,
      },
    }),
  }).catch(() => undefined);

  const navId = browser.nextId();
  await new Promise((resolve, reject) => {
    browser.pending.set(navId, { resolve, reject });
    browser.socket.send(
      JSON.stringify({
        id: navId,
        method: "Target.sendMessageToTarget",
        params: {
          sessionId: page.sessionId,
          message: JSON.stringify({
            id: navId,
            method: "Page.navigate",
            params: { url },
          }),
        },
      }),
    );
  });
  await new Promise((r) => setTimeout(r, settleMs));
  if (url.includes("Mobile")) {
    await evalOn(
      page,
      `(() => {
      const outer = document.querySelector("body > x-dc > div, body > div");
      const phone = outer && outer.querySelector(":scope > div");
      const inner = phone && phone.querySelector(":scope > div");
      if (inner) {
        document.body.style.margin = "0";
        document.body.style.background = "#F6F3EE";
        outer.style.cssText = "margin:0;padding:0;min-height:100vh;background:#F6F3EE";
        phone.style.cssText = "width:100%;height:100vh;border-radius:0;padding:0;box-shadow:none;background:transparent";
        inner.style.cssText = inner.style.cssText + ";width:100%;height:100vh;border-radius:0";
        const status = inner.querySelector(":scope > div");
        if (status && status.textContent && status.textContent.includes("9:41")) {
          status.style.display = "none";
        }
      }
    })()`,
    );
    await new Promise((r) => setTimeout(r, 200));
  }
  const shot = await evalCdp(page, "Page.captureScreenshot", { format: "png" });
  writeFileSync(path, Buffer.from(shot.data, "base64"));
}

function evalOn(page, expression) {
  return evalCdp(page, "Runtime.evaluate", { expression, returnByValue: true, awaitPromise: true });
}

function evalCdp(page, method, params) {
  const id = browser.nextId();
  return new Promise((resolve, reject) => {
    const onMessage = (event) => {
      const outer = JSON.parse(String(event.data));
      if (
        outer.method === "Target.receivedMessageFromTarget" &&
        outer.params.sessionId === page.sessionId
      ) {
        const inner = JSON.parse(outer.params.message);
        if (inner.id === id) {
          browser.socket.removeEventListener("message", onMessage);
          inner.error ? reject(new Error(JSON.stringify(inner.error))) : resolve(inner.result);
        }
      }
      if (outer.id === id && !outer.method) {
        browser.socket.removeEventListener("message", onMessage);
        outer.error ? reject(new Error(JSON.stringify(outer.error))) : resolve(outer.result);
      }
    };
    browser.socket.addEventListener("message", onMessage);
    browser.socket.send(
      JSON.stringify({
        id,
        method: "Target.sendMessageToTarget",
        params: {
          sessionId: page.sessionId,
          message: JSON.stringify({ id, method, params }),
        },
      }),
    );
  });
}

const targets = await fetch(`http://127.0.0.1:${debug}/json`).then((r) => r.json());
const pageTarget = targets.find((item) => item.type === "page") ?? targets[0];
const pageWs = await cdpSession(pageTarget.webSocketDebuggerUrl);

async function simpleCapture(
  url,
  file,
  width,
  height,
  scale = 1,
  extraEval = null,
  settleMs = 4000,
) {
  await cdp(pageWs, "Emulation.setDeviceMetricsOverride", {
    width,
    height,
    deviceScaleFactor: scale,
    mobile: width <= 410,
  });
  await cdp(pageWs, "Page.enable");
  await cdp(pageWs, "Page.navigate", { url });
  await new Promise((r) => setTimeout(r, settleMs));
  if (extraEval) {
    await cdp(pageWs, "Runtime.evaluate", { expression: extraEval, returnByValue: true });
    await new Promise((r) => setTimeout(r, 250));
  }
  const shot = await cdp(pageWs, "Page.captureScreenshot", {
    format: "png",
    captureBeyondViewport: false,
  });
  writeFileSync(file, Buffer.from(shot.result?.data ?? shot.data, "base64"));
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

const STRIP_MOBILE_CHROME = `(() => {
  const candidates = [...document.querySelectorAll("div")];
  const phone = candidates.find((el) => el.style && el.style.height === "874px");
  const inner = phone && phone.querySelector(":scope > div");
  if (!inner) return "no-phone";
  document.body.style.margin = "0";
  document.body.style.background = "#F6F3EE";
  const outer = phone.parentElement;
  if (outer) {
    outer.style.padding = "0";
    outer.style.minHeight = "100vh";
    outer.style.background = "#F6F3EE";
    outer.style.display = "block";
  }
  phone.style.cssText = "width:100%;height:100vh;border-radius:0;padding:0;box-shadow:none;background:transparent";
  inner.style.borderRadius = "0";
  inner.style.height = "100vh";
  const status = inner.firstElementChild;
  if (status && /9:41/.test(status.textContent || "")) status.style.display = "none";
  return "stripped";
})()`;

const VIEWPORTS = [
  { name: "1440x940", width: 1440, height: 940, html: "web" },
  { name: "1280x800", width: 1280, height: 800, html: "web" },
  { name: "410x874", width: 410, height: 874, html: "mobile" },
  { name: "390x844", width: 390, height: 844, html: "mobile" },
  { name: "320", width: 320, height: 844, html: "mobile" },
];

for (const vp of VIEWPORTS) {
  const url = vp.html === "web" ? refWeb : refMobile;
  const extra = vp.html === "mobile" ? STRIP_MOBILE_CHROME : null;
  const settle = vp.html === "web" ? 8000 : 8000;
  console.log(`reference ${vp.name}`);
  await simpleCapture(
    url,
    join(evidence, `reference-${vp.name}.png`),
    vp.width,
    vp.height,
    1,
    extra,
    settle,
  );
}

const vite = spawn(
  "pnpm",
  ["--filter", "@itaa/web", "exec", "vite", "--host", "127.0.0.1", "--port", "5180"],
  {
    cwd: repo,
    stdio: "pipe",
  },
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
await new Promise((r) => setTimeout(r, 800));

const MEASURE = `(() => {
  const rgb = (el, prop) => {
    if (!el) return null;
    return getComputedStyle(el)[prop];
  };
  const app = document.querySelector(".re-app");
  const rail = document.querySelector(".re-rail");
  const list = document.querySelector(".re-list");
  const detail = document.querySelector(".re-detail");
  const btn = document.querySelector(".re-new");
  const card = document.querySelector(".re-row");
  const tabs = document.querySelector(".re-tabs");
  const hits = [...document.querySelectorAll("button, a.re-tab, a.re-rail-btn")].map((el) => {
    const box = el.getBoundingClientRect();
    return { label: (el.textContent || "").trim().slice(0, 40), w: Math.round(box.width), h: Math.round(box.height) };
  });
  return {
    body: rgb(document.body, "backgroundColor"),
    app: rgb(app, "backgroundColor"),
    font: rgb(app, "fontFamily"),
    railDisplay: rail ? getComputedStyle(rail).display : null,
    railW: rail ? Math.round(rail.getBoundingClientRect().width) : 0,
    listW: list ? Math.round(list.getBoundingClientRect().width) : 0,
    detailW: detail ? Math.round(detail.getBoundingClientRect().width) : 0,
    btnBg: btn ? rgb(btn, "backgroundColor") : null,
    cardRadius: card ? getComputedStyle(card).borderRadius : null,
    tabsBottom: tabs ? Math.round(tabs.getBoundingClientRect().bottom) : null,
    overflowX: document.documentElement.scrollWidth - document.documentElement.clientWidth,
    viewport: { w: window.innerWidth, h: window.innerHeight },
    hits: hits.slice(0, 24),
  };
})()`;

const measures = {};
for (const vp of VIEWPORTS) {
  console.log(`impl ${vp.name}`);
  await simpleCapture(
    `http://127.0.0.1:5180/`,
    join(evidence, `impl-${vp.name}.png`),
    vp.width,
    vp.height,
    1,
    null,
    1200,
  );
  const measured = await cdp(pageWs, "Runtime.evaluate", {
    expression: MEASURE,
    returnByValue: true,
  });
  measures[vp.name] = measured.result?.value ?? measured.value;
}

console.log("impl 1440 200%");
await simpleCapture(
  `http://127.0.0.1:5180/`,
  join(evidence, "impl-1440x940-200zoom.png"),
  1440,
  940,
  2,
  null,
  1200,
);

await simpleCapture(
  refWeb,
  join(evidence, "reference-1440x940-200zoom.png"),
  1440,
  940,
  2,
  null,
  8000,
);

writeFileSync(join(evidence, "measurements.json"), JSON.stringify(measures, null, 2));

await cdp(pageWs, "Emulation.setDeviceMetricsOverride", {
  width: 1440,
  height: 940,
  deviceScaleFactor: 1,
  mobile: false,
});
await cdp(pageWs, "Page.navigate", { url: "http://127.0.0.1:5180/" });
await new Promise((r) => setTimeout(r, 1000));
await cdp(pageWs, "Runtime.evaluate", {
  expression: `document.querySelector(".re-new")?.focus()`,
});
await new Promise((r) => setTimeout(r, 200));
const focusShot = await cdp(pageWs, "Page.captureScreenshot", { format: "png" });
writeFileSync(join(evidence, "impl-1440x940-focus.png"), Buffer.from(focusShot.data, "base64"));

await cdp(pageWs, "Emulation.setEmulatedMedia", {
  features: [{ name: "prefers-reduced-motion", value: "reduce" }],
});
await cdp(pageWs, "Page.navigate", { url: "http://127.0.0.1:5180/" });
await new Promise((r) => setTimeout(r, 1000));
const motionShot = await cdp(pageWs, "Page.captureScreenshot", { format: "png" });
writeFileSync(
  join(evidence, "impl-1440x940-reduced-motion.png"),
  Buffer.from(motionShot.data, "base64"),
);

writeFileSync(
  join(evidence, "compare.html"),
  `<!doctype html><meta charset="utf-8"><title>COMP-G1-05 Phase 1 visual compare</title>
<style>
  body { margin: 24px; font: 14px/1.45 system-ui, sans-serif; background: #E9E6DF; color: #221F1A; }
  h1 { font-size: 22px; }
  section { margin: 28px 0; }
  .pair { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
  img { width: 100%; border: 1px solid #E6E1D8; background: #fff; }
  .cap { font: 11px/1.4 ui-monospace, monospace; color: #6C685F; margin-bottom: 6px; }
</style>
<h1>Phase 1 — reference vs implementation</h1>
<p>Left: rendered Reservedge HTML. Right: apps/web. Inbox / shell only.</p>
${VIEWPORTS.map(
  (vp) =>
    `<section><div class="cap">${vp.name}</div><div class="pair"><div><div class="cap">reference</div><img src="reference-${vp.name}.png" alt="reference ${vp.name}"></div><div><div class="cap">implementation</div><img src="impl-${vp.name}.png" alt="implementation ${vp.name}"></div></div></section>`,
).join("\n")}
`,
);

vite.kill("SIGTERM");
chromeProc.kill("SIGTERM");
server.close();
try {
  rmSync(profile, { recursive: true, force: true });
} catch {
  // Chrome may still hold the profile directory.
}
console.log(`wrote ${evidence}`);
