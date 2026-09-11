# ADR-0006 — Intent-first orchestration and conversation/authority boundary

- Status: Accepted
- Date: 2026-09-01
- Decision owners: Product Owner
- Approved: 1 September 2026 — Product Owner approved the revision-2 v1.1 candidates for normative replacement. `G0-CHANGE-CONTROL` is satisfied. COMP-G1-06 remains unactivated.

## Context

The registered v1.0 normative documents describe ITAA as an airport-parking Intent Inbox that is “not primarily a chatbot,” treat PurchaseIntent as the root commercial object, and retain an older cool-slate visual specification. COMP-G1-05 delivered the ReservEdge shell and parking-first live path. On 31 August 2026 the Product Owner accepted `docs/design/proposals/intent-first-2026-08-31/DEFINITION_GATE.md` as the Intent-first product model.

That freeze conflicted with the v1.0 registered DOCX files. On 1 September 2026 the Product Owner approved the revision-2 v1.1 replacements. This ADR records the architectural decisions those registered documents now encode. It does not reopen `DEFINITION_GATE.md`, activate COMP-G1-06, or authorize product-code changes.

Related accepted ADRs remain in force: ADR-0002 (cloud-neutral core), ADR-0003 (simulation honesty), ADR-0004 (canonical governance bindings). ADR-0005 remains Proposed for ranking package ownership; this ADR does not change ranking economics or locked vectors.

## Decision

### Intent-first orchestration

- Public product name is **ReservEdge**. Internal program name and `itaa_*` namespaces remain unchanged unless a later migration is approved.
- The parent objective container is **Intent** (internal `OrchestrationIntent` / `ObjectiveIntent`). PurchaseIntent remains the minimized supplier-facing contract of a Booking Task.
- Hierarchy:

  `Intent → Conversation + Plan → Booking Tasks → Requirements/PurchaseIntents → Offers/Recommendations → Selection → Authorization → confirmed Booking → Cost Ledger`

- A Booking exists only after authoritative supplier/connector confirmation. A4 is authorization to attempt the exact transaction, not a Booking.

### Conversation versus structured authority

- Conversation is the primary intake, clarification, modification, and continuity surface.
- Conversation is not the authoritative decision record.
- Plan, Booking Tasks, Requirements, disclosures, offers, approvals, authorizations, bookings, Cost Ledger, and audit records remain structured and authoritative.
- Decisions must never be buried only in transcript text.
- This supersedes the v1.0 “not primarily a chatbot / chat window” conflict without turning the product into an unstructured chat agent.

### Multi-domain architecture, parking-first implementation

- Product architecture is multi-domain. Domain selection sits beneath the Intent and is not a mandatory front door.
- Current real implementation remains airport-parking-first.
- Rental and entertainment remain explicitly simulated/design-fixture capabilities until separately approved.
- Hotel, flight, and other domains are architecture/roadmap scope, not current production capability.
- Do not create a lowest-common-denominator universal booking schema. Use a canonical orchestration contract with domain-specific extensions.

### Privacy and transaction boundaries

- Preferences and preference history remain private. They may influence local filtering and deterministic ranking. They never enter aggregator queries, A2 envelopes, supplier payloads, or later/separate A2 approvals.
- Supplier-required constraints must become explicit task Requirements confirmed at A1.
- Preserve minimum disclosure, per-supplier envelopes, scoped opaque identifiers, purpose limitation, and no competitor leakage.
- A1 confirms the exact task Requirement/version. A2 approves exact requirement-field/purpose/recipient/hash/expiry disclosure. A3 records selected-offer review/acceptance. A4 authorizes ReservEdge to attempt the exact transaction.
- Simulation: `a4_required → authorized_simulated` (terminal). Live/future: `a4_required → authorized_live → booking_pending → confirmed_booking | booking_failed`.
- Offer validity, inventory hold, authorization, and confirmation are separate. `validUntil` never implies `inventoryHeldUntil`. Simulation never claims inventory, payment, supplier contact, or a Booking.
- `scoreMicros` remains internal to ranking/audit/tests and is excluded from buyer-facing Offer projections.
- Cost Ledger arithmetic is deterministic. No LLM totals. Mixed currencies stay separate unless rate, source, and timestamp are evidenced.
- Current backend durability is unsupported. Browser session storage is cache, not authority. Responsive web is the approved mobile surface. No native-mobile framework is selected in this change.

### Relationship to `DEFINITION_GATE.md`

`DEFINITION_GATE.md` is the accepted freeze contract. This ADR and the registered v1.1 DOCX files implement that freeze as formal change control. They do not amend or reopen the freeze. Where a registered DOCX and the freeze could be read to differ, the freeze wins until Product Owner directs otherwise.

### Visual identity

The approved public visual identity is ReservEdge: warm cream/canvas surfaces, coral accent, dark rail, Schibsted Grotesk, JetBrains Mono, responsive shell, accessibility, and reduced-motion behavior. Reconciling presentation does not alter privacy, governance, ranking, or simulation semantics.

## Consequences

- The v1.1 registered DOCX files are now the source-of-truth specifications. Destination filenames remain `ITAA_*.docx`.
- `G0-CHANGE-CONTROL` is satisfied. COMP-G1-06 remains blocked on `G0-LEASES` and explicit `G0-ACTIVATE`.
- Buyer Offer projection must drop `scoreMicros` in a later contracts change; internal ranker vectors stay locked.
- `apps/mobile` remains a placeholder. Native toolchain selection requires a later ADR.
- Durable repositories and cross-session resume remain out of scope while `/readyz` reports durability unsupported.

## Traceability

| Artifact                                                                    | Role                                       |
| --------------------------------------------------------------------------- | ------------------------------------------ |
| `docs/design/proposals/intent-first-2026-08-31/DEFINITION_GATE.md`          | Accepted freeze; not reopened              |
| `docs/design/proposals/intent-first-2026-08-31/NORMATIVE_CHANGE_CONTROL.md` | Approved and registered replacement record |
| `docs/source-of-truth/ITAA_*.docx` (v1.1, 1 September 2026)                 | Registered replacements                    |
| `docs/work-orders/ITAA_Cursor_Work_Order_COMP-G1-06.md`                     | Issued work order; still activation-gated  |
