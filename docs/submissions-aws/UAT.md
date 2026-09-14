# UAT — final human checkpoint (14 September 2026)

Primary evidence is the hosted competition staging at https://bookingdemo.reservedge.com with **Simulation mode** on and live Bedrock behind `/v1/agent/**`. Local fake-mode remains available for `make check` and credential-free clones.

Product path: `/v1/agent/**`. Sessions are process-local. After restart, use **New intent**.

## Final human UAT truth (accepted)

| Script                                                                                                  | Result                                                                                                                               |
| ------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------ |
| **A** Dubai → London, search, date cascade, month-less second shift, optional simulated parking receipt | **PASS**                                                                                                                             |
| **B** Hotel-only date change after parking exists                                                       | **PASS**                                                                                                                             |
| **C** Keep hotel/parking when changing flight                                                           | **PASS**                                                                                                                             |
| **D** Mumbai → Milan / MXP honesty                                                                      | **PASS** on honesty (no invented JFK/Heathrow lots). **MXP airport-clarification usability issue accepted.** Video avoids Milan/MXP. |
| **E** Messy human chat                                                                                  | **Functional PASS.** Typo-spam may repeat running-search messages. **Accepted.** Video does not use typo-spam.                       |

Additional known low-severity presentation issue: raw baggage JSON on some sandbox flight cards. No further product fixes for typo-spam, MXP, or baggage JSON unless required for build correctness.

## Script A — primary demo (must still pass)

Start a **New intent**. Paste exactly:

```text
I am travelling from Dubai to London on the the 12th of october. flight booking needed. hotel in London needed fro 12 to 16 October. covered parking also needed in heathrow from 12 to 16 from 7 am to 10 pm
```

1. If asked which airports for the flight: `dxb to London` or `all airports`.
2. When asked to search: `yes`.
3. **Pass:** Flight, then Hotel, then Airport parking. Shared context ~12–16 Oct, LHR parking 07:00–22:00. Three **Curated offer** parking cards. No JFK. No “this booking is complete”.
4. `change the flight search to 19 to 22nd october` — agent asks whether hotel and parking should follow.
5. `yes` — all three move to 19–22 Oct and re-search. Lane order unchanged.
6. `change the dates to 23rd to 25th` (no month) — **23–25 October 2026**. All three update.
7. Optional: **Take this one** → authorize simulated reservation. Receipt is simulated. Flight and hotel remain changeable.

## Script B — hotel-only after parking exists

Same opening, search with `yes`. Then `check-in to 13th instead of 12`. **Pass:** hotel window shifts; parking dates held; parking does not jump to the top.

## Script C — keep hotel/parking when changing flight

Search first. `modify the flight booking to 15th October to 18th.` When asked: `keep hotel and parking`. **Pass:** only flight dates/search change.

## Script D — honesty / empty catalog

```text
Travelling from Mumbai to Milan from 20 to 30 October. Need flight, hotel and parking at the airport.
```

**Pass:** does not collapse to JFK. Empty or declined parking at MXP is acceptable if labelled honestly. Do not invent Heathrow/JFK lots. Clarification quality at unnamed Milan airports is an accepted usability weakness.

## Script E — messy human chat

Typos, `proceed`, `okay`, mid-search notes. Watch spinner-before-bubble, lost history, duplicate searches. Repeating running-search copy under typo-spam is accepted.

## Honesty / durability checks

- [ ] Restart the API process: agent `unknown_resource`. Start **New intent**.
- [ ] No AWS account id or operator profile in buyer-visible projection JSON.
- [ ] Parking receipt `mode` is `SIMULATED`.
- [ ] Flight/hotel copy remains sandbox research, not a ticket/reservation.

## Automated evidence

```bash
/usr/bin/make check
```

Python coverage ≥ 90% and web statement coverage at the Vite threshold.

## Local fake-mode (credential-free)

For clones without Bedrock: keep `ITAA_AWS_MODEL_MODE=fake`. Historical Demo A/B/C fixtures and A1–A4 parking grants remain in the test suite. They are not the judge video. Live hosted UAT superseded them as the camera script on 14 September 2026.
