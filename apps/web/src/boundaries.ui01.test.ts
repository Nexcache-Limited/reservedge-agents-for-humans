import { readFileSync, readdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");

const FORBIDDEN = [
  "vercel",
  "@vercel",
  "@google",
  "aws-sdk",
  "@aws-sdk",
  "revenuecat",
  "@revenuecat",
  "gtag",
  "analytics.google",
];

function walk(directory: string): string[] {
  return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const path = join(directory, entry.name);
    if (
      entry.isDirectory() &&
      entry.name !== "node_modules" &&
      entry.name !== "dist" &&
      entry.name !== "coverage"
    ) {
      return walk(path);
    }
    return [path];
  });
}

describe("UI-01 boundaries", () => {
  it("has no Vercel, Google, AWS, or analytics dependencies", () => {
    const manifest = JSON.parse(readFileSync(join(root, "package.json"), "utf8")) as {
      dependencies?: Record<string, string>;
      devDependencies?: Record<string, string>;
    };
    const names = [
      ...Object.keys(manifest.dependencies ?? {}),
      ...Object.keys(manifest.devDependencies ?? {}),
    ];
    expect(names.some((name) => FORBIDDEN.some((item) => name.includes(item)))).toBe(false);
    expect(names).toContain("react");
    expect(names).toContain("vite");
  });

  it("keeps fetch inside the API client and colors inside tokens", () => {
    const sources = walk(join(root, "src"))
      .filter((path) => path.endsWith(".ts") || path.endsWith(".tsx"))
      .filter((path) => !path.includes(".ui01.test.") && !path.includes(".test."));
    const failures: string[] = [];
    for (const file of sources) {
      const source = readFileSync(file, "utf8");
      const relative = file.slice(root.length + 1);
      if (relative !== "src/api/client.ts" && /\bfetch\s*\(/.test(source)) {
        failures.push(`${relative} calls fetch`);
      }
      if (
        relative !== "src/api/progress.ts" &&
        /\bEventSource\b/.test(source) &&
        !relative.endsWith(".ui07.test.ts")
      ) {
        failures.push(`${relative} constructs EventSource`);
      }
      if (/#[0-9A-Fa-f]{6}/.test(source) && !relative.includes("test/")) {
        failures.push(`${relative} contains a raw hex color`);
      }
    }
    expect(failures).toEqual([]);
  });
});
