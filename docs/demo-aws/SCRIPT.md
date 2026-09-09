# ≤5-minute demo script / storyboard

**Mode for the current recording draft:** `ITAA_AWS_MODEL_MODE=fake` at `http://127.0.0.1:5180`.  
**Do not** open AWS console, IAM, or Bedrock on camera. **Do not** say “AgentCore”. Local live Bedrock Plan UAT succeeded 7 September 2026 (one Bedrock cycle per planning turn; ~6–8 s HTTP). Do not record a live-Bedrock video until Product Owner authorizes that take. Exact live env and shot list: [LIVE_RECORDING.md](LIVE_RECORDING.md).

Voiceover covers Devpost’s three pitch beats in the first 40 seconds, then the product. On-camera face is optional.

Paste objectives **exactly**. Fake fixtures match the full normalized string. Same-session refinement uses **Answer and update plan** (structured answers), not a free-form note — a note is concatenated and misses Demo A/B.

---

## 0:00–0:40 — Problem, who, why

**Screen:** Composer — “What are you planning or trying to get done?”

**VO:**  
Everyday trip errands steal an evening: parking, a car on landing, a hotel near the venue. Reservedge is for people who can say what they are trying to get done out loud. An agent proposes the work; you stay on every approval. Supplier execution and payment are simulated. This recording is fake model mode — not AgentCore.

---

## Beat 1–3 (0:40–1:50) — Demo C: free-form, clarification, same-session refinement

**Paste:**

```text
I'm going away next month and I'll need a car.
```

Click **Start booking**.

| Beat                      | Show                                                                                                       |
| ------------------------- | ---------------------------------------------------------------------------------------------------------- |
| 1 Arbitrary objective     | Full sentence in the composer; not a domain form                                                           |
| 2 Clarification           | Blocking card: exact dates (and departing-from if shown). Activity: asking a question that blocks the plan |
| 3 Same-session refinement | Fill dates; **Answer and update plan**. Same session. Not canned JFK parking                               |

**VO:** The agent does not invent an airport. It asks. Updating the plan does not contact suppliers.

---

## Beat 4–5 (1:50–2:50) — Demo B: provenance, then confirm

New **Start booking**. **Paste exactly:**

```text
I'm travelling from London to Edinburgh for a conference 14–19 October 2026 and I'll need a car when I land, somewhere near the venue.
```

| Beat           | Show                                                                                                        |
| -------------- | ----------------------------------------------------------------------------------------------------------- |
| 4 Provenance   | **Explicit** rental · **Inferred** parking · **Proposed** hotel. Point at the chips. Flight is not Explicit |
| 5 Confirmation | **Confirm plan**. Copy: nothing sent to any supplier. Session is process-local                              |

**VO:** Code assigns provenance. The model cannot upgrade Proposed to Explicit.

---

## Beat 5–7 (2:50–4:40) — Demo A: confirm, A1–A4, simulated execution

New session. **Paste exactly:**

```text
I'm flying from JFK on September 3 at 1 PM and returning September 8 at 10 PM. I have a standard EV, prefer covered parking, and don't want a shuttle longer than 20 minutes.
```

Parking **Explicit**. **Confirm plan**. **Begin parking requirement**. On intake, **Use the example** (exact Demo A sentence) then **Send to Reservedge**. Live parking chrome (not IntentWorkspace):

| Grant | Button                  | Call out                                                                       |
| ----- | ----------------------- | ------------------------------------------------------------------------------ |
| A1    | Confirm requirement     | Research only; no supplier yet                                                 |
| A2    | Send this request       | Isolated simulated ParkDirect, SkyShield, TerminalFlex                         |
| Rank  | See the recommendation  | SkyShield USD 148.00 — not a live marketplace; buyer JSON omits ranking scores |
| A3    | Confirm offer selection | Selection is not a booking                                                     |
| A4    | Authorize USD 148.00    | Mode: simulated                                                                |

**SIMULATED RECEIPT** — “No card was charged. No supplier reservation was created.”

| Beat                             | Show                                  |
| -------------------------------- | ------------------------------------- |
| 6 Simulated parking behind A1–A4 | Each grant clicked; human not skipped |
| 7 Simulated payment/execution    | Receipt stamp + VO below              |

**VO (mandatory):** Supplier execution and payment are simulated. There are no real charges, reservations, or supplier bookings. `SIMULATED - NO REAL CHARGES OR RESERVATIONS`. A4 is not a booking.

---

## 4:40–5:00 — Close

**VO:** Strands decided what work was needed. Governance decided what was allowed. Local fake-mode demo. Not AgentCore.

Cut.

---

## Timing backup if Demo B is slow

Keep Demo C (beats 1–3) and Demo A (confirm + A1–A4 + receipt). On Demo A, say: mixed Explicit / Inferred / Proposed is on the conference trip in UAT; this cut shows Explicit parking into the simulated golden path. Prefer the full three-session script if time allows.

## Failures — stop and restart Python

- Generic/mismatched paste → not Demo A/B
- Follow-up **message** on Demo A/B → fixture miss in fake mode
- `ITAA_AWS_MODEL_MODE=live` without `ITAA_AWS_LIVE_INVOKE=1` → fail closed
- Live invoke is for authorized local UAT or an authorized live recording only ([LIVE_UAT.md](../submissions-aws/LIVE_UAT.md), [LIVE_RECORDING.md](LIVE_RECORDING.md)); not this fake-mode recording
