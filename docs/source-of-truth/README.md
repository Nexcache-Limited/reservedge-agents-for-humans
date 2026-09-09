# Source of truth

These files are the approved product and engineering specifications for ITAA v1. They are product data. Cursor work orders implement bounded slices; they do not replace these documents.

## Normative priority

1. `ITAA_v1_Product_and_Technical_Specification.docx`
2. `ITAA_Unified_UI_UX_Design_Specification.docx`
3. `ITAA_Engineering_Kickoff_Pack.docx`
4. The active Cursor work order's implementation choices

If documents conflict, a higher document wins. Internal Cursor work orders are execution records, not a higher-priority specification, and are omitted from this public export.

Design-source HTML exports, screenshots, and Python generators are references. They are not substitutes for the approved `.docx` outputs in this directory.

## Document register

| File | Title | Version / date | SHA-256 |
|---|---|---|---|
| `ITAA_v1_Product_and_Technical_Specification.docx` | ReservEdge / ITAA v1 Product + Technical Specification | Version 1.1, 1 September 2026 | `4fd24641963a19f93fdead7aab3fc38ee5c6a891c5cc31d3246570da21d59900` |
| `ITAA_Engineering_Kickoff_Pack.docx` | ReservEdge / ITAA Engineering Kickoff Pack | Version 1.1, 1 September 2026 | `611c8f87925a81771870cc0eb1a57a56556845f96d49b828d2109fe1fbef13d4` |
| `ITAA_Unified_UI_UX_Design_Specification.docx` | ReservEdge Unified UI/UX Design Specification | Version 1.1, 1 September 2026 | `aeba64e717eb07446a90e95b1f47b633c143000d7138d4abcee0aeee7e955e7f` |

Product Owner approved these revision-2 candidates for normative replacement on 1 September 2026. Registered destination filenames remain `ITAA_*.docx`. Traceability: [ADR-0006](../adr/ADR-0006-intent-first-orchestration.md) (Accepted) and [NORMATIVE_CHANGE_CONTROL.md](../design/proposals/intent-first-2026-08-31/NORMATIVE_CHANGE_CONTROL.md) (local review-candidate paths omitted). Previous v1.0 checksums are superseded and must not be restored without a later Product Owner replacement approval.

## Replacing a normative document

1. Product Owner approves the replacement and its version identifier.
2. Replace only the named file in this directory. Do not edit `.docx` content from the repository as a shortcut.
3. Recalculate SHA-256 and update this README and the checksum test.
4. Add or update an ADR / change-log reference describing why the document changed.
5. Do not treat generators, design-tool exports, or chat transcripts as the new source of truth.
