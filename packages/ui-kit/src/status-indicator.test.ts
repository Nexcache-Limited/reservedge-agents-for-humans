import assert from "node:assert/strict";
import test from "node:test";

import { STATUS_VARIANTS, statusIndicatorHtml } from "./index.js";

const LABELS = {
  neutral: "Ready",
  working: "Working",
  attention: "Needs review",
  confidence: "Verified",
  denial: "Failed",
  offline: "Offline",
} as const;

test("every status variant requires a visible text label", () => {
  assert.deepEqual(
    [...STATUS_VARIANTS],
    ["neutral", "working", "attention", "confidence", "denial", "offline"],
  );

  for (const variant of STATUS_VARIANTS) {
    const html = statusIndicatorHtml({ variant, label: LABELS[variant] });
    assert.match(html, new RegExp(`data-variant="${variant}"`));
    assert.match(html, /itaa-status__label/);
    assert.match(html, new RegExp(LABELS[variant]));
    assert.match(html, /role="status"/);
    assert.match(html, /itaa-status__swatch/);
    assert.match(html, /aria-hidden="true"/);
  }
});

test("color cannot replace the label", () => {
  assert.throws(
    () => statusIndicatorHtml({ variant: "confidence", label: "   " }),
    /visible text label/,
  );
  assert.throws(() => statusIndicatorHtml({ variant: "denial", label: "" }), /visible text label/);
});

test("removing the color class still leaves the label", () => {
  const html = statusIndicatorHtml({ variant: "attention", label: "Needs review" });
  const withoutColor = html.replace("itaa-status--attention", "itaa-status");
  assert.match(withoutColor, /Needs review/);
  assert.match(withoutColor, /itaa-status__label/);
  assert.doesNotMatch(withoutColor, /itaa-status--attention/);
});
