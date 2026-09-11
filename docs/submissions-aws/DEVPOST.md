# Devpost description draft

**Not submitted.** Product Owner owns the Devpost form, track confirmation, Builder ID, and optional live demo link.

**Working title:** Reservedge — an intent-first buyer agent for everyday trip errands
**Recommended track:** Everyday Agents
**Built with:** Strands Agents SDK, Amazon Bedrock Plan UAT on allowlisted `global.anthropic.claude-sonnet-4-6`, LiteAPI sandbox stay research, Prioticket experience adapter, local FastAPI + React UI
**License:** Apache License 2.0
**Public repo:** https://github.com/Nexcache-Limited/reservedge-agents-for-humans
**Do not check or imply:** Amazon Bedrock AgentCore, real bookings, or a production URL. Do not claim Prioticket as a working Milan experience catalog. Do not claim a live-Bedrock judge video until Product Owner records one. Do not paste Builder ID email or AWS account identifiers into the form from this repository — they are not in this tree.

---

## Short description (paste)

People lose hours to small trip errands: a hotel near the venue, something to do in the city, a car on landing, airport parking. Each one is a form, a comparison, and a payment decision. Reservedge starts from what you actually said — not from a domain picker — and turns that free-form objective into a small set of blocking questions, a plan labelled Explicit / Inferred / Proposed, and closed capability routing.

Stay research can query LiteAPI. Experience search can query Prioticket and will say when the provider catalog is empty. Parking still uses a governed simulated path with A1–A4. Rental stays requirement-only. Nothing here is a real booking: `SIMULATED - NO REAL CHARGES OR RESERVATIONS`. AgentCore is not in this submission.

---

## What it does

Reservedge is a privacy-first **Intent to Action Agent**. You type an arbitrary objective the way you would say it out loud. The Strands buyer orchestrator interprets it, asks at most three blocking questions, and returns a structured plan. A code projector — not the model — assigns **Explicit**, **Inferred**, or **Proposed** and routes to:

- `stay.search` — LiteAPI sandbox hotel research (not a booking)
- `experience.search` — Prioticket adapter; city inventory currently provider-limited
- `parking.search` — labelled simulated suppliers
- `rental.search` — requirement-only, no invented inventory

When parking is on the confirmed plan, the existing golden path still requires you at every approval:

1. **A1** Confirm requirement (research scope; no supplier contact yet)
2. **A2** Authorize disclosure to three isolated simulated suppliers
3. Isolated simulated offers, deterministic ranking, grounded recommendation
4. **A3** Confirm offer selection
5. **A4** Authorize a **simulated** reservation

The model cannot skip a grant, change a score, or place a charge.

---

## Who it is for

Travellers and households who already know *what they are trying to get done* and should not have to become form experts before a buyer agent is allowed to help. Everyday Agents: trip chores around a destination, with a human still on the approval loop.

---

## How it works (technical, honest)

Browser → product BFF `POST /v1/agent/sessions` (and turns, confirm, SSE). The BFF forwards only to `/v1/aws/plan-turns` and `/v1/aws/execute-turns`. Strands, boto3, and Bedrock stay inside `adapters/`. Closed tools wrap the cloud-neutral `GoldenPathFacade` and the stay/experience ports. Unknown tools fail closed. Planning turns do not bind mutating tools.

This submission’s working demonstration recording uses **`ITAA_AWS_MODEL_MODE=fake`** until Product Owner records a live video. Live Bedrock Plan turns were exercised locally on 7 September 2026 against allowlisted `global.anthropic.claude-sonnet-4-6` (one Bedrock cycle per planning turn, ~6–8 s HTTP). LiteAPI sandbox stay search returned destination-dated hotel research in later UAT. Prioticket OAuth works; city-linked catalog inventory is not yet provisioned. Default live mode without `ITAA_AWS_LIVE_INVOKE=1` still fails closed. AgentCore is out of scope.

---

## What we reused vs what we built for the hackathon

See [PROVENANCE.md](PROVENANCE.md). Pre-existing: domain/policy/ranking, A1–A4, simulated suppliers, composer and Clarify & Plan chrome. Competition-new: Strands Plan/Execute, `/v1/aws/**`, `/v1/agent/**`, conversation-first multi-domain routing, LiteAPI and Prioticket adapters, agent-visible UI wiring, this pack.

---

## Demo video notes (for the upload form)

Maximum 5 minutes. Script: [`docs/demo-aws/SCRIPT.md`](../demo-aws/SCRIPT.md). Cover (1) the problem, (2) who it is for, (3) why it matters, then the seven product beats. Voiceover is enough; no face required.

Architecture diagram: [`docs/demo-aws/architecture.svg`](../demo-aws/architecture.svg).

---

## Optional fields

| Field | Value |
| -------------------- | ------------------------------------------------------------------------------------------------- |
| Public repo URL | https://github.com/Nexcache-Limited/reservedge-agents-for-humans |
| License | Apache License 2.0 |
| AWS Builder ID | Operator-only; not stored in this public tree |
| Live demo URL | None. Local only. Live Plan UAT is not a public URL. |
| builder.aws.com post | Bonus; not started. Title must include “Agents for Humans”. |
