# Simulation and human-approval honesty

Use these lines in the README, demo voiceover, Devpost text, and on-camera UI. Do not soften them. Do not imply a live marketplace.

## Canonical statements

1. **Supplier execution and payment are simulated.** There are no real charges, reservations, tickets, or supplier bookings.
2. **`SIMULATED - NO REAL CHARGES OR RESERVATIONS`** — the contract and receipt stamp. A4 `mode` must be `SIMULATED`. Non-simulated authorization modes are rejected in this MVP profile.
3. **No provider search before conversational authorization.** LiteAPI stay/flight research and simulated parking search wait until the buyer confirms the ready set in chat.
4. **A1–A4 are distinct human grants.** Opening a page is not approval. The model cannot approve, dispatch, or charge.
   - **A1** Confirm requirement — research scope only; no supplier contact yet.
   - **A2** Authorize disclosure to 3 isolated simulated suppliers — shares only the listed fields; does not reserve or charge.
   - **A3** Confirm offer selection — selection is not a booking.
   - **A4** Authorize simulated reservation — simulated only. A4 is not a booking.
5. **Stay and flight results are research only.** Selecting a hotel is not a booking. Selecting a flight is not a ticket.
6. **Changing one requirement** stales only the affected domain and requires a new search authorization. Other domains stay put.
7. **Session state is process-local and non-durable.** Booking Chats (Running / Pending / History) resume only while the API process is up. Restarting the API discards every session (`unknown_resource`).
8. **The submitted recording, until Product Owner records otherwise, uses the hosted competition staging build** with live Bedrock Plan and LiteAPI sandbox. AgentCore is not demonstrated.

## On-screen copy already in the product (keep visible)

| Surface        | Wording |
| -------------- | ------- |
| Booking Chats | Running, Pending, and History. Resume a chat; do not invent Unknown intent. |
| Clarify & Plan | Session state is process-local and non-durable. Nothing is sent to any supplier until you authorize search. |
| Search auth    | I have what I need to search. Shall I request offers? No search until you confirm. |
| A1             | You are confirming what Reservedge should research. No supplier has been contacted yet. Opening this page is not approval. |
| A2             | Authorize disclosure to 3 isolated simulated suppliers. This shares only the fields below. It does not reserve, buy, or charge anything. |
| A4             | This demonstration authorizes a simulated reservation only. No card will be charged and no supplier booking will be created. |
| Receipt        | SIMULATED RECEIPT. No card was charged. No supplier reservation was created. |

## Voiceover lines (≤5-minute video)

- “Nothing is sent to a real supplier until you authorize search.”
- “Hotel and flight results are research only. Selecting one is not a booking or a ticket.”
- “Parking research and ranking run in an isolated simulation.”
- “If I change the hotel dates, only stay goes stale. Parking stays.”
- “The receipt is simulated. There is no payment and no reservation.”
- “We are not showing AgentCore.”
