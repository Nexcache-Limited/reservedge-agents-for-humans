# ADR-0005 — Deterministic ranking and isolated supplier simulation

- Status: Proposed
- Date: 2026-08-20
- Decision owners: Product Owner; recorded from WP-05

## Context

WP-05 must compete three simulated suppliers, validate offers at the buyer boundary,
and rank eligible offers without a model, provider SDK, or shared supplier state.
ADR-0003 already requires explicit simulation. ADR-0004 locked canonical hashing
separators and A2 dispatch as the authorization boundary.

## Decision

- `packages/ranking` owns integer scoring, versioned `airport_parking_v1` weights,
  tie-breakers, fit labels, and explanation facts. It depends only on `itaa-domain`.
- `packages/application` owns the supplier port, isolation-safe collection,
  generated WP-02 Offer parsing, contextual/policy eligibility, WP-03 mapping,
  and hashing of ranking fingerprint material.
- `apps/supplier-simulator` owns the three seeded strategies and may depend inward.
  No core package may import it.
- Supplier invocation requires a successful `DispatchService.authorize()` result
  and receives only that envelope plus injected time/IDs. Denied dispatch never
  invokes a simulator.
- Ranking does not implement a second canonical-JSON library. Application hashes
  ranking `fingerprint_material()` with `itaa.ranking.decision.v1`, which extends
  the ADR-0004 separator lock list. Existing separator digests are unchanged.
- Generated WP-02 models are allowed in application at the Offer boundary only.
  Domain, policy, observability, and ranking remain free of Pydantic/contracts.
- Cloudflare and AWS remain the product infrastructure direction. WP-05 adds no
  Cloudflare, AWS, Google, Vercel, agent, database, HTTP, or telemetry SDK.
- Offers, availability, and collection results remain simulated. WP-05 does not
  reserve, charge, or contact a real supplier.

## Consequences

- Golden ranking tests lock SkyShield `671_000`, ParkDirect `660_000`,
  TerminalFlex `535_000` against the canonical Offer fixtures.
- Simulator economics may emit different prices than those fixtures because of
  billable-day floors; fixtures stay the ranking/contract vectors.
- Preference learning, FastAPI use cases, persistence, and UI remain later
  packages (WP-06 / UI-00).

## Traceability

| Ticket / FR           | Primary modules                  | Primary tests                                                    |
| --------------------- | -------------------------------- | ---------------------------------------------------------------- |
| ITAA-050 / FR-020     | `supplier_port.py`               | `test_wp05_solicitation.py`                                      |
| ITAA-051 / FR-020     | `itaa_supplier_simulator`        | `test_wp05_simulator_guardrails.py`                              |
| ITAA-052 / FR-021     | `solicitation_service.py`        | `test_wp05_solicitation.py`, `test_wp05_simulator_collection.py` |
| ITAA-053 / FR-014     | `offer_boundary.py`              | `test_wp05_offer_boundary.py`                                    |
| ITAA-054 / FR-023–024 | `itaa_ranking`                   | `test_ranking_golden.py`, `test_ranking_rules.py`                |
| ITAA-055 / FR-015/025 | `rank.py`, `ranking_decision.py` | `test_ranking_golden.py`, `test_wp05_privacy.py`                 |
