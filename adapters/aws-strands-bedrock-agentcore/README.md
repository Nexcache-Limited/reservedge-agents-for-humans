# AWS Strands / Bedrock adapter — COMP-AWS-01.

AWS Strands, Bedrock, and (later) AgentCore adapter around the cloud-neutral ITAA core.

COMP-AWS-01 implements fake Plan/Execute turns. Live Bedrock Plan turns were exercised in local UAT on 7 September 2026 behind `ITAA_AWS_MODEL_MODE=live` and `ITAA_AWS_LIVE_INVOKE=1` (one Bedrock cycle per planning turn; earlier two-cycle ~10–16 s HTTP figures are superseded). That live Plan path is frozen for the competition unless a demonstrated defect appears. Default live mode without that invoke flag stays **fail-closed** (`model: unavailable`). AgentCore is design-only (`docs/demo-aws/AGENTCORE.md`).

## Authority

Strands (when live) may interpret, clarify, and select closed tools. Code owns provenance, ranking, policy, ids, idempotency, isolation, and A1–A4. Models cannot approve, dispatch, or charge.

Browser product HTTP is `/v1/agent/**` (COMP-AWS-02). This adapter exposes **`/v1/aws/plan-turns`** and **`/v1/aws/execute-turns`**. Do not document `/v1/aws/**` as the UI path.

## Mode

| Env                    | Values                                                                                    |
| ---------------------- | ----------------------------------------------------------------------------------------- |
| `ITAA_AWS_MODEL_MODE`  | `fake` (default) \| `live`. Unknown fails closed. Live never silently falls back to fake. |
| `ITAA_AWS_ADAPTER_URL` | BFF → this process. Default `http://127.0.0.1:8080`. Never `VITE_*`.                      |
| `ITAA_AWS_TIMEOUT_MS`  | Live deadline 5000–45000. Required in live.                                               |
| `ITAA_AWS_MODEL`       | Allowlisted live id: `global.anthropic.claude-sonnet-4-6`.                                |
| `ITAA_AWS_LIVE_TEST`   | `1` for credentialed tests (skipped in CI).                                               |
| `ITAA_AWS_LIVE_INVOKE` | `1` allows LiveOrchestrator to call Bedrock. Default unset: live mode fails closed.       |

`ITAA_AWS_LIVE=1` selects live only when `ITAA_AWS_MODEL_MODE` is unset.

## Local

Preferred: API `:8000`, this adapter `:8080`. BFF may call `/v1/aws/**` only. It must never recurse into `/v1/agent/**` or HTTP-loopback into the same worker.

```text
PYTHONPATH=adapters/aws-strands-bedrock-agentcore/src uv run pytest adapters/aws-strands-bedrock-agentcore/tests
```

Live extra (`strands-agents==1.54.0`) is declared here. Default live plan/execute does not invoke Bedrock. `ITAA_AWS_LIVE_INVOKE=1` is the explicit invoke gate for authorized local UAT only.

Google/Gemini is not used on this path.

## Fake-mode limitations (not an integration blocker)

The fake projector does not alias airport names (`Heathrow` → `LHR`) or parse day-month plus a bare ordinal (`14 October … the 19th`). Structured `answers` (`dates`, `startDate`, `endDate`, `departureAirport`, `carNeed`) update projected facts. Natural-language aliases remain a live-Bedrock / demo consideration.
