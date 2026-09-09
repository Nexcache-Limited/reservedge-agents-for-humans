import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import {
  BUTTON_STATES,
  BUTTON_VARIANTS,
  buttonHtml,
  FOCUS_RING_CLASS,
  renderStylesheet,
  touchTargetPx,
} from "./index.js";

const source = readFileSync(
  join(dirname(fileURLToPath(import.meta.url)), "primitives", "button.ts"),
  "utf8",
);

test("button variants and states are the approved set", () => {
  assert.deepEqual([...BUTTON_VARIANTS], ["primary", "consent", "ghost", "destructive"]);
  assert.deepEqual(
    [...BUTTON_STATES],
    ["default", "hover", "focus-visible", "pressed", "disabled", "busy"],
  );
});

test("button is keyboard activatable and exposes default, disabled, and busy semantics", () => {
  const ready = buttonHtml({ label: "Continue", id: "continue" });
  assert.match(ready, /type="button"/);
  assert.match(ready, /data-state="default"/);
  assert.match(ready, new RegExp(FOCUS_RING_CLASS));
  assert.match(ready, />Continue</);
  assert.doesNotMatch(ready, /aria-busy/);
  assert.doesNotMatch(ready, /aria-disabled/);
  assert.doesNotMatch(ready, /aria-describedby/);
  assert.doesNotMatch(ready, /continue-reason/);
  assert.doesNotMatch(ready, /itaa-visually-hidden/);

  const disabled = buttonHtml({
    label: "Authorize",
    id: "authorize",
    disabled: true,
    disabledReason: "Disclosures have not been reviewed",
  });
  assert.match(disabled, /disabled/);
  assert.match(disabled, /aria-disabled="true"/);
  assert.match(disabled, /aria-describedby="authorize-reason"/);
  assert.match(disabled, /id="authorize-reason"/);
  assert.match(disabled, /Disclosures have not been reviewed/);

  const busy = buttonHtml({ label: "Authorize", variant: "consent", busy: true });
  assert.match(busy, /aria-busy="true"/);
  assert.match(busy, /data-state="busy"/);
  assert.match(busy, /disabled/);
  assert.match(busy, /Working/);
  assert.match(busy, /itaa-button--consent/);
  assert.doesNotMatch(busy, /Authorized/);
  assert.doesNotMatch(busy, /data-variant="confidence"/);
  assert.doesNotMatch(busy, /aria-describedby/);
});

test("busy state does not switch a primary button to consent or success styling", () => {
  const busy = buttonHtml({ label: "Save", variant: "primary", busy: true });
  assert.match(busy, /itaa-button--primary/);
  assert.doesNotMatch(busy, /itaa-button--consent/);
});

test("disabledReason requires an id", () => {
  assert.throws(
    () => buttonHtml({ label: "Save", disabled: true, disabledReason: "Locked" }),
    /aria-describedby/,
  );
});

test("enabled button rejects disabledReason without leaking submitted text", () => {
  const submittedReason = 'Locked for <user id="acct-9"> until review';
  assert.throws(
    () =>
      buttonHtml({
        label: "Continue",
        id: "continue-enabled",
        disabledReason: submittedReason,
      }),
    (error: unknown) => {
      assert.ok(error instanceof Error);
      assert.match(error.message, /disabledReason may be supplied only when disabled or busy/);
      assert.doesNotMatch(error.message, /Locked for/);
      assert.doesNotMatch(error.message, /acct-9/);
      assert.doesNotMatch(error.message, /continue-enabled/);
      assert.doesNotMatch(error.message, /<user/);
      assert.doesNotMatch(error.message, /<button/);
      return true;
    },
  );
});

test("valid disabledReason HTML-like content is escaped", () => {
  const html = buttonHtml({
    label: "Authorize",
    id: "authorize-escape",
    disabled: true,
    disabledReason: '<img src=x onerror=alert(1)> & "quote"',
  });
  assert.match(html, /aria-describedby="authorize-escape-reason"/);
  assert.match(html, /&lt;img src=x onerror=alert\(1\)&gt; &amp; &quot;quote&quot;/);
  assert.doesNotMatch(html, /<img /);
});

test("stylesheet covers hover, focus-visible, pressed, disabled, busy, and 44px targets", () => {
  const css = renderStylesheet();
  assert.match(css, /\.itaa-button:focus-visible/);
  assert.match(css, /@media \(hover: hover\)/);
  assert.match(css, /\.itaa-button:active:not\(:disabled\)/);
  assert.match(css, /\.itaa-button:disabled/);
  assert.match(css, /\.itaa-button\[aria-busy="true"\]/);
  assert.match(css, new RegExp(`min-height:\\s*var\\(--itaa-touch-min\\)`));
  assert.match(css, new RegExp(`min-width:\\s*var\\(--itaa-touch-min\\)`));
  assert.equal(touchTargetPx.min, 44);
});

test("button implementation consumes semantic classes instead of locked hex values", () => {
  assert.doesNotMatch(
    source,
    /#221F1A|#6C685F|#E9E6DF|#F6F3EE|#E85D2C|#1A1714|#1BA672|#CB8A1B|#D9483B|#E6E1D8/i,
  );
  assert.doesNotMatch(source, /fetch\(|XMLHttpRequest/);
});
