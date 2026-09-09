# UAT instructions — fake mode (COMP-AWS-05)

Run against the green fake-mode implementation for the default demo pack. Do not set `ITAA_AWS_MODEL_MODE=live` for this fake-mode checklist. Live Plan UAT is in [LIVE_UAT.md](LIVE_UAT.md).

Browser: `http://127.0.0.1:5180` after the setup in [README.md](README.md). Product path is `/v1/agent/**`.

Paste objectives **exactly** (spacing included). Fake PlanTurns key off normalized full-string match. A free-form follow-up note is concatenated onto the objective and will **miss** the Demo A/B fixtures — use structured answers for same-session refinement.

## Automated evidence

```bash
/usr/bin/make check
```

Expect Python coverage ≥ 90% and web statement coverage at the Vite threshold. COMP-AWS-04 evals/adversarial/security files must stay green.

## Demo C — arbitrary objective, clarification, same-session refinement

1. Open the composer: “What are you planning or trying to get done?”
2. Paste: `I'm going away next month and I'll need a car.`
3. Click **Start booking**.
4. **Pass:** Clarify & Plan is `clarify`. At least one blocking question (exact dates; often also departing-from). Parking is **not** canned JFK. No SkyShield.
5. Enter exact dates in the schedule fields **one at a time** (any valid future range). Optionally set departing-from to a real IATA code that is **not** implied by a JFK collapse.
6. Click **Answer and update plan**.
7. **Pass:** Same `as_*` session. Plan updates. Still not a single-task JFK parking plan.

## Demo B — Explicit / Inferred / Proposed

1. New objective (new session after API restart or a fresh Start booking):  
   `I'm travelling from London to Edinburgh for a conference 14–19 October 2026 and I'll need a car when I land, somewhere near the venue.`
2. **Pass:** Rental **Explicit**; parking **Inferred**; hotel **Proposed**. Flight is not Explicit. Destination Edinburgh; inferred parking airport EDI.
3. Click **Confirm plan**.
4. **Pass:** Status “Plan confirmed”. Nothing dispatched to suppliers. Honesty copy still visible.

Parking on Demo B is inferred at EDI. The locked SkyShield 671000 vector is the **JFK** fixture — do not use Demo B for the ranking screenshot.

## Demo A — confirm and simulated parking A1–A4

1. New session. Paste exactly:  
   `I'm flying from JFK on September 3 at 1 PM and returning September 8 at 10 PM. I have a standard EV, prefer covered parking, and don't want a shuttle longer than 20 minutes.`
2. **Pass:** Parking **Explicit**. No false Explicit hotel.
3. **Confirm plan**.
4. On the parking task, **Begin parking requirement**.
5. On intake, **Use the example** (exact Demo A sentence) then **Send to Reservedge**. The reconstructed handoff draft misses the fake extractor fixture.
6. **A1** **Confirm requirement** — copy says no supplier has been contacted yet.
7. **A2** **Send this request** (live parking chrome) — ParkDirect, SkyShield, TerminalFlex; isolated lanes. Progress: “Suppliers are answering.”
8. **See the recommendation**. **Pass:** SkyShield **USD 148.00** (do not expect a numeric ranking overlay or the prototype JetPark $71.40).
9. **A3** **Confirm offer selection**.
10. **A4** **Authorize USD 148.00**. Mode on screen is simulated.
11. **Pass:** **SIMULATED RECEIPT**. Copy: no card charged, no supplier reservation created.

Say on camera: supplier execution and payment are simulated.

## Honesty / durability checks

- [ ] Restart the Python process, reload Clarify & Plan: “No plan in this session” / agent `unknown_resource`.
- [ ] No AWS account id, model id, or `global.anthropic` in buyer-visible projection JSON.
- [ ] Receipt `mode` is `SIMULATED`.

## Live Bedrock UAT

Agreement is `AVAILABLE`. Dedicated-role smoke test and local product-path Plan UAT succeeded 7 September 2026. One Bedrock cycle per planning turn (~6–8 s HTTP); the earlier two-cycle ~10–16 s figures are superseded. Default live mode without `ITAA_AWS_LIVE_INVOKE=1` still fails closed. The live Plan path is frozen for the competition unless a demonstrated defect appears.

See [LIVE_UAT.md](LIVE_UAT.md) for configuration and results. Authorized live recording shot list: [LIVE_RECORDING.md](../demo-aws/LIVE_RECORDING.md) (do not record until Product Owner authorizes). Remaining gates: AgentCore, live-demo recording, Devpost submit.
