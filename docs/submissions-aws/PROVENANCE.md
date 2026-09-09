# Provenance disclosure — pre-existing vs competition-new

Hackathon: **AWS Agents for Humans** (Everyday Agents track).  
This public export is generated from private-main checkpoint `0e24c62b203dd046125acf313a08dc78b77ba14d`. See [BUILD_PROVENANCE.md](../../BUILD_PROVENANCE.md).

The submitted _project_ is the Strands buyer agent wrapping the governed façade. It is not a rebadge of the earlier platform extraction, and it is not a claim that the whole ITAA platform was built during the competition window.

## Pre-existing (disclose; do not claim as this window’s invention)

Created before or independently of the Agents for Humans Strands cut:

- Cloud-neutral domain, application, policy, ranking, and contracts packages
- `GoldenPathFacade` A1–A4, isolation, idempotency, and simulated A4
- Isolated supplier simulator (ParkDirect, SkyShield, TerminalFlex) and the locked JFK ranking vector (SkyShield 671000)
- Local FastAPI golden path and React/Vite buyer UI
- Intent composer and Clarify & Plan chrome, including **Explicit / Inferred / Proposed** labels
- Client heuristic planner in `apps/web/src/intent-first/plan.ts` — retained as **labelled fallback only**
- Buyer-safe orchestration reads (`GET /v1/orchestration/**`)
- Google adapter under `adapters/google` — **not claimed on this Devpost**

## Competition-new (this window)

Developed during the AWS Agents for Humans competition period:

- AWS Strands adapter (`adapters/aws-strands-bedrock-agentcore`) — fake Plan/Execute turns, live Plan path behind `ITAA_AWS_LIVE_INVOKE`, projector, closed tools
- Provider HTTP `/v1/aws/plan-turns` and `/v1/aws/execute-turns`
- Product BFF `/v1/agent/**` and conversation-first agent session / domain state
- Browser wiring: Start booking → `/v1/agent/sessions`; Clarify & Plan renders the BFF `PlanProjection`
- AWS env/docs under `infra/aws`
- This AWS Devpost / demo pack (`docs/submissions-aws`, `docs/demo-aws`)
- COMP-AWS-04 evals, adversarial, and Strands lock tests

## Authority split (do not blur on camera)

| Layer              | May do                                                                                                               | Must not do                                                                                                                                           |
| ------------------ | -------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------- |
| Strands (adapter)  | Interpret objective; ask ≤3 blocking questions; propose tasks; choose closed tools; emit buyer-safe copy             | Approve A1–A4; rank; change scores/winner/totals; mint PI/governance ids; copy raw text into PurchaseIntent or supplier envelopes; upgrade provenance |
| Code projector     | Assign Explicit / Inferred / Proposed; cap questions; map PlanTurn → UI `PlanProjection`; downgrade invalid Explicit | Invent parking as the only task; treat model provenance as authoritative                                                                              |
| `GoldenPathFacade` | A1–A4, isolation, ranking, idempotency, simulated A4                                                                 | Trust an unconfirmed model proposal                                                                                                                   |
| Human / UI         | Confirm plan; A1–A4 consents                                                                                         | Be skipped by a tool call                                                                                                                             |

## License

This public export is licensed under Apache License 2.0. See [LICENSE](../../LICENSE) and [NOTICE](../../NOTICE).
