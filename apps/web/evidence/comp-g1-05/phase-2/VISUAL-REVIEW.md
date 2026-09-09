# COMP-G1-05 Phase 2 visual review

Domain picker and bounded composer. Ranking/Offers restyle remains Phase 4. G1-04 lifecycle backend is unchanged.

Side-by-side board: `compare.html` in this folder.

## Measured comparison (implementation picker)

| Item | Spec | 1440×940 | 1280×800 | 410×874 | 390×844 | 320 |
| --- | --- | --- | --- | --- | --- | --- |
| Outer / body | `#E9E6DF` | `rgb(233,230,223)` | same | same | same | same |
| App canvas | `#F6F3EE` | `rgb(246,243,238)` | same | same | same | same |
| Type | Schibsted Grotesk | yes | yes | yes | yes | yes |
| Domain cards | 3 | 3 | 3 | 3 | 3 | 3 |
| Card radius | 18px (picker) | 18px | 18px | 18px | 18px | 18px |
| Overflow-x | 0 | 0 | 0 | 0 | 0 | 0 |
| “Spa is next” | Product Owner: remove | absent | absent | absent | absent | absent |
| Parking flag | Live competition path | yes | yes | yes | yes | yes |
| Rc / En flag | Simulated demonstration | yes | yes | yes | yes | yes |

## Screenshots

- `picker-*.png` at required viewports
- `composer-parking-step1-1440x940.png` — one-line intake, JFK example, live path chip, requirement card 0/8
- `composer-rental-q1-1440x940.png` — Question 1 of 3, skip allowed, simulated demonstration chip
- `composer-rental-requirement-1440x940.png` — Question 2 of 3 after first answer; requirement 2/4
- `composer-ents-step1-1440x940.png`
- `composer-mobile-410x874.png`
- `picker-1440x940-focus.png`, `picker-1440x940-reduced-motion.png`

## Findings

### High

None for picker/composer chrome.

### Medium

1. Parking requirement card lists eight canonical intake fields (airport, start, end, vehicle, covered, shuttle, currency, accessibility) rather than the HTML’s four compact rows. This is the competition mapper, not a visual regression of ranking.
2. Confirming a parking intent still navigates to the legacy `pi_*` `IntentWorkspace` (A1–A4 copy). Portfolio restyle of that path is Phase 3.
3. Offers yellow banner was reduced to an inline `Simulated demonstration` line on Rc/En seed workspaces only. Parking Offers keep SIM chip + toggle. Authorization dialog banner is unchanged (Phase 4).

### Low

1. “Use the example” on parking embeds the full JFK paragraph in the chip, so the step-1 card is tall.
2. Mobile picker stacks three domain cards; Entertainment sits below the fold at 410×874, matching HTML density.

## Prohibited customer copy (Phase 2 surfaces)

Scanned picker, composer, registry: no Gate 1, A1–A4, WP numbers, process-memory, or giant simulation banner. “Spa is next” is absent.
