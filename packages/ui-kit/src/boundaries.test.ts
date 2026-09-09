import assert from "node:assert/strict";
import { readdirSync, readFileSync } from "node:fs";
import { dirname, join, relative } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");

const FORBIDDEN_IMPORTS = [
  "react",
  "react-dom",
  "react-native",
  "expo",
  "vite",
  "storybook",
  "fastapi",
  "vercel",
  "@vercel",
  "aws-sdk",
  "@aws-sdk",
  "cloudflare",
  "google-adk",
  "@google",
  "revenuecat",
  "@revenuecat",
  "@itaa/contracts",
  "itaa_domain",
  "itaa_application",
  "itaa_ranking",
];

const LOCKED_HEX = [
  "#221F1A",
  "#6C685F",
  "#E9E6DF",
  "#F6F3EE",
  "#E85D2C",
  "#1A1714",
  "#1BA672",
  "#CB8A1B",
  "#D9483B",
  "#E6E1D8",
];

function walk(directory: string): string[] {
  const entries = readdirSync(directory, { withFileTypes: true });
  return entries.flatMap((entry) => {
    const path = join(directory, entry.name);
    if (entry.isDirectory()) {
      if (entry.name === "node_modules") {
        return [];
      }
      return walk(path);
    }
    return [path];
  });
}

function implementationFiles(): string[] {
  return walk(join(root, "src")).filter(
    (path) => path.endsWith(".ts") && !path.endsWith(".test.ts"),
  );
}

function importSpecifiers(source: string): string[] {
  const specifiers: string[] = [];
  const pattern = /from\s+["']([^"']+)["']/g;
  for (const match of source.matchAll(pattern)) {
    const specifier = match[1];
    if (specifier !== undefined) {
      specifiers.push(specifier);
    }
  }
  return specifiers;
}

test("ui-kit has no prohibited framework, provider, or domain imports", () => {
  const files = implementationFiles();
  const failures: string[] = [];

  for (const file of files) {
    const source = readFileSync(file, "utf8");
    for (const specifier of importSpecifiers(source)) {
      for (const forbidden of FORBIDDEN_IMPORTS) {
        if (specifier === forbidden || specifier.startsWith(`${forbidden}/`)) {
          failures.push(`${relative(root, file)} imports ${specifier}`);
        }
      }
    }
    if (/\bfetch\s*\(/.test(source) || source.includes("XMLHttpRequest")) {
      failures.push(`${relative(root, file)} performs network I/O`);
    }
  }

  const manifest = JSON.parse(readFileSync(join(root, "package.json"), "utf8")) as {
    dependencies?: Record<string, string>;
    devDependencies?: Record<string, string>;
  };
  const dependencyNames = [
    ...Object.keys(manifest.dependencies ?? {}),
    ...Object.keys(manifest.devDependencies ?? {}),
  ];
  for (const forbidden of [
    "react",
    "react-dom",
    "react-native",
    "expo",
    "vite",
    "storybook",
    "vercel",
    "fastapi",
    "revenuecat",
  ]) {
    if (dependencyNames.includes(forbidden)) {
      failures.push(`package.json depends on ${forbidden}`);
    }
  }

  assert.deepEqual(failures, []);
});

test("locked hex values stay in the token source, not component implementations", () => {
  const primitiveFiles = walk(join(root, "src", "primitives")).filter((path) =>
    path.endsWith(".ts"),
  );
  const accessibility = join(root, "src", "accessibility", "index.ts");
  const failures: string[] = [];

  for (const file of [...primitiveFiles, accessibility]) {
    const source = readFileSync(file, "utf8");
    for (const hex of LOCKED_HEX) {
      if (source.toUpperCase().includes(hex.toUpperCase())) {
        failures.push(`${relative(root, file)} duplicates ${hex}`);
      }
    }
  }

  assert.deepEqual(failures, []);
});

test("primitives do not encode product or provider behavior", () => {
  const sources = walk(join(root, "src"))
    .filter((path) => path.endsWith(".ts") && !path.endsWith(".test.ts"))
    .map((path) => readFileSync(path, "utf8"))
    .join("\n");

  assert.doesNotMatch(sources, /PurchaseIntent|RevenueCat|AgentCore|Bedrock/);
  assert.doesNotMatch(sources, /createCharge|reserveBooking|authorizePayment/);
});
