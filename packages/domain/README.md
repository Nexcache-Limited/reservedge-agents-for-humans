# packages/domain

Cloud-neutral domain kernel: immutable value objects, aggregates, exhaustive
Purchase Intent / Offer / Transaction state machines, and redaction-safe domain
events.

Rules:

- Empty runtime dependency list. Standard library only.
- No I/O, system clock, randomness, environment access, or network.
- No Pydantic, generated contract models, JSON Schema validators, FastAPI, ORM,
  provider SDKs, or UI imports.
- Simulation-only authorization: `reserve_parking` + `SIMULATED`.
- Internal aggregate `revision` is distinct from commercial Offer `offer_version`.
- Advanced Transaction/Offer snapshots reject incomplete or impossible metadata.
- Forward Purchase Intent and Offer advancement cannot occur at/after expiry.
- Simulated authorization cannot occur at/after the decision or Acceptance deadline.
- Event actor/correlation IDs are domain-only Crockford tokens (`ar_`, `cr_`).
  Reason codes are closed enums. DomainEvent validates an exhaustive per-type
  binding of resource, action, target state, reason family, and whether
  `offer_id`, `acceptance_id`, and `payload_hash` are required, optional, or
  forbidden. Generic `apply` methods accept only the exact reason enum for that
  action. Constructor `event_type`, aggregate `state`, and generic `apply`
  actions require the exact `StrEnum` type; raw strings are not coerced.
  `EVENT_SPECS` is an immutable mapping.
- Snapshot reconstruction uses the same time bounds as transitions:
  `AUTHORIZED_SIMULATED` requires `updated_at` before the decision and
  Acceptance deadlines; `ACCEPTED` and other live terms-bearing Offer states
  require `updated_at` before `terms.validity.end`; `EXPIRED` snapshots cannot
  precede those deadlines.
- Offer `reject` and `decline` remain matrix-legal after validity ends, so
  `REJECTED` and `DECLINED` snapshots may be reconstructed at or after
  `terms.validity.end`. `expire` is the dedicated post-validity path.

Timestamp precision: domain snapshot serialization uses Python `datetime`
microseconds. A nine-digit fractional `Z` timestamp is stored/emitted with six
digits. This is an internal snapshot boundary, not the canonical WP-02 contract
string and not the representation WP-04 must hash or sign.

WP-03 implements ITAA-030 through ITAA-034. WP-04 adds policy, approvals,
isolation, idempotency ports, and audit vocabulary in separate packages. Domain
state machines and event types remain unchanged.
