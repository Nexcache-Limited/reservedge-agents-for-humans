# packages/policy

Cloud-neutral deterministic disclosure, hashing, approval, isolation, and
idempotency request binding.

## Profiles and modules

| Ticket   | Module           | Responsibility                                             |
| -------- | ---------------- | ---------------------------------------------------------- |
| ITAA-040 | `disclosure.py`  | `parking_v1` firewall, sent/withheld preview, content hash |
| ITAA-041 | `envelopes.py`   | Supplier-specific envelopes and dispatch manifest          |
| ITAA-042 | `isolation.py`   | Deny-by-default supplier authorization predicate           |
| ITAA-043 | `approvals.py`   | Exact A1–A4 grants and validation                          |
| ITAA-044 | `idempotency.py` | Request-hash types; atomic storage is an application port  |
| Shared   | `canonical.py`   | Canonical JSON v1 and context-separated SHA-256            |

Runtime dependencies: `itaa-domain` only. Standard library plus workspace domain types. No Google, AWS, FastAPI, database, model, or UI imports.

## Canonicalization and hashes

Hash material is WP-02 transport JSON, never reconstructed WP-03 datetime serialization. See [ADR-0004](../../docs/adr/ADR-0004-canonical-governance-bindings.md).

`parking_v1` content hashing omits `/intentId`, `/buyerToken`, and `/disclosure/approvedPayloadHash`. Those aliases are unique per supplier envelope. A2 binds the envelope manifest, not merely the content hash. `verify_dispatch` checks envelope membership and requires the approved recipient rows and envelopes to be an exact one-to-one set across supplier token, invitation, scoped aliases, and envelope hash. Row order is bound by the A2 manifest hash; verification treats the set as unordered once that hash matches. Policy `authorize_dispatch` evaluates a supplied A2 snapshot plus envelope/scope identity; `DispatchService` is the application authorization boundary because it resolves grant and revocation atomically.

Content-hash material rejects non-string keys without coercion. Solicitation expiry is exact: the supplied `expires_at` must equal payload `expiresAt`.

## Approvals and isolation

A1–A4 are exact enums and cannot substitute for one another. Opaque supplier tokens and invitation tokens are authorization inputs, not authentication credentials. There is no wildcard, list-all, admin, or competitor-read capability.

## Exclusions

- No randomness, system clock, I/O, or logging.
- No live purchase, payment, booking, or reservation.
- No claim that an opaque token is authenticated or unforgeable.
- In-memory repositories belong in tests only.
