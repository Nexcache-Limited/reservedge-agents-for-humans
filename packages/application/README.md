# packages/application

Cloud-neutral application use cases and ports.

Rules:

- May depend on `packages/domain`, `packages/policy`, `packages/observability`,
  `packages/ranking`, and the installable generated WP-02 package
  `itaa-contracts-generated` at the Offer validation boundary.
- Must not import `apps/supplier-simulator`, adapters, FastAPI, database clients,
  cloud SDKs, RevenueCat, or UI packages.

## WP-04 services

| Ticket   | Module                   | Responsibility                                            |
| -------- | ------------------------ | --------------------------------------------------------- |
| ITAA-043 | `approval_service.py`    | Issue/validate/revoke A1–A4 via an append-only port       |
| ITAA-041 | `dispatch_service.py`    | Atomic grant/revocation resolve, then envelope evaluation |
| ITAA-044 | `idempotency_service.py` | Atomic reserve/replay; public result is ResultRef         |
| ITAA-045 | `audit_service.py`       | Hash and append domain and governance audit records       |
| Shared   | `governance_ports.py`    | Repository/sink protocols only                            |

## WP-05 services

| Ticket   | Module                    | Responsibility                                                                                |
| -------- | ------------------------- | --------------------------------------------------------------------------------------------- |
| ITAA-050 | `supplier_port.py`        | Closed supplier terminal vocabulary; supplier-originated kinds are OFFER/DECLINED only        |
| ITAA-052 | `solicitation_service.py` | Exactly three isolated channels; WP-04 dispatch required before invoke; buyer-owned terminals |
| ITAA-053 | `offer_boundary.py`       | Generated-contract parse, contextual bind, policy eligibility, WP-03 mapping                  |
| ITAA-054 | `ranking_decision.py`     | Hash ranking fingerprint material with the WP-04 canonical hasher                             |

`DispatchService.authorize()` remains the authorization boundary. A simulator may
be invoked only with the envelope from a successful authorization. In-memory
repositories under `tests/fakes.py` are test references only.

WP-05 does not add a composition root, HTTP route, database adapter, or real
supplier/payment integration. All offers remain simulated.
