# Reservedge — Intent-to-Action booking agent

**AWS Agents for Humans · Everyday Agents**

Reservedge turns one natural-language trip objective into coordinated flight, hotel and parking work inside one Booking Chat. Strands Agents SDK + Amazon Bedrock interpret and refine the objective; deterministic application code controls provenance, provider dispatch, ranking and authorization. The competition build uses LiteAPI sandbox research for flights/hotels and labelled simulated Curated offers for parking, including a simulated receipt. No real charge, ticket or reservation occurs.

## Judge links

- **Live competition demo:** https://bookingdemo.reservedge.com — Competition staging — sessions are process-local; an API process restart discards active chats.
- **Demo video:** https://vimeo.com/1226748038?share=copy&fl=sv&fe=ci
- **Architecture:** [docs/demo-aws/architecture.svg](docs/demo-aws/architecture.svg) ([source](docs/demo-aws/architecture.mmd))
- **Honesty / simulation boundary:** [docs/submissions-aws/HONESTY.md](docs/submissions-aws/HONESTY.md)
- **Build provenance:** [docs/submissions-aws/BUILD_PROVENANCE.md](docs/submissions-aws/BUILD_PROVENANCE.md)
- **Demo script:** [docs/demo-aws/SCRIPT.md](docs/demo-aws/SCRIPT.md)
- **Devpost copy:** [docs/submissions-aws/DEVPOST.md](docs/submissions-aws/DEVPOST.md)

**SIMULATED — NO REAL CHARGES OR RESERVATIONS**

## What to watch in the demo

1. A free-form objective becomes **Flight → Hotel → Parking** tasks.
2. Conversational authorization happens before search.
3. Cross-domain date refinement does not restart the journey.
4. A simulated **Curated** parking offer → human authorization → simulated receipt. Flight and hotel research stay open.

## Architecture summary

```text
Browser
  → /v1/agent/**                 product BFF
  → /v1/aws/plan-turns
  → /v1/aws/execute-turns
  → Strands Agents SDK
  → Amazon Bedrock
  → code projector / closed capabilities
```

The **browser never calls Bedrock**. Hosted staging uses live Bedrock. A local clone defaults to fake model mode and needs no cloud credentials. Amazon Bedrock AgentCore is **not deployed**.

Capabilities in this build:

| Capability          | Adapter                                                           | Honesty                                       |
| ------------------- | ----------------------------------------------------------------- | --------------------------------------------- |
| `flight.search`     | LiteAPI sandbox                                                   | Research only — not a ticket                  |
| `stay.search`       | LiteAPI sandbox                                                   | Research only — not a reservation             |
| `parking.search`    | Simulated Curated suppliers (ParkDirect, SkyShield, TerminalFlex) | Simulated replies; governed simulated receipt |
| `experience.search` | Prioticket                                                        | Provider-limited catalog                      |
| `rental.search`     | None                                                              | Requirement only — no production inventory    |

**Curated offer** is a first-class label on parking cards. The product pattern is **public/sandbox search plus a simulated curated/reverse-bid offer path**: standard search retrieves catalog results; the curated path shows providers responding to the buyer’s requirements. In this competition build those curated replies are simulated. No live curated marketplace is connected.

## Human control

Code, not the model, owns:

- **Explicit / Inferred / Proposed** provenance
- disclosure and supplier isolation
- search authorization
- deterministic ranking
- offer selection state
- simulated money action

A4 authorizes a simulated reservation action. The resulting receipt is simulated; no real supplier reservation or charge is created.

## Competition provenance

Reservedge includes platform work created before the Agents for Humans window (domain, policy, ranking, simulated parking golden path, intent-first chrome). Competition-period work is the Strands adapter, `/v1/agent` BFF, LiteAPI/Prioticket capability wiring, and conversation-first Booking Chat. See [BUILD_PROVENANCE.md](docs/submissions-aws/BUILD_PROVENANCE.md) and [PROVENANCE.md](docs/submissions-aws/PROVENANCE.md).

## Repository map

| Path                      | Responsibility                                                           |
| ------------------------- | ------------------------------------------------------------------------ |
| `apps/api`                | Local FastAPI composition root (process-local sessions)                  |
| `apps/web`                | React/Vite buyer client (Booking Chat + domain lanes)                    |
| `apps/mobile`             | Reserved native client placeholder                                       |
| `apps/worker`             | Reserved async composition placeholder                                   |
| `apps/supplier-simulator` | Isolated simulated parking suppliers                                     |
| `packages/domain`         | Cloud-neutral domain; no I/O                                             |
| `packages/application`    | Use cases and ports; no providers                                        |
| `packages/contracts`      | Canonical JSON Schema 2020-12 and generated types                        |
| `packages/policy`         | Deterministic disclosure, hashing, approvals, isolation                  |
| `packages/ranking`        | Deterministic scoring and explanation facts                              |
| `packages/observability`  | Audit vocabulary and append-only sink port                               |
| `packages/ui-kit`         | Shared Reservedge design tokens and primitives                           |
| `adapters/`               | AWS Strands, LiteAPI, Prioticket, Google (Google not claimed on Devpost) |
| `infra/`                  | Provider deployment sketches; not a production service                   |
| `tests/`                  | Fixtures, contract, evals, e2e, security, adversarial                    |
| `docs/source-of-truth/`   | Approved specifications                                                  |
| `docs/adr/`               | Architecture decisions                                                   |
| `docs/submissions-aws/`   | Competition pack (Devpost, honesty, UAT, export)                         |
| `docs/demo-aws/`          | Demo script and architecture diagram                                     |
| `tools/`                  | Contract validation/generation, secret scan, demo seed                   |

Local Compose (`compose.yaml` at repo root) provides an empty PostgreSQL on host port **5433**. The current product path does **not** persist sessions there.

## Quick start

Prerequisites:

- Python 3.12
- [uv](https://docs.astral.sh/uv/) 0.12+
- Node.js 22+
- pnpm 11.9.x (`corepack enable && corepack prepare pnpm@11.9.0 --activate`)
- GNU Make
- Docker Engine or Docker Desktop (needed for `make compose-config` inside `make check`; not required to run the local web/API demo)

`make` locates `uv` and `pnpm` on `PATH` or in `$HOME/.local/bin`.

```bash
git clone <this-repository>
cd <repo>
cp .env.example .env
make setup
make check
```

`make setup` uses only committed lockfiles and the copied `.env.example` defaults. It does not require cloud credentials.

### Run the local product (fake mode)

Vite binds **5180** and proxies `/v1`, `/healthz`, and `/readyz` to the API on **8011**. Combined process (product BFF + Strands adapter in-process):

```bash
ITAA_AWS_MODEL_MODE=fake \
uv run uvicorn itaa_aws_adapter.app:app \
  --app-dir adapters/aws-strands-bedrock-agentcore/src \
  --host 127.0.0.1 --port 8011
```

```bash
pnpm --filter @itaa/web dev
```

Open `http://127.0.0.1:5180`. Restarting the API discards every in-memory session.

### Quality commands

| Command                             | Purpose                                                        |
| ----------------------------------- | -------------------------------------------------------------- |
| `make setup`                        | Install Python and TypeScript workspace dependencies           |
| `make check`                        | Complete local quality gate                                    |
| `make test`                         | Python pytest plus ui-kit, contracts, and web Vitest suites    |
| `make web-integration`              | Live HTTP golden-path integration (starts or requires FastAPI) |
| `pnpm --filter @itaa/web test`      | Web unit/component tests with coverage thresholds              |
| `make format` / `make format-check` | Apply or verify formatting                                     |
| `make lint`                         | Lint Python and TypeScript                                     |
| `make typecheck`                    | Strict type checks                                             |
| `make validate-contracts`           | Schema, fixtures, invariants, generated-output drift           |
| `make secrets`                      | Secret-pattern scan                                            |
| `make compose-config`               | Validate Compose file                                          |

Optional local PostgreSQL (empty; not used by the current demo path):

```bash
make deps-up
make db-health
make deps-down
```

## Quality

- **Full quality gate:** `make check` runs format-check, lint, typecheck, Python and TypeScript tests, contract validation, OpenAPI drift, secret scan, and Compose config validation.
- **Web tests:** `pnpm --filter @itaa/web test` (Vitest + v8 coverage thresholds in `apps/web/vite.config.ts`).
- **Web integration:** `make web-integration` (fails if the API cannot be reached; it does not treat connection failure as a pass).

## Cloud-neutral dependency rules

```text
apps / adapters  -->  application  -->  policy / observability -->  domain
ranking  -->  domain
UI  -->  typed contracts / view models
```

Forbidden:

- `packages/domain` or `packages/application` importing FastAPI, ORM/database clients, Google, AWS, model SDKs, RevenueCat, or UI packages
- Provider SDKs outside `adapters/` or `infra/`
- UI redefining disclosure, ranking, approval, or simulation semantics

See [ADR-0002](docs/adr/ADR-0002-cloud-neutral-boundaries.md) and [ADR-0003](docs/adr/ADR-0003-simulation-boundary.md).

## Security and privacy

- **Supplier isolation.** Each simulated parking supplier receives only its authorized envelope.
- **Minimum disclosure.** A2 approves exact fields before dispatch.
- **Human authorization.** Search, offer selection, and simulated money action are distinct grants. A4 authorizes the simulated booking step; it never creates a real booking.
- **Simulation status** is explicit (`SIMULATED — NO REAL CHARGES OR RESERVATIONS`).
- **No hidden real transaction.** Non-simulated authorization modes are rejected in this MVP profile.
- **No raw private data in buyer responses.** Internal scores such as `scoreMicros` are not buyer commercial fields.

Do not file security issues with live credentials, personal data, or supplier payloads. Reporting contact will be published by the Product Owner; until then, handle suspected exposure privately with the repository owner and rotate any revealed secret immediately.

## Mobile

Responsive **mobile-web** is implemented in `apps/web`. Native mobile (`apps/mobile`) remains a placeholder. Mobile-web is not a native application.

## Source of truth

Approved documents live in [docs/source-of-truth](docs/source-of-truth/README.md). Intent-first orchestration is recorded in [ADR-0006](docs/adr/ADR-0006-intent-first-orchestration.md). Competition pack: [docs/submissions-aws/README.md](docs/submissions-aws/README.md). Demo script: [docs/demo-aws/SCRIPT.md](docs/demo-aws/SCRIPT.md).

## License

This private tree is all-rights-reserved (`LICENSE`) until the public competition export. That export uses **Apache-2.0** and `NOTICE`. See [COMP_AWS_06_EXPORT.md](docs/submissions-aws/COMP_AWS_06_EXPORT.md).
