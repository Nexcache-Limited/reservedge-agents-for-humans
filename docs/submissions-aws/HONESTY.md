# Simulation and human-approval honesty

Use these lines in the README, demo voiceover, Devpost text, and on-camera UI. Do not soften them. Do not imply a live marketplace, live curated suppliers, or AgentCore.

## Canonical statements

1. **Flight and hotel results are sandbox research only.** LiteAPI returns research offers. They are not tickets and not reservations.
2. **Parking Curated offers are simulated supplier replies.** ParkDirect, SkyShield, and TerminalFlex answer a buyer requirement in this competition build. No live curated or reverse-bid marketplace is connected. Do not name RDN. Do not claim private discounts or real parking inventory.
3. **The product pattern is public/sandbox search plus a simulated curated/reverse-bid offer path.** Standard search retrieves available catalog results. The curated path demonstrates providers responding to a buyer’s requirements and preferences. In this competition build those curated supplier responses are simulated. The buyer retains control of disclosure, selection, and simulated authorization.
4. **A4 authorizes the simulated booking step. It never creates a real booking.** The resulting receipt is simulated. No real supplier reservation or charge is created. No card is charged. A4 `mode` must be `SIMULATED`. Non-simulated authorization modes are rejected in this MVP profile.
5. **`SIMULATED — NO REAL CHARGES OR RESERVATIONS`** — the contract and receipt stamp.
6. **A1–A4 are distinct human grants** on the parking path. Opening a page is not approval. The model cannot approve, dispatch, or charge.
   - **A1** Confirm requirement — research scope only; no supplier contact yet.
   - **A2** Authorize disclosure to isolated simulated suppliers — shares only the listed fields; does not reserve or charge.
   - **A3** Confirm offer selection — selection is not a real booking.
   - **A4** Authorize the simulated reservation action — simulated only.
7. **Session state is process-local and non-durable.** Clarify & Plan and `/v1/agent` sessions live in process memory (plus browser session cache for the plan chrome). Restarting the API discards every session (`unknown_resource`). Hosted staging at https://bookingdemo.reservedge.com is the same class of process-local session.
8. **The hosted competition demo uses live Amazon Bedrock** through Strands Agents SDK. The browser never calls Bedrock. **Amazon Bedrock AgentCore is not deployed.**
9. **Rental car** is a requirement capability with no production inventory adapter. **Experience search** uses Prioticket and is provider-limited.

## On-screen copy already in the product (keep visible)

| Surface              | Wording                                                                                                                                      |
| -------------------- | -------------------------------------------------------------------------------------------------------------------------------------------- |
| Clarify & Plan       | Session state is process-local and non-durable; it is not persisted to durable storage.                                                      |
| Parking lane         | Simulated parking path. Conversation is the primary editor. Selection is not a booking. **Curated offer** labels on simulated parking cards. |
| Flight / hotel lanes | Sandbox research. Not a ticket / not a reservation.                                                                                          |
| A4                   | This demonstration authorizes a simulated reservation only. No card will be charged and no supplier booking will be created.                 |
| Receipt              | SIMULATED RECEIPT. No card was charged. No supplier reservation was created.                                                                 |

## Voiceover lines (≤5-minute video)

- “One Booking Chat coordinates flight, hotel, and parking from what I said out loud.”
- “The model interprets. Code owns provenance, search authorization, ranking, and money-sensitive state.”
- “Flights and hotels here are sandbox research — not a ticket, not a reservation.”
- “These parking cards are simulated Curated offers. Providers are responding to my requirements; they are not a live marketplace.”
- “I authorize a simulated reservation. The receipt is simulated. No card is charged.”
- “We are not showing AgentCore.”

## Known limitations (do not contradict these)

Recorded in the 14 September 2026 human UAT checkpoint and **not hidden**:

- **Script D (Mumbai → Milan / MXP):** honesty holds (no invented JFK/Heathrow lots). Airport clarification at unnamed Milan airports is a usability weakness. The judge video avoids Milan/MXP.
- **Script E:** functional. Deliberate typo-spam can repeat running-search messages. The judge video does not use typo-spam.
- Raw baggage JSON on some sandbox flight cards is a low-severity presentation issue.

Do not “fix” these in copy by claiming they do not exist.
