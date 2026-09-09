import assert from "node:assert/strict";
import test from "node:test";

import {
  CONTRAST_LARGE_TEXT_MIN,
  CONTRAST_NON_TEXT_MIN,
  CONTRAST_TEXT_MIN,
  LOCKED_LIGHT_COLORS,
  colorRoles,
  contrastRatio,
} from "./index.js";

interface ContrastCase {
  name: string;
  foreground: string;
  background: string;
  minimum: number;
}

const TEXT_PAIRS: ContrastCase[] = [
  {
    name: "primary text on raised surface",
    foreground: colorRoles.text.primary,
    background: colorRoles.surface.raised,
    minimum: CONTRAST_TEXT_MIN,
  },
  {
    name: "primary text on canvas",
    foreground: colorRoles.text.primary,
    background: colorRoles.surface.canvas,
    minimum: CONTRAST_TEXT_MIN,
  },
  {
    name: "secondary text on raised surface",
    foreground: colorRoles.text.secondary,
    background: colorRoles.surface.raised,
    minimum: CONTRAST_TEXT_MIN,
  },
  {
    name: "secondary text on canvas",
    foreground: colorRoles.text.secondary,
    background: colorRoles.surface.canvas,
    minimum: CONTRAST_TEXT_MIN,
  },
  {
    name: "inverse text on simulation rail",
    foreground: colorRoles.text.inverse,
    background: colorRoles.surface.simulation,
    minimum: CONTRAST_TEXT_MIN,
  },
  {
    name: "primary text on confidence tint",
    foreground: colorRoles.text.primary,
    background: colorRoles.surface.confidenceTint,
    minimum: CONTRAST_TEXT_MIN,
  },
  {
    name: "primary text on attention tint",
    foreground: colorRoles.text.primary,
    background: colorRoles.surface.attentionTint,
    minimum: CONTRAST_TEXT_MIN,
  },
  {
    name: "primary text on denial tint",
    foreground: colorRoles.text.primary,
    background: colorRoles.surface.denialTint,
    minimum: CONTRAST_TEXT_MIN,
  },
];

const LARGE_TEXT_PAIRS: ContrastCase[] = [
  {
    name: "secondary metadata as large editorial text on canvas",
    foreground: colorRoles.text.secondary,
    background: colorRoles.surface.canvas,
    minimum: CONTRAST_LARGE_TEXT_MIN,
  },
];

const NON_TEXT_PAIRS: ContrastCase[] = [
  {
    name: "focus ring on raised surface",
    foreground: colorRoles.focus.ring,
    background: colorRoles.surface.raised,
    minimum: CONTRAST_NON_TEXT_MIN,
  },
  {
    name: "ghost button strong border on raised surface",
    foreground: colorRoles.border.strong,
    background: colorRoles.surface.raised,
    minimum: CONTRAST_NON_TEXT_MIN,
  },
  {
    name: "inverse text on primary coral control",
    foreground: colorRoles.text.inverse,
    background: colorRoles.action.primary,
    minimum: CONTRAST_NON_TEXT_MIN,
  },
  {
    name: "inverse text on consent control",
    foreground: colorRoles.text.inverse,
    background: colorRoles.action.consent,
    minimum: CONTRAST_NON_TEXT_MIN,
  },
  {
    name: "inverse text on destructive control",
    foreground: colorRoles.text.inverse,
    background: colorRoles.action.destructive,
    minimum: CONTRAST_NON_TEXT_MIN,
  },
];

test("approved text combinations meet 4.5:1 contrast", () => {
  for (const pair of TEXT_PAIRS) {
    const ratio = contrastRatio(pair.foreground, pair.background);
    assert.ok(
      ratio + Number.EPSILON >= pair.minimum,
      `${pair.name} is ${ratio.toFixed(2)}:1, need ${pair.minimum}:1`,
    );
  }
});

test("large-text combinations meet 3:1 contrast", () => {
  for (const pair of LARGE_TEXT_PAIRS) {
    const ratio = contrastRatio(pair.foreground, pair.background);
    assert.ok(
      ratio + Number.EPSILON >= pair.minimum,
      `${pair.name} is ${ratio.toFixed(2)}:1, need ${pair.minimum}:1`,
    );
  }
});

test("meaningful non-text boundaries meet 3:1 contrast", () => {
  for (const pair of NON_TEXT_PAIRS) {
    const ratio = contrastRatio(pair.foreground, pair.background);
    assert.ok(
      ratio + Number.EPSILON >= pair.minimum,
      `${pair.name} is ${ratio.toFixed(2)}:1, need ${pair.minimum}:1`,
    );
  }
});

test("rule on surface is a documented decorative separator exception", () => {
  const ratio = contrastRatio(LOCKED_LIGHT_COLORS.rule, LOCKED_LIGHT_COLORS.surface);
  assert.ok(ratio < CONTRAST_NON_TEXT_MIN);
  assert.equal(colorRoles.border.default, LOCKED_LIGHT_COLORS.rule);
});
