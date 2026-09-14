# Devpost description

**Status:** Final submission copy  
**Working title:** Reservedge — Intent-to-Action booking agent  
**Track:** Everyday Agents  
**Built with:** Strands Agents SDK, Amazon Bedrock, local FastAPI + React UI, LiteAPI sandbox (flights/hotels), Prioticket (experiences), simulated parking Curated offers  
**Do not check or imply:** Amazon Bedrock AgentCore, real bookings, real payment, or live curated marketplaces.

---

## Short description (paste)

Reservedge is an Intent-to-Action travel agent that turns one conversational objective into coordinated flight, hotel and parking work. Built with Strands Agents SDK and Amazon Bedrock, it asks only for missing facts, waits for the buyer before consequential actions, searches connected sandbox providers, supports cross-domain refinements, and demonstrates a simulated Curated-offer parking flow through a simulated receipt.

---

## What it does

People lose hours to trip chores: a flight, a hotel, parking at the airport. Each one is a form, a comparison, and a payment decision. Reservedge starts from what you actually said — not from a domain picker — and turns that free-form objective into one **Booking Chat**.

Strands Agents SDK and Amazon Bedrock interpret and refine the trip. Deterministic application code owns provenance (**Explicit / Inferred / Proposed**), capability routing, disclosure, ranking, and money-sensitive state. The browser never calls Bedrock.

In this competition build:

1. **Flight** — LiteAPI sandbox research. Not a ticket.
2. **Hotel** — LiteAPI sandbox research. Not a reservation.
3. **Airport parking** — simulated **Curated offers** (ParkDirect, SkyShield, TerminalFlex) after the buyer authorizes search. **Take this one** then **Authorize** runs a governed simulated reservation. The receipt is simulated.
4. **Experience** — Prioticket adapter, provider-limited catalog.
5. **Rental** — requirement capability only; no production inventory adapter.

The curated path is the product pattern: standard search retrieves catalog results; curated/reverse-bid style replies demonstrate providers responding to the buyer’s requirements. **In this build those curated supplier responses are simulated.** No live curated marketplace is connected.

---

## Who it is for

Travellers who can say what they are trying to get done out loud and should not have to become form experts before a buyer agent is allowed to help. Everyday Agents: trip coordination with a human still on search authorization, offer selection, and simulated money action.

---

## How it works (technical, honest)

```text
Browser
  → /v1/agent/**          product BFF
  → /v1/aws/plan-turns
  → /v1/aws/execute-turns
  → Strands Agents SDK
  → Amazon Bedrock
  → code projector / closed capabilities
```

Hosted competition staging (https://bookingdemo.reservedge.com) uses **live Bedrock**. Sessions are process-local. Local clone defaults to fake model mode so judges can run without cloud credentials. AgentCore is not deployed.

Closed tools wrap the cloud-neutral `GoldenPathFacade`. Unknown tools fail closed. Planning turns do not bind mutating tools. Search capabilities dispatch only after conversational authorization.

---

## What we reused vs what we built for the hackathon

See [BUILD_PROVENANCE.md](BUILD_PROVENANCE.md) and [PROVENANCE.md](PROVENANCE.md). Pre-existing: domain/policy/ranking, A1–A4, simulated suppliers, composer and Clarify & Plan chrome. Competition-new: Strands Plan/Execute, `/v1/aws/**`, `/v1/agent/**`, LiteAPI/Prioticket capability wiring, conversation-first Booking Chat, this pack.

---

## Demo video notes (for the upload form)

Maximum 5 minutes. Target finished length **4:40–4:55**. Script: [`docs/demo-aws/SCRIPT.md`](../demo-aws/SCRIPT.md) — Script A only (Dubai → London). Architecture: [`docs/demo-aws/architecture.svg`](../demo-aws/architecture.svg). Honesty: [HONESTY.md](HONESTY.md).

**Demo video URL:** https://vimeo.com/1226748038?share=copy&fl=sv&fe=ci

---

## Submission fields

| Field                    | Value                                                                             |
| ------------------------ | --------------------------------------------------------------------------------- |
| Live demo URL            | https://bookingdemo.reservedge.com (competition staging — process-local sessions) |
| Demo video URL           | https://vimeo.com/1226748038?share=copy&fl=sv&fe=ci                               |
| Public repo URL          | https://github.com/Nexcache-Limited/reservedge-agents-for-humans                  |
| License                  | Apache License 2.0                                                                |
| AWS Builder ID           | Operator-only; not in this tree                                                   |
| Amazon Bedrock AgentCore | Not deployed                                                                      |
| builder.aws.com post     | Bonus; title must include “Agents for Humans”                                     |
