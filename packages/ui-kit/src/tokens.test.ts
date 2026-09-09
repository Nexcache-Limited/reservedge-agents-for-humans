import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import {
  COLOR_USAGE,
  CSS_VAR,
  LOCKED_LIGHT_COLORS,
  SEMANTIC_TOKEN_NAMES,
  colorRoles,
  focusTreatment,
  fontFamilies,
  implementedThemes,
  lightTints,
  motion,
  radiusPx,
  renderStylesheet,
  semanticToken,
  spacingPx,
  spacingScalePx,
  themeSlots,
  touchTargetPx,
  typeRoles,
} from "./index.js";

test("semantic token contract is complete and stable", () => {
  assert.deepEqual(
    [...SEMANTIC_TOKEN_NAMES],
    [
      "text.primary",
      "text.secondary",
      "text.tertiary",
      "text.inverse",
      "surface.page",
      "surface.canvas",
      "surface.raised",
      "surface.muted",
      "surface.rail",
      "surface.confidenceTint",
      "surface.attentionTint",
      "surface.denialTint",
      "surface.infoTint",
      "surface.accentSoft",
      "surface.neutralTint",
      "surface.simulation",
      "status.neutral",
      "status.working",
      "status.attention",
      "status.confidence",
      "status.denial",
      "status.info",
      "status.offline",
      "border.default",
      "border.subtle",
      "border.strong",
      "border.focus",
      "action.primary",
      "action.pressed",
      "action.consent",
      "action.destructive",
      "action.ghost",
      "focus.ring",
    ],
  );

  for (const name of SEMANTIC_TOKEN_NAMES) {
    assert.equal(typeof semanticToken(name), "string");
    assert.ok(semanticToken(name).length > 0);
  }
});

test("locked light-theme colors are the approved Reservedge values", () => {
  assert.deepEqual(LOCKED_LIGHT_COLORS, {
    ink: "#221F1A",
    muted: "#6C685F",
    tertiary: "#9B968B",
    desk: "#E9E6DF",
    canvas: "#F6F3EE",
    surface: "#FFFFFF",
    mutedFill: "#F0EDE6",
    rail: "#1A1714",
    accent: "#E85D2C",
    accentPressed: "#CE4E22",
    accentSoft: "#FBE9DE",
    confidence: "#1BA672",
    attention: "#CB8A1B",
    denial: "#D9483B",
    info: "#2F6FED",
    rule: "#E6E1D8",
    ruleSubtle: "#EFEBE3",
  });

  assert.equal(colorRoles.text.primary, LOCKED_LIGHT_COLORS.ink);
  assert.equal(colorRoles.text.secondary, LOCKED_LIGHT_COLORS.muted);
  assert.equal(colorRoles.surface.page, LOCKED_LIGHT_COLORS.desk);
  assert.equal(colorRoles.surface.canvas, LOCKED_LIGHT_COLORS.canvas);
  assert.equal(colorRoles.surface.raised, LOCKED_LIGHT_COLORS.surface);
  assert.equal(colorRoles.status.confidence, LOCKED_LIGHT_COLORS.confidence);
  assert.equal(colorRoles.status.attention, LOCKED_LIGHT_COLORS.attention);
  assert.equal(colorRoles.status.denial, LOCKED_LIGHT_COLORS.denial);
  assert.equal(colorRoles.border.default, LOCKED_LIGHT_COLORS.rule);
  assert.equal(colorRoles.surface.simulation, LOCKED_LIGHT_COLORS.rail);
  assert.equal(colorRoles.action.primary, LOCKED_LIGHT_COLORS.accent);
});

test("color roles document meaning without deal or urgency shortcuts", () => {
  assert.match(COLOR_USAGE.confidence, /never best deal/i);
  assert.match(COLOR_USAGE.attention, /not urgency/i);
  assert.match(COLOR_USAGE.denial, /invalidated approval/i);
  assert.equal(colorRoles.surface.confidenceTint, lightTints.confidence);
  assert.equal(lightTints.confidence, "#E3F4EB");
  assert.equal(lightTints.attention, "#FBEFD6");
  assert.equal(lightTints.denial, "#FBE3E0");
});

test("typography roles use Schibsted Grotesk and JetBrains Mono without remote fonts", () => {
  assert.match(fontFamilies.editorial, /Schibsted Grotesk/);
  assert.doesNotMatch(fontFamilies.editorial, /Newsreader|Georgia/);
  assert.match(fontFamilies.interface, /Schibsted Grotesk/);
  assert.match(fontFamilies.interface, /system-ui/);
  assert.match(fontFamilies.facts, /JetBrains Mono/);
  assert.match(fontFamilies.facts, /ui-monospace/);
  assert.equal(typeRoles.body.fontSizeRem, 1);
  assert.equal(typeRoles.fact.fontVariantNumeric, "tabular-nums");
  assert.ok(typeRoles.body.fontSizeRem * 16 >= 16);
});

test("spacing, radius, motion, focus, and touch targets are locked", () => {
  assert.equal(spacingPx.base, 4);
  assert.deepEqual([...spacingScalePx], [4, 8, 12, 16, 24, 32, 40]);
  assert.equal(radiusPx.card, 16);
  assert.equal(radiusPx.cardMin, 14);
  assert.equal(radiusPx.cardMax, 20);
  assert.equal(radiusPx.pill, 999);
  assert.equal(touchTargetPx.min, 44);
  assert.equal(motion.durationMs.standard, 300);
  assert.equal(motion.easing.standard, "cubic-bezier(0.2, 0.7, 0.3, 1)");
  assert.equal(motion.reducedMotionDurationMs, 0);
  assert.equal(focusTreatment.widthPx, 2);
  assert.equal(focusTreatment.offsetPx, 2);
  assert.equal(focusTreatment.color, LOCKED_LIGHT_COLORS.ink);
});

test("token structure reserves a dark theme slot without implementing dark values", () => {
  assert.deepEqual([...themeSlots], ["light", "dark"]);
  assert.deepEqual([...implementedThemes], ["light"]);
});

function customPropertyMap(css: string): Map<string, string> {
  const values = new Map<string, string>();
  for (const match of css.matchAll(/(--itaa-[\w-]+):\s*([^;]+);/g)) {
    const name = match[1];
    const value = match[2];
    if (name !== undefined && value !== undefined) {
      values.set(name, value.trim().toLowerCase());
    }
  }
  return values;
}

test("stylesheet custom properties are generated from the typed tokens", () => {
  const css = renderStylesheet();
  const committed = readFileSync(
    join(dirname(fileURLToPath(import.meta.url)), "itaa-ui-kit.css"),
    "utf8",
  );
  assert.deepEqual(customPropertyMap(committed), customPropertyMap(css));
  assert.match(css, new RegExp(`${CSS_VAR.textPrimary}: ${LOCKED_LIGHT_COLORS.ink}`));
  assert.match(css, new RegExp(`${CSS_VAR.surfaceCanvas}: ${LOCKED_LIGHT_COLORS.canvas}`));
  assert.match(css, new RegExp(`${CSS_VAR.surfacePage}: ${LOCKED_LIGHT_COLORS.desk}`));
  assert.match(css, new RegExp(`${CSS_VAR.layoutRail}: 236px`));
  assert.match(css, new RegExp(`${CSS_VAR.statusConfidence}: ${LOCKED_LIGHT_COLORS.confidence}`));
  assert.match(css, new RegExp(`${CSS_VAR.touchMin}: 44px`));
  assert.match(css, new RegExp(`${CSS_VAR.motionDuration}: 300ms`));
  assert.match(css, /prefers-reduced-motion:\s*reduce/);
  assert.doesNotMatch(css, /url\(https?:\/\//);
  assert.match(css, /Schibsted Grotesk/);
  assert.match(css, /\.\/fonts\/schibsted-grotesk-latin-wght-normal\.woff2/);
});
