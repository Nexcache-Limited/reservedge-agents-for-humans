# AWS Agents for Humans — submission pack

**Status:** Public Apache-2.0 competition export of private-main `c79d0a667b1605cf4cfbe338e7a0509ec0ffd867`.
**Default demo:** fake mode (`ITAA_AWS_MODEL_MODE=fake`) at `http://127.0.0.1:5180`.
**Track (recommended):** Everyday Agents.
**Local live Bedrock Plan UAT succeeded 7 September 2026** (allowlisted `global.anthropic.claude-sonnet-4-6`, one Bedrock cycle per planning turn). **This pack does not claim Amazon Bedrock AgentCore.**

Browser product HTTP is `/v1/agent/**`. Do not document `/v1/aws/**` as the UI path.

| Document | Role |
| ---------------------------------------------------------- | ----------------------------------------------------------------- |
| This README | Setup path, honesty, what is and is not claimed |
| [DEVPOST.md](DEVPOST.md) | Devpost description draft |
| [PROVENANCE.md](PROVENANCE.md) | Pre-existing vs competition-new |
| [HONESTY.md](HONESTY.md) | Simulation and human-approval wording |
| [UAT.md](UAT.md) | Fake-mode UAT (default demo) |
| [LIVE_UAT.md](LIVE_UAT.md) | Live Plan path UAT (generic credentials; no operator identifiers) |
| [PUBLIC_REPO_SANITIZATION.md](PUBLIC_REPO_SANITIZATION.md) | Public-export checklist |
| [COMP_AWS_06_EXPORT.md](COMP_AWS_06_EXPORT.md) | How this export was prepared |

Operator IAM JSON, account-scoped Bedrock setup notes, Builder ID details, and local agreement evidence are **not** in this public tree.

## What judges should see

Reservedge is a conversation-first buyer agent: an arbitrary free-form objective becomes clarification, a labelled multi-task plan, closed capability routing, then **simulated** parking execution behind A1–A4 when parking is actually in the plan. Stay research may call LiteAPI. Experience search may call Prioticket and can truthfully return empty when the provider catalog does not expose city inventory. Rental stays requirement-only.

**Strands decides what work is needed. Deterministic governance decides what is allowed.** Models cannot approve, dispatch, rank, or charge.

## What this cut claims

- Local fake-mode Strands Plan/Execute turns behind `/v1/agent/**` (default demo pack).
- Local live Bedrock Plan turns behind `ITAA_AWS_MODEL_MODE=live` and `ITAA_AWS_LIVE_INVOKE=1` (UAT 7 Sep 2026; one cycle per turn, ~6–8 s HTTP). See [LIVE_UAT.md](LIVE_UAT.md).
- Code projector assigns **Explicit / Inferred / Proposed**. The model cannot upgrade provenance.
- LiteAPI sandbox stay **research** (not booking). Configuration names only.
- Prioticket experience adapter integrated; city catalog currently provider-limited.
- Parking after plan confirm uses the existing governed façade (A1–A4, isolated simulated suppliers, locked JFK ranking vector) when parking is on the plan.
- Rental is requirement-only. No live car inventory.
- Supplier execution and payment are **simulated**. A4 `mode` must be `SIMULATED`.

## What this cut does not claim

- Amazon Bedrock AgentCore, or a recorded live-Bedrock judge video
- A production Bedrock deployment or public live URL
- Real bookings, inventory holds, supplier contact, or card charges
- Prioticket as a working Milan experience catalog until the provider provisions it
- Durable sessions (restart discards `as_*` sessions → `unknown_resource`)
- Production authentication
- Google/Gemini on this path

Default live mode without `ITAA_AWS_LIVE_INVOKE=1` still fails closed (`model: unavailable`). Do not set the invoke flag for the fake-mode demo.

## Honesty (say this on camera)

Use the canonical lines in [HONESTY.md](HONESTY.md):

- Supplier execution and payment are simulated. There are no real charges, reservations, or supplier bookings.
- `SIMULATED - NO REAL CHARGES OR RESERVATIONS`
- A4 is not a booking. Mode is `SIMULATED`.
- Session state is process-local and non-durable.
- Until a live recording is authorized: this recording uses fake model mode. It does not demonstrate live Bedrock or AgentCore.

## Local setup (fake mode)

Prerequisites match the repository root README: Python 3.12, uv 0.12+, Node.js 22+, pnpm 11.9.x, GNU Make. Cloud credentials are **not** required for fake mode.

```bash
cp .env.example .env
make setup
```

Copy names from [`infra/aws/env.example`](../../infra/aws/env.example). Keep `ITAA_AWS_MODEL_MODE=fake`. Do not commit secret values.

### Combined process (simplest local demo)

```bash
ITAA_AWS_MODEL_MODE=fake uv run uvicorn itaa_aws_adapter.app:app   --app-dir adapters/aws-strands-bedrock-agentcore/src   --host 127.0.0.1 --port 8011
```

```bash
pnpm --filter @itaa/web dev
```

Open `http://127.0.0.1:5180`.

### Preferred split topology

API on `:8011`, adapter on `:8080`. BFF HTTP-calls `/v1/aws/**` only.

```bash
ITAA_AWS_MODEL_MODE=fake ITAA_AWS_ADAPTER_URL=http://127.0.0.1:8080 uv run uvicorn itaa_api.app:app --app-dir apps/api/src --host 127.0.0.1 --port 8011
```

```bash
ITAA_AWS_MODEL_MODE=fake uv run uvicorn itaa_aws_adapter.app:app   --app-dir adapters/aws-strands-bedrock-agentcore/src   --host 127.0.0.1 --port 8080
```

```bash
pnpm --filter @itaa/web dev
```

Restarting Python discards every in-memory agent session.

## Architecture

Source: [`docs/demo-aws/architecture.mmd`](../demo-aws/architecture.mmd)
Rendered: [`docs/demo-aws/architecture.svg`](../demo-aws/architecture.svg)

## Demo script

[`docs/demo-aws/SCRIPT.md`](../demo-aws/SCRIPT.md) — ≤5-minute storyboard covering the seven required beats.
[`docs/demo-aws/LIVE_RECORDING.md`](../demo-aws/LIVE_RECORDING.md) — live env and shot list (recording remains gated).

## Tests

From the repository root, after `make setup`:

```bash
/usr/bin/make check
```

Narrower fake-mode evidence:

```bash
PYTHONPATH=adapters/aws-strands-bedrock-agentcore/src   uv run pytest adapters/aws-strands-bedrock-agentcore/tests tests/evals/test_comp_aws_04_*.py   tests/adversarial/test_comp_aws_04_*.py tests/security/test_comp_aws_04_strands_lock.py
pnpm --filter @itaa/web test
```

Step-by-step UAT is in [UAT.md](UAT.md).

## Still gated

- Hosted public live demo / deploy
- Final live-demo recording
- Devpost submit
- AgentCore deploy
- Real Prioticket booking or catalog enablement
