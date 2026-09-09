# apps/web

Buyer-facing React + Vite client for the simulated JFK airport-parking golden path (UI-01). Comparison attributes that the snapshot does not carry (lot, shuttle, terms, evidence) are looked up from the locked fixture catalog by supplier token, not Offer ID.

This application talks only to the local WP-06 FastAPI surface. Offers and authorizations are **SIMULATED**. No real reservation or payment is created.

## Durability

The API keeps sessions in process memory. **Restarting the API discards every intent.** Browser refresh reconstructs the workspace from `GET /v1/simulations/airport-parking/intents/{intentId}`. The inbox list is session memory of opaque intent ids only.

## Local run

From the repository root, after `make setup`:

```text
uv run uvicorn itaa_api.app:app --app-dir apps/api/src
pnpm --filter @itaa/web dev
```

Open `http://127.0.0.1:5173`. Vite proxies `/v1`, `/healthz`, and `/readyz` to the API.

## Routes

- `/` — Intent Inbox
- `/intents/new` — seeded JFK demo start
- `/intents/:intentId` — progressive A1–A4 workspace
- `/intents/:intentId/confirmation` — simulated receipt

## Quality

Unit and component suite (no live API required):

```text
pnpm --filter @itaa/web lint
pnpm --filter @itaa/web typecheck
pnpm --filter @itaa/web test
pnpm --filter @itaa/web build
```

WP-06 orchestrated HTTP integration (requires or starts local FastAPI). This target **fails** if the API is absent; it does not convert connection failures into a passing assertion:

```text
make web-integration
# or
pnpm --filter @itaa/web test:integration
```

320 CSS-pixel overflow measurements (Chrome):

```text
pnpm --filter @itaa/web test:viewport
```

Acceptance command for UI-01-R1:

```text
pnpm --filter @itaa/web lint && pnpm --filter @itaa/web typecheck && pnpm --filter @itaa/web test && pnpm --filter @itaa/web build && make web-integration && /usr/bin/make check
```
