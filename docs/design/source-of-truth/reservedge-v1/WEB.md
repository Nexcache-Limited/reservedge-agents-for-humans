# Reservedge — Web surface

File: `Reservedge Web.dc.html`. Design canvas 1440 × 940, minimum usable width ~1180.

## Shell

Three columns, full viewport height, no page scroll — each column scrolls independently.

| Column | Width | Background |
|---|---|---|
| Nav rail | 236px fixed | `--ws-rail` `#1A1714` |
| Intent list | 320px fixed | `--ws-surface` white, right hairline `--ws-border` |
| Detail | fills | `--ws-canvas` `#F6F3EE`, content capped at 940px and centred, padding `24px 24px 60px` |

**Nav rail.** App mark: 28px rounded square (radius 9px), coral gradient, white "I", 800 weight 13px; wordmark "Reservedge" 15px/700 in `#F6F3EE`; mono `SIM` chip right-aligned, 9px, `.12em` tracking, 1px `rgba(255,255,255,.14)` border. Below it five nav buttons (Intents, Activity, Preferences, Your data, Plan) — 13px/500, `#EDE9E1`, radius 11px, hover `rgba(255,255,255,.06)`, active marked by a 3×15px coral bar at the left. A "DOMAINS LIVE" panel pinned to the bottom (`rgba(255,255,255,.05)`, radius 14px) lists the live domains with their mono codes.

**Detail header.** 60px tall, `rgba(246,243,238,.86)` + `backdrop-filter: blur(8px)`, bottom hairline. Left: intent title 14px/650 with ellipsis, then mono timestamp 10.5px in `--ws-ink-3`. Right: "Simulation mode" label and a coral 34×20px toggle, permanently on.

## Intent list

Header row: "Intents" 15px/700 and a coral "+ New" button (radius 10px, 12.5px/600). Sub-line: "{n} waiting on you · {n} paused", 12px `--ws-ink-2`.

Filter pills: All · Needs you · Running · Pending · History. Radius 999px, 12px/600, min-height 34px. Selected = `--ws-ink` fill, white text. Unselected = `--ws-muted` fill, `--ws-ink-2`.

Rows are grouped under mono day headings: `TODAY · 29 AUG`, `YESTERDAY · 28 AUG`, `EARLIER`. Empty groups are not rendered.

**Intent row.** White card, radius 14px, padding `12px 13px`, 8px gap. Selected row: background `--ws-canvas`, 1px `--ws-accent` border. Contents: mono domain code chip · status pill · mono date, then title 14px/650, then sub-line 12px `--ws-ink-2`. A 28px ✕ button (radius 9px, hairline border) deletes; hover turns it `--danger`. Completed intents have no delete.

**Status pills** (11px/600, radius 999px):

| Status | Label | Fill / text |
|---|---|---|
| decision | Decision ready | `--ws-accent-soft` / `--ws-accent-d` |
| needs | Needs a detail | `--amber-soft` / `--amber` |
| running | Researching | `--info-soft` / `--info` |
| pending | Pending · paused by you | `--ws-muted` / `--ws-ink-2` |
| draft | Draft | `--ws-muted` / `--ws-ink-2` |
| done | Authorized · simulated | `--green-soft` / `--green` |
| cancelled | Cancelled by you | `--ws-muted` / `--ws-ink-3` |

Empty state: "Nothing here." / "No intents match this filter." / coral **New intent** button.

## Domain picker (`New intent`)

H2 "What do you need?" 24px/700. Sub: "Pick the kind of thing you're buying. Each one tells you up front what suppliers will need before they can price it."

Three cards in `repeat(auto-fit, minmax(260px, 1fr))`, 14px gap, white, radius 18px, padding 20px, hover border coral. Each: mono code chip, name 17px/700, a tier pill, an explanatory paragraph, and a "Needs: … · compared on N dimensions" line in `--ws-ink-3`.

- Parking tier pill — green soft, "Anonymous until you book".
- Rental tier pill — amber soft, "Needs licence class and driver age".
- Entertainment tier pill — green soft, "Anonymous · party size only".

Below, a dashed-border muted card: "Entertainment booking and spa are next. Adding a domain means declaring three things — its requirement fields, its disclosure tier, and up to six offer dimensions. No new screens."

## Composer (bounded conversation)

Two columns, `1.15fr 1fr`, 14px gap. Left = the exchange; right = a sticky requirement card that fills in live.

Header row: mono domain chip, domain name 22px/700, tier pill.

**Step 1 — what the user needs.** Before any question: a white card with a coral 1px border, eyebrow `STEP 1 · WHAT DO YOU NEED?` in `--ws-accent-d`, the line "One line is enough. Reservedge will ask up to three questions after this, then stop.", a 3-row textarea (muted fill, radius 12px, 13.5px/1.55, placeholder "Type what you need…"), an "Use the example: …" pill that prefills it, and a coral **Send to Reservedge** button (disabled look at `opacity .45` while empty). The domain's tier note sits underneath.

**After sending:**

- *What you typed* — white card, mono eyebrow `WHAT YOU TYPED`, the user's line at 13.5px.
- *Question card* — white, coral border, radius 18px. Eyebrow `QUESTION n OF 3` in `--ws-accent-d`; right-aligned 11.5px why-line ("changes shuttle pricing", "ranks the offers", "required — no offer without it"). Question 16px/650. Answer chips: muted fill, hairline border, radius 999px, min-height 40px, hover coral. A greyed "Or type your own answer…" field and a **Skip this** text button — skip is absent on required questions, which instead show the blue note "Required — suppliers in this domain cannot price without it."
- *Ready state* — green soft card: "That's enough to work with." plus the assumption/approval note.
- *Blocked state* — info soft card: "1 required answer left: {question}" and a dark **Answer it** button that jumps back to that question.
- *Actions* — coral **Confirm requirement and research**, white **Use what you have**. Both dim to `opacity .5` while a required answer is missing and route to the missing question instead of proceeding. Footnote: "Question n of 3. Questions are capped — Reservedge asks for permission before a fourth."

**Requirement card (right, sticky).** Mono header `REQUIREMENT · BUILDING` with an `n/total` counter. One row per field: mono label, value 13.5px/600, note 11.5px. Unanswered value reads "Not answered yet" in `--ws-ink-3`; skipped reads "Assumed — you skipped this" in `--amber` with the note "Correctable at any time in the Request tab". The tier note closes the card.

## Intent detail

**Status bar** — white card, radius 16px: mono domain chip, status pill, step text, and right-aligned actions. Live intents get **Keep pending**, **Modify intent**, **Cancel intent** (danger border). Paused intents also get a dark **Resume**. History shows "Kept in history · read-only".

**Tabs** — segmented control in a `--ws-muted` track, radius 12px, 4px padding. Active tab = white pill, radius 9px, shadow `0 1px 3px rgba(40,30,15,.14)`. Tabs: Request · Research · Offers · Activity.

**Landing rule:** opening an intent lands on the furthest tab needing attention — offers for `offers`/`gate`/`done`, research for `research`, request otherwise. Never default to Request.

### Request tab
**Schema-driven — there is one implementation for every domain.** Two columns `1.5fr 1fr`. Left: the confirmed requirement rendered by looping the domain's row schema — mono label, value 15px/600, provenance note, and a confidence pill. Each row declares a `kind`, which supplies the pill and colours:

| kind | pill | pill fill / text | note colour | row fill |
|---|---|---|---|---|
| `ok` | High | `--green-soft` / `--green` | `--ws-ink-2` | transparent |
| `req` | Required | `--info-soft` / `--info` | `--ws-ink-2` | transparent |
| `warn` | Check | `--amber-soft` / `--amber` | `--amber` | `#FEFBF4` |

A row with `fix: true` also renders **Correct** / **It's right** buttons (the assumed parking vehicle). A row with `tags` renders muted 8px-radius tags instead of a value and no pill (must-haves). The last row drops its bottom border.

Right column is also schema-driven: an eyebrow, an optional tier pill, a body paragraph, an optional disclosure button, and an optional schema note — parking supplies "HOW THIS WAS CAPTURED" plus `⌄ Show the 3 questions`; rental and entertainment supply "DISCLOSURE TIER · STATED UP FRONT" with their tier pill. Every domain then gets the same amber warning: "**Editing after dispatch has a consequence.** Change a field now and the offers you have received stop applying — suppliers would need a fresh, re-approved request."

### Research tab
Two columns. Left: an autonomous checklist — two green ✓ rows, one pulsing blue `•` row ("Normalising taxes and fees"), one grey `–` row ("Cancellation terms"), then the note that no supplier is involved. Right: public-market card (range in mono 26px, a 6px coral progress track at 46%), a red soft failure card ("One source didn't respond" + which sources were skipped), and a coral **Continue to the offers tab** button.

### Offers tab
A pill row switches between **Disclosure record · Recommendation · Compare offers**. When the intent is still at the gate, the pill row is replaced by the gate itself.

**Disclosure gate (approval 1 of 2).** Dark `--ws-rail` block, radius 20px: eyebrow `APPROVAL 1 OF 2 · DISCLOSURE` in `#8A8479`, H3 "What suppliers will see" in white, intro in `#B9B3A8` capped at 62ch. Below, two white cards side by side: `SENT · n FIELDS` (green eyebrow, each row ✓ + bold label + reason) and `WITHHELD · n FIELDS` (grey eyebrow, ✕ + label). A muted metadata strip states Purpose · Recipients ("3 suppliers, isolated from each other") · Expires ("In 30 minutes") · Tier. Actions: coral **Hold to send this request**, white **Not now — keep pending**.

**Disclosure record.** Same two cards after the fact, headed "What was sent, and what was not" with the approval timestamp and the line "A record, not an action. This approval has already been used; asking these suppliers anything further needs a new one."

**Added disclosure — the re-ask approval.** Reached from the incomplete-offer card via the "Answer and re-ask" dialog. Dark `--ws-rail` block, radius 20px: eyebrow `ADDED DISCLOSURE · 1 FIELD`, H3 "One more field, one more approval", and the body "The approval you already gave has been used. Adding a field to the request is a new disclosure, so it is asked separately — and it goes to one supplier, not all three." Below, the same two-card sent/withheld pattern as the main gate, at one field and four: `SENT · 1 FIELD` (payment method type — credit card, "Required to quote a deposit hold. The card number itself is not included.") and `STILL WITHHELD · 4 FIELDS` (card number/expiry/CVC, name, licence number, that two other suppliers also offered). Metadata strip in a 2×2 grid: Purpose "Complete CityDrive's offer" · Recipient "CityDrive only — not the other two suppliers" · Expires "In 15 minutes" · Tier "Unchanged · tier 2". Actions: coral **Hold to send this one field**, white **Leave it incomplete**, and the footnote "Declining costs nothing. CityDrive's offer simply stays marked incomplete and unrecommendable."

Sending it returns to Compare with a green banner: "**The added field was sent to CityDrive only.** CityDrive answered: $400 deposit hold, credit only. Its offer is now complete, and still not recommended — the hold is $200 higher than Northgate's and mileage is capped at 250 mi / day." The compare grid updates that one cell and its evidence count; the incomplete card disappears; the audit trail gains "You approved a single added field · 1 sent, 1 recipient".

**Supplier progress.** Three cards: 38px gradient avatar with the supplier's two-letter code, name 15px/650, state ("Offer received · 12s", "Offer received · incomplete").

**Recommendation.** `1.5fr 1fr`. Main card white, radius 20px, raised shadow: "Recommended" pill + mono "valid 26m"; supplier name 23px/700; one-sentence why; price mono 32px/600 with "total, taxes and fees included"; breakdown line; a 2×2 dimension grid; then three reason lines — green `+` benefit, amber `–` trade-off, grey `?` unverified gap. Actions: coral **Take this one**, white **Compare all three**. Side column: "WHY THIS ONE" card with three headline + body reasons and a switch-condition line ("If covered parking became a must-have, Avia wins…"), plus the disclaimer "Reservedge's opinion on the offers received, not a rating or a financial score."

**Compare.** Grid `190px + 3 × minmax(150px,1fr) + 150px`, min-width 840px, horizontal scroll. Header row on `--ws-muted`; recommended column headed in `--ws-accent-d` with "· recommended". One row per dimension; cell colour carries meaning (green good, amber caution, danger bad, `--ws-ink-3` not stated). The last column is always the public market. Below the grid, when an offer is incomplete: an amber card naming the supplier, explaining the gap, and offering **Answer and re-ask**. Footnote defines "Evidence checked".

**Receipt.** Green ✓ disc, "Authorization recorded" / "Simulated. No card charged, nothing reserved." White card with a rotated `SIMULATED` stamp in the corner, mono reference, and a 2×2 grid: Supplier · Amount · Authorized · Newly shared. Then **View this intent's activity**.

### Activity tab
Per-intent audit rows in a white card: `64px | 1fr | 200px` grid — mono time, then what happened (13.5px/600) with a "Why · …" line, then what was shared ("5 sent, 6 withheld", "Nothing shared", "Received only").

## Global views

- **Activity** — the same rows across all intents, with a mono domain code column inserted (`64px | 44px | 1fr | 190px`).
- **Preferences** — 2-column card grid. Each card: mono scope eyebrow (`GLOBAL` / `PARKING` / `RENTAL CAR`), the belief 15px/650, a confidence pill (Confident / Unsure / You set this), an "Evidence · …" line, and Keep / Change / Delete actions. A dashed card states preferences are never sent to suppliers.
- **Your data** — `1.4fr 1fr`. Left: Identity · Attributes · Preference history · Disclosure log, each with a one-line description. Right: Export everything, Delete preference history, Delete my account (both destructive actions on a `rgba(217,72,59,.35)` border).
- **Plan** — amber quota banner, two price cards (yearly card gets a 2px coral border and a "Save 37%" pill), subscribe / restore / stay-free actions, and a red soft renewal-failure notice.

## Dialogs

Centred modals over `rgba(26,23,20,.4)` + `blur(3px)`, white, radius 22px, shadow `0 40px 90px -24px rgba(40,30,15,.5)`.

1. **Authorize (approval 2 of 2)** — max 520px. Dark simulation banner, eyebrow `APPROVAL 2 OF 2 · TRANSACTION`, Supplier / What / Amount rows, then a muted block: "This authorizes: …" and "It does not authorize: recurring bookings, price changes, or contact with the other suppliers." Coral **Hold to authorize {amount}**, then **Not now**.
2. **Answer and re-ask** — max 470px. Explains that answering adds a field, so it counts as a new disclosure needing approval. Lists "Would send" and "Still withheld". **Review the new disclosure** opens the added-disclosure screen above (`ov: 'reask'`); **Leave it incomplete** dismisses.
3. **Modify intent** — max 460px. Steers to editing the requirement first. Actions: **Edit the requirement instead** (dark) / **Discard this one and start fresh** (coral) / **Keep it pending and start a new one** / **Never mind**.
4. **Delete intent** — max 430px. Names the intent, states offers simply expire, and notes the audit trail keeps a single "intent deleted" entry. **Delete intent** (danger) / **Keep it**.

## State model

```
view      'list' is mobile-only; web uses 'intent' | 'domains' | 'composer'
          | 'activity' | 'prefs' | 'privacy' | 'paywall'
sel       selected intent id
tab       'request' | 'research' | 'offers' | 'activity'
ov        offers sub-view: 'gate' | 'record' | 'progress' | 'reco' | 'compare' | 'reask'
filter    'all' | 'needs' | 'running' | 'pending' | 'history'
dlg       null | 'auth' | 'reask' | 'modify' | 'cancel'
intents[] { id, domain, title, sub, status, stage, step, day, date }
reasked   boolean — the single added field was approved and sent
composer  { domain, ans:{}, i, typed, draft } | null
```

Transitions worth naming:

- `select(id)` → view `intent`, tab = landing rule above, `ov` = `gate` if the intent is paused at the gate, else `reco`.
- Composer send → `composer.typed` set, questions begin.
- Chip answer → writes `ans[qid]`, advances `i`. Skip writes the string `'skipped'`.
- Confirm with a required field missing → does **not** proceed; jumps to that question.
- Confirm clean → creates a new intent (status `running`, stage `research`), selects it, opens the Research tab.
- Dispatch → stage `offers`, status `decision`, `ov` = `progress`.
- Confirm authorize → status `done`, stage `done`, sub becomes "{amount} · ref {reference}".
- Delete → removes the intent, selects the next one, returns to the list.
- Keep pending → status `pending`, stage unchanged, so Resume can restore it.
- Send added field → `reasked = true`, back to Compare. Derived from it: the deposit-hold cell, the evidence count, the loss of the incomplete card, the green result banner, and one extra audit row.
