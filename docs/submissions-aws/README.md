# AWS Agents for Humans — submission pack

**Status:** Final private checkpoint for Product Owner review. Not merged. Public export is blocked until this pack merges to private `main`.  
**Track:** Everyday Agents.  
**Hosted staging:** https://bookingdemo.reservedge.com (live Bedrock, process-local sessions).  
**AgentCore:** not deployed.

This directory plus [`docs/demo-aws/`](../demo-aws/README.md) is the competition documentation pack. Browser product HTTP is `/v1/agent/**`. The browser never calls Bedrock. Do not document `/v1/aws/**` as the UI path.

| Document                                                   | Role                                                           |
| ---------------------------------------------------------- | -------------------------------------------------------------- |
| This README                                                | Pack index                                                     |
| [DEVPOST.md](DEVPOST.md)                                   | Devpost description draft                                      |
| [BUILD_PROVENANCE.md](BUILD_PROVENANCE.md)                 | Judge-facing provenance                                        |
| [PROVENANCE.md](PROVENANCE.md)                             | Pre-existing vs competition-new (detail)                       |
| [HONESTY.md](HONESTY.md)                                   | Simulation, Curated offers, A4 wording                         |
| [UAT.md](UAT.md)                                           | Final human UAT Scripts A–E                                    |
| [COMP_AWS_06_EXPORT.md](COMP_AWS_06_EXPORT.md)             | Sanitized public-export sandbox (do not publish from an agent) |
| [PUBLIC_REPO_SANITIZATION.md](PUBLIC_REPO_SANITIZATION.md) | Public-export checklist                                        |
| [LIVE_UAT.md](LIVE_UAT.md)                                 | Live Bedrock configuration (no operator identities)            |

Operator IAM, Builder ID, and `iam/*.json` stay out of version control and out of the public export.

## What judges should see

Reservedge — Intent-to-Action booking agent — turns one natural-language trip into coordinated **flight**, **hotel**, and **parking** work in one Booking Chat.

- LiteAPI **sandbox research** for flights and hotels (not a ticket / not a reservation).
- Simulated **Curated offers** for parking, then a governed simulated reservation and simulated receipt.
- Strands Agents SDK + Amazon Bedrock interpret; code owns provenance, authorization, ranking, and money-sensitive state.

## What this cut claims

- Hosted staging uses live Bedrock behind `/v1/agent/**`.
- Local clone defaults to fake model mode (no cloud credentials).
- Code projector assigns **Explicit / Inferred / Proposed**.
- Parking Curated offers and A4 are **simulated**.
- Experience search is Prioticket / provider-limited. Rental is requirement-only.

## What this cut does not claim

- Amazon Bedrock AgentCore
- Real bookings, inventory holds, supplier contact, or card charges
- Live curated / reverse-bid marketplaces (do not name RDN)
- Durable sessions
- Production authentication

## Honesty (say this on camera)

Use [HONESTY.md](HONESTY.md):

- Flights/hotels = sandbox research only.
- Parking Curated offers = simulated supplier replies.
- A4 authorizes the simulated booking step. It never creates a real booking.
- `SIMULATED — NO REAL CHARGES OR RESERVATIONS`
- Session state is process-local and non-durable.
- AgentCore is not deployed.

## Local setup (fake mode)

Prerequisites match the repository root README: Python 3.12, uv 0.12+, Node.js 22+, pnpm 11.9.x, GNU Make. Cloud credentials are **not** required for fake mode.

```bash
cp .env.example .env
make setup
```

Copy names from [`infra/aws/env.example`](../../infra/aws/env.example). Keep `ITAA_AWS_MODEL_MODE=fake`. Do not commit secret values.

### Combined process (simplest local demo)

```bash
ITAA_AWS_MODEL_MODE=fake \
uv run uvicorn itaa_aws_adapter.app:app \
  --app-dir adapters/aws-strands-bedrock-agentcore/src \
  --host 127.0.0.1 --port 8011
```

```bash
pnpm --filter @itaa/web dev
```

Open `http://127.0.0.1:5180`.

Restarting Python discards every in-memory agent session.

## Architecture

Source: [`docs/demo-aws/architecture.mmd`](../demo-aws/architecture.mmd)  
Rendered: [`docs/demo-aws/architecture.svg`](../demo-aws/architecture.svg)

## Demo script

[`docs/demo-aws/SCRIPT.md`](../demo-aws/SCRIPT.md) — Script A (Dubai → London), target 4:40–4:55.

## Tests

```bash
/usr/bin/make check
```

Human UAT: [UAT.md](UAT.md).

## Still gated from this pack

- Merge to private `main` (Product Owner)
- Public repository publish
- Devpost submit
- AgentCore deploy
