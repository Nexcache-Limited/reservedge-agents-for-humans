# Simulation and human-approval honesty

Use these lines in the README, demo voiceover, Devpost text, and on-camera UI. Do not soften them. Do not imply a live marketplace.

## Canonical statements

1. **Supplier execution and payment are simulated.** There are no real charges, reservations, or supplier bookings.
2. **`SIMULATED - NO REAL CHARGES OR RESERVATIONS`** — the contract and receipt stamp. A4 `mode` must be `SIMULATED`. Non-simulated authorization modes are rejected in this MVP profile.
3. **A1–A4 are distinct human grants.** Opening a page is not approval. The model cannot approve, dispatch, or charge.
   - **A1** Confirm requirement — research scope only; no supplier contact yet.
   - **A2** Authorize disclosure to 3 isolated simulated suppliers — shares only the listed fields; does not reserve or charge.
   - **A3** Confirm offer selection — selection is not a booking.
   - **A4** Authorize simulated reservation — simulated only. A4 is not a booking.
4. **Session state is process-local and non-durable.** Clarify & Plan and `/v1/agent` sessions live in process memory (plus browser session cache for the plan chrome). Restarting the API discards every session (`unknown_resource`).
5. **The submitted recording, until Product Owner records otherwise, uses fake model mode.** Local live Bedrock Plan UAT succeeded on 7 September 2026: one Bedrock cycle per planning turn (~6–8 s HTTP). Earlier two-cycle ~10–16 s figures are superseded. That is not AgentCore and is not the judge video until a live recording is authorized.

## On-screen copy already in the product (keep visible)

| Surface        | Wording                                                                                                                                                                                                                                     |
| -------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Clarify & Plan | This plan is formed in this browser session for review. It is not production planning intelligence. Session state is process-local and non-durable — not persisted to durable storage — and nothing is sent to any supplier from this step. |
| A1             | You are confirming what Reservedge should research. No supplier has been contacted yet. Opening this page is not approval.                                                                                                                  |
| A2             | Authorize disclosure to 3 isolated simulated suppliers. This shares only the fields below. It does not reserve, buy, or charge anything.                                                                                                    |
| A4             | This demonstration authorizes a simulated reservation only. No card will be charged and no supplier booking will be created.                                                                                                                |
| Receipt        | SIMULATED RECEIPT. No card was charged. No supplier reservation was created.                                                                                                                                                                |

## Voiceover lines (≤5-minute video)

- “Nothing is sent to a real supplier from planning.”
- “Parking research and ranking run in an isolated simulation.”
- “The receipt is simulated. There is no payment and no reservation.”
- “We are not showing AgentCore. Supplier execution is simulated.”
- Until a live recording is authorized: “This recording uses fake model mode, not live Bedrock.”
