# apps/api

Local-only FastAPI composition root for the simulated JFK airport-parking golden path.

This process is **not** a production authorization surface. There is no production authentication. Offers, availability, and transaction receipts are **SIMULATED**. The API never places a real reservation or payment.

## Durability

Session state is process-local and in-memory. **Restart discards every session.** Durable persistence is WP-11. Do not treat this composition as a database.

Default `itaa_api.app:app` uses the canonical local-demo supplier roster. Fresh demonstrations emit the locked JFK ranking vector (SkyShield 671,000 / ParkDirect 660,000 / TerminalFlex 535,000, USD 29.00 downside). Each dispatch clones isolated simulated capacity, so one demo does not exhaust the next. Restart still discards sessions.

Buyer-side policy is independent of the live offer. `GoldenPathPolicyPort` looks up a trusted table built from checked-in contract fixture JSON at import time and ignores the candidate payload. That fixture-file load is an MVP limitation, not a policy database.

Default composition assigns a unique Offer ID (and unique signature, correlation, acceptance, authorization, audit, and result identities) for every generated resource. The same supplier answering two intents never reuses an Offer ID. Tendered invitation and scoped-intent aliases may stay reused.

The WP-05 `seeded_ports()` economic engine remains available for isolated simulator tests. It is not the default HTTP composition.

## Local run

From the repository root, after `make setup`:

```text
uv run uvicorn itaa_api.app:app --app-dir apps/api/src
```

Uvicorn is provided only for this documented local command.

## Routes

- `GET /healthz` — process liveness
- `GET /readyz` — local composition ready; no external calls
- `POST /v1/simulations/airport-parking/intents`
- `POST /v1/simulations/airport-parking/intents/{intentId}/confirm`
- `POST /v1/simulations/airport-parking/intents/{intentId}/dispatch`
- `GET /v1/simulations/airport-parking/intents/{intentId}`
- `POST /v1/simulations/airport-parking/intents/{intentId}/acceptances`
- `POST /v1/simulations/airport-parking/intents/{intentId}/transaction-authorizations` — requires `Idempotency-Key` equal to body `idempotencyKey`

OpenAPI is exported to `apps/api/openapi/itaa-v1.json`. `make check` runs a non-mutating drift check.
