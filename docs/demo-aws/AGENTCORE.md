# AgentCore — design only (not deployed)

**Status:** Stretch design. **Do not deploy.** This submission uses Strands Agents SDK + Amazon Bedrock behind `/v1/agent/**`. AgentCore is not in the judge video, hosted demo, or public export.

The judge camera script is [SCRIPT.md](SCRIPT.md) (Script A, Dubai → London).

## Why later

Judges score Strands implementation and a live demo. AgentCore can strengthen Technical Implementation but is optional. This submission uses Strands Agents SDK + Amazon Bedrock behind `/v1/agent/**`. Hosted staging is live Bedrock; local clones default to fake mode. AgentCore is still not deployed.

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
- Identity: dedicated competition Bedrock role in `eu-west-2`, model `global.anthropic.claude-sonnet-4-6`.
- Observability: buyer-safe activity events only; no chain-of-thought, account ids, or model ids in buyer JSON.

## Out of scope until a later authorization

- `bedrock-agentcore` SDK wiring
- AgentCore Memory/Gateway/Identity services
- CloudFormation/Terraform AgentCore deploy
