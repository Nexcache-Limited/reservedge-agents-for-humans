# packages/observability

Canonical audit vocabulary and an append-only sink port.

## Modules

| Ticket   | Module         | Responsibility                                              |
| -------- | -------------- | ----------------------------------------------------------- |
| ITAA-045 | `audit.py`     | Redaction-safe audit records and 24 DomainEvent projections |
| ITAA-045 | `redaction.py` | Forbidden-name helpers that never echo values               |
| ITAA-045 | `ports.py`     | Atomic append port; no update/delete                        |

Runtime dependencies: `itaa-domain` only. Hashing is applied by `packages/application` using the shared policy canonicalizer (`itaa.audit.event.v1`). Observability does not import policy.

## Non-claims

- An optional previous-hash chain is tamper-evident linkage, not signed non-repudiation or WORM storage. A named stream cannot restart by omitting its current tail.
- `signature_handle` is a representation-only `SignatureHandle`. This package does not create or verify digital signatures.
- Reason codes are the closed `AuditReason` vocabulary. Resource IDs use a resource-type-to-prefix map; isolation uses `iv_` invitation references.
- Provider labels are closed adapter names, never SDK or model objects.
- In-memory sinks used in tests are not production adapters.
- Raw source, direct identity, prompts, payment, itinerary, competitor offers, and credentials must not appear in audit records.

Real database/WORM storage, signing keys, exports, and administrative audit are later adapters.
