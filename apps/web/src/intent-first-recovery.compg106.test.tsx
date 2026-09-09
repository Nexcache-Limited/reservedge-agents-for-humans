import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const viteConfig = readFileSync(join(root, "vite.config.ts"), "utf8");
const webPrototype = readFileSync(join(root, "public/intent-first/web.dc.html"), "utf8");

describe("intent-first design artifacts are reference-only", () => {
  it("does not redirect the Vite front door at the dc.html canvas", () => {
    expect(viteConfig).not.toContain("intent-first-front-door");
    expect(viteConfig).not.toContain('Location", INTENT_FIRST_WEB');
  });

  it("keeps the recovered canvas as a design source, not the product runtime", () => {
    expect(webPrototype).toContain("What are you planning or trying to get done?");
    expect(webPrototype).toContain("Already know the exact booking?");
  });
});
