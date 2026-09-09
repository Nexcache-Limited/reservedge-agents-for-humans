# Reservedge intent-first — mobile specification

File: `Reservedge Intent-First Mobile.dc.html`
Frame: 410 × 874, matching the existing Reservedge mobile handoff.

## Structure

```
status bar
header ......... back or mark · title · mono meta · SIM badge
task bar ....... screens 5–9 only, parking / rental
scroll body
action bar ..... screens with an approval, fixed
tab bar ........ Intent · Bookings · Activity
```

Home is **New intent**, not the bookings list. The Reservedge mark shows there
instead of a back arrow; every other screen shows back.

## The three decisions that differ from web

**1. The side-by-side becomes two tabs.**
The booking workspace has a segmented control: *Plan · 4 tasks* and
*Conversation*. Plan is the default. A decision waiting on the user is never
buried in a transcript. The agent's "↳ Plan updated · 4 tasks" line in the
conversation jumps to the plan rather than restating it.

**2. Approvals use a fixed bottom action bar.**
Primary plus at most one secondary, with the consequence line beneath. The
approve button never scrolls out of reach, and the user reaches it having
scrolled the fields it commits to.

| Screen | Primary | Secondary | Note |
|---|---|---|---|
| New intent | Start booking | — | Nothing is sent to any supplier from this step. |
| Clarify | Answer and update plan | — | Skipping is fine — unanswered fields become missing details. |
| Disclosure | Approve and send | Send without <field> | Declining costs nothing and leaves the task open. |
| Selection review | Continue to authorization | Choose a different offer | Nothing is reserved and nothing is charged yet. |
| Authorization | Authorize <amount> · simulated | Not yet | Binds this exact supplier, amount, terms and version. |

Offers and receipt have no action bar; their actions belong to individual cards.

**3. Offer cards restack.**
The web card's two columns become one. Supplier and price share the top line,
badges wrap on the second, then summary, reasons, downside, and a footer row
pairing validity with the completeness chip. Select and review is full width.

## Screens

1. **New intent** — heading, composer field, three example rows, direct-domain chips.
2. **Bookings** — filters, then Needs you / In progress / History.
3. **Clarify** — two chat turns, then the three-question card. Yes/No/Not sure as three equal 44px buttons.
4. **Booking workspace** — Plan / Conversation tabs. Plan carries the same four task states as web; the isolation panel restacks to label-over-text.
5. **Disclosure** — sent card, withheld card, metadata as a two-column grid, re-ask card on rental, amber invalidation notice.
6. **Offers** — stacked cards, non-responder row, ordering panel.
7. **Selection review** — offer card with breakdown and terms stacked, then what changes if you continue.
8. **Authorization** — dark separation callout, rows as label-over-value, authorizes/does-not pair, first-time-shared chips.
9. **Receipt** — check and reference, four-cell grid, hold note, audit trail with the reason indented under each entry, what's left.

## Touch and type

- Every interactive element is at least 44px tall. Tab bar items are 46px.
- Smallest type is 11px, used only for mono metadata and footnotes.
- Body copy 12.5–13.5px, headings 18–23px.
- Long mono values use `word-break: break-word`; ISO datetimes wrap rather than
  overflow.

## Navigation

Back targets: Bookings → New intent; Clarify → New intent; Workspace →
Bookings; Disclosure and Offers → Workspace; Review → Offers; Authorize →
Review; Receipt → Workspace.

The step chips below the device are a review aid for this prototype only. They
are not product navigation.

## Reduced motion

The spinner, fade-up and pop are disabled under `prefers-reduced-motion`,
falling back to the end state.
