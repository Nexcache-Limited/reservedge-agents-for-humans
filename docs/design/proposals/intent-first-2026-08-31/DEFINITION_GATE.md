# Intent-first definition gate

**Status:** Accepted — Intent-first product model and flow definition frozen.  
**Approved:** Product Owner, 31 August 2026.  
**Execution:** This approval does not activate COMP-G1-06 or authorize product-code changes.  
**Date:** 31 August 2026  
**Revision:** freeze-pack corrections (2) — preferences never disclosed; A4 is authorization not Booking confirmation.  
**Branch:** `work/comp-g1-05-reservedge-ui`  
**HEAD:** `ff12fef` (plus a large uncommitted COMP-G1-05 Reservedge UI + RC remediation cut)

This pack applies the six freeze edits from the 31 August review to the Intent-first prototype. It does **not** freeze the UI/flow and does **not** authorize production code changes.

Normative `.docx` files are unchanged. This is a design/ADR-class proposal under `docs/design/proposals/`.

## Decision requested

Freeze edits 1–5 are accepted in principle. Prior pack corrections (ledger split, per-field partial disclosure, `scoreMicros` off the buyer projection, nested task routes, draft deletion) remain. This revision is submitted for **edit 6** (definition-pack) approval after two further definition-only corrections: preferences never disclosed; A4 is not Booking confirmation.

1. **Accept** the corrected public language: parent aggregate is **Intent**; **Booking** is a child transaction produced by a Booking Task. A simulated authorization is not a Booking. Live A4 is not a Booking.
2. **Accept** Cost Ledger + combined multi-domain recommendation as ship-required surfaces (fixtures until durable repositories exist). Ledger buckets `authorized_simulated`, `authorized_live`, and `booking_pending` are distinct from `confirmed_booking`; only an authoritative supplier/connector confirmation fills `confirmed_booking`. Simulation never fills it.
3. **Accept** that production copy must not claim cross-session/device/restart resume while `/readyz` reports `durability: unsupported`.
4. **Accept** the three-way split: offer validity ≠ inventory hold ≠ transaction result; simulation never claims a hold.
5. **Accept** task-level A1 as a first-class step, with correction/override, the per-field partial-disclosure table in §5.1 (requirements only; preferences never in A2), and the live A4 sequence in §5.2.
6. **Accept** this definition pack (matrices, offer projection, route/migration, mobile toolchain) as the freeze contract for a later work order.

Until edit 6 is accepted, do not start Intent-first feature implementation.

---

## 1. Inspect report

### Worktree

- Live tree: `[local-path]/ITAA-comp-g1-05`
- Uncommitted COMP-G1-05 Reservedge chrome, live parking composer, RC UAT remediation (EV/`ev_charging`, WallClock, portal CTA, honest click labels).
- Must be preserved. Do not reset, rebase, or mix a second product cut into the same uncommitted delta without a new work order and file leases.

### Source-of-truth priority (unchanged)

1. `ITAA_v1_Product_and_Technical_Specification.docx`
2. `ITAA_Unified_UI_UX_Design_Specification.docx`
3. `ITAA_Engineering_Kickoff_Pack.docx`
4. Active work order

The Intent-first prototype **conflicts** with (1) on chatbot primacy and parking-only v1 scope. Formal change control is required; this pack does not silently supersede the `.docx` files.

### Prototype ingested

Copied (not edited) to `docs/design/handoffs/intent-first-2026-08-31/`.

Review source copied to `review-and-cursor-prompt.md`.

Prototype defects that this pack corrects in **definitions**, not in the `.dc.html` files:

| Prototype as delivered | Corrected for freeze |
|---|---|
| Parent named Booking (`BK_4K21`), list “Bookings”, “Start booking” | Parent **Intent**; Booking = `confirmed_booking` only |
| No Cost Ledger | Intent-level deterministic ledger; `confirmed_booking` only after supplier/connector confirmation |
| Parking ready + rental researching only | Combined recommendations when ≥2 tasks are offer-ready |
| Receipt “holds” a bay/vehicle in simulation | Inventory `not_held` in simulation; validity is not a hold |
| “Resumed 2 days later” | Future-state watermark; do not ship |
| A1 not shown as a task step | Task-level requirement review/confirm |
| Direct-domain shortcut jumps to four-task workspace | One-task Intent |

### Mobile toolchain

`apps/mobile/README.md` remains a WP-01 placeholder. **No Expo / React Native / native scaffold.** Responsive web at 320 / 390 / 410 is the mobile surface until PO accepts a native ADR.

---

## 2. Implementation map (current → keep / adapt / replace)

Do not begin feature edits until PO accepts this map.

| Current | Role today | Intent-first | Overlap / risk |
|---|---|---|---|
| `PortfolioLayout`, rail, inbox, tokens | Reservedge shell | **Keep** | Uncommitted COMP-G1-05 owns these files |
| `inbox.ts` filters, `SEED_INTENTS` | Domain-first list | **Adapt** labels stay Intent; rows become Intent not PurchaseIntent | Seeds vs live `pi_*` already split |
| `/intents/new` → `DomainPicker` | Domain-first | **Replace** with objective composer; domain chips = one-task Intent | Compatibility redirect `/intents/new/:domainId` |
| `Composer.tsx` + `registry.ts` | ≤3 questions, parking live / rental+ents fixture | **Adapt** as Booking Task A1 input; batch ≤3 per round at Intent level too | RC EV/accessibility work must survive |
| `LiveParkingWorkspace` vs `SeedWorkspace` | `startsWith("pi_")` split | **Replace** with one Intent/Task view-model; adapters behind it | High risk if done in the same uncommitted cut |
| `competition-offers.tsx` | RankedOffer + fixture catalog | **Adapt** to buyer Offer projection; **no `scoreMicros` on that projection** | Locked 671000 vector stays in ranker/audit/tests only |
| Buyer `RankedOffer` DTO | currently includes `scoreMicros` | **Replace** with §7 projection; **deprecate and remove `scoreMicros` from buyer DTO/OpenAPI** | Contracts/OpenAPI change — coordinator-owned |
| A1–A4 in `golden_path.py` / intake | Parking PurchaseIntent | **Keep** semantics; **adapt** so each Booking Task has its own PI | Do not merge approvals |
| `session/memory.ts` | sessionStorage inbox | **Keep as cache only**; never “resumed after 2 days” | `/readyz` durability unsupported |
| Draft `deleteDraft` / inbox `canDelete` | Pre-A2 delete | **Keep** as Intent `deleted` | Distinct from `cancelled` |
| `apps/mobile` | Placeholder | **No native work** | PO decision required later |

---

## 3. Canonical model

Public product term: **Intent**. Internal type: `OrchestrationIntent` (or `ObjectiveIntent`). Never name the parent Booking in UI or routes.

```
Intent (oi_*)
  conversation events + structured summary
  shared context facts (value, provenance, confidence, source, correction)
  preferences (evidence + Intent-level override; **never disclosed to suppliers**)
  Plan of Booking Tasks
  Cost Ledger (deterministic)
  activity / audit
    Booking Task (parking | rental | …)
      domain schema, requirement versions
      A1 requirement confirm → PurchaseIntent
      A2 disclosure → isolated envelopes (requirements only; never preferences)
      offers + recommendation + user selection
      A3 accept / A4 authorize (attempt permission, not a Booking)
      authorized_simulated   ← simulation terminal; not a Booking
      authorized_live → booking_pending → confirmed_booking | booking_failed
                         ← live only; Booking exists solely at confirmed_booking
```

Never send the parent Intent, conversation, whole plan, sibling tasks, or **preferences** to a supplier.

A **Booking** exists only in `confirmed_booking`, and only after an authoritative supplier/connector confirmation. A4 success is not a Booking. `authorized_simulated` is a simulation terminal. `authorized_live` and `booking_pending` are live post-A4 states, not Bookings.

---

## 4. Intent state matrix

| State | Meaning | Buyer can | Notes |
|---|---|---|---|
| `draft` | Objective typed; no accepted tasks | Edit objective, accept/decline proposed tasks, **delete/abandon** | Session-scoped until durable repos. Pre-A2 only. |
| `clarifying` | ≤3 blocking questions this round | Answer, skip (becomes missing on tasks), **delete/abandon** | Not “all questions done” while required gaps remain. Still pre-A2. |
| `planning` | ≥1 accepted task; none past A2 | Accept/decline tasks; open a task; **delete/abandon** | Proposed tasks inactive. Delete allowed until first A2. |
| `deleted` | Draft abandoned before any A2 | None (terminal) | Preserves current `deleteDraft` lifecycle. One audit tombstone. Not in All. Not History-as-Booking. Irreversible in this session. |
| `attention` | A task needs A1/A2/A3/A4 or missing details | Act on that task | Inbox “Needs you”. After first A2, abandon is `cancelled`, not `deleted`. |
| `in_progress` | Researching / waiting on suppliers | Pause, replace, cancel task | Independent per task |
| `offers_ready` | ≥1 task has selectable offers | Compare / select / authorize per task | Combined recs if ≥2 ready |
| `partially_authorized_simulated` | ≥1 task `authorized_simulated`; others open | Continue other tasks | Ledger: `authorized_simulated` + estimated. **Not** `confirmed_booking`. |
| `partially_authorized_live` | ≥1 task `authorized_live` or `booking_pending`; none `confirmed_booking` | Wait / continue other tasks | Live A4 succeeded or attempt in flight. **Not** a Booking. Empty on the simulation path. |
| `partially_booked` | ≥1 task `confirmed_booking`; others open | Continue other tasks | Only after supplier/connector confirmation. Empty on the simulation path. Empty after A4 alone. |
| `completed_simulated` | All accepted tasks terminal in simulation | History | All tasks `authorized_simulated`, `cancelled`, or `failed`. No Booking. |
| `completed` | All accepted tasks terminal with ≥1 `confirmed_booking` | History | Not reachable on the simulation path. Not reachable from A4 alone. |
| `paused` | Buyer paused after A2 | Resume **in this session only** | No cross-restart copy |
| `cancelled` | Buyer cancelled after A2 (or cancelled a live task) | Tombstone in history | Does not unshare already-sent envelopes. Distinct from `deleted`. |
| `failed` | Unrecoverable (offline, all tasks failed) | Retry per task policy | See task matrix |

**Draft deletion / abandonment (existing lifecycle):**

- Allowed in `draft`, `clarifying`, and `planning` (no A2 issued on any task).
- Action is the current delete-draft path: remove from All/Needs you/Pending; write one audit tombstone; do not create a Booking.
- After any task A2, delete-draft is unavailable; the Intent uses `cancelled` (and task cancel/replace), matching current dispatched-intent rules.
- Inbox `canDelete` remains true only while the Intent is pre-A2.

Invalidation: material change on task T invalidates T’s A2/offers/A3/A4 only.

---

## 5. Booking Task state matrix

Includes A1–A4, live booking confirmation, expiry, supersession, no-offer, timeout, offline, auth failure. A4 authorizes an attempt; it does not confirm a Booking.

| State | Gate | Buyer action | Consequence |
|---|---|---|---|
| `proposed` | none | Accept / Not needed | Decline is free; siblings unchanged |
| `missing_details` | — | Correct fields | Blocking fields prevent A1 |
| `a1_review` | A1 | Confirm requirement version **or** correct | Confirms exact requirement/version; creates/binds PurchaseIntent |
| `a1_blocked` | A1 failed / incomplete | Fix and re-confirm | No silent confirm |
| `public_research` | — | Wait / skip to disclosure when ready | If aggregator query left the system, record query fields — never “no field disclosed” if dates/location were sent |
| `a2_required` | A2 | Approve exact fields/purposes/recipients/hash/expiry; or **partial** per §5.1; or decline | Consequence is the row in §5.1 for each omitted field; if any omitted field is `blocked`, A2 does not issue |
| `researching` | A2 held | Wait | Isolation preserved |
| `supplier_timeout` | — | Refresh / continue with partial set | Non-responders remain visible |
| `no_offer` | — | Relax / cancel task | No invented ranking |
| `offers_ready` | — | Compare; select | Fit Strong/Good/Fair only; no numeric scores in buyer UI or buyer DTO |
| `offers_expiring` | `validUntil` near | Refresh/requote | Amber, no countdown |
| `offers_expired` | `validUntil` passed | Requote | Cannot A3/A4 |
| `superseded` | terms/version change | Review new version | Fresh A3/A4 |
| `a3_review` | A3 | Accept **selected** offer (not merely recommended) | No reserve, no charge |
| `a3_ineligible` | expired/superseded/stale | Refresh | |
| `a4_required` | A4 | Authorize ReservEdge to attempt the exact supplier, amount, currency, offer/version, terms hash, validity | Authorization to attempt. **Not** a Booking. Simulation: no hold, no money movement. |
| `a4_failed` | A4 auth error | Retry with current idempotency rules | Buyer authorization did not succeed. No attempt, no Booking. |
| `authorized_simulated` | A4 ok (simulation) | Simulated receipt | **Simulation terminal.** Inventory = `not_held`; transaction = `simulated`. **Not** a Booking. Does not continue to `authorized_live` / `booking_pending` / `confirmed_booking`. Ledger: `authorized_simulated` only. |
| `authorized_live` | A4 ok (live) | Wait | ReservEdge is authorized to attempt the exact transaction. **Not** a Booking. Ledger: `authorized_live`. Simulation never enters this state. |
| `booking_pending` | live attempt in flight | Wait | Connector/supplier confirmation not yet received. **Not** a Booking. Ledger: `booking_pending`. Simulation never enters this state. |
| `confirmed_booking` | authoritative supplier/connector confirmation | Booking receipt | The only state that creates a Booking or writes ledger `confirmed_booking`. Never follows A4 directly. Simulation never enters this state. |
| `booking_failed` | live attempt rejected/timed out after `authorized_live` | Retry / replace / cancel per policy | No Booking. Does not populate `confirmed_booking`. Distinct from `a4_failed`. Simulation never enters this state. |
| `paused` / `cancelled` / `failed` / `offline_readonly` | — | Resume in session / cancel | Revocation copy: future use + audit retention; not “unshared” |

### Validity vs inventory vs transaction (freeze edit 4)

| Axis | Values | Simulation rule |
|---|---|---|
| Validity | `valid`, `expiring`, `expired`, `superseded` | From `validFrom` / `validUntil` / version |
| Inventory | `not_held`, `subject_to_availability`, `held_until` | **Always `not_held` in simulation.** Never infer from validity. |
| Transaction | `simulated`, `authorized_simulated`, `authorized_live`, `booking_pending`, `confirmed_booking`, `booking_failed`, `failed`, `cancelled` | Simulation: `simulated` / `authorized_simulated` only. Live confirmation is not A4. Never `confirmed_booking` without supplier/connector confirmation. |

Refresh/requote creates a new offer version. Expired/superseded cannot be selected.

### 5.1 Partial-disclosure consequences (deterministic)

A1 completeness is unchanged: a registry field with `required: true` still blocks A1 confirm. §5.1 applies only to **A2 payload omit** of an already-confirmed field (sent vs withheld). It does not reopen A1.

Partial A2 names the omitted field(s). The task outcome is the **strictest** consequence among omitted fields: `blocked` > `quotes_incomplete` > `quotes`.

Closed vocabulary:

| Code | Meaning |
|---|---|
| `blocked` | A2 is refused. No envelopes, no solicitation. Buyer must include the field or decline A2. |
| `quotes_incomplete` | A2 may issue without the field. Solicitation proceeds. Offers are marked incomplete on that dimension and **cannot be recommended**. A3/A4 on those offers is blocked until a targeted re-ask or a new A2 includes the field. |
| `quotes` | A2 may issue without the field. Solicitation proceeds. Ranking uses the stated default below. Offers remain complete on that dimension. No current registry field maps to `quotes`; the code remains defined for requirement-field omit only, never for preferences. |

Preferences influence local filtering and ranking only. They **never** enter an A2 payload, including a “separate” or later A2. There is no preference-disclosure exception.

If a supplier cannot quote without a constraint, that constraint must be an explicit task **requirement** (A1 field on the domain schema), not a profile or preference leaked through A2. Omitting a preference is not an A2 decision: the preference was never a candidate field.

#### Airport parking (`parking`) — registry fields

| Field | A2 omit | Default if `quotes` / incomplete rule |
|---|---|---|
| `airportCode` | `blocked` | Location is required to price. |
| `start` | `blocked` | Window start is required to price. |
| `end` | `blocked` | Window end is required to price. |
| `vehicleClass` | `blocked` | Closed vehicle class is required to price. |
| `currency` | `blocked` | ISO currency is required to price. |
| `covered` | `quotes_incomplete` | Offers that do not state cover are incomplete; cannot be recommended. |
| `shuttleMaxMinutes` | `quotes_incomplete` | Offers that do not state shuttle minutes are incomplete; cannot be recommended. |
| `accessibility` | `quotes_incomplete` | Offers that do not state the requested access need (including `ev_charging`) are incomplete; cannot be recommended. |

Name and plate are A4-only. They are not A2 fields; they cannot be “partially disclosed” at A2.

#### Rental car (`rental`) — registry fields

| Field | A2 omit | Default if `quotes` / incomplete rule |
|---|---|---|
| `when` (pickup and return) | `blocked` | Service window is required to price. |
| `driver` (age band and licence class) | `blocked` | Tier 2: suppliers cannot legally quote without both. |
| `class` (vehicle class) | `quotes_incomplete` | Offers that do not state vehicle class are incomplete; cannot be recommended. |

Static row `MUST-HAVES` (free cancellation, mileage, no debit deposit) is a **preference**. It is never disclosed to suppliers. It never appears in any A2 payload. It is used only for local filtering and ranking. If a rental supplier cannot quote without one of those constraints, that constraint must be added as an explicit task requirement on the rental schema (A1), not sent as preference disclosure.

#### Entertainment booking (`ents`) — registry fields

| Field | A2 omit | Default if `quotes` / incomplete rule |
|---|---|---|
| `when` (evening) | `blocked` | Event date/window is required to hold or price seats. |
| `party` (party size / together) | `blocked` | Tier 1 still requires party size to hold seats. |
| `what` (category) | `quotes_incomplete` | Offers that do not state category/genre are incomplete; cannot be recommended. |

Static row `CEILING` (price band from the typed line) is a **preference**. It is never disclosed to suppliers, including as a band. It is used only for local filtering and ranking. If a venue cannot quote without a price band, `ceiling` must be added as an explicit task requirement on the ents schema (A1), not sent as preference disclosure.

No other omit outcome is permitted. Implementations must not choose freely among quote / incomplete / blocked.

### 5.2 Authorization vs Booking

A4 authorizes ReservEdge to attempt the exact named transaction. A4 success does not create a Booking and does not populate `confirmed_booking`.

**Simulation (current path):**

`a4_required` → (`a4_failed` → retry `a4_required`) → `authorized_simulated` (terminal).

Simulation must not enter `authorized_live`, `booking_pending`, `confirmed_booking`, or `booking_failed`.

**Live:**

`a4_required` → (`a4_failed` → retry `a4_required`) → `authorized_live` → `booking_pending` → `confirmed_booking` | `booking_failed`.

Only an authoritative supplier/connector confirmation may create a Booking or write ledger `confirmed_booking`. A timeout or reject after `authorized_live` is `booking_failed`, not a Booking.

---

## 6. Cost Ledger (freeze edit 2)

Deterministic, view-model arithmetic. No LLM totals. Mixed currencies stay separate unless FX rate + source + timestamp are evidenced.

Rows: one per Booking Task (and line items when an offer has breakdown).

Columns / buckets:

- `confirmed_booking` — only after an authoritative supplier/connector confirmation creates a Booking. **Empty on the simulation path.** A4 must never write this bucket. `authorized_live` and `booking_pending` must never write this bucket.
- `authorized_simulated` — amounts from `authorized_simulated` / `TRANSACTION_AUTHORIZED_SIMULATED`. Display as simulated authorization, not a Booking, not payable, not a reservation.
- `authorized_live` — amounts from live A4 success. Display as authorized to attempt, not a Booking, not payable-as-confirmed.
- `booking_pending` — same live amounts while awaiting supplier/connector confirmation. Not a Booking.
- selected, not authorized
- estimated (recommended or researching)
- expired / excluded
- deposits / holds (only if authoritative; **omit or zero in simulation**; live holds only when the connector reports a hold, never inferred from A4)
- taxes / fees
- payable now / payable later — **empty while every authorization is simulated**; live payable-now only after `confirmed_booking` (or an evidenced live hold, never from A4 alone)

A simulated receipt must not increment `confirmed_booking`, `authorized_live`, `booking_pending`, payable-now, or deposits/holds. A live A4 receipt must not increment `confirmed_booking`.

Combined multi-domain state: parking + rental both `offers_ready` on one Intent Plan, each with independent Compare / Review / Authorize, plus ledger impact.

---

## 7. Buyer-facing Offer projection

Extend the **buyer-visible** offer object (and buyer OpenAPI) so UI does not use `golden.ts` catalog as commercial truth.

**Allowed on the buyer Offer projection:**

- `sourceType`: `aggregator_rate` | `public_market_reference` | `supplier_private_quote`
- `offerClass`: `standard` | `curated`
- display identity + opaque ids (as today)
- `issuedAt`, `validFrom`, `validUntil`, `version`, `supersededBy`, `withdrawn`, `termsHash`
- price breakdown: total, taxes/fees, deposit, pay-later, currency
- qualitative fit: `strong` | `good` | `fair` (derived for display; not a numeric score)
- normalized dimensions, completeness, evidence
- `simulation`
- optional `inventoryHeldUntil` only when authoritative (omit in simulation)
- `rank` as ordinal position is allowed only if it is not a scoring unit; prefer “recommended / alternative” without exposing micros

**Excluded from the buyer Offer projection (deprecated if present on today’s `RankedOffer`):**

- `scoreMicros` — **removed**. Not omitted in the UI while still serialized. Not an optional hide. Buyer DTO, buyer OpenAPI, and buyer snapshots must not include this member.

**Internal only** (ranker, policy audit, adversarial/golden tests, non-buyer logs): `scoreMicros` remains the locked ranking unit (671000 / 660000 / 535000). Those surfaces are not the buyer Offer projection.

---

## 8. Route / DTO / fixture / live / stored-state migration

Task screens nest under the owning Intent. No top-level `/tasks/:taskId` product route.

| Current | Compatibility | Target |
|---|---|---|
| `/` inbox | Keep | Intent rows (`oi_*`); `pi_*` cards adapt as one-task Intents |
| `/intents/new` | Keep path | Objective composer |
| `/intents/new/:domainId` | Keep | One-task Intent + existing composer |
| `/intents/:intentId` | Keep `pi_*` as one-task Intent id or wrap | Intent Plan + Conversation |
| `/intents/:intentId/confirmation` | Redirect | `/intents/:intentId/tasks/:taskId/confirmation` for the sole wrapping task |
| New | — | `/intents/:intentId/plan` |
| New | — | `/intents/:intentId/tasks/:taskId` |
| New | — | `/intents/:intentId/tasks/:taskId/a1` |
| New | — | `/intents/:intentId/tasks/:taskId/a2` |
| New | — | `/intents/:intentId/tasks/:taskId/offers` |
| New | — | `/intents/:intentId/tasks/:taskId/a3` |
| New | — | `/intents/:intentId/tasks/:taskId/a4` |
| New | — | `/intents/:intentId/tasks/:taskId/confirmation` — simulation: `authorized_simulated` receipt, inventory `not_held`, not a Booking. Live: `authorized_live` / `booking_pending` / `confirmed_booking` / `booking_failed` as the task state, never a Booking from A4 alone |
| sessionStorage | Cache | Same keys OK; never durable truth |
| Fixtures (rental/ents) | Label simulated demonstration | Same Task view-model as live parking |
| OpenAPI buyer offer | Additive commercial fields; **delete `scoreMicros` from buyer schema** | Coordinator-owned; ranker schema may keep `scoreMicros` internally |

Stored-state: in-memory API + session cache. Restart ⇒ `unknown_resource`. Production copy must say so.

---

## 9. Direct-domain and back-navigation

| Entry | Outcome |
|---|---|
| Objective line, no domain | Intent draft → propose tasks → accept parking/rental independently |
| Domain chip “Airport parking” | One-task Intent; full A1–A4; **not** the four-task fixture workspace |
| Bookmark `/intents/new/parking` | Same as domain chip |
| Bookmark `/intents/pi_*` | Wrap as one-task Intent; Plan at `/intents/:intentId`; task at `/intents/:intentId/tasks/:taskId/...` |
| Back from A2/A3/A4 | `/intents/:intentId/tasks/:taskId` or Intent Plan; do not dump to JetPark seed |
| Delete draft | Pre-A2 only → Intent `deleted` |
| Mobile | Plan tab first when a decision needs attention; Conversation is the other tab |

---

## 10. Public research vs aggregator query

If a search request sends dates/location to an external aggregator, the disclosure/audit line must name those query fields. “No field disclosed” is reserved for truly local/public scrape with no outbound task payload. Preferences never appear in an aggregator query, A2 envelope, or other supplier payload.

---

## 11. Native mobile

**Decision for this gate:** do not choose a native stack. Deliverable after web Intent-first ships: a short ADR proposing shared contracts/view-models and a toolchain, then stop pending PO.

---

## 12. Delivery after approval (not started)

Phased work order, separate from the uncommitted COMP-G1-05 RC cut unless PM authorizes one integration:

1. Contracts + buyer Offer projection without `scoreMicros` (coordinator)
2. Compatibility adapters for `pi_*` onto nested `/intents/:intentId/tasks/:taskId/...`
3. OrchestrationIntent view models + ledger (`authorized_simulated` ≠ `authorized_live` ≠ `booking_pending` ≠ `confirmed_booking`; preferences never leave the Intent)
4. Objective composer + Plan + draft delete
5. Task A1–A4 panels with §5.1 partial disclosure (requirements only) and §5.2 live booking sequence
6. Offers/validity/no-score buyer UI
7. Combined recs + ledger surfaces
8. Responsive 1440 / 1280 / 410 / 390 / 320 + tests

Existing parking golden path, privacy, lifecycle, simulation honesty, and tests must keep passing.

---

## 13. Explicitly not doing now

- Editing `App.tsx`, composer, ranker economics, or OpenAPI
- Overwriting `docs/source-of-truth/*.docx`
- Editing the prototype `.dc.html` files
- Scaffolding `apps/mobile`
- Claiming UI/flow freeze
- Commit / push / merge / deploy / video
