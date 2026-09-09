# Reservedge intent-first — web specification

File: `Reservedge Intent-First.dc.html`

## Shell

Three fixed columns plus content.

| Region | Width | Notes |
|---|---|---|
| Rail | 224px | Dark `--ws-rail`. Screen navigation for review; in production this is the product nav |
| Bookings list | 262px | White, always present. Filters, then grouped bookings |
| Content | fill | 58px sticky command bar, optional task bar, routed body |

The command bar carries the screen title, a mono metadata line, and the
simulation toggle. The task bar appears only on task-scoped screens (4–8) and
switches between airport parking and rental car.

Content bodies are width-capped: 660px composer, 600–640px plan column,
800px disclosure and review, 940px offers.

## Bookings list

Groups, in order: **Needs you**, **In progress**, **History**. Each row shows a
mono booking code, a status pill, the title, and a one-line substatus. History
retains authorized bookings with their reference and cancelled bookings with the
disclosure-revoked note — cancellation does not delete the record.

Status pill colours: decision ready `--ws-accent-soft` / `--ws-accent-d`;
researching `--info-soft` / #1F4FB0; paused `--ws-muted` / `--ws-ink-2`;
authorized `--green-soft` / `--green`; cancelled `--ws-muted` / `--ws-ink-3`.

## Screens

### 1 · New intent
Eyebrow, question as a 29px heading, one contenteditable field, and the line
"Nothing is sent to any supplier from this step." Three example chips below.
A secondary block offers the three known domains as a direct start; each creates
a one-task booking.

No domain is chosen at this point and no schema is bound.

### 2 · Clarify & plan
Conversation column 396px, plan column fills.

The clarification card is a single card carrying all three blocking questions —
never three separate turns. Each field states which tasks it unblocks. The card
is marked "CLARIFICATION · 3 OF 3" with a blocking pill, and ends with
"Skipping is fine. Unanswered fields become missing details on the affected tasks."

The plan shows shared context as chips, each with a provenance tag: YOU SAID
(accent), INFERRED (info), CONFIRMED (green). Below, four task cards — two
confirmed with a solid border, two proposed with a dashed border.

### 3 · Booking workspace
Same two-column split. This is the resume state: the conversation carries a date
divider and picks up two days later.

Four task cards demonstrate four states:

| Task | State | Treatment |
|---|---|---|
| Airport parking | 3 offers ready | Accent border, coral glow, primary action |
| Rental car | Researching | Spinner pill, 62% progress bar, source count, dependency line |
| Hotel | 2 details missing | Amber chips naming each missing field |
| Flight | Proposed | Dashed border, Add to plan / Not needed |

Agent messages that changed the plan carry a "↳ Plan updated · 4 tasks" marker.
Decisions are never made in the transcript.

A "What each supplier can see" panel closes the column, one row per domain,
with the note that no supplier receives the booking, the other tasks, or a
stable identifier.

### 4 · Task disclosure (A2)
Two-column sent/withheld. Sent fields carry name, mono value and a purpose line.
Withheld fields are listed with a note that the rest of the itinerary is part of
the booking but not part of this payload.

A metadata strip states recipients, payload version and hash, approval expiry,
and purpose. An amber notice states that changing a field after dispatch
invalidates this approval and its offers, and that other tasks are unaffected.

Actions: **Approve and send** (primary), a partial-approval button naming the
field it omits, and a text Decline with "Declining costs nothing and leaves the
task open."

Rental adds an answer-and-re-ask card: one field, one supplier, expiry stated,
tier unchanged, declining keeps the other quotes intact.

### 5 · Offers & validity (A3)
Card per offer: left side identity and reasoning, right side a 208px rail with
price, fit, validity and actions.

Each card states source type, curated class where it applies, offer id, summary,
one or more `+` reasons, exactly one `–` downside, and three mono chips —
completeness, provenance, version.

The rail shows total, price note, fit pill, absolute validity over relative
validity, Select and review, and Refresh quote. Validity turns amber when close.

Below the cards: the non-responder row, then a "How these were ordered" panel
that names the dimensions used and states which preference influenced the order
and that it was not disclosed.

### 6 · Selection review (A3)
The offer the user actually clicked. Price breakdown and terms as quoted side by
side, validity and provenance, then "What changes if you continue" — a short
list of exactly which fields reach which supplier, with the reminder that other
suppliers are told nothing and other tasks are unchanged.

### 7 · Authorization (A4)
Opens with a dark callout separating this from the disclosure approved earlier.
Rows: supplier, what, amount, offer version and terms hash, valid until. Then the
"This authorizes / It does not authorize" pair, then the fields shared for the
first time as accent chips.

Primary button names the amount. Secondary is "Not yet". A footnote states that
press-and-hold is available in preferences and either path records the same
authorization.

### 8 · Receipt & activity
Green check, reference, supplier, amount, authorized time, newly shared, and a
plain-language hold note. Below, the task's audit trail — time, what, why,
what was shared — then "What's left in this booking" with a link into the other
task.

## Two domains, one implementation

The task bar switches `state.task`. Screens 4–8 read one task object. Nothing
branches on domain.

| | Airport parking | Rental car |
|---|---|---|
| Tier | 1 — anonymous until you book | 2 — age band and licence class required |
| Fields sent | 5 | 6, two hard-required |
| Fields withheld | 7 | 8, including that parking was also booked |
| Re-ask | none | payment method type, one supplier |
| Currency | GBP | USD |
| Offer dimensions | cost, transfer, cancellation, completeness | cost, deposit, mileage, fuel, cancellation, completeness |

## Rules a developer must not lose

- Authorization and receipt copy derives from the **selected** offer, never the
  recommended one. Supplier name, amount, hold note, "this authorizes" sentence
  and the first two audit rows are all interpolated.
- Currency strings contain `$`. Interpolate with a function replacement, not a
  string one, or `$2` in "\$214.60" is read as a capture group.
- Every offer must carry validFrom / validUntil from the authoritative offer.
  Never reconstruct them from a supplier catalog.
- No numeric score reaches the customer.

## Tweakable props

`bookingTitle` (text) and `showIsolationNotes` (boolean, default true).
