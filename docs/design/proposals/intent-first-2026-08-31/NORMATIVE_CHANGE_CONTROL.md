# G0-CHANGE-CONTROL — Intent-first normative replacement

**Status:** Approved and registered  
**Product Owner approval date:** 1 September 2026  
**Version:** 1.1, revision 2  
**Baseline:** branch `work/comp-g1-05-reservedge-ui`, SHA `85c24d09d3aa18dda95ca6031e5623b4baaa217c`  
**Freeze:** `docs/design/proposals/intent-first-2026-08-31/DEFINITION_GATE.md` (accepted 31 August 2026; **unchanged**)  
**ADR:** [ADR-0006](../../adr/ADR-0006-intent-first-orchestration.md) — **Accepted** 1 September 2026  
**Registration commit SHA:** `7d646abab1a925fd5386ccaee346c60857c13c37`

`G0-CHANGE-CONTROL` is **satisfied**. The revision-2 v1.1 candidates are the registered source-of-truth documents. `DEFINITION_GATE.md` remains frozen. COMP-G1-06 remains **unactivated**. Remaining gates: `G0-LEASES` and explicit `G0-ACTIVATE`.

Registered destinations and exact hashes:

| Registered path | SHA-256 |
| --- | --- |
| `docs/source-of-truth/ITAA_v1_Product_and_Technical_Specification.docx` | `4fd24641963a19f93fdead7aab3fc38ee5c6a891c5cc31d3246570da21d59900` |
| `docs/source-of-truth/ITAA_Unified_UI_UX_Design_Specification.docx` | `aeba64e717eb07446a90e95b1f47b633c143000d7138d4abcee0aeee7e955e7f` |
| `docs/source-of-truth/ITAA_Engineering_Kickoff_Pack.docx` | `611c8f87925a81771870cc0eb1a57a56556845f96d49b828d2109fe1fbef13d4` |

Normative authority is now:

1. registered Product + Technical Specification v1.1  
2. registered Unified UI/UX Design Specification v1.1  
3. registered Engineering Kickoff Pack v1.1  
4. this change-control record (Approved and registered)  
5. accepted `DEFINITION_GATE.md`  
6. issued COMP-G1-06 work order (still activation-gated)

## Product Owner dispositions encoded (revision 2)

The Intent-first product model remains accepted and frozen. The six first-pass judgment items are now closed as follows:

1. **Filenames.** Registered destination filenames remain `ITAA_*.docx`. ReservEdge is the public product name; ITAA and `itaa_*` remain internal program/namespace names.
2. **G3 / RevenueCat / store / sharing.** Remain only as clearly deferred productization. They are not current implementation requirements or claims.
3. **Work Order 001.** Kept verbatim with its existing supersession note.
4. **Buyer `scoreMicros`.** Removal remains a MUST to be implemented later under COMP-G1-06. Contracts are unchanged now.
5. **G0 SUCCESS.** Revised delivered-slice description kept; original 17 August wording preserved only as dated historical context.
6. **Sharing screen.** Kept as future G3 UX. Public term is “Share to ReservEdge”. “Share-to-ITAA” appears only as an explicitly identified historical/internal contract label.

## Candidate registration table (revision 2)

| Candidate filename | Version / date | SHA-256 | Source path | Intended registered destination | Sections changed in revision 2 | Reason |
| --- | --- | --- | --- | --- | --- | --- |
| `ITAA_v1_Product_and_Technical_Specification_v1.1.docx` | Version 1.1, 1 September 2026, rev. 2 | `4fd24641963a19f93fdead7aab3fc38ee5c6a891c5cc31d3246570da21d59900` | `[local-path]/Documents/Reservedge-ITAA project/review-candidates/intent-first-v1.1-2026-09-01/ITAA_v1_Product_and_Technical_Specification_v1.1.docx` | `docs/source-of-truth/ITAA_v1_Product_and_Technical_Specification.docx` | JTBD share bullet; FR-002; §12.3; success table R3/R6; golden-path receive; Share Confirmation CTA; Free/Pro offering names; G3/NFR/delivery tables 30–32 incl. Sep store rows; ADR-010; document-control amendment row | Quarantine G3/native as non-acceptance; public ReservEdge terminology; filenames stay `ITAA_*.docx` |
| `ITAA_Unified_UI_UX_Design_Specification_v1.1.docx` | Version 1.1, 1 September 2026, rev. 2 | `aeba64e717eb07446a90e95b1f47b633c143000d7138d4abcee0aeee7e955e7f` | `[local-path]/Documents/Reservedge-ITAA project/review-candidates/intent-first-v1.1-2026-09-01/ITAA_Unified_UI_UX_Design_Specification_v1.1.docx` | `docs/source-of-truth/ITAA_Unified_UI_UX_Design_Specification.docx` | Document map; §3.1–3.3 + TABLE 9; UX-02/03/05/13–16 copy; **new §5.18–5.31 UX-17–UX-29**; **new §6.5**; §6.2 compact/touch; §9.1–9.2; §12.1/12.5; §14 banner; C-20 split + C-25–27; VMs; API map; capability/AC/delivery tables; public ReservEdge copy | Complete Intent-first UI contracts; separate Plan vs subscription; never-A2 preferences; validity/inventory/transaction split; responsive web is current mobile |
| `ITAA_Engineering_Kickoff_Pack_v1.1.docx` | Version 1.1, 1 September 2026, rev. 2 | `611c8f87925a81771870cc0eb1a57a56556845f96d49b828d2109fe1fbef13d4` | `[local-path]/Documents/Reservedge-ITAA project/review-candidates/intent-first-v1.1-2026-09-01/ITAA_Engineering_Kickoff_Pack_v1.1.docx` | `docs/source-of-truth/ITAA_Engineering_Kickoff_Pack.docx` | G0 SUCCESS historical 17 August note; G3 Mobile / WP-13 public Share-to-ReservEdge wording | Preserve WO-001 verbatim; add dated G0 historical context only |

Superseded revision-1 hashes (not this candidate): Product `0d54753a…15fb13`, UI `d5a7b2a4…d7b498`, Kickoff `9095a9dd…825d82b2`.

v1.0 checksums are superseded by the registered table above. Do not restore them without a later Product Owner replacement approval.

## Revision 2 — section-by-section corrections

### A. Complete the Intent-first UI architecture

Normative screen contracts, not introductory prose only:

| ID | Surface | Route / nesting |
| --- | --- | --- |
| UX-17 | Objective-first Intent composer; no mandatory domain | `/intents/new` |
| UX-18 | Domain shortcut → one-task Intent | `/intents/new/:domainId` → nested A1 |
| UX-19 | Intent workspace: Conversation + Plan | `/intents/:intentId`, `/intents/:intentId/plan` |
| UX-20 | Booking Task summary under Plan | `/intents/:intentId/tasks/:taskId` |
| UX-21 | Task A1 requirement confirmation | `.../a1` (adapts UX-03) |
| UX-22 | Task A2 disclosure approval | `.../a2` (adapts UX-05) |
| UX-23 | Task offers | `.../offers` (adapts UX-07/08) |
| UX-24 | Task A3 selected-offer review | `.../a3` (adapts UX-09) |
| UX-25 | Task A4 authorization; **not a Booking** | `.../a4` (adapts UX-10) |
| UX-26 | Task confirmation/result | `.../confirmation` |
| UX-27 | Combined recommendations when ≥2 tasks offer-ready | Intent Plan |
| UX-28 | Deterministic Intent-level Cost Ledger | desktop + compact Plan/Ledger |
| UX-29 | Compatibility-wrapped `pi_*` one-task Intents | `/intents/pi_*` wrap + nested task routes |

Existing UX-03–UX-11 remain the task-scoped parking screens and MUST nest under an Intent/Task. Desktop and compact 320/390/410 access Conversation, Plan, Tasks, combined recommendations, and Cost Ledger.

§3.3 and TABLE 9 now use the frozen hierarchy:

`Intent → Conversation + Plan → Booking Tasks → Requirements/PurchaseIntents → Offers/Recommendations → Selection → Authorization → confirmed Booking → Cost Ledger`

Task sequence shows A1, A2, Offers, A3, A4 distinctly. A4 does not create a Booking.

Supporting contracts: C-20 (Intent Plan), C-26 CostLedger, C-27 CombinedRecommendations; IntentWorkspaceVM, BookingTaskVM, BuyerOfferVM, CostLedgerVM; API map rows UX-17–28.

### B. Correct the component contract

- **C-20 PlanCard** is now the Intent Plan / Booking Task orchestration Plan (not Free/Pro).
- **C-25 EntitlementPlanCard** is the separately named subscription/entitlement card, labelled **FUTURE PRODUCTIZATION only**.

### C. Encode the frozen privacy rule in the UI specification

New **§6.5 Preferences are never disclosure candidates**: preferences and preference history influence only buyer-local filtering and deterministic ranking; they are never A2 candidates; they never enter aggregator queries, disclosure envelopes, supplier payloads, or later/separate A2 approvals. The UI MUST NOT describe preferences as “withheld” in a way that implies elective disclosure. Supplier-needed constraints become explicit A1 Requirements.

Also updated: privacy-shield copy, UX-05/13/14, TABLE 17 acceptance, TABLE 29 withheld group, C-07/C-19, DisclosurePreviewVM, PreferenceVM, UX-AC-04.

### D. Separate validity, inventory, authorization, and confirmation

Buyer Offer and task view models now distinguish:

- validity: `valid` / `expiring` / `expired` / `superseded`
- inventory: `not_held` / `subject_to_availability` / `held_until` (simulation always `not_held`)
- transaction result: simulated / authorized / pending / confirmed / failed

`validUntil` never implies `inventoryHeldUntil`. Expired or superseded offers cannot proceed to A3/A4. Updated C-11, C-14, DecisionVM, OfferComparisonVM, AuthorizationVM, ReceiptVM, UX-23–26, UX-AC-07/11.

### E. Remove current native-mobile implementation instructions

Reconciled with the freeze:

- `apps/mobile` remains a placeholder
- responsive web at 320 / 390 / 410 CSS pixels is the approved mobile surface
- no native framework, shell, share extension, store client, or RevenueCat client is selected for current work

Corrected: §3.1 (compact responsive-web navigation), §6.2 compact/touch (not native-app) gesture, §9.1 compact breakpoints, **§12.1** architectural boundary + TABLE 41, **§12.5** repository placement + TABLE 44, TABLE 36 capability Share/Navigation, TABLE 37 accessibility, §8.6 token mapping, UX-AC-01, G1 deferred-safely row.

### F. Quarantine historical G3 plans

Product success “public mobile app” is no longer a current acceptance criterion. TABLE 30 G3, TABLE 31 Sep native/RevenueCat/store rows, TABLE 32 Shipaton row, FR-002, NFR mobile quality, and ADR-010 carry an explicit supersession: not current ACs; do not authorize native work; current mobile is responsive web; native requires a later Product Owner-approved ADR and work order.

UI §9.2, §14, UX-00/02/15, UI-08, G3 delivery row, TABLE 46 paywall, and store-screenshot bullets sit under **“FUTURE PRODUCTIZATION — no current implementation authority.”**

### G. Public terminology consistently ReservEdge

Buyer-facing copy such as “ITAA recommends”, “your ITAA buyer agent”, “what ITAA knows/does/will research”, and “ITAA explains” is now ReservEdge. ITAA remains for internal namespaces, historical text, registered filenames (`ITAA_*.docx`), ticket IDs, and explicitly labelled internal/historical contract names (Share-to-ITAA, ITAA Pro offering label).

## Prior revision-1 substance retained

Unaffected and still present: cloud-neutral core; Google/AWS adapters; ranking weights/formula; isolation; hash-bound A2; simulation honesty; two gates; qualitative Strong/Good/Fair; ReservEdge visual tokens; persistence honesty; A4 ≠ Booking in product FR-050–053 / kickoff §1.2.1; historical WP-01–WP-04 tickets.

## Rendered-page counts and visual QA

Candidates were amended in place (copy-on-write from revision 1, originally cloned from registered v1.0), exported to PDF **serially through Microsoft Word** (one file, close, next), identity-checked, and rendered page-by-page at 1.4×.

| Document | v1.0 pages | Rev.1 pages | Rev.2 pages | Automated overflow/blank | Visual QA |
| --- | --- | --- | --- | --- | --- |
| Product + Technical Specification | 30 | 33 | **33** | none | Pass. G3/native rows carry supersession. Last BUILD RULE page remains short by design. |
| Unified UI/UX Design Specification | 33 | 35 | **47** | none | Pass. Growth is the new UX-17–UX-29 contracts. TABLE 9 hierarchy box wraps inside the cell (deliberate wrapping; readable). C-20/C-25 split, §6.5, §12.1/12.5, UX-27/28 inspect clean. Final page 47 is the short directive box (same pattern as v1.0). |
| Engineering Kickoff Pack | 21 | 21 | **21** | none | Pass. G0 SUCCESS includes dated 17 August historical wording. WO-001 body unchanged after the existing supersession note. |

PDF title/content identity (first text line):

- Product: `ReservEdge  |  PRODUCT + TECHNICAL SPECIFICATION  |  v1.1`
- UI: `ReservEdge  |  Unified UI/UX Design Specification  |  v1.1`
- Kickoff: `ReservEdge  |  ENGINEERING KICKOFF PACK  |  v1.1`

No cross-export recurrence. Headers/footers show ReservEdge, v1.1, 1 September 2026, sequential page numbers. No unintended blank pages.

Rendered evidence (local, not for repository registration):

`[local-path]/Documents/Reservedge-ITAA project/review-candidates/intent-first-v1.1-2026-09-01/rendered-pages/`

## Contradiction search (revision 2)

Searched extracted DOCX text and exported PDFs:

| Probe | Result |
| --- | --- |
| parent Booking or PurchaseIntent as parent objective | No hits. Hierarchy states PurchaseIntent is not the parent. |
| unsupported resume/persistence | Honesty retained; UX-26 prohibits resume-after-days copy; no durable resume claim. |
| preference disclosure / “withheld” as elective | §6.5 forbids that reading. TABLE 17/29 no longer list preference history as withheld-electable. |
| validity/hold conflation | `validUntil` never implies hold; simulation inventory `not_held`. |
| A4 as Booking | Explicitly not; UX-25 MUST NOT write `confirmed_booking`. |
| buyer `scoreMicros` | Still internal MUST; buyer surfaces forbid it; **no contract/schema change now**. |
| current native-mobile instructions | §12.1/12.5/TABLE 41/44 state placeholder + responsive web. Remaining native/share/store/RevenueCat text is future-productization labelled. |
| missing combined recommendations or Cost Ledger | UX-27 and UX-28 plus C-26/C-27 and VM/API rows. |
| public-facing ITAA terminology | Remaining ITAA is filename/namespace/historical/internal labels, or WO-001 historical body. |

## What this registration did not do

- `DEFINITION_GATE.md` was not modified.
- COMP-G1-06 was not activated. No implementation worktree, lease assignment, or product-code change.
- No push, PR, merge, or deployment.
- No native-mobile implementation.

## Verdict

`G0-CHANGE-CONTROL` is satisfied by Product Owner approval on 1 September 2026 and registration of the revision-2 v1.1 documents.

Remaining gates: `G0-LEASES` and explicit `G0-ACTIVATE`. Wait for Product Owner instruction.
