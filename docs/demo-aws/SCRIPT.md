# ≤5-minute demo script / storyboard

**Mode for the judge video:** hosted live Bedrock at https://bookingdemo.reservedge.com  
**Local fallback:** `http://127.0.0.1:5180` with the same product path `/v1/agent/**`.  
**Do not** open AWS console, IAM, or Bedrock on camera. **Do not** say “AgentCore”. **Do not** name RDN. **Do not** claim a real ticket, hotel reservation, payment, or live curated marketplace.

Target finished length **4:40–4:55** (not a hard 5:00) so encode/upload still fits the 5-minute cap.

Script **A only** (Dubai → London). Do not film Milan/MXP or deliberate typo-spam.

Voiceover covers Devpost’s three pitch beats in the first 35 seconds, then the product. On-camera face is optional. Leave **Simulation mode** on.

Paste the objective **exactly**.

---

## 0:00–0:35 — Problem, who, why

**Screen:** Composer — “What are you planning or trying to get done?”

**VO:**  
Everyday trip chores steal an evening: a flight, a hotel, parking at the airport. Reservedge is an Intent-to-Action booking agent for people who can say what they are trying to get done out loud. One Booking Chat coordinates the work. The model interprets. You stay on every consequential approval. Flights and hotels in this demo are sandbox research. Parking Curated offers and the receipt are simulated.

---

## 0:35–1:40 — One objective becomes three tasks

**Paste exactly:**

```text
I am travelling from Dubai to London on the the 12th of october. flight booking needed. hotel in London needed fro 12 to 16 October. covered parking also needed in heathrow from 12 to 16 from 7 am to 10 pm
```

Click **Start booking**. Hold on **Understanding your objective**.

If asked which airports to search for the **flight**: reply `DXB to LHR` (or `all airports` if that is the on-screen choice).

When asked to search: `yes`.

| Must show                                                   | Must not show                  |
| ----------------------------------------------------------- | ------------------------------ |
| Lanes **Flight → Hotel → Airport parking**                  | JFK invented on a London trip  |
| Shared context ~12–16 Oct; parking Heathrow LHR 07:00–22:00 | “This booking is complete”     |
| Flight DXB→LHR (or city metros if `all airports`)           | AWS console; model id          |
| London hotel sandbox results                                | Real ticket / payment language |
| Three parking cards labelled **Curated offer**              | Live marketplace / RDN         |

**VO:** One sentence became three tasks. Code labelled what I said explicitly. I authorized search before anything left this chat. Parking cards are simulated Curated offers — suppliers responding to my covered-parking requirement, not a live lot inventory.

---

## 1:40–3:10 — Cross-domain date refinement

Type:

```text
change the flight search to 19 to 22nd october
```

**Check:** The agent asks whether hotel and parking should follow, or stay on 12–16 Oct. Do not re-search everything yet.

Reply: `yes`

**Check:** Flight, hotel, and parking move to 19–22 Oct. All three re-search. Lane order remains Flight → Hotel → Parking.

Type (no month):

```text
change the dates to 23rd to 25th
```

**Check:** Becomes **23–25 October 2026**. All three domains update and re-search. Copy stays short. No airline-ticket or payment fiction.

**VO:** I changed the trip in conversation. The agent asked before moving hotel and parking. A date without a month kept October. I did not restart the booking.

---

## 3:10–4:25 — Simulated Curated offer → human authorization → simulated receipt

On a parking card, click **Take this one**. Then **Authorize** the simulated reservation (on-screen amount).

| Must show                                                                | Must not show                            |
| ------------------------------------------------------------------------ | ---------------------------------------- |
| **Curated offer** label                                                  | “Booking complete” for the whole trip    |
| Authorize simulated reservation                                          | Card PAN; real payment                   |
| **SIMULATED RECEIPT** — no card charged, no supplier reservation created | AgentCore                                |
| Flight and hotel tasks still open / changeable                           | Claim that flights or hotels were booked |

**VO:** A4 authorizes the simulated booking step. It never creates a real booking. The receipt is simulated. Flight and hotel research stay open.

---

## 4:25–4:50 — Close

**VO:** Strands and Bedrock interpreted the trip. Deterministic code owned provenance, search authorization, ranking, and the simulated money action. Sandbox research plus simulated Curated offers. Not AgentCore. `SIMULATED — NO REAL CHARGES OR RESERVATIONS`.

Cut.

---

## Failures — abort and restart from **New intent**

- Fallback copy “Using the local planner (labelled)”
- Invented JFK or Heathrow parking on the wrong city
- Parking Completes the whole trip
- Take this one → “Could not complete this step”
- Address bar showing AWS console, localhost env files, or `/v1/aws`

Sessions are process-local. After any API restart, start a **New intent**.
