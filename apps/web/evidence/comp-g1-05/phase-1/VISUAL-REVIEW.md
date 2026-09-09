# COMP-G1-05 Phase 1 visual review

Read-only review of the Reservedge **shell + inbox**. Phases 2–4 are gated until Product Owner accepts this pass.

Side-by-side: open `compare.html` in this folder.

## Measured comparison (implementation)

| Item | Spec | 1440×940 | 1280×800 | 410×874 | 390×844 | 320 CSS |
| --- | --- | --- | --- | --- | --- | --- |
| Outer / body | `#E9E6DF` | `rgb(233,230,223)` | same | same | same | same |
| App canvas | `#F6F3EE` | `rgb(246,243,238)` | same | same | same | same |
| Rail width | 236px | 236 | 236 | hidden | hidden | hidden |
| List width | 320px | 320 | 320 | 378 (fluid) | 358 (fluid) | 288 (fluid) |
| Detail width | remainder | 884 | 724 | hidden on inbox | hidden | hidden |
| Type | Schibsted Grotesk | yes | yes | yes | yes | yes |
| Primary button | `#E85D2C` | `rgb(232,93,44)` | same | same | same | same |
| Card radius | 14 web / 16 mobile | 14px | 14px | 16px | 16px | 16px |
| Nav | desktop rail / mobile tabs | rail | rail | bottom tabs | bottom tabs | bottom tabs |
| Document overflow-x | 0 except allowed filter row | 0 | 0 | 0 | 0 | 0 |

Document-level `overflow-x` is 0. The mobile filter row is allowed to scroll horizontally; History can sit off-screen at 320px.

## Shell / inbox findings

### High

1. **Desktop detail is not the HTML inbox landing.** Rail, list, header, status bar, and workspace tabs match. The HTML default is Offers → Recommendation (JetPark card + “Why this one”). Implementation leaves the Offers pane empty. Ranking content is Phase 4 and must use the locked JFK vector (SkyShield 671,000), not the prototype’s JetPark $71.40. **Inbox screenshot parity is therefore not PASS.**
2. **`/intents/new` still mounts the previous ITAA composer** (`NewIntentScreen`). Do not use New intent for this UAT pass. Composer is Phase 2.

### Medium

1. Desktop filter pills wrap (`History` on a second line) because the 320px list is narrower than five pills in one row. HTML does the same.
2. Keyboard focus: `impl-1440x940-focus.png` was captured after focusing **New intent**. Confirm a visible `:focus-visible` ring in the browser; the headless PNG may not show `:focus-visible` the same way as a real Tab press.
3. Old `IntentWorkspace` (A1–A4 copy, “Return to Intent Inbox”, “ITAA”) still mounts for `pi_*` API intents. Seed ids (`jfk`, …) use the new landing. Do not drive a live `pi_*` intent during this visual pass.

### Low

1. Mobile list shows a selected orange border on the first card. HTML keeps `sel` on list view too.
2. Full-width **New intent** on mobile sits below the fold when five cards are visible, matching HTML.

## Prohibited customer copy (Phase 1 inbox surfaces)

Scanned `AppShell`, `InboxScreen`, `reservedge/*`, `index.html` for Gate 1, A1–A4, WP, process-memory, giant simulation banner, eight-step pills. **Absent** on the inbox route.

Still present in **ungated** `IntentWorkspace` / `NewIntentScreen` (previous cut). Hidden on the seed inbox.

## Keyboard / reduced motion

- `impl-1440x940-focus.png`
- `impl-1440x940-reduced-motion.png` (`prefers-reduced-motion: reduce`; app animations disabled in CSS)

## Verdict

**Shell + inbox chrome: close to the HTML rail/list/mobile app bar.**  
**Visual acceptance of the full web inbox screenshot: not PASS** until the Offers landing is implemented without changing ranking economics (Phase 4) and New intent is the Reservedge domain picker (Phase 2).

Product Owner: review `compare.html` at 1440×940 and 410×874 first. Do not authorize Phase 2 until High 1 is accepted as deferred or the Offers landing is in.
