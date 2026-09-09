# Reservedge — Intent to Action Agent

**AWS Agents for Humans · Everyday Agents track**

Reservedge is a privacy-first **Intent to Action Agent (ITAA)**. A buyer types an open-ended objective the way they would say it out loud. Strands Agents interprets that objective, asks at most three blocking questions, and returns a structured multi-task plan. Deterministic code — not the model — labels each task **Explicit**, **Inferred**, or **Proposed**, then the existing governed parking path still requires a human at **A1–A4**.

This repository is the public competition export of an accepted local checkpoint. It is a **working local product**, not a stub. Offers, availability, and authorizations in this cut are **simulated**. There are no real charges, reservations, or supplier bookings.

```text
Browser  →  /v1/agent/**  (product BFF)
                 ↓
            /v1/aws/**    (Strands adapter + code projector)
                 ↓
            GoldenPathFacade A1–A4 (simulated suppliers)
```

The browser talks to `/v1/agent/**`. Do not treat `/v1/aws/**` as the UI path.

## What this checkpoint is

- **Strands Agents SDK** Plan/Execute behind a closed tool set
- **Amazon Bedrock live Plan path** (allowlisted model; fail-closed unless explicitly invoked)
- **Code-validated structured agent state** (`PlanTurn` → UI `PlanProjection`)
- **Explicit / Inferred / Proposed** provenance assigned by the projector, not the model
- **A1–A4 human authorization** before any simulated supplier work or simulated reservation
- Default judge/local setup is **fake mode** — no cloud credentials required

Local live Bedrock Plan turns were exercised on 7 September 2026 (one Bedrock cycle per planning turn). That is not Amazon Bedrock AgentCore and is not a public live demo. AgentCore is **not deployed** and is not claimed.

## What this checkpoint is not

Do not read the demo as a live marketplace. This cut does **not** include:

- real bookings, inventory holds, or contact with real suppliers
- real payments or card charges
- production supplier integrations (external booking APIs are a later workstream)
- durable persistence or cross-session resume
- production authentication
- a native iOS/Android application (responsive mobile-web only)
- Amazon Bedrock AgentCore
- a hosted public live-demo URL

## Pre-existing platform vs competition-period AWS work

**Do not treat all of ITAA as hackathon-week work.** See [NOTICE](NOTICE) and [docs/submissions-aws/PROVENANCE.md](docs/submissions-aws/PROVENANCE.md).

**Already in the Reservedge platform** (before or independent of this competition window): cloud-neutral domain and application core, disclosure/isolation, A1–A4 governance, deterministic ranking, simulated suppliers, FastAPI golden path, React/Vite buyer UI, and the intent-first substrate.

**Competition-period AWS work:** Strands Agents integration, Bedrock live Plan path, `/v1/aws/**`, `/v1/agent/**`, conversation-first agent session/domain state, and the AWS demo/submission pack under `docs/demo-aws` and `docs/submissions-aws`.

The Google/Gemini adapter under `adapters/google` is not part of this Devpost claim.

## Honesty (say this on camera)

Canonical wording: [docs/submissions-aws/HONESTY.md](docs/submissions-aws/HONESTY.md).

- Supplier execution and payment are simulated. `SIMULATED - NO REAL CHARGES OR RESERVATIONS`
- A1–A4 are distinct human grants. Opening a page is not approval. The model cannot approve, dispatch, rank, or charge.
- **A4 is not a booking.** Mode is `SIMULATED`.
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

The clone URL is the **proposed** public repository name. Do not treat it as already published until Product Owner review completes.

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

| Command                        | Purpose                                                     |
| ------------------------------ | ----------------------------------------------------------- |
| `make setup`                   | Install Python and TypeScript workspace dependencies        |
| `make check`                   | Complete local quality gate                                 |
| `make test`                    | Python pytest plus ui-kit, contracts, and web Vitest suites |
| `make secrets`                 | Secret-pattern scan                                         |
| `pnpm --filter @itaa/web test` | Web unit/component tests                                    |

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

## Architecture

Conceptual layers:

```text
Responsive Web UI
    ↓
Intent / Clarify & Plan  (/v1/agent/**)
    ↓
Strands Plan/Execute + code projector
    ↓
Governance (A1–A4)
    ↓
Supplier isolation + ranking
    ↓
Simulated suppliers
```

Models may extract or explain. Code owns policy, eligibility, ranking, approvals, money, isolation, idempotency, and simulation status.

Diagram: [docs/demo-aws/architecture.svg](docs/demo-aws/architecture.svg) · source [docs/demo-aws/architecture.mmd](docs/demo-aws/architecture.mmd)

See [ADR-0002](docs/adr/ADR-0002-cloud-neutral-boundaries.md) and [ADR-0003](docs/adr/ADR-0003-simulation-boundary.md).

## Repository map

| Path                                     | Responsibility                                               |
| ---------------------------------------- | ------------------------------------------------------------ |
| `apps/api`                               | Local FastAPI composition root (process-local simulation)    |
| `apps/web`                               | React/Vite buyer client (intent-first + parking golden path) |
| `apps/supplier-simulator`                | Isolated simulated suppliers                                 |
| `packages/domain`                        | Cloud-neutral domain; no I/O                                 |
| `packages/application`                   | Use cases and ports; no providers                            |
| `packages/contracts`                     | Canonical JSON Schema 2020-12 and generated types            |
| `packages/policy`                        | Deterministic disclosure, hashing, approvals, isolation      |
| `packages/ranking`                       | Deterministic scoring and explanation facts                  |
| `adapters/aws-strands-bedrock-agentcore` | Strands / Bedrock adapter (fake default; live Plan opt-in)   |
| `docs/submissions-aws`                   | Competition honesty, provenance, UAT, Devpost draft          |
| `docs/demo-aws`                          | Demo script, architecture, AgentCore design-only note        |

Local Compose (`compose.yaml`) provides an empty PostgreSQL on host port **5433**. The current golden path does **not** persist product state there.

## Security and privacy

- **Supplier isolation.** Each simulated supplier receives only its authorized envelope.
- **Minimum disclosure.** A2 approves exact fields before dispatch.
- **Human authorization.** A1–A4 are distinct grants. A4 is not a booking.
- **Simulation status** is explicit in contracts, UI, receipts, and tests.

Do not file security issues with live credentials or personal data.

## License

Apache License 2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE).

Build provenance for this public export: [BUILD_PROVENANCE.md](BUILD_PROVENANCE.md).
