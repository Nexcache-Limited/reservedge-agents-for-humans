# Live UAT (Bedrock Plan path)

Fake-mode and the 14 September 2026 human Scripts A–E live in [UAT.md](UAT.md). This page is the live Bedrock Plan gate.

**Current competition staging:** https://bookingdemo.reservedge.com uses live Amazon Bedrock through Strands Agents SDK. Sessions are process-local. AgentCore is not deployed.

**Local default remains fake.** Do not set `ITAA_AWS_LIVE_INVOKE=1` except for authorized local UAT.

Earlier local Plan UAT (7 September 2026) proved one Bedrock cycle per planning turn (~6–8 s HTTP). The judge video and hosted demo supersede that rehearsal’s Demo C → B → A camera sequence; use [SCRIPT.md](../demo-aws/SCRIPT.md) (Script A, Dubai → London).

## Configuration (names only)

| Item         | Value                                                                      |
| ------------ | -------------------------------------------------------------------------- |
| Mode         | `ITAA_AWS_MODEL_MODE=live`                                                 |
| Invoke gate  | `ITAA_AWS_LIVE_INVOKE=1` (local UAT only)                                  |
| Timeout      | `ITAA_AWS_TIMEOUT_MS=30000`                                                |
| Model        | `ITAA_AWS_MODEL=global.anthropic.claude-sonnet-4-6`                        |
| Region       | `eu-west-2`                                                                |
| Provider     | Amazon Bedrock via Strands `BedrockModel`                                  |
| Product HTTP | Combined `itaa_aws_adapter.app` → `/v1/agent/**` (in-process `/v1/aws/**`) |

Live failures stay fail-closed (`model: unavailable`) or, for timeout/schema only, the labelled projector (`FALLBACK_DETERMINISTIC`). There is no silent fake-fixture substitution. The browser never calls Bedrock.

Operator AWS profile and role names are not recorded here. Owner supplies credentials at runtime. Do not commit keys.

## Local product-path command (authorized)

```bash
ITAA_AWS_MODEL_MODE=live ITAA_AWS_LIVE_INVOKE=1 \
ITAA_AWS_TIMEOUT_MS=30000 ITAA_AWS_MODEL=global.anthropic.claude-sonnet-4-6 \
uv run uvicorn itaa_aws_adapter.app:app \
  --app-dir adapters/aws-strands-bedrock-agentcore/src \
  --host 127.0.0.1 --port 8011
```

Unset `ITAA_AWS_LIVE_INVOKE` when finished. Restarting Python discards every `as_*` session.

## Local one-cycle Plan UAT (accepted 7 September 2026)

Live Plan forces `PlanTurn` structured output on the first Bedrock cycle. Fake mode is unchanged.

| Turn           | Cycles | Structured on cycle 1 | HTTP wall | Bedrock latency | Tokens in / out / total | Fallback |
| -------------- | ------ | --------------------- | --------- | --------------- | ----------------------- | -------- |
| Demo C initial | 1      | yes (`tool_use`)      | 5.97 s    | 5664 ms         | 2321 / 452 / 2773       | no       |
| Demo C refine  | 1      | yes (`tool_use`)      | 7.64 s    | 7425 ms         | 2345 / 546 / 2891       | no       |
| Demo A plan    | 1      | yes (`tool_use`)      | 5.69 s    | 5475 ms         | 2360 / 550 / 2910       | no       |

Projector, not the model, remains authoritative for provenance.

## Hosted human UAT (14 September 2026)

See [UAT.md](UAT.md): Scripts A–C passed; Script D honesty passed with accepted MXP clarification weakness; Script E functional with accepted typo-spam duplication. The judge video avoids Milan/MXP and typo-spam.
