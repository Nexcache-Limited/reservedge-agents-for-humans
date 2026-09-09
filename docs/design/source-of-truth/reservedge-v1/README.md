# Handoff: Reservedge

## Overview

Reservedge is a privacy-first personal procurement agent. The user states an intent ("I need parking at JFK for my flight on the 4th"), Reservedge turns it into a structured requirement, researches the public market on its own, asks the user's permission before disclosing anything to suppliers, collects private offers, recommends one with its reasoning, and takes a second, separate authorization before transacting. Nothing about the user reaches a supplier without an explicit, itemised approval.

Two surfaces are covered by this handoff:

- **Web** — a desktop operator console (`Reservedge Web.dc.html`), three-column: nav rail, intent list, intent detail.
- **Mobile** — the same product as a phone app (`Reservedge Mobile.dc.html`), single column with a bottom tab bar.

Both run on **one domain-agnostic spine**. Three domains are proven in the prototypes — **airport parking**, **rental car** and **entertainment booking** — and they share every screen. Only three things vary per domain:

1. **Requirement schema** — which fields exist, which are hard-required.
2. **Disclosure tier** — what a supplier must know before it can price at all.
3. **Offer dimensions** — up to six axes the offers are compared on.

Entertainment booking was added to the finished prototypes as a proof of that claim: it declared a schema, a tier and five dimensions, and reused every existing screen — the requirement view is rendered from the schema, not written per domain. Adding a further domain (spa) must work the same way. Treat that as an architectural constraint, not a nice-to-have.

## About the design files

The files in this bundle are **design references created in HTML** — prototypes showing intended look and behaviour. They are **not production code to copy**. The task is to recreate these designs in the target codebase's existing environment (React, Vue, SwiftUI, Compose, native, whatever is in place) using its established patterns, component library, routing and state conventions. If no environment exists yet, choose the framework that fits the product and implement the designs there.

The prototypes are single-file components with an inline logic class and inline styles. That structure is an artefact of the prototyping tool. Do not mirror it. Do mirror the **information architecture, the state machine, the copy, and the visual specification**.

## Fidelity

**High-fidelity.** Colours, typography, spacing, radii, shadows and copy are final and exact. Recreate the UI faithfully using the codebase's own primitives. Every value used is listed under *Design tokens* below.

All product copy in the prototypes is final and reviewed. Ship it verbatim — the wording carries the privacy guarantees and is the main trust surface of the product. Do not paraphrase, shorten, or "make it friendlier".

## The universal flow

Every intent, in every domain, moves through the same seven steps:

1. **Intent** — the user types one line.
2. **Requirement** — the agent asks up to three targeted questions, each filling one field. Capped; a fourth needs permission.
3. **Disclosure** — an itemised preview of what will be sent and what is withheld. Requires approval. *(Approval 1 of 2.)*
4. **Offers** — suppliers answer in isolation. None of them can see each other or the user.
5. **Decision** — one recommendation with stated reasons, plus a full comparison grid against the public market.
6. **Authorization** — a separate approval for the money. *(Approval 2 of 2.)*
7. **Receipt** — a simulated record, and an audit entry naming exactly what was newly shared.

The two approvals are deliberately separate decisions and must never be merged into one confirm.

## Product rules that must survive implementation

- **Nothing is sent without approval.** The disclosure screen lists every field sent, each with a reason, and every field withheld. Counts are shown ("5 sent, 6 withheld").
- **Disclosure tier is stated before the user starts**, on the domain picker — not discovered mid-flow.
- **Questions are bounded.** Maximum three per requirement, ranked by impact on the outcome. Skipping is allowed and recorded as an assumption, correctable forever.
- **The requirement stays editable for the intent's whole life**, with a stated consequence: editing after dispatch invalidates the offers received.
- **Preferences rank offers; they are never sent.** No supplier can learn the user is price-sensitive.
- **An unanswered offer dimension is marked incomplete, never guessed.** An offer missing a must-have answer cannot be recommended. Getting that answer is a *new disclosure* with its own approval screen — one field, one named recipient, a 15-minute expiry, and a stated cost of declining. The already-given approval is never silently reused.
- **A re-ask can change the answer without changing the recommendation.** In the prototype CityDrive answers with a $400 hold; its offer becomes complete and is still not recommended. The system says so plainly rather than hiding the outcome.
- **Deleting an intent leaves one tombstone** in the audit trail ("Intent deleted") and nothing else. Completed intents stay in history.
- **Everything is simulated** in these builds: no card is charged, nothing is reserved. The SIM chip, the "SIMULATED" receipt stamp and the simulation banner in the authorize sheet all say so.

## Domain definitions used in the prototypes

### Airport parking (`Pk`)
- **Tier 1 — anonymous until you book.** Suppliers price with no attribute about the user. Name and plate go only at authorization.
- **Requirement fields (4):** airport/terminal, parking window, vehicle class (assumed from saved vehicle), must-haves.
- **Questions (3):** which airport and terminal · when do you need the space · what matters most this trip.
- **Offer dimensions (4):** total all-in, cancellation, shuttle, distance, cover, EV charging, evidence checked, validity.
- **Disclosure:** 5 fields sent, 6 withheld.

### Entertainment booking (`En`)
- **Tier 1 — anonymous, party size only.** A venue holds seats without knowing anything about the user. The name reaches the venue only on the issued ticket.
- **Requirement fields (5):** category, evening, party size *(required)*, price ceiling (taken from the typed line, sent as a band), must-haves.
- **Questions (3):** what kind of night · which evening · how many seats and together *(required)*.
- **Offer dimensions (5):** total all-in, seats together, exchange, seat zone, delivery, evidence checked, validity.
- **Disclosure:** 5 fields sent, 6 withheld.
- **Added last, changed nothing.** No new screen, no new component, no branch in the flow — the requirement view reads its rows from the domain's schema.

### Rental car (`Rc`)
- **Tier 2 — needs licence class and driver age.** Suppliers cannot legally quote without them. Identity is still withheld until authorization.
- **Requirement fields (6):** pickup location, pickup/return times (derived from the flight, not typed), vehicle class, driver age band *(required)*, licence class *(required)*, must-haves.
- **Questions (3):** pickup and return times · what size car · driver age band and licence class *(required — blocks confirmation)*.
- **Offer dimensions (6):** total all-in, cancellation, vehicle class, mileage, pickup, deposit hold, evidence checked, validity.
- **Disclosure:** 6 fields sent, 6 withheld.
- **Carries the incomplete-offer case:** CityDrive cannot state a deposit hold without knowing card vs debit, so its offer is marked incomplete and excluded from recommendation.

## Identity

The name is **Reservedge** — one word, one capital. Never *ReservEdge*, never *Reserve Edge*.

The mark is a bracket holding one dot: the bracket is the approval gate, the dot is the offer waiting on the far side of it. Full spec, geometry, size ladder and rules are in `LOGO.md`, with the visual reference in `Reservedge Logo.dc.html` and the SVGs in `assets/`. In short:

- Wordmark: Schibsted Grotesk 700, tracking `-0.03em`. It appears in exactly one place inside the product — the app rail (web) and the list-screen app bar (mobile). Everywhere else the mark stands alone.
- Icon: rounded square on the coral gradient, radius 22px at 80px / 14px at 48 / 10px at 32 / 7px at 20. Stroke weight rises as it shrinks: 1.8 at 48+, 2.0 at 32, 2.4 at 20. Below 32px the gradient is replaced by flat `--ws-accent`; below 20px use a mono `Re` chip instead of the mark.
- Monochrome: white knocked out of `--ws-ink`, or ink on white. Never on amber, green or danger fills — those carry status meaning.

## Design tokens

From the AdeHQ workspace palette (warm cream paper, coral accent, dark rail). Exact values:

**Surfaces**
| Token | Hex | Use |
|---|---|---|
| `--ws-cream` | `#E9E6DF` | outermost page / desk |
| `--ws-canvas` | `#F6F3EE` | app canvas |
| `--ws-surface` | `#FFFFFF` | cards, panels |
| `--ws-muted` | `#F0EDE6` | fills, tracks, chips |
| `--ws-border` | `#E6E1D8` | hairline borders |
| `--ws-border-2` | `#EFEBE3` | internal dividers |
| `--ws-rail` | `#1A1714` | dark nav rail, dark hero blocks |

**Text**
| Token | Hex |
|---|---|
| `--ws-ink` | `#221F1A` |
| `--ws-ink-2` | `#6C685F` |
| `--ws-ink-3` | `#9B968B` |

**Accent**
| Token | Hex |
|---|---|
| `--ws-accent` | `#E85D2C` |
| `--ws-accent-d` | `#CE4E22` |
| `--ws-accent-soft` | `#FBE9DE` |

**Status**
| Token | Hex | Soft tint |
|---|---|---|
| `--green` | `#1BA672` | `#E3F4EB` |
| `--amber` | `#CB8A1B` | `#FBEFD6` |
| `--danger` | `#D9483B` | `#FBE3E0` |
| `--info` | `#2F6FED` | `#E5EDFD` |

**Supplier avatar gradients** (140°): indigo `#4759A8 → #7A8BD8`, green `#1BA672 → #54C79A`, violet `#9A6BCB → #C29BE6`, coral `#E85D2C → #F2974E` (app mark).

**Typography**
- UI: **Schibsted Grotesk**, weights 400/500/600/650/700/800.
- Numerics, IDs, timestamps, money, eyebrow labels, codes: **JetBrains Mono**.
- Headings tracked `-0.02em` (`-0.01em` on small headings). Body line-height 1.5–1.6.
- Eyebrow labels are the only uppercase: mono, 9–9.5px, `letter-spacing: .14em`, colour `--ws-ink-3` (or `--green` / `--ws-accent-d` when semantic).

**Radii:** buttons/inputs/nav `9–13px` · cards `16–20px` · hero blocks, modals, bottom sheets `20–26px` · pills and chips `999px` · mono code chips `8px`.

**Spacing rhythm:** 7 / 9 / 11 / 14 / 16 / 18 / 22px.

**Shadows**
- Resting card: none or `0 1px 3px rgba(40,30,15,.14)`.
- Raised card (recommendation): `0 12px 30px -22px rgba(40,30,15,.5)`.
- Modal / sheet: `0 40px 90px -24px rgba(40,30,15,.5)`.
- Coral primary button glow: `0 8px 20px -8px rgba(232,93,44,.5)`.
- Phone shell: `0 40px 90px -24px rgba(40,30,15,.45)`.

**Motion**
- `itaaFadeUp` — `opacity 0 → 1`, `translateY(8px) → 0`, `.3s cubic-bezier(.2,.7,.3,1)`. Used on every view change.
- Success check — same keyframes at `.4s cubic-bezier(.2,.8,.3,1.2)`.
- `itaaPulse` — opacity `.35 ⇄ 1`, `1.6s` infinite, on the in-progress research dot.
- `prefers-reduced-motion: reduce` disables all animation and lands on the end state.

**Hit targets:** never below 44px on mobile; 34–40px is acceptable for secondary desktop controls, 44px+ for anything that discloses, authorizes, or deletes.

## Iconography

Lucide-style line icons, 24×24 viewBox, `fill:none`, `stroke:currentColor`, stroke-width ≈1.8–2, rounded joins, rendered 13–18px inline. Bare text glyphs are used deliberately and should stay text: `✓ ✕ ‹ ⌄ → • – + ?`. Two-letter mono codes identify domains (`Pk`, `Rc`) and suppliers (`JP`, `AV`, `RC`, `NT`, `HV`, `CD`). No emoji anywhere.

## Assets

None. There is no photography or illustration in Reservedge. Avatars are gradient rounded-squares bearing two-letter codes. Fonts load from Google Fonts (Schibsted Grotesk, JetBrains Mono) — self-host them in production.

## Files in this bundle

| File | What it is |
|---|---|
| `Reservedge Web.dc.html` | Web prototype — final |
| `Reservedge Mobile.dc.html` | Mobile prototype — final |
| `WEB.md` | Screen-by-screen spec for the web surface |
| `MOBILE.md` | Screen-by-screen spec for the mobile surface |
| `LOGO.md` | Identity handover — name, mark geometry, colour, size ladder, asset index |
| `Reservedge Logo.dc.html` | Identity sheet — lockups, icon ladder, clear space, rules |
| `assets/` | Logo SVGs — icon (gradient / flat / ink), glyph, and both lockups |
| `support.js` | Prototype runtime. Required only to open the HTML files. Not part of the design. |
| `tokens/` | The colour, type, spacing and font token stylesheets the prototypes reference |

To view a prototype, open the `.dc.html` file in a browser with `support.js` and `tokens/` alongside it.

## Known gaps

- **Free-text answers in the composer are stubbed.** The user types the opening line, but the three follow-up answers are chip-only in the prototype. Real input requires the questions to be curated from what the user typed — the schema fixes *which fields* must be filled and their ranking, while the wording and the offered chips should be generated per intent. This is the main piece of product logic that the prototypes represent but do not implement.
- **Spa is undesigned**, deliberately. Entertainment proved the spine; spa should be added as data by whoever needs it.
- **Simulation only.** No payment, reservation, or supplier integration exists behind any screen.
