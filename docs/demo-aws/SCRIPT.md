# ≤5-minute demo script / storyboard

**Mode for the current recording take:** hosted competition staging at `https://bookingdemo.reservedge.com` (live Bedrock Plan, LiteAPI sandbox stay/flight, simulated parking).
**Do not** open AWS console, IAM, or Bedrock on camera. **Do not** say “AgentCore”.
**Brand:** Reservedge. Inbox is **Booking Chats**.

Paste objectives **exactly**. Do not click a domain picker first.

---

## 0:00–0:35 — Problem, who, why

**Screen:** Composer — “What are you planning or trying to get done?” Reservedge wordmark visible.

**VO:**
Everyday trip errands steal an evening: a flight, a hotel, airport parking. Reservedge is an Intent-to-Action booking agent. You say what you are trying to get done. The agent proposes the work; you authorize every search. Hotel and flight results are research only. Parking execution is simulated. This is not AgentCore.

---

## Beat 1–3 — Combined journey, no search yet

**Paste:**

```text
I need a flight from Manchester to Heathrow on 25 October, a hotel near Heathrow those dates, and parking at Heathrow.
```

Click **Start booking**.

| Beat | Show |
| ---- | ---- |
| 1 Arbitrary objective | Full sentence; Booking Chats Running row appears |
| 2 Clarification | Missing parking clocks/covered if asked. No hotel or flight offers yet |
| 3 Authorization | Chat asks to search the ready set. **No LiteAPI or parking search until you say yes** |

**VO:** The agent does not search suppliers while it is still gathering facts.

Confirm search in chat (“yes”). Then show:

- Flight offers (LiteAPI sandbox; not a ticket)
- Hotel offers (LiteAPI sandbox; not a booking)
- Simulated parking offers after the parking path is complete enough

---

## Beat 4 — Refinement, one domain only

In the same chat:

```text
change the hotel dates to 26 to 28 October
```

| Show | Call out |
| ---- | -------- |
| Stay stale | Hotel results marked stale; new stay authorization required |
| Flight/parking unchanged | Flight and parking lanes stay put |
| No silent re-search | Nothing hits LiteAPI until you authorize stay again |

**VO:** Changing one requirement does not throw away the other work.

---

## Beat 5–6 — Booking Chats resume

Open **Booking Chats**. Leave Running, then reopen the same chat.

| Show | Call out |
| ---- | -------- |
| Running | Same session, not Unknown intent |
| Pending | Park an unfinished booking by starting a new intent |
| Brand | Reservedge wordmark and Booking Chats label |

---

## Beat 7 — Honesty close

Parking A1–A4 if shown: simulated receipt. **SIMULATED - NO REAL CHARGES OR RESERVATIONS.**

**VO:** Hotel and flight were research. Parking was a labelled simulation. You stayed on every authorization.
