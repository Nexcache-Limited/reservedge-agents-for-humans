# ADR-0004 — Canonical governance bindings

- Status: Accepted
- Date: 2026-08-20
- Decision owners: Product Owner; recorded from the authorized WP-04 work order implementing ADR-0002/ADR-0003 product policy

## Context

WP-02 defined SHA-256 hash _shape_ (`sha256:` plus 64 lowercase hex characters) but not canonical bytes. WP-03 domain timestamps serialize with microsecond precision and must not be hashed as if they were WP-02 contract strings. PurchaseIntent wire objects contain `disclosure.approvedPayloadHash`, so a naïve hash of the whole object cannot bind the object to itself. Dispatch approval must cover both the disclosed business content and the exact per-supplier envelopes without sharing aliases across suppliers.

This ADR records the WP-04 implementation of already-accepted product policy (minimum disclosure, exact approval binding, supplier isolation). It does not change product policy.

## Decision

### Canonical JSON v1

One shared canonicalizer lives in `packages/policy`. Hash material is transport JSON: objects, arrays, strings, JavaScript-safe integers, booleans, and null. Floats, decimals, bytes, sets, enums, dataclasses, dates/times, non-string keys, unpaired surrogates, and out-of-range integers are rejected. Bytes are UTF-8 with no BOM, no insignificant whitespace, object keys sorted by UTF-8 bytes, array order preserved, and only required JSON string escapes.

### Context-separated SHA-256

Every binding is `sha256(ASCII(domain_separator) || 0x00 || canonical_json_bytes)` rendered as `sha256:` plus 64 lowercase hex characters. Locked separators:

- `itaa.requirement.confirmation.v1`
- `itaa.disclosure.content.v1`
- `itaa.supplier.envelope.v1`
- `itaa.disclosure.manifest.v1`
- `itaa.offer.terms.v1`
- `itaa.transaction.authorization.v1`
- `itaa.idempotency.request.v1`
- `itaa.audit.event.v1`

### Self-hash and envelope manifest

Content hashing omits `/intentId`, `/buyerToken`, and `/disclosure/approvedPayloadHash` and does not mutate the input. The resulting content hash is inserted into each supplier envelope as `disclosure.approvedPayloadHash`. Each envelope is then hashed in full, including scoped aliases. A2 approval binds a manifest hash over the sorted recipient set (supplier token, invitation, scoped intent/buyer aliases, envelope hash) plus content hash, intent resource id/version, purpose, and expiry. `verify_dispatch` requires that recipient rows and envelopes form a privacy-safe bijection across those five fields, with canonical opaque types and globally unique identifiers. Recipient-row order is part of the A2 manifest hash; after that hash matches, verification treats the set as unordered. Policy `authorize_dispatch` evaluates a supplied A2 grant snapshot plus a consistent assignment/scope/payload binding; it does not prove repository revocation. Application `DispatchService.authorize` is the dispatch-authorization boundary because it resolves grant and revocation state atomically before that evaluation.

The supplied `expires_at` argument and payload `expiresAt` must be the same UTC timestamp; a mismatch is rejected. Changing the effective expiry therefore changes the content and manifest hashes.

Opaque supplier tokens and invitation tokens are authorization inputs, not authentication credentials. Audit event hashing uses `itaa.audit.event.v1` and excludes the record's own `event_hash` and representation-only signature field. An optional previous-hash chain is tamper-evident linkage, not signed non-repudiation or WORM storage. Once a named stream has a tail, a later append must present that exact hash; omitting the predecessor is a conflict. Identical event-id replay is checked before chain rules. Unchained writes (no stream id) remain allowed.

Completed idempotency is reference-only: first completion and replay return the same typed `ResultRef`. Raw effect bodies are hashed, not stored or returned.

## Consequences

- WP-05/WP-06 consume these bindings; they must not invent a second canonicalizer.
- Changing separators, omitted content-hash paths, or JSON rules requires a superseding ADR and Product Owner approval.
- Real persistence, KMS, signature creation/verification, and live authorization remain later packages.
