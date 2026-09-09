# Live Bedrock recording configuration and shot list

**Do not record the judge video from this page until Product Owner authorizes that take.** This is the exact local configuration and shot list for that authorized recording. AgentCore deploy, public repo publish, and Devpost submit remain blocked.

Default storyboard copy and fake-mode draft: [SCRIPT.md](SCRIPT.md). Product path: `http://127.0.0.1:5180` → `/v1/agent/**`.

The live Plan path is **frozen** for the competition unless a demonstrated defect appears. Do not shrink `PlanTurn`, change prompts, add model routing, or further optimize tokens before submission.

A full browser-level live rehearsal of this sequence succeeded on 7 September 2026. That rehearsal is **not** the judge video.

## Configuration (exact)

Identity: default AWS SDK credential chain (environment, shared config, or IAM role). Region via `AWS_REGION` (local UAT used `eu-west-2`). Do not open AWS console, IAM, CloudWatch, or Bedrock on camera. Do not display account ids or operator profile names.

Three local processes. Combined AWS product API on **8011**. Vite on **5180**. Parking intake still extracts through the existing G1 fake Google adapter on **8080** (off camera; not live Gemini; not claimed on Devpost). Combined AWS already occupies 8011, so 8080 must be the fake extractor — not a second AWS adapter.

```bash
AWS_REGION=eu-west-2 \
AWS_DEFAULT_REGION=eu-west-2 \
ITAA_AWS_MODEL_MODE=live \
ITAA_AWS_LIVE_INVOKE=1 \
ITAA_AWS_TIMEOUT_MS=30000 \
ITAA_AWS_MODEL=global.anthropic.claude-sonnet-4-6 \
uv run uvicorn itaa_aws_adapter.app:app \
  --app-dir adapters/aws-strands-bedrock-agentcore/src \
  --host 127.0.0.1 --port 8011
```

```bash
ITAA_GOOGLE_MODEL_MODE=fake \
uv run uvicorn itaa_google_adapter.app:app \
  --app-dir adapters/google/src \
  --host 127.0.0.1 --port 8080
```

```bash
pnpm --filter @itaa/web dev
```

Open **`http://127.0.0.1:5180`**. Vite proxies `/v1` to `:8011` (same origin; do not browse `:8011` or `:8080`).

Unset `ITAA_AWS_LIVE_INVOKE` when the take is finished. Restarting Python discards every `as_*` session.

### Capture chrome

- Browser window 1440×940 (or full desktop with bookmarks and extensions hidden).
- Address bar may show `127.0.0.1:5180` only. Do not show DevTools, Network, or a second terminal with env vars.
- Do not display model id, profile name, account id, token counts, or `ITAA_*` on screen.

### Expected Plan-turn timing (one Bedrock cycle; 7 September 2026)

Supersedes the earlier two-cycle ~10–16 s HTTP figures. See [LIVE_UAT.md](../submissions-aws/LIVE_UAT.md).

| Turn           | HTTP wall | Bedrock latency | Tokens in / out | Cycles | Structured on cycle 1 |
| -------------- | --------- | --------------- | --------------- | ------ | --------------------- |
| Demo C initial | ~6.0 s    | 5664 ms         | 2321 / 452      | 1      | yes                   |
| Demo C refine  | ~7.6 s    | 7425 ms         | 2345 / 546      | 1      | yes                   |
| Demo A plan    | ~5.7 s    | 5475 ms         | 2360 / 550      | 1      | yes                   |

Hold the camera on buyer-safe progress for the whole wait. Composer: **Understanding your objective**. Refine: **Updating your plan**. Abort the take if **Using the local planner (labelled)** appears.

## Shot list (full intended sequence)

Paste objectives **exactly**. Same-session refinement uses **Answer and update plan** (structured dates / departing-from), not a free-form note.

Fill date fields **one at a time**. Filling start and end in parallel can race and clear the other field.

| Time (guide) | Shot           | Action                                                                                                                                                                 | Must show                                                                                                                                     | Must not show                                                                  |
| ------------ | -------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------ |
| 0:00–0:40    | Composer       | Cursor in “What are you planning or trying to get done?”                                                                                                               | Honesty: nothing sent to any supplier                                                                                                         | AWS console; model id                                                          |
| 0:40–1:00    | Demo C paste   | Paste the Demo C sentence. **Start booking**. Hold 5–8 s                                                                                                               | **Understanding your objective**; `aria-busy` on Start booking                                                                                | Fallback copy; JFK; SkyShield                                                  |
| 1:00–1:30    | Demo C clarify | Clarify & plan, phase Gathering                                                                                                                                        | Dates blocking card; rental not canned JFK parking                                                                                            | Operator tokens; `planTurn` JSON                                               |
| 1:30–1:55    | Demo C refine  | Start `2026-10-14`, then end `2026-10-19`. If departing-from is shown, `LHR`. **Answer and update plan**. Hold 5–8 s                                                   | **Updating your plan**                                                                                                                        | Second “reformat” wait; fake JFK collapse                                      |
| 1:55–2:10    | Demo C formed  | Same session, Forming                                                                                                                                                  | Rental **Explicit**; 14–19 Oct; no JFK                                                                                                        | Fallback                                                                       |
| 2:10–2:50    | Demo B         | New **Start booking**. Paste Demo B. Wait 5–8 s, then point at chips                                                                                                   | Rental **Explicit** · parking **Inferred** · hotel **Proposed**. **Confirm plan**. Honesty copy still visible                                 | Flight as Explicit; SkyShield ranking                                          |
| 2:50–3:20    | Demo A plan    | New session. Paste Demo A. Wait 5–8 s                                                                                                                                  | Parking **Explicit**; no false Explicit hotel                                                                                                 | Fallback; model id                                                             |
| 3:20–3:50    | Demo A handoff | **Confirm plan** → **Begin parking requirement**. On intake, **Use the example** (exact Demo A sentence) then **Send to Reservedge**. Confirm requirement and research | Prefill JFK / 3–8 Sep; live competition path                                                                                                  | Sending the reconstructed handoff draft; A1–A4 skipped                         |
| 3:50–4:40    | A1–A4          | Click each grant in the live parking chrome. After A2 wait, **See the recommendation**                                                                                 | A1 copy (no supplier yet); A2 three isolated suppliers; SkyShield **USD 148.00**; A3 selection ≠ booking; A4 simulated; **SIMULATED RECEIPT** | Real charges; marketplace; JetPark $71.40 as the winner; ranking-score overlay |
| 4:40–5:00    | Close          | Receipt in frame                                                                                                                                                       | `SIMULATED - NO REAL CHARGES OR RESERVATIONS`; SkyShield USD 148.00                                                                           | AgentCore; “production Bedrock”; `anthropic`; AWS profile names; account ids   |

### Paste strings

**Demo C**

```text
I'm going away next month and I'll need a car.
```

**Demo B**

```text
I'm travelling from London to Edinburgh for a conference 14–19 October 2026 and I'll need a car when I land, somewhere near the venue.
```

**Demo A** (composer **and** parking **Use the example**)

```text
I'm flying from JFK on September 3 at 1 PM and returning September 8 at 10 PM. I have a standard EV, prefer covered parking, and don't want a shuttle longer than 20 minutes.
```

The fake extractor keys off that full string. The reconstructed handoff draft (dates and airport only) misses the fixture and can 400. Click **Use the example** on `/intents/new/parking` before **Send to Reservedge**. Handoff still prefills JFK and the 3–8 Sep 2026 window on the review fields.

### A1–A4 buttons (live parking chrome, in order)

This path uses the live competition parking chrome (`/intents/new/parking` → `pi_*`), not IntentWorkspace.

1. **Confirm requirement** (A1). Copy: no supplier has been contacted yet.
2. **Send this request** (A2). Isolated simulated ParkDirect, SkyShield, TerminalFlex. Progress: “Suppliers are answering.”
3. **See the recommendation** when ranking is ready.
4. **Confirm offer selection** (A3) on recommended SkyShield. Selection does not reserve or charge.
5. Auth sheet: **Authorize USD 148.00** (A4 simulated reservation). Then **SIMULATED RECEIPT**.

Buyer HTTP offers omit `scoreMicros` (privacy). Do not wait for a numeric ranking overlay. The winner is SkyShield **USD 148.00**, not prototype JetPark $71.40. Inbox seed rows from other sessions are not this intent.

## Timing backup

If the take overruns: keep Demo C (clarify + refine) and Demo A (confirm + A1–A4 + receipt). Say on camera that mixed Explicit / Inferred / Proposed is on the conference trip; this cut shows Explicit parking into simulated execution.

## Voiceover delta vs fake-mode draft

Use [HONESTY.md](../submissions-aws/HONESTY.md). For an authorized live take, replace “this recording uses fake model mode” with: planning calls allowlisted Bedrock through Strands; supplier execution and payment remain simulated; this is not AgentCore. Do not mention the off-camera fake extractor, token counts, or the model id.

## Abort / restart Python

- Fallback banner **Using the local planner (labelled)**
- Fail-closed **Could not complete this step**
- Parking intake `model: unavailable` (fake extractor on `:8080` is down)
- Demo C becomes JFK parking
- Ranking winner is not SkyShield USD 148.00
- Any AWS account, model id, or token/latency overlay in the UI
- `ITAA_AWS_MODEL_MODE=live` without `ITAA_AWS_LIVE_INVOKE=1` (fail closed; do not record)
