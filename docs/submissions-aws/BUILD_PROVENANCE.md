# Build provenance — AWS Agents for Humans

Hackathon: **AWS Agents for Humans** (Everyday Agents).  
Private development tree: `Nexcache-Limited/ITAA`.  
Intended public export: `Nexcache-Limited/reservedge-agents-for-humans` (Apache-2.0 after Product Owner publish).

The submitted project is the Strands buyer agent wrapping the governed façade, not a rebadge of earlier extraction work. Pre-existing platform components are disclosed below and in [PROVENANCE.md](PROVENANCE.md).

## Live checkpoint this pack describes

- Hosted competition staging: https://bookingdemo.reservedge.com
- Hosted sessions: process-local and non-durable
- Hosted planning: Strands Agents SDK + Amazon Bedrock (`ITAA_AWS_MODEL_MODE=live`)
- Local default: fake model mode (no cloud credentials)
- Amazon Bedrock AgentCore: **not deployed**

## Pre-existing (disclose; do not claim as this window’s invention)

- Cloud-neutral domain, application, policy, ranking, and contracts packages
- `GoldenPathFacade` A1–A4, isolation, idempotency, and simulated A4
- Isolated supplier simulator (ParkDirect, SkyShield, TerminalFlex)
- Local FastAPI golden path and React/Vite buyer UI
- Intent composer and Clarify & Plan chrome, including **Explicit / Inferred / Proposed**
- Client heuristic planner in `apps/web/src/intent-first/plan.ts` — labelled fallback only
- Buyer-safe orchestration reads (`GET /v1/orchestration/**`)
- Google adapter under `adapters/google` — **not claimed on this Devpost**

## Competition-period (this submission)

- AWS Strands adapter (`adapters/aws-strands-bedrock-agentcore`) — Plan/Execute, projector, closed tools
- Provider HTTP `/v1/aws/plan-turns` and `/v1/aws/execute-turns`
- Product BFF `/v1/agent/**`
- Browser Booking Chat wired to `/v1/agent/sessions`
- LiteAPI sandbox `flight.search` and `stay.search`
- Prioticket `experience.search` (provider-limited catalog)
- Conversation-first parking search → simulated **Curated offer** selection → simulated receipt
- This AWS Devpost / demo pack (`docs/submissions-aws`, `docs/demo-aws`)

## Authority split

| Layer              | May do                                                                                               | Must not do                                                            |
| ------------------ | ---------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------- |
| Strands + Bedrock  | Interpret and refine the objective; ask missing facts; propose tasks                                 | Approve grants; rank; change money-sensitive state; upgrade provenance |
| Code projector     | Assign Explicit / Inferred / Proposed; map PlanTurn → UI                                             | Treat model provenance as authoritative                                |
| Capability routing | Dispatch only buyer-authorized `flight.search`, `stay.search`, `parking.search`, `experience.search` | Invent rental inventory; contact suppliers before search authorization |
| `GoldenPathFacade` | Isolation, ranking, simulated A3/A4                                                                  | Trust an unconfirmed model proposal                                    |
| Human / UI         | Authorize search; take a Curated offer; authorize the simulated parking step                         | Be skipped by a tool call                                              |

## Public export source

This public tree was exported from private `Nexcache-Limited/ITAA` `main` at:

`f438e1802f7b5caf5c2bdca8d32f7f42a2570a6b`

(squash merge of PR #20 on 14 September 2026). Operator IAM, Builder ID, `.env`, and hosted origin files are excluded. See [PUBLIC_REPO_SANITIZATION.md](PUBLIC_REPO_SANITIZATION.md) and [COMP_AWS_06_EXPORT.md](COMP_AWS_06_EXPORT.md).
