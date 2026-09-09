# apps/supplier-simulator

Isolated **simulated** suppliers for local competition. This is not a live
marketplace, inventory feed, or reservation system. Every offer and availability
value remains `simulation: true` / `*_simulated`.

No core package may import this app. The app depends inward on application,
policy, and domain.

## Seeded strategies (`sim.v1`)

| Supplier     | Strategy               | Floor / day | Notes                                     |
| ------------ | ---------------------- | ----------- | ----------------------------------------- |
| ParkDirect   | Value / uncovered      | USD 17      | Max 10% discount; 15–30 minute validity   |
| SkyShield    | Premium / covered + EV | USD 28      | Positive EV bundle margin; faster shuttle |
| TerminalFlex | Convenience / flexible | USD 24      | 20-minute validity; limited capacity      |

Billable days are `ceil((service_end - service_start) / 24 hours)` in integer
seconds. The floor applies to the discounted base subtotal before fees, tax, and
add-ons. Effective `validUntil` is `min(occurred_at + validity, response
deadline, envelope expiry)` and must sit in the trusted min/max window before an
offer is constructed. Canonical WP-02 Offer fixtures are ranking/contract
vectors and are not byte-identical to simulator output.

## Isolation

Each `SimulatedSupplier` receives one authorized `SupplierEnvelope` plus injected
time, offer ID, and signature handle. It never receives competitor identity,
other offers, buyer preferences, payment data, or a shared result collection.
Dispatch authorization stays in `DispatchService`; the simulator is not an A2
bypass.

## Deterministic invocation

There is no default clock, random source, network call, or model call. The same
policy, envelope, and injected identifiers produce the same payload.

## Tests

From the repository root, after `make setup`:

```bash
/usr/bin/make check
```

Targeted:

```bash
uv run pytest apps/supplier-simulator/tests packages/ranking/tests/test_ranking_golden.py
```

Do not describe a completed reservation or real availability in this package.
