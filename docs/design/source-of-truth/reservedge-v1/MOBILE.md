# Reservedge — Mobile surface

File: `Reservedge Mobile.dc.html`. Drawn inside a 410 × 874 phone shell (bezel `#1A1714`, outer radius 44px, 10px padding, inner radius 34px). The shell is presentation only — build to the device viewport.

Same spine, same copy, same state machine as the web surface (`WEB.md`). This document covers only what differs.

## Shell

Vertical stack inside the screen:

1. **Status bar** — 9:41 and a battery glyph, mono 11px, padding `11px 22px 4px`.
2. **App bar** — flex row, padding `8px 16px 10px`, bottom hairline `--ws-border`. A 34px `‹` back button (white, radius 11px, hairline border) appears on every screen except the list. Then the title 14.5px/650 with a mono 10px meta line beneath it, and a mono `SIM` chip on the right.
3. **Scroll region** — `flex:1`, padding `14px 16px 22px`. Only this scrolls.
4. **Bottom tab bar** — 4 equal columns, top hairline, `rgba(246,243,238,.94)` + `blur(8px)`, padding `8px 6px 14px`. Each tab: a 16×3px coral indicator bar (opacity 0 or 1) above an 11px/600 label. Tabs: **Intents · Activity · Prefs · Data**. The Intents tab stays lit across list, domain picker, composer and intent detail.

Bottom sheets are absolutely positioned inside the screen (`inset: 0`), scrim `rgba(26,23,20,.45)` + `blur(3px)`, sheet pinned to the bottom, radius `26px 26px 34px 34px`, padding `20px 18px 24px`.

## Navigation model

The web surface shows list and detail side by side. Mobile splits them:

```
Intents (list)  ──tap row──►  Intent detail  ──‹──►  back to list
      │
      └──New intent──►  Domain picker  ──pick──►  Composer  ──confirm──►  Intent detail
```

Bottom tabs switch between Intents, Activity, Prefs and Data at any point. The back arrow always returns to the list, never to the previous stack position — the flow is shallow by design.

## Screens

### Intents (list) — the home screen
Sub-line "{n} waiting on you · {n} paused". Filter pills scroll horizontally in a single row (`overflow-x:auto`, 36px min-height). Rows are grouped by day exactly as on web, but the row lays out vertically: code chip + status pill on line 1, title 14.5px/650, sub-line, then the mono date last. The ✕ delete button is 32px. A full-width coral **New intent** button closes the list.

### Domain picker
The three domain cards stack full width, radius 18px, padding 17px, 11px apart. Same content and tier pills as web; the dimension line is shortened to "· 4 dimensions" / "· 6 dimensions" / "· 5 dimensions". Dashed muted card about future domains closes the screen.

### Composer
Single column. Header is just the mono domain chip and the tier pill — the domain name lives in the app bar.

**Step 1.** White card, coral border: eyebrow `STEP 1 · WHAT DO YOU NEED?`, the line "One line is enough. Reservedge will ask up to three questions after this, then stop.", a 3-row textarea (muted fill, radius 12px, placeholder "Type what you need…"), a full-width "Use the example: …" pill that prefills it, and a coral **Send to Reservedge** button that sits at `opacity .45` until the field has content. The domain's tier note follows in a muted card.

**After sending,** in order down the page: *what you typed* card → question card → ready or blocked card → the requirement card → the two confirm buttons → the cap footnote. The requirement card is **not** sticky on mobile; it sits below the question so the answer and its effect are seen in sequence rather than side by side.

Answer chips become **full-width stacked buttons** (left-aligned text, radius 12px, min-height 46px) instead of a wrapping pill row — options here are sentences, not tags. Skip becomes a compact text button beside the "Or type your own…" field.

### Intent detail
Status card first: chip + pill on one line, step text below, then the action buttons wrapping (**Keep pending · Modify · Cancel**, or **Resume** when paused). Labels are shortened from the web's "Modify intent" / "Cancel intent".

Tabs are a 4-up segmented control filling the width, 11.5px/600, min-height 40px, same white-pill active treatment. The same landing rule applies: open on the furthest tab needing attention.

**Request** — same schema-driven rows as web (see `WEB.md` for the `kind` table), stacked full width with the confidence pill right-aligned and `white-space: nowrap`. The side column becomes a stack below the requirement card: capture-or-tier card, optional schema note, then the amber "editing after dispatch" warning.

**Research** — checklist card, then the public-market card, then the failure card, then a full-width coral **Continue to the offers tab**.

**Offers** — the sub-view pill row scrolls horizontally. The gate stacks: dark intro block → SENT card → WITHHELD card → a 2×2 metadata grid (Purpose / Expires / Recipients / Tier) → full-width **Hold to send this request** and **Not now — keep pending**. Supplier progress cards become horizontal rows (avatar left, name and state right). The recommendation card keeps its full anatomy at reduced type (name 21px, price mono 29px) with stacked full-width actions.

**Added disclosure (re-ask)** — the same screen as web, stacked: dark intro block → `SENT · 1 FIELD` → `STILL WITHHELD · 4 FIELDS` → 2×2 metadata grid → full-width **Hold to send this one field** and **Leave it incomplete** → the declining-costs-nothing footnote. Reached from the "Answer and re-ask" sheet; sending returns to Compare with the green result banner.

**Compare** — the one intentional compromise. The grid keeps its row alignment and scrolls sideways: `120px + 3 × 120px + 110px`, min-width 590px, 12px type, header column labels shortened (`Public` instead of `Public market`, supplier names truncated to one word). The instruction "Swipe the table sideways." is added to the intro line. Do not reflow this into per-offer cards — comparability across a row is the point of the screen.

**Receipt** — as web, at reduced type; reference mono 15px.

**Activity** — rows stack instead of using a 3-column grid: time chip and headline on one line, "Why · …" beneath, shared-fields line last in `--ws-ink-3`.

### Global Activity, Prefs, Data, Plan
Single column versions of the web views. In global Activity each row leads with a small time + domain-code pair, then the headline, reason, and shared line. Preference cards stack. The Data screen puts the four data categories in one white card and the three destructive actions below as full-width left-aligned buttons.

## Bottom sheets

The four web dialogs become bottom sheets with identical copy and button order:

1. **Authorize** — scrollable to 90% height; simulation banner, transaction rows, the authorizes / does-not-authorize block, coral **Hold to authorize {amount}**, then **Not now**.
2. **Answer and re-ask**.
3. **Modify this intent?** — four stacked actions.
4. **Delete this intent?** — two side-by-side actions (danger left, keep right).

## Mobile-specific rules

- Every interactive element is at least 44px tall; the delete ✕ is 32px square but sits inside a 46px row.
- Only one thing scrolls at a time: the content region. The app bar and tab bar are fixed within the screen.
- Horizontal scrolling exists in exactly two places — the filter row and the compare grid — and both are visually cut off at the edge so it reads as scrollable.
- No hover states. Every affordance is visible at rest.
- The status bar and phone bezel are prototype scaffolding, not part of the design.
