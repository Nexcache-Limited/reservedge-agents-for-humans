#!/usr/bin/env node
import { spawn } from "node:child_process";
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const evidence = join(dirname(fileURLToPath(import.meta.url)), "../evidence");
const ids = JSON.parse(readFileSync(join(evidence, "live-screen-ids.json"), "utf8"));
const chrome = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const debug = 9460;
const profile = mkdtempSync(join(tmpdir(), "itaa-ui01-live-"));
const child = spawn(
  chrome,
  [
    "--headless=new",
    "--disable-gpu",
    "--no-first-run",
    `--remote-debugging-port=${debug}`,
    `--user-data-dir=${profile}`,
    "--window-size=320,4000",
    "http://localhost:5173/",
  ],
  { stdio: ["ignore", "pipe", "pipe"] },
);

async function wait() {
  for (let i = 0; i < 80; i += 1) {
    try {
      const list = await fetch(`http://127.0.0.1:${debug}/json/version`);
      if (list.ok) return;
    } catch {
      // retry
    }
    await new Promise((r) => setTimeout(r, 200));
  }
  throw new Error("chrome debug missing");
}

async function cdp(method, params = {}) {
  const targets = await fetch(`http://127.0.0.1:${debug}/json`).then((r) => r.json());
  const page = targets.find((item) => item.type === "page") ?? targets[0];
  return await new Promise((resolve, reject) => {
    const socket = new WebSocket(page.webSocketDebuggerUrl);
    let id = 0;
    socket.addEventListener("open", () => {
      id += 1;
      socket.send(JSON.stringify({ id, method, params }));
    });
    socket.addEventListener("message", (event) => {
      const payload = JSON.parse(String(event.data));
      if (payload.id === id) {
        socket.close();
        payload.error ? reject(new Error(JSON.stringify(payload.error))) : resolve(payload.result);
      }
    });
    socket.addEventListener("error", reject);
  });
}

await wait();
const screens = [
  ["inbox-live-320.png", "http://localhost:5173/"],
  ["a1-live-320.png", `http://localhost:5173/intents/${ids.a1}`],
  ["a2-live-320.png", `http://localhost:5173/intents/${ids.a2}`],
  ["offers-a3-live-320.png", `http://localhost:5173/intents/${ids.ranked}`],
  ["receipt-live-320.png", `http://localhost:5173/intents/${ids.receipt}/confirmation`],
];
const rows = [];
for (const [file, url] of screens) {
  await cdp("Page.navigate", { url });
  await new Promise((r) => setTimeout(r, 800));
  await cdp("Emulation.setDeviceMetricsOverride", {
    width: 320,
    height: 4000,
    deviceScaleFactor: 1,
    mobile: false,
  });
  const metrics = await cdp("Runtime.evaluate", {
    expression:
      "({title: document.title, innerWidth, clientWidth: document.documentElement.clientWidth, scrollWidth: document.documentElement.scrollWidth, body: document.body?.innerText?.slice(0,80)})",
    returnByValue: true,
  });
  if (String(metrics.result.value.body ?? "").includes("This site can't be reached")) {
    throw new Error(`captured error page for ${url}`);
  }
  const shot = await cdp("Page.captureScreenshot", { format: "png", fromSurface: true });
  writeFileSync(join(evidence, file), Buffer.from(shot.data, "base64"));
  rows.push({ file, url, ...metrics.result.value });
}
child.kill("SIGTERM");
await new Promise((r) => setTimeout(r, 300));
try {
  rmSync(profile, { recursive: true, force: true });
} catch {
  // ignore
}
writeFileSync(join(evidence, "live-320-measurements.json"), JSON.stringify(rows, null, 2) + "\n");
const overflow = rows.filter((item) => item.scrollWidth > item.clientWidth);
if (overflow.length > 0) {
  console.error("FAIL live 320 overflow", overflow);
  process.exit(1);
}
console.log(JSON.stringify(rows, null, 2));
console.log("PASS: live React 320 overflow");
