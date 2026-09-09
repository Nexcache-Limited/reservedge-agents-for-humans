# Reservedge — Intent-first redesign, design handover

Date: 31 August 2026
Status: design proposal for Product Owner decision. Not production code.

## What this is

Two interactive prototypes and their specifications for the intent-first
(objective-first) direction described in the local-baseline review. They replace
the domain picker as the front door with a single intent composer, introduce a
parent booking that holds several domain tasks, and carry two of those tasks —
airport parking and rental car — end to end through disclosure, offers,
selection, authorization and receipt.

The visual system is unchanged. This is a structural proposal, not a re-skin:
same warm cream canvas, coral accent, dark rail, Schibsted Grotesk and JetBrains
Mono as the existing Reservedge handoff.

## The decision in front of the Product Owner

Adopt or reject the revised model. Concretely, adopting it means accepting:

1. Conversation becomes the primary intake and continuity surface. Structured
   task, requirement, disclosure, offer and audit objects remain the primary
   decision surfaces. This supersedes the normative statement that the product
   is "not primarily a chatbot" — see Conflicts below.
2. A parent orchestration object exists above PurchaseIntent. The prototypes
   call it a **booking**; the internal name can stay OrchestrationIntent.
3. Multi-domain scope. v1 normative scope is airport parking only.
4. Numeric ranking scores leave customer-facing surfaces, replaced by
   Strong / Good / Fair fit plus factual reasons and a stated downside.
5. Offers carry source type and class, and authoritative validity, through the
   buyer snapshot rather than being reconstructed from a supplier-token catalog.

## Files

| File | What it is |
|---|---|
| `Reservedge Intent-First.dc.html` | Web prototype, 8 screens |
| `Reservedge Intent-First Mobile.dc.html` | Mobile prototype, 9 screens |
| `WEB.md` | Web screen and component specification |
| `MOBILE.md` | Mobile specification and the decisions that differ from web |
| `tokens/` | colors, typography, spacing, fonts — reference copies |
| `assets/` | Reservedge mark and lockups, unchanged from the previous handoff |
| `support.js` | Runtime for the .dc.html prototypes |

Open either `.dc.html` in a browser. The prototypes reference the AdeHQ design
system bundle at `_ds/adehq-design-system-e7369172-d959-4682-9ed3-9320bc3582a7/`;
run them from the project root, or repoint the five `<link>` tags and one
`<script>` tag in `<helmet>` at the copies in `tokens/`.

## Object model shown

```
Booking (BK_4K21) ......... user-owned, persistent, holds conversation + plan
  shared context .......... each field carries provenance: you said / inferred / confirmed
  DomainTask (pi_8f2c) .... airport parking — own Requirement, Disclosure, Offers, Authorization
  DomainTask (pi_3a90) .... rental car — same, independent
  DomainTask (pi_5c77) .... hotel — blocked on 2 missing details
  DomainTask (proposed) ... flight — inferred, inactive until accepted
```

A task never inherits another task's disclosure. Shared context is a store the
tasks draw from, never a payload that travels as one piece.

## Preserved from the current implementation

- Intent inbox as the durable work queue, with attention-first ordering.
- One domain-agnostic spine. Both domains render through identical screens;
  only the requirement schema, the disclosure tier and the offer dimensions
  differ. There is no per-domain screen flow.
- A1 / A2 / A3 / A4 separation, and fresh approval after material change.
- Exact sent/withheld preview with a purpose per field.
- Per-supplier envelopes and recipient isolation; no competitor leakage and no
  stable buyer identifier.
- Deterministic eligibility and ranking with missing-data penalties, stated
  downside, provenance and user override.
- Offer versioning, expiry, refresh/requote, simulation honesty.

## Changed

1. `/intents/new` opens an intent composer, not a domain picker. Domain cards
   are demoted to a secondary "already know the exact booking?" row that still
   creates a one-task booking with the full approval path.
2. Tasks are inferred and shown as **proposed** (dashed border) until accepted.
   Accepting is an explicit act; declining is free.
3. Clarification questions are batched — three at once, marked blocking, with
   each field stating which tasks it unblocks. Skipping converts them into
   missing details on the affected task.
4. Disclosure is task-scoped and says so on the screen. Partial approval is a
   first-class button, not a hidden affordance.
5. Offers state `sourceType` (supplier private quote / aggregator rate / public
   market reference) and `offerClass` (curated). A curated quote is labelled but
   is not automatically recommended.
6. Validity is absolute plus relative — "Valid until 14:30 BST" over
   "26 minutes remaining" — coloured amber when close. No countdown timer, no
   manufactured urgency.
7. Incomplete offers are ranked lower and labelled, not hidden. A supplier that
   did not reply is shown as a non-responder rather than dropped.
8. Numeric scores are gone. Fit is Strong / Good / Fair, with reasons and one
   named downside per offer.
9. Authorization names the exact supplier, amount, offer id, version, terms hash
   and validity of the offer the user actually selected.
10. Press-and-hold is offered as a preference, never as the only path.

## Conflicts requiring formal change control

| # | Normative statement | Proposed supersession |
|---|---|---|
| 1 | Product is an Intent Inbox, "not primarily a chatbot" | Conversation is the primary intake and continuity surface; structured objects remain the primary decision, disclosure, approval and authorization surfaces |
| 2 | v1 scope is airport parking | Multi-domain booking orchestration; needs roadmap and ADR update |
| 3 | Older cool-slate visual system | Reservedge warm/coral system, if confirmed as the approved identity |
| 4 | UI must not expose numerical fit scores | Already honoured here; the live implementation still violates it and needs a fix |
| 5 | Hold-to-confirm is part of the design | Deliberate confirmation required; gesture optional, standard activation always available |

## Deliberately not claimed

The prototypes show resume-after-two-days on the booking workspace. Durable
persistence does not exist in the backend yet. Do not ship the resume promise
until repositories exist for bookings, conversation events, task and requirement
versions, offers, approvals, activity and idempotency.

## Not in this pass

State matrices, canonical contract additions, the route-to-target migration map,
and acceptance criteria. Those are the written half of the brief and follow once
the model itself is approved.
