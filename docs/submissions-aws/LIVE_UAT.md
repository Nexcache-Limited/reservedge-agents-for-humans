# Live UAT (local Bedrock Plan path)

Fake-mode UAT remains in [UAT.md](UAT.md). This page is the live Bedrock Plan gate.

**Status (7 September 2026):** Dedicated-role smoke test succeeded. Local product-path UAT (`POST /v1/agent/sessions` and turns) succeeded for Demo C then Demo A, including the accepted one-cycle structured-output path (~6–8 s HTTP). A full browser-level rehearsal of the intended judge sequence (Demo C → B → A, A1–A4, simulated receipt) succeeded the same day. A1–A4 human gates were unchanged and still required. The live Plan path is frozen unless a demonstrated defect appears. **Default app mode remains fake.** Do not leave `ITAA_AWS_LIVE_INVOKE=1` set except for authorized local UAT or an authorized live recording.

**Still blocked:** AgentCore deploy, final live-demo recording until Product Owner authorizes that take, public GitHub push, Devpost submit.

## Configuration used for local UAT

| Item         | Value                                                                                                                                                    |
| ------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Mode         | `ITAA_AWS_MODEL_MODE=live`                                                                                                                               |
| Invoke gate  | `ITAA_AWS_LIVE_INVOKE=1` (local UAT only)                                                                                                                |
| Timeout      | `ITAA_AWS_TIMEOUT_MS=30000`                                                                                                                              |
| Model        | `ITAA_AWS_MODEL=global.anthropic.claude-sonnet-4-6` (allowlisted)                                                                                        |
| Region       | Configurable via `AWS_REGION` / `AWS_DEFAULT_REGION` (local UAT used `eu-west-2`)                                                                        |
| Provider     | Amazon Bedrock via Strands `BedrockModel` (`strands-agents==1.54.0`)                                                                                     |
| Identity     | Default AWS SDK credential chain (environment, shared config, or IAM role). No account ids or operator profile names are documented in this public tree. |
| Product HTTP | Combined `itaa_aws_adapter.app` → `/v1/agent/**` (in-process `/v1/aws/**`)                                                                               |

Live failures stay fail-closed (`model: unavailable`) or, for timeout/schema only, the labelled projector (`FALLBACK_DETERMINISTIC`). There is no silent fake-fixture substitution.

## Recheck model availability (inspect)

Use whatever identity your SDK chain already provides. Do not commit profile names or account identifiers.

```bash
aws sts get-caller-identity --query Arn --output text
aws bedrock get-foundation-model-availability \
  --region "${AWS_REGION:-eu-west-2}" \
  --model-id anthropic.claude-sonnet-4-6 \
  --query '{modelId:modelId,agreement:agreementAvailability.status,auth:authorizationStatus,entitlement:entitlementAvailability,region:regionAvailability}' \
  --output json
```

Expect an IAM role (or equivalent) that is authorized for Bedrock invoke, and `agreementAvailability.status=AVAILABLE` if your account uses Marketplace agreement for that model.

## Smoke-test command (already run; do not treat as the product path)

```bash
aws bedrock-runtime converse \
  --region "${AWS_REGION:-eu-west-2}" \
  --model-id global.anthropic.claude-sonnet-4-6 \
  --messages '[{"role":"user","content":[{"text":"Reply with the single word pong."}]}]' \
  --inference-config '{"maxTokens":8,"temperature":0}' \
  --query 'output.message.content[0].text' \
  --output text
```

## Local product-path UAT (authorized)

```bash
AWS_REGION="${AWS_REGION:-eu-west-2}" \
AWS_DEFAULT_REGION="${AWS_DEFAULT_REGION:-eu-west-2}" \
ITAA_AWS_MODEL_MODE=live ITAA_AWS_LIVE_INVOKE=1 \
ITAA_AWS_TIMEOUT_MS=30000 ITAA_AWS_MODEL=global.anthropic.claude-sonnet-4-6 \
uv run uvicorn itaa_aws_adapter.app:app \
  --app-dir adapters/aws-strands-bedrock-agentcore/src \
  --host 127.0.0.1 --port 8011
```

Prefer Demo C first (ambiguous objective → clarification → structured answers → same-session refine), then Demo A, then A1–A4 on the existing parking golden path. Unset `ITAA_AWS_LIVE_INVOKE` when finished.

## Local UAT result (7 September 2026)

| Step              | Result                                                                                              |
| ----------------- | --------------------------------------------------------------------------------------------------- |
| Demo C initial    | `/v1/agent/sessions` 200, `fallback=false`, phase `clarify`, dates question, no JFK                 |
| Demo C refine     | Same `as_*` session, structured LHR + 14–19 Oct 2026, phase `forming`, rental **Explicit**          |
| Demo A plan       | Parking **Explicit**, no false Explicit hotel, `fallback=false`                                     |
| Demo A confirm    | `prepare_parking_requirement` handoff JFK 2026-09-03 → 2026-09-08                                   |
| A1–A4             | Confirm / dispatch / accept / simulated authorize all 200; SkyShield locked 14800; `mode=SIMULATED` |
| Fake substitution | None. Timeout/schema fallback did not fire.                                                         |

Token/latency **superseded:** the first product-path UAT on 7 September 2026 used two Bedrock cycles per turn (prose, then reformat). Those HTTP wall times were ~10 s / ~16 s / ~14 s (Demo C initial 2213/537 tokens, 6758 ms; refine 5079/1105, 9397 ms; Demo A 5135/1199, 10314 ms). Do not quote them as current.

## One-cycle Plan UAT (accepted 7 September 2026)

Live Plan now forces `PlanTurn` structured output on the **first** Bedrock cycle. Fake mode is unchanged. `PlanTurn` schema, projector authority, provenance, A1–A4, and `/v1/agent/**` are unchanged. This live planning path is **frozen** for the competition unless a demonstrated defect appears.

| Turn           | Cycles | Structured on cycle 1 | HTTP wall | Bedrock latency | Tokens in / out / total | Fallback |
| -------------- | ------ | --------------------- | --------- | --------------- | ----------------------- | -------- |
| Demo C initial | 1      | yes (`tool_use`)      | 5.97 s    | 5664 ms         | 2321 / 452 / 2773       | no       |
| Demo C refine  | 1      | yes (`tool_use`)      | 7.64 s    | 7425 ms         | 2345 / 546 / 2891       | no       |
| Demo A plan    | 1      | yes (`tool_use`)      | 5.69 s    | 5475 ms         | 2360 / 550 / 2910       | no       |

Projector, not the model, remains authoritative for provenance and blocking questions shown in Clarify & Plan.

Authorized live recording configuration and shot list: [LIVE_RECORDING.md](../demo-aws/LIVE_RECORDING.md). Do not record the judge video until Product Owner authorizes that take.

## Browser rehearsal (7 September 2026)

Full intended sequence at `http://127.0.0.1:5180` against the live Plan process above. Parking intake used the existing G1 **fake** Google extractor on `:8080` (off camera; not live Gemini). Plan path remained frozen (no schema/prompt/token further work).

| Beat           | Result                                                                                                                              |
| -------------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| Demo C wait UX | **Understanding your objective** visible for the 5–8 s Plan turn; `aria-busy` on Start booking                                      |
| Demo C clarify | Phase Gathering; exact dates; no JFK in the main plan; no fallback                                                                  |
| Demo C refine  | Dates `2026-10-14`–`2026-10-19` via **Answer and update plan**; **Updating your plan** during the wait; rental **Explicit**; no JFK |
| Demo B         | Rental **Explicit**, parking **Inferred** EDI, hotel **Proposed**, flight not Explicit; **Confirm plan** left honesty copy visible  |
| Demo A plan    | Parking **Explicit**; no hotel; JFK 3–8 Sep 2026; `fallback=false`                                                                  |
| Demo A handoff | **Begin parking requirement** → `/intents/new/parking`. **Use the example** then Send; intent `pi_*`                                |
| A1             | Confirm requirement; “No supplier has been contacted yet.”                                                                          |
| A2             | **Send this request**; isolated ParkDirect / SkyShield / TerminalFlex; “Suppliers are answering.”                                   |
| Rank           | **See the recommendation**; SkyShield **USD 148.00**; buyer JSON omits `scoreMicros`                                                |
| A3             | **Confirm offer selection**                                                                                                         |
| A4             | **Authorize USD 148.00** → `/confirmation`; **SIMULATED RECEIPT**; no card charged                                                  |
| Leakage        | No model id, region, Bedrock, token counts, or fallback banner in the buyer pane                                                    |

This rehearsal is not the judge video. Unset `ITAA_AWS_LIVE_INVOKE` after the take.
