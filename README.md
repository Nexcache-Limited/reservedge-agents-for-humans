# Reservedge — Intent to Action Agent

**AWS Agents for Humans · Everyday Agents track**

Reservedge is a privacy-first **Intent to Action Agent (ITAA)**. A buyer types an open-ended objective the way they would say it out loud. **AWS Strands Agents** on **Amazon Bedrock** interpret that objective, ask at most three blocking questions, and return a structured multi-task plan. Deterministic code — not the model — labels each task **Explicit**, **Inferred**, or **Proposed** and routes it to a closed capability. Provider search waits for **conversational authorization**. Parking still requires **A1–A4**. Stay, flight, and experience research never become a booking or ticket.

This repository is the public competition export of an accepted local checkpoint. It is a **working local product**, not a stub. There are **no real charges, reservations, or supplier bookings**.

```text
Browser  →  /v1/agent/**  (product BFF)
                 ↓
            /v1/aws/**    (Strands adapter + code projector)
                 ↓
            closed capabilities
                 ├── stay.search      LiteAPI sandbox hotel research
                 ├── flight.search    LiteAPI sandbox flight research (not a ticket)
                 ├── experience.search Prioticket adapter (catalog currently provider-limited)
                 ├── parking.search   labelled simulated suppliers
                 └── rental.search    requirement-only (no invented inventory)
                 ↓
            GoldenPathFacade A1–A4 (simulated parking only)
```

The browser talks to `/v1/agent/**`. Do not treat `/v1/aws/**` as the UI path.

## What this checkpoint is

- **Conversation-first** intent: “What are you planning or trying to get done?”
- **AWS Strands Agents SDK** Plan/Execute behind a closed tool set
- **Amazon Bedrock live Plan path** (allowlisted model; fail-closed unless explicitly invoked)
- **Multi-domain task inference and routing** — stay, flight, experience, parking, rental — without location heuristics (Milan does not become a hotel, “I'm flying from JFK…” does not open a flight lane, London does not become an experience)
- **Conversational search authorization** — no LiteAPI or parking search until the buyer confirms the ready set in chat
- **Conversational refinements** — date/task/preference mutations stale only the affected domain and require a new search authorization
- **Capability-aware suggestions** — the agent asks only newly missing facts for the ready capabilities
- **Booking Chats UX** — Running / Pending / History inbox; resume does not invent an Unknown intent
- **LiteAPI** sandbox **hotel research** (`stay.search`) and **flight research** (`flight.search`) — server-side env names only; not a booking or ticket
- **Prioticket** experience adapter (`experience.search`) integrated with OAuth2 client-credentials; **city-linked catalog inventory is currently provider-limited**, so Milan/London experience search can return a truthful empty set
- **Governed simulated parking** (`parking.search`) — ParkDirect / SkyShield / TerminalFlex, labelled simulation; parking clocks are **airport-local wall time** (UTC only at the provider/execution boundary)
- **Recording-final domain UX** — yearless dates resolve to the nearest future occurrence; one compact card per domain; flight stays **Proposed** unless explicitly accepted so hotel/parking/experience can search independently
- **Rental capability without live inventory** — requirement capture only; no invented cars
- **Reservedge** visible branding in buyer chrome (internal `itaa_*` namespaces unchanged)
- **Code-validated structured agent state** (`PlanTurn` → UI `PlanProjection`)
- **Explicit / Inferred / Proposed** provenance assigned by the projector, not the model
- **A1–A4 human authorization** before any simulated parking supplier work
- Default judge/local setup is **fake mode** — no cloud credentials required

Local live Bedrock Plan turns were exercised on 7 September 2026 (one Bedrock cycle per planning turn). LiteAPI sandbox stay and flight search return research-only pages after conversational authorization. That is not Amazon Bedrock AgentCore and not a real hotel, flight ticket, or experience booking. AgentCore is **not deployed** and is not claimed.

## What this checkpoint is not

Do not read the demo as a live marketplace. This cut does **not** include:

- real bookings, tickets, inventory holds, payments, or contact with real suppliers
- Prioticket as a working Milan (or other city) experience catalog until the provider provisions that inventory
- production supplier booking APIs
- durable persistence (process-local sessions; Booking Chats resume only while the API process is up)
- production authentication
- a native iOS/Android application (responsive mobile-web only)
- Amazon Bedrock AgentCore
- a production booking marketplace

## Pre-existing platform vs competition-period AWS work

**Do not treat all of ITAA as hackathon-week work.** See [NOTICE](NOTICE) and [docs/submissions-aws/PROVENANCE.md](docs/submissions-aws/PROVENANCE.md).

**Already in the Reservedge platform** (before or independent of this competition window): cloud-neutral domain and application core, disclosure/isolation, A1–A4 governance, deterministic ranking, simulated suppliers, FastAPI golden path, React/Vite buyer UI, and the intent-first substrate.

**Competition-period AWS work:** Strands Agents integration, Bedrock live Plan path, `/v1/aws/**`, `/v1/agent/**`, conversation-first multi-domain session/domain state, conversational search authorization and refinements, LiteAPI stay and flight adapters, Prioticket experience adapter, Booking Chats UX, and the AWS demo/submission pack under `docs/demo-aws` and `docs/submissions-aws`.

The Google/Gemini adapter under `adapters/google` is not part of this Devpost claim.

## Honesty (say this on camera)

Canonical wording: [docs/submissions-aws/HONESTY.md](docs/submissions-aws/HONESTY.md).

- Supplier execution and payment are simulated. `SIMULATED - NO REAL CHARGES OR RESERVATIONS`
- No provider search runs before conversational authorization.
- LiteAPI stay and flight results are **research only**. Selecting a hotel is not a booking. Selecting a flight is not a ticket.
- Prioticket is an integrated experience adapter. Empty city results mean the provider catalog does not currently expose that inventory — not a silent fixture.
- Parking is a **labelled simulation**. A1–A4 remain distinct human grants.
- Rental is requirement-only. The product does not invent car inventory.
- Changing one requirement stales only the affected domain and requires a new search authorization.
- A4 is not a booking. Mode is `SIMULATED`.
- Session state is process-local and non-durable. Restarting the API discards every session.

## Judge setup (credential-free fake mode)

This is the safe default. Cloud credentials are not required.

### Prerequisites

- Python 3.12
- [uv](https://docs.astral.sh/uv/) 0.12+
- Node.js 22+
- pnpm 11.9.x (`corepack enable && corepack prepare pnpm@11.9.0 --activate`)
- GNU Make
- Docker Engine or Docker Desktop (needed for `make compose-config` inside `make check`; not required to run the local demo)

`make` locates `uv` and `pnpm` on `PATH` or in `$HOME/.local/bin`.

### Clone and install

```bash
git clone https://github.com/Nexcache-Limited/reservedge-agents-for-humans.git
cd reservedge-agents-for-humans
cp .env.example .env
make setup
```

`make setup` uses committed lockfiles and `.env.example` defaults. It does not require cloud credentials.

Stay, flight, and experience adapters default to fake mode. Optional sandbox names (`ITAA_LITEAPI_API_KEY`, `ITAA_PRIOTICKET_CLIENT_ID`, `ITAA_PRIOTICKET_CLIENT_SECRET`) stay empty in `.env.example`. Never use `VITE_*` for those values. `ITAA_STAY_SEARCH_MODE=sandbox` also enables LiteAPI flight research when a key is supplied at runtime.

### Fake-mode startup (default demo)

One Python process mounts the product API and the AWS adapter in-process. Vite on **5180** proxies `/v1` to **8011**.

```bash
ITAA_AWS_MODEL_MODE=fake \
uv run uvicorn itaa_aws_adapter.app:app \
  --app-dir adapters/aws-strands-bedrock-agentcore/src \
  --host 127.0.0.1 --port 8011
```

```bash
pnpm --filter @itaa/web dev
```

Open **http://127.0.0.1:5180**.

Restarting the API discards every in-memory session.

Demo script: [docs/demo-aws/SCRIPT.md](docs/demo-aws/SCRIPT.md). Fake-mode UAT: [docs/submissions-aws/UAT.md](docs/submissions-aws/UAT.md).

### Test commands

```bash
make check
```

Narrower fake-mode evidence:

```bash
PYTHONPATH=adapters/aws-strands-bedrock-agentcore/src \
  uv run pytest adapters/aws-strands-bedrock-agentcore/tests tests/evals/test_comp_aws_04_*.py \
  tests/adversarial/test_comp_aws_04_*.py tests/security/test_comp_aws_04_strands_lock.py
pnpm --filter @itaa/web test
```

| Command | Purpose |
| ------------------------------ | ----------------------------------------------------------- |
| `make setup` | Install Python and TypeScript workspace dependencies |
| `make check` | Complete local quality gate |
| `make test` | Python pytest plus ui-kit, contracts, and web Vitest suites |
| `make secrets` | Secret-pattern scan |
| `pnpm --filter @itaa/web test` | Web unit/component tests |

## Optional live Bedrock Plan path

Fake mode remains the judge/local default. Live Plan is opt-in, fail-closed, and uses the **normal AWS SDK credential chain**. This repository does not contain access keys, secret keys, session tokens, account ids, or operator profile names.

```bash
export AWS_REGION=eu-west-2
export AWS_DEFAULT_REGION=eu-west-2
export ITAA_AWS_MODEL_MODE=live
export ITAA_AWS_LIVE_INVOKE=1
export ITAA_AWS_TIMEOUT_MS=30000
export ITAA_AWS_MODEL=global.anthropic.claude-sonnet-4-6
uv run uvicorn itaa_aws_adapter.app:app \
  --app-dir adapters/aws-strands-bedrock-agentcore/src \
  --host 127.0.0.1 --port 8011
```

- **Region** is configurable (`AWS_REGION` / `AWS_DEFAULT_REGION`).
- **Model** is configurable only within the adapter allowlist. The allowlisted live id is `global.anthropic.claude-sonnet-4-6`.
- Credentials come from the default AWS SDK chain (environment, shared config, or an IAM role). Do not put credentials in the repo or the browser.
- Without `ITAA_AWS_LIVE_INVOKE=1`, live mode fails closed (`model: unavailable`). There is no silent fallback to fake fixtures.
- Live UAT notes (no operator identifiers): [docs/submissions-aws/LIVE_UAT.md](docs/submissions-aws/LIVE_UAT.md).

Optional LiteAPI sandbox stay and flight research (server-side only; both gated by conversational authorization):

```bash
export ITAA_STAY_SEARCH_MODE=sandbox
export ITAA_LITEAPI_API_KEY=   # supply at runtime; never commit
```

Optional Prioticket sandbox (server-side only; city catalog may still be empty):

```bash
export ITAA_EXPERIENCE_SEARCH_MODE=sandbox
export ITAA_PRIOTICKET_CLIENT_ID=
export ITAA_PRIOTICKET_CLIENT_SECRET=
```

## Architecture

Conceptual layers:

```text
Responsive Web UI
    ↓
Intent / Clarify & Plan  (/v1/agent/**)
    ↓
Strands Plan/Execute + code projector
    ↓
Closed capability routing
    ↓
Adapters (LiteAPI stay/flight research, Prioticket adapter, simulated parking, rental requirement)
    ↓
Governance (A1–A4) for simulated parking
```

Models may extract or explain. Code owns policy, eligibility, ranking, approvals, money, isolation, idempotency, and simulation status.

Parking golden-path diagram: [docs/demo-aws/architecture.svg](docs/demo-aws/architecture.svg) · source [docs/demo-aws/architecture.mmd](docs/demo-aws/architecture.mmd)

See [ADR-0002](docs/adr/ADR-0002-cloud-neutral-boundaries.md) and [ADR-0003](docs/adr/ADR-0003-simulation-boundary.md).

## Repository map

| Path | Responsibility |
| ---------------------------------------- | ------------------------------------------------------------ |
| `apps/api` | Local FastAPI composition root (process-local simulation) |
| `apps/web` | React/Vite buyer client (Booking Chats, conversation-first, parking golden path) |
| `apps/supplier-simulator` | Isolated simulated parking suppliers |
| `packages/domain` | Cloud-neutral domain; no I/O |
| `packages/application` | Use cases, capability routing, external-search port |
| `packages/contracts` | Canonical JSON Schema 2020-12 and generated types |
| `packages/policy` | Deterministic disclosure, hashing, approvals, isolation |
| `packages/ranking` | Deterministic scoring and explanation facts |
| `adapters/aws-strands-bedrock-agentcore` | Strands / Bedrock adapter (fake default; live Plan opt-in) |
| `adapters/liteapi-hotels` | LiteAPI stay and flight research adapter (names-only config) |
| `adapters/prioticket-experiences` | Prioticket experience adapter (names-only config) |
| `docs/submissions-aws` | Competition honesty, provenance, UAT, Devpost draft |
| `docs/demo-aws` | Demo script, architecture, AgentCore design-only note |

Local Compose (`compose.yaml`) provides an empty PostgreSQL on host port **5433**. The current golden path does **not** persist product state there.

## Security and privacy

- **Supplier isolation.** Each simulated parking supplier receives only its authorized envelope.
- **Minimum disclosure.** A2 approves exact fields before dispatch.
- **Human authorization.** A1–A4 are distinct grants. A4 is not a booking.
- **External research ≠ booking.** LiteAPI and Prioticket responses never skip grants or invent inventory.
- **Simulation status** is explicit in contracts, UI, receipts, and tests.

Do not file security issues with live credentials or personal data.

## License

Apache License 2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE).

Build provenance for this public export: [BUILD_PROVENANCE.md](BUILD_PROVENANCE.md).
