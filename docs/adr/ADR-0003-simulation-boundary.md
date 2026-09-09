# ADR-0003 — Simulation boundary

- Status: Accepted
- Date: 2026-08-15
- Decision owners: Product Owner; recorded from the approved Product + Technical Specification and Engineering Kickoff Pack

## Context

The MVP must prove governed intent, disclosure, isolated supplier competition, ranking, dual approval, and authorization without executing real purchases. Presenting simulated supplier or payment behavior as a live reservation or charge would violate product principles and competition honesty.

## Decision

- MVP supplier agents and transaction authorization are simulated.
- No real card charge, supplier reservation, or booking is allowed in the MVP.
- Simulation state must be explicit in contracts, UI, tests, logs, receipts, and demos. The approved UI copy includes `SIMULATED - NO REAL CHARGES OR RESERVATIONS`.
- Non-SIMULATED authorization modes are rejected by the MVP profile when those contracts exist (WP-02 and later).
- Moving to real supplier integrations or real payments requires a later approved ADR plus security and operational review. This ADR does not authorize that move.

## Consequences

- Demo scripts, receipts, and later UI must label simulated actions as simulated.
- Supplier simulator code belongs under `apps/supplier-simulator` and `adapters/transaction-sim`, not in domain packages.
- Tests must fail if a simulated capability is named or presented as a real purchase or reservation.
