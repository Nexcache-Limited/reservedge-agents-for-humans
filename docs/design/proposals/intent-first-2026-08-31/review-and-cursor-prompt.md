# ReservEdge Intent-first prototype review and Cursor implementation brief

Date: 31 August 2026

## Executive decision

**Product-model decision: GO.** The prototype establishes the right core identity for ReservEdge: objective-first conversational discovery combined with structured, governed execution.

**Final UI/flow freeze: NO-GO as delivered; conditional GO after the six final edits below.** The visual system and the main interaction spine can be frozen. The complete product flow should not be called final yet because the prototype renames the parent objective to “Booking,” omits the Cost Ledger and combined multi-domain recommendation state, conflates offer validity with inventory holds, displays an unsupported two-day resume, and does not include the A1/state/contract/migration definition required for safe implementation.

No further foundational redesign is needed. Once the six edits are incorporated and the deferred state/contract/migration artifacts are approved, the UI/flow can be frozen and engineering can proceed.

## Scope reviewed

The review covered every supplied file in `Reservedge prototype walkthrough-2.zip`:

- desktop prototype: 8 screens;
- mobile prototype: 9 screens;
- `README.md`, `WEB.md`, and `MOBILE.md`;
- all desktop/mobile interaction data and transitions in the two `.dc.html` files;
- shared runtime, colour, spacing, typography and font tokens;
- all supplied logo/glyph assets.

It was reconciled with the current local baseline:

- live worktree: `[local-path]/ITAA-comp-g1-05`;
- branch: `work/comp-g1-05-reservedge-ui`;
- current commit: `ff12fefdd1b56f78a7b390959d46ad04cd3f7be6` (deployment evidence only);
- current React routes, shell, domain registry, composer, live/fixture workspaces, offer UI, API DTOs, in-memory/session state and visual evidence;
- local source-of-truth folder: `[local-path]/Documents/Reservedge-ITAA project`;
- existing responsive evidence at 1440, 1280, 410, 390 and 320 CSS pixels.

The in-app browser rejected local `file://` navigation under its security policy. Visual conclusions therefore use the supplied HTML/CSS specifications plus the repository’s existing rendered visual evidence; no claim is made that the new `.dc.html` files were interactively rendered in the browser during this review.

## A. Product and UX review

### Approved strengths

1. **Intent-first entry is correct.** “What are you planning or trying to get done?” is a much stronger front door than the current domain picker. Domain shortcuts are correctly demoted beneath the objective.
2. **Conversation plus Plan is the right product shape.** Conversation handles discovery and modification; structured task cards remain the decision record. The mobile decision to open the Plan tab first is especially sound.
3. **Task-level governance is preserved.** The prototype retains separate requirement, disclosure, selection and authorization semantics; disclosure is scoped per task and material changes invalidate only the affected task.
4. **Supplier isolation is clear.** Sent/withheld fields, purposes, bounded recipients, scoped identifiers, no competitor leakage and no itinerary-wide payload are all represented well.
5. **Curated/private offers are represented neutrally.** Direct private quotes, aggregator rates and public references use one offer surface; curated offers do not automatically win.
6. **Offer presentation is materially better.** Numeric fit scores are removed. Strong/Good/Fair fit, reasons, a downside, completeness, provenance and version are more defensible and understandable.
7. **Validity presentation is calm and factual.** Absolute expiry plus relative time, amber only when close, and no ticking countdown avoid manufactured urgency.
8. **Incomplete and non-responsive suppliers remain visible.** This improves trust and prevents ranking from hiding inconvenient evidence.
9. **A3 and A4 bind the selected offer.** The review and authorization screens correctly use the exact supplier, amount, offer/version, terms hash and validity selected by the user—not merely the recommended offer.
10. **The visual system can be preserved.** The warm cream/coral/dark-rail system, Schibsted Grotesk, JetBrains Mono, cards, density and responsive shell align with the current ReservEdge implementation.
11. **Mobile fundamentals are good.** Plan-first tabs, fixed consequence-aware action bars, stacked offer cards, 44px targets, wrapping mono values and reduced-motion support are appropriate.

### Blocking approval issues

#### 1. The parent object is named and presented incorrectly

The established hierarchy is:

`Intent → Conversation + Plan → Booking Tasks → PurchaseIntent/Offer/Authorization/Booking → Cost Ledger`

The prototype instead presents `Booking (BK_4K21)` as the persistent parent, labels the list “Bookings,” uses “Start booking,” and calls the main surface “Booking workspace.” This collapses the objective container into a transaction word and regresses the current product language, whose rail and routes already use Intents.

**Required:** public UI and canonical product language must use **Intent** for the objective container. “Booking” should describe an authorized/confirmed transaction produced by a Booking Task. Internal code may use `OrchestrationIntent` or `ObjectiveIntent`; do not make `Booking` the parent aggregate.

#### 2. The Cost Ledger is absent

There is no cross-task ledger, combined estimate, currency treatment, or distinction between confirmed, selected, estimated, expired, deposit, tax and pay-later amounts. This is a core part of the approved model, not an optional analytics widget.

**Required:** add a deterministic Intent-level Cost Ledger to desktop and mobile. Show task rows and at least: confirmed; selected/not authorized; estimated; expired/excluded; deposits/holds; taxes/fees; payable now/later. Mixed currencies must remain separate unless an evidenced FX conversion, rate source and timestamp are shown.

#### 3. The design does not show the combined multi-domain decision state

Parking is ready while rental is researching, so the prototype never demonstrates the moment when recommendations from two or more Booking Tasks are simultaneously ready. Users therefore cannot validate the promised single-window, multi-domain experience.

**Required:** add one final Intent Plan state showing at least parking and rental recommended offers together, their validity, task status and ledger impact, while preserving independent task review and authorization.

#### 4. Offer validity and inventory hold are conflated

The established model distinguishes `validUntil` from optional `inventoryHeldUntil`. The prototype has authoritative offer validity, but its simulated receipt says a supplier “holds” a bay or vehicle even while the same screen says no supplier was contacted. That is contradictory and risks promising inventory that is not reserved.

**Required:** model and display three separate concepts:

- price/terms validity (`validFrom`, `validUntil`);
- inventory state (`not held`, `subject to availability`, or `held until inventoryHeldUntil`);
- transaction result (`simulated`, `authorized`, `confirmed`, `failed`).

Never claim a hold in simulation. Never infer a hold from offer validity. Add expiring, expired, superseded/terms-changed and refresh/requote treatments before freeze.

#### 5. Unsupported persistence is still a visible product promise

The README caveat is correct, but the actual desktop UI says “Resumed 2 days later” and “resumed after 2 days,” while the object model calls the parent persistent. The current backend reports durability unsupported and loses state on restart; browser state is session-scoped.

**Required:** remove all cross-session/device/restart resume copy from the shippable design. If the future-state screen remains in design documentation, watermark it **Future state — requires durable repositories; do not ship**. Production copy must describe only the continuity actually supported in the current session.

#### 6. The happy path is not yet a safe implementation contract

The intentional omission of state matrices, canonical contract additions and the route/migration map is acceptable for model review, but those artifacts are required before engineering changes the live product. A1 requirement confirmation is asserted as preserved but is not actually shown as a complete task-level step. Several prototype controls are illustrative only, and the direct-domain shortcut jumps to the hard-coded four-task workspace instead of demonstrating a one-task Intent.

**Required:** after model approval and before code:

- complete Intent and Booking Task state matrices, including errors and invalidation;
- show/define task-level A1 requirement review and confirmation;
- define canonical orchestration and offer projection additions with domain extensions;
- define route, DTO, fixture/live and stored-state migration/compatibility mapping;
- specify every direct-domain and back-navigation outcome.

### Other gaps and inconsistencies to resolve in the final pass

- “Parking and the flight can proceed” conflicts with the flight remaining proposed/inactive.
- Shared-context provenance is good, but inferred facts and preferences need visible correction, confidence/source and Intent-level override controls. “2 travellers” must not appear as inferred without evidence.
- “No field disclosed” is too broad if an aggregator API receives dates/location in a search request. Distinguish passive public research from external aggregator requests, and say exactly what non-personal query data left the system.
- Partial disclosure needs a consequence state: whether the task can still quote, returns incomplete offers, or remains blocked.
- The prototype needs explicit no-offer, offline/read-only, authorization failure and recovery copy in the deferred state matrix.
- Editable `div` elements, visual toggles and segmented controls are prototype shorthand. Production must use labelled semantic controls, keyboard focus, live-region announcements and correct tab/selection semantics.
- A fixed action bar must not cover disclosure fields, validation messages or the mobile tab bar; account for safe-area insets and keyboard opening.
- Cancellation/revocation copy must not imply already transmitted supplier data can literally be “unshared.” Describe future-use revocation and audit retention precisely.

## Current implementation: preserve vs change

### Preserve

- `PortfolioLayout`, the dark rail, Intent inbox, responsive app bar/bottom tabs, attention-first list ordering and existing ReservEdge tokens.
- The domain registry and schema-driven composer engine as domain capability inputs.
- The existing A1/A2/A3/A4 governance services, payload hashes, approval expiry, supplier envelopes, idempotency, audit and deterministic ranking.
- Current lifecycle semantics: pending/paused, replace/supersede, cancel, history/tombstone and activity.
- The live parking path and its canonical contract/adapters as the first real Booking Task.
- Simulation/live labelling, reduced motion, focus treatment and 1440/1280/410/390/320 responsive evidence practice.

### Change

- Replace `/intents/new` domain-first routing with an objective composer; retain domain shortcuts only as a secondary one-task Intent path.
- Add an Intent-level orchestration view model above current `PurchaseIntent` snapshots.
- Replace ID-prefix routing and the `LiveParkingWorkspace`/`SeedWorkspace` split with one task view-model contract backed by real or fixture adapters.
- Extend buyer-visible offer DTOs. The current `RankedOffer` drops validity, terms, source/class, evidence and normalized dimensions, forcing commercial details to be reconstructed from fixtures.
- Remove all customer-facing numeric scores.
- Add Intent/Plan/Booking Task/Cost Ledger surfaces and task-specific A1/A2/A3/A4 routes or panels.
- Keep `sessionStorage` as a cache only; it must not be represented as durable truth.

### Mobile implementation constraint

`apps/mobile` is only a placeholder and explicitly says no React Native/Expo/native toolchain has been selected. “Both web and mobile” can safely mean:

1. implement and verify the responsive web experience at 320, 390 and 410 widths now; and
2. implement a native client only after the repository contains an approved mobile stack/ADR.

Cursor must not silently choose Expo, React Native or another native stack. If the placeholder remains unchanged, it should produce an implementation-ready native parity plan and shared contract boundaries, then stop native scaffolding pending Product Owner approval.

## B. Freeze recommendation

**Do not freeze the complete UI/flow in its current form.** Freeze the visual language and approve the Intent-first conversational/structured spine. Apply the six final edits above, approve the deferred state matrices/contracts/migration map, then freeze. This is a contained finalisation pass, not another redesign cycle.

## C. Concise final edits before freeze

1. Rename the parent and all public navigation from Booking to Intent; keep Booking as a child transaction outcome.
2. Add the Intent Cost Ledger and a combined multi-domain recommendations state on web and mobile.
3. Remove/rescope all two-day/cross-session persistence claims.
4. Separate offer validity, inventory hold and transaction/confirmation state; remove false simulated hold copy and add expiry/refresh states.
5. Add the missing task-level A1 review plus correction/override and partial-disclosure consequences.
6. Complete and approve the deferred state matrices, canonical contract additions and route/data migration map before implementation.

## D. Cursor implementation prompt

Use the prompt below only after the six freeze edits are accepted. It deliberately begins with a definition/compatibility gate because the current worktree is a large uncommitted integration cut and the mobile directory has no selected native stack.

---

You are implementing the approved ReservEdge Intent-first product model across the existing web application and its mobile experience. Work in the current repository; do not generate a replacement application.

### Outcome

Evolve ReservEdge from a domain-first booking UI into:

`Intent → Conversation + Plan → Booking Tasks → task-scoped PurchaseIntents/Offers/Authorizations/Bookings → Cost Ledger`

The user begins with an objective. ReservEdge proposes and coordinates relevant domain tasks. Each task keeps its own governed requirement, disclosure, offers, selection and transaction authorization. Domain selection remains available only underneath an Intent or as a secondary shortcut that creates a one-task Intent.

### Non-negotiable first step: inspect and report before editing

1. Read repository instructions and inspect `git status`, current branch, latest commit and the complete uncommitted delta. Preserve all existing user changes. Do not reset, overwrite or normalize unrelated work.
2. Read the source-of-truth register and its three normative documents in their declared priority order.
3. Read the current ReservEdge design reference, conflicts, web/mobile specifications and the approved Intent-first handoff/review.
4. Inspect, at minimum:
   - `apps/web/src/App.tsx`;
   - `components/AppShell.tsx`;
   - `screens/DomainPicker.tsx`, `Composer.tsx`, `LiveParkingWorkspace.tsx`, `SeedWorkspace.tsx`;
   - `reservedge/registry.ts`, `composer-engine.ts`, `competition-offers.tsx`, `inbox.ts`, `portfolio.tsx`;
   - `api/types.ts`, API client and OpenAPI schema;
   - `session/memory.ts`;
   - relevant packages under `packages/contracts`, `packages/domain`, `packages/application`, `packages/ranking`;
   - API intake, portfolio and composition code;
   - all focused UI, API, privacy, lifecycle and adversarial tests;
   - current visual evidence at desktop and 320/390/410 mobile widths;
   - `apps/mobile/README.md` and any mobile ADR/toolchain that may have been added.
5. Produce a concise implementation map: current component/contract → keep/adapt/replace; identify overlap with uncommitted files; list risks. Do not begin feature edits until this map is internally consistent.

### Definition gate before implementation

Create or update reviewable engineering-definition artifacts for Product Owner approval before broad code changes:

- Intent state matrix;
- Booking Task state matrix, including A1/A2/A3/A4, invalidation, expiry, supersession, no-offer, supplier timeout, offline/read-only and authorization failure;
- canonical orchestration contract additions plus domain-extension boundary;
- buyer-visible Offer projection additions;
- route/DTO/fixture/live/stored-state migration and compatibility map;
- mobile implementation decision if `apps/mobile` is still a placeholder.

Do not overwrite registered normative documents without the repository’s formal change-control process. Put proposals in the appropriate design/ADR/work-order location.

### Canonical model

Implement a buyer-owned `OrchestrationIntent` or `ObjectiveIntent` as the parent aggregate while keeping **Intent** as the public product term. Do not call the parent a Booking.

It must expose or support:

- Intent id, objective/title, status and timestamps;
- conversation events and a concise structured summary;
- shared context facts with value, provenance, confidence, source reference and correction/override state;
- structured preferences with evidence/source and Intent-level overrides;
- a Plan containing Booking Tasks and task dependencies;
- task-specific versioned Requirements and existing PurchaseIntent governance;
- Intent-level activity/audit;
- deterministic Cost Ledger entries.

Each Booking Task owns its domain id/schema, requirement versions, task status, dependencies, disclosure approvals, offer set, recommendation, user selection, authorization and resulting booking. Never send the parent Intent, complete conversation, whole plan or unrelated tasks to a supplier.

Use a canonical orchestration envelope for shared lifecycle concepts and domain-specific extensions for parking, rental and future domains. Do not create a lowest-common-denominator universal booking schema.

### Persistence truth

The current backend is non-durable. Architect repository ports and IDs so durable storage can be added later, but do not claim resume across sessions, devices or backend restarts. No “resumed after two days” production copy. `sessionStorage` may cache a view, never serve as authoritative persistence.

If a future-state persistence design remains in docs or fixtures, label it clearly: “Future state — requires durable repositories; do not ship.”

### Web UX

1. `/intents/new` opens the objective composer. Preserve the current ReservEdge shell, tokens and accessibility foundation.
2. Secondary domain shortcuts create a one-task Intent and enter the same governed flow. Preserve legacy direct-domain URLs with a compatibility redirect/adapter; do not break bookmarks unnecessarily.
3. Desktop Intent workspace shows Conversation and Plan together where width permits. Structured decisions never exist only in transcript prose.
4. Plan task cards cover proposed, missing details, requirement review, public research, disclosure required, researching, offers ready/expiring, selected, authorization required, authorized/confirmed, expired, failed, paused and cancelled states.
5. Add an Intent-level combined recommendations state. Each ready task shows its recommended offer, source/class, price, validity and fit, with independent Compare/Review/Authorize actions.
6. Add a deterministic Cost Ledger. Separate confirmed, selected-not-authorized, estimated, expired/excluded, deposits/holds, taxes/fees and payable-now/later. Do not use LLM arithmetic. Do not silently sum currencies; show separate totals or evidenced FX conversion with rate source and timestamp.

### Mobile UX

Implement responsive web parity at 320, 390 and 410 CSS pixels:

- Plan and Conversation become accessible tabs/segmented controls; Plan opens first when a decision needs attention.
- Use fixed bottom action areas only where appropriate; support safe-area insets, visible validation, scrolling above the action area and the on-screen keyboard.
- Stack offer details, keep at least 44×44 CSS pixel touch targets, wrap long IDs/datetimes and preserve reduced motion.
- Keep A2/A3/A4 consequences adjacent to their actions.

If an approved native toolchain already exists, implement the same model using shared contracts/view models without duplicating governance logic. If `apps/mobile` remains a placeholder, do not choose or scaffold a native stack. Deliver a native parity/architecture proposal and flag the Product Owner decision required.

### Conversation, Plan and preferences

- Conversation is intake, clarification, modification and continuity—not the authoritative decision record.
- Batch a maximum of three high-impact clarification questions per round, not necessarily per entire Intent.
- Every material answer updates an inspectable proposed structured fact/requirement version.
- Show provenance (`you said`, `inferred`, `confirmed`), allow correction, and never present an inference as fact without evidence.
- Preferences may shape ranking but must not be disclosed to suppliers unless independently required and explicitly approved for that task.
- Proposed tasks remain inactive until accepted; declining is free and does not disturb unrelated tasks.

### Governance and privacy

Preserve the existing semantic separation:

- A1: confirm the exact task requirement/version;
- A2: approve exact fields, purposes, recipients, payload version/hash and expiry;
- A3: select/review an eligible exact offer; no reservation or charge;
- A4: authorize exact supplier, action, amount, currency, offer/version, terms hash and validity.

Material changes invalidate only affected approvals/offers. Support partial disclosure only when its consequence is explicit. Preserve per-supplier envelopes, opaque scoped identifiers, no competitor leakage, minimum disclosure, purpose limitation, idempotency and audit. Do not imply that previously transmitted data is literally “unshared”; distinguish revocation of future use from audit retention.

Clarify public research semantics. If an external aggregator request transmits dates/location or other task data, record and explain that query rather than saying “no field disclosed.” Keep personal/preferences data out unless the appropriate approval exists.

### Offers, validity and curated/private supply

Extend the authoritative buyer projection/API so the UI never reconstructs commercial facts from supplier-token fixtures. Carry:

- `sourceType`: aggregator rate, public market reference, supplier private quote;
- `offerClass`: standard or curated;
- audience/visibility scope and channel/provenance;
- supplier/aggregator display identity and opaque identifiers;
- issued time, `validFrom`, `validUntil`, version, supersession/withdrawal and terms hash;
- normalized price breakdown, taxes/fees, deposits, pay-later amounts;
- normalized domain dimensions, restrictions, completeness, evidence and provenance;
- simulation/live status;
- optional `inventoryHeldUntil` only when authoritative.

Display absolute and calm relative validity. Never use a ticking countdown or manufactured urgency. A curated quote is not automatically recommended. Preserve deterministic eligibility/ranking and user override. Remove every customer-facing numeric score.

Treat validity, inventory and transaction status independently:

- validity: valid, expiring, expired, superseded/terms changed;
- inventory: not held/subject to availability/held until an authoritative time;
- transaction: simulated, authorized, confirmed, failed/cancelled.

Expired or superseded offers cannot be selected or authorized. Refresh/requote creates a new authoritative version, shows material changes, and requires fresh selection/authorization. Never claim an inventory hold in simulation.

### Unify current implementations

Replace `startsWith("pi_")` routing and the `LiveParkingWorkspace`/`SeedWorkspace` product split with one Intent/Task view-model contract. Real parking and simulated rental/entertainment may use different adapters, but they must render through the same components and state semantics. Keep fixtures explicitly labelled and out of production commercial truth.

Preserve existing `pi_*` parking snapshots and routes through adapters or compatibility mappings. Do not rename public ReservEdge branding or existing `itaa_*` internal namespaces in this work.

### Accessibility and responsive requirements

- Use semantic inputs, labels, buttons, headings, lists/tables and tab roles; no production contenteditable placeholder controls.
- Full keyboard operation and logical focus restoration after route/state changes and modal/sheet close.
- Visible focus, screen-reader names/states, live announcements for progress/errors/expiry, and no colour-only status.
- WCAG AA contrast, 200% zoom without loss, no document-level horizontal overflow at target widths.
- Respect `prefers-reduced-motion`; progress must remain understandable without animation.

### Tests and verification

Preserve existing tests and add:

- unit tests for Intent/Plan/Task/Ledger view models and deterministic ledger arithmetic;
- contract/schema tests for orchestration and Offer projection additions;
- migration/compatibility tests for existing `pi_*` and legacy routes;
- governance/adversarial tests proving no cross-task disclosure, competitor leakage, blanket approval or stale authorization;
- validity tests for timezone display, expiring/expired/superseded offers, refresh/version changes and no false inventory holds;
- selected-vs-recommended tests proving A3/A4/receipt always bind the user-selected offer;
- fixture/live parity tests through one workspace contract;
- accessibility tests for labels, tabs, focus, live regions and action bars;
- responsive/visual evidence at 1440×940, 1280×800, 410×874, 390×844 and 320px, plus 200% zoom and reduced motion;
- mobile keyboard/safe-area checks;
- API, privacy, lifecycle, ranking and idempotency regression suites.

Report exact commands and pass counts. Do not update snapshots blindly; explain intentional visual changes.

### Acceptance criteria

1. A user can begin with “I’m planning a five-day trip to New York” without selecting a domain.
2. One Intent contains a Conversation, structured Plan, at least parking and rental Booking Tasks, and a Cost Ledger.
3. Domain shortcuts are secondary and create a one-task Intent.
4. Proposed tasks require acceptance; task changes do not invalidate unrelated tasks.
5. A1/A2/A3/A4 remain distinct and inspectable per task.
6. No supplier receives the full Intent, unrelated task data, competitor offers, preference history or a stable buyer identifier.
7. Two ready task recommendations can be viewed together, but selection/authorization remains independent.
8. All offer cards/reviews/authorization surfaces use authoritative validity/source/version/terms; no hard-coded supplier catalog reconstruction.
9. Expired/superseded offers are ineligible and requotes require fresh review.
10. Validity is never presented as an inventory hold; simulation never claims inventory or money movement.
11. Numeric ranking scores are absent from customer-facing UI.
12. Ledger totals are deterministic, status-aware and currency-honest.
13. No production copy promises cross-session/device/restart resume while durability is unsupported.
14. Existing parking functionality, privacy semantics, lifecycle, simulation honesty, tokens, accessibility and tests continue to pass.
15. Responsive web passes at desktop and 320/390/410 widths. Native implementation occurs only with an approved repository toolchain.

### Out of scope

- durable database/repository implementation and cross-device persistence;
- supplier-side portal/marketplace implementation;
- new real supplier or aggregator integrations;
- merchant-of-record, unified payment/checkout, settlement, refunds or PCI expansion;
- production enablement of hotel/flight/rental/entertainment connectors beyond approved fixtures/adapters;
- ranking-policy/economic changes unrelated to removing numeric UI scores and carrying authoritative offer fields;
- broad `ITAA` internal namespace migration;
- visual rebrand or replacement of approved ReservEdge tokens;
- automatic permanent preference learning without evidence and user control.

### Delivery discipline

Implement in small reviewable phases: definitions/contracts → compatibility adapters → parent Intent/view models → objective composer/Plan → task governance → offers/validity → Cost Ledger → responsive/mobile → tests/evidence. After each phase, run focused tests and report remaining risks. Do not claim the work complete while freeze blockers, migration ambiguity or native-toolchain approval remain unresolved.

---
