# packages/contracts

Canonical ITAA v1 contracts. **JSON Schema 2020-12 is the semantic source of truth.** Python and TypeScript files under `generated/` are produced from those schemas and must not be edited by hand.

Tickets: ITAA-020 through ITAA-024.

## Layout

```text
packages/contracts/
  registry.json              schema inventory
  schemas/v1/                canonical JSON Schema 2020-12
  fixtures/valid|invalid/    sanitized golden-path fixtures
  generated/python/          generated Pydantic v2 models
  generated/typescript/      generated TypeScript types
```

Python generated output lives in `generated/python/itaa_contracts_generated` so it is importable. TypeScript generated output lives in `generated/typescript` and is exported as `@itaa/contracts`. Canonical schemas stay separate from both.

Schema `$id` values use the non-resolving namespace `https://contracts.itaa.invalid/v1/`. Validators map those IDs to repository files. Normal checks never fetch the network.

## Conventions (ITAA-020)

| Concern        | Rule                                                                                                                                                              |
| -------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Schema dialect | JSON Schema 2020-12                                                                                                                                               |
| Profile        | `schemaVersion` const `1.0`                                                                                                                                       |
| Objects        | `additionalProperties: false` on signed/approval-bound payloads and nested objects                                                                                |
| Time           | UTC RFC 3339 `date-time` ending in `Z`; calendar/clock values are format-checked                                                                                  |
| Money          | non-negative integer minor units, max `9007199254740991`                                                                                                          |
| Currency       | ISO 4217, three uppercase letters                                                                                                                                 |
| IDs/tokens     | `{type}_{26-char crockford ulid}`: `pi_`, `bs_`, `of_`, `sp_`, `co_`, `ac_`, `ta_`, `ap_`, `ik_`, `sg_`, plus COMP-G1-06 `oi_`, `bt_`, `ce_`, `cf_`, `pl_`, `ld_` |
| Hashes         | `sha256:` + 64 lowercase hex; WP-02 checks shape only                                                                                                             |
| Signatures     | opaque `sg_` tokens; no cryptographic verify here                                                                                                                 |

## Contracts

| Schema                   | `$id`                                       | Generated Python           | Generated TypeScript       |
| ------------------------ | ------------------------------------------- | -------------------------- | -------------------------- |
| Common defs              | `.../common.schema.json`                    | shared via refs            | inlined by generator       |
| PurchaseIntent           | `.../purchase-intent.schema.json`           | `PurchaseIntent`           | `PurchaseIntent`           |
| Offer                    | `.../offer.schema.json`                     | `Offer`                    | `Offer`                    |
| CounterOffer             | `.../counter-offer.schema.json`             | `CounterOffer`             | `CounterOffer`             |
| Acceptance               | `.../acceptance.schema.json`                | `Acceptance`               | `Acceptance`               |
| TransactionAuthorization | `.../transaction-authorization.schema.json` | `TransactionAuthorization` | `TransactionAuthorization` |
| OrchestrationIntent      | `.../orchestration-intent.schema.json`      | `OrchestrationIntent`      | `OrchestrationIntent`      |
| Conversation             | `.../conversation.schema.json`              | `Conversation`             | `Conversation`             |
| IntentPlan               | `.../intent-plan.schema.json`               | `IntentPlan`               | `IntentPlan`               |
| BookingTask              | `.../booking-task.schema.json`              | `BookingTask`              | `BookingTask`              |
| CostLedger               | `.../cost-ledger.schema.json`               | `CostLedger`               | `CostLedger`               |
| BuyerOffer               | `.../buyer-offer.schema.json`               | `BuyerOffer`               | `BuyerOffer`               |

BuyerOffer is the buyer-facing commercial projection. It must not contain `scoreMicros`. Existing Offer remains the supplier-normalized commercial offer and is not this projection.

### Purchase Intent (ITAA-021)

Supplier-visible minimized parking envelope. Not the buyer-domain Requirement or Disclosure Preview. `disclosure.approvedPayloadHash` is a representation only; later packages bind it to a canonical serialization.

### Offer / CounterOffer (ITAA-022)

Offers are multidimensional and `simulation` is const `true`. Service availability values are `*_simulated`. Distance is integer metres (the spec example used a float mile value; WP-02 avoids non-integer commercial quantities).

CounterOffer `proposedChanges` is a closed `oneOf` allowlist of commercial paths. One-round enforcement and comparison against undisclosed terms are **not** standalone contract checks.

### Acceptance / Transaction Authorization (ITAA-023)

Acceptance carries offer version, terms hash, and buyer approval id.

Transaction Authorization `mode` is const `SIMULATED` and `action` is const `reserve_parking`. Exact amount/merchant matching, fresh approval ownership, and one-receipt-per-key uniqueness require domain state and are deferred.

## Standalone vs deferred

Enforced here:

- Shape, formats, unknown fields, UTC, money integers, opaque IDs, hashes, simulation const, SIMULATED mode, totals, and time-order windows.

Deferred to WP-03/WP-04 and later:

- Hash computation and approval binding
- Invitation match, supplier isolation, current offer version, ownership
- Approval freshness and actor identity
- Idempotency uniqueness and receipt signing
- One-round counteroffer policy and ranking

## Commands

```bash
make generate-contracts   # rewrite generated/ from schemas
make validate-contracts   # schema, registry, fixtures, invariants, non-mutating drift
make check                # includes validate-contracts
```

Drift detection generates into a temporary directory and compares. It does not write `generated/` unless you run `make generate-contracts`.
