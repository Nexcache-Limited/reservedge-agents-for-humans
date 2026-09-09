# AgentCore — design only (not deployed)

**Status:** Stretch design. **Do not deploy.** Freeze: AgentCore is out of the required cut; stretch only after Demo A is recorded.  
This document does not claim AgentCore is in the submission.

## Why later

Judges score Strands implementation and a live demo. AgentCore can strengthen Technical Implementation but is optional. Fake-mode `/v1/agent` + closed tools is the current recorded product path. Local live Bedrock Plan UAT succeeded 7 September 2026; AgentCore is still not deployed.

## Intended shape (when authorized)

Keep the cloud-neutral core. AgentCore would wrap the **existing** AWS adapter process, not a second planner.

```text
Browser → /v1/agent/** (BFF)
            → /v1/aws/** (this adapter: Strands Plan/Execute + projector + GoldenPathFacade)
                 → optional AgentCore runtime hosting the same adapter
```

| Keep                                                                 | Do not                                         |
| -------------------------------------------------------------------- | ---------------------------------------------- |
| One Buyer Orchestrator; no Graph/Swarm                               | AgentCore tools that skip A1–A4                |
| Closed tool names from the freeze                                    | Browser calling AgentCore directly             |
| `ITAA_AWS_MODEL_MODE` fake/live                                      | Silent fallback to fake                        |
| Simulated A4                                                         | Real payment or supplier booking               |
| ADR-0002: Strands/boto3/AgentCore only under `adapters/` or `infra/` | AgentCore imports in `packages/` or `apps/api` |

## Runtime sketch (not implemented)

- Host `itaa_aws_adapter.app:app` as the AgentCore entry (same FastAPI wrapper).
- Session memory remains process-local unless a later freeze adds durability (`unsupported` today).
- Identity: a dedicated IAM role with Bedrock invoke permission via the default AWS SDK credential chain. Region and model are configurable (`AWS_REGION`, `ITAA_AWS_MODEL`). Local UAT used `eu-west-2` and allowlisted `global.anthropic.claude-sonnet-4-6`.
- Observability: buyer-safe activity events only; no chain-of-thought, account ids, or model ids in buyer JSON.

## Out of scope until a later authorization

- `bedrock-agentcore` SDK wiring
- Memory/Gateway/Identity services
- CloudFormation/Terraform deploy
- Public live URL
