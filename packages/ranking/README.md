# packages/ranking

Deterministic airport-parking scoring and explanation facts.

`itaa-ranking` is a pure Python workspace package. It depends only on `itaa-domain`.
It does not import application, policy, generated contracts, simulators, adapters,
FastAPI, databases, or cloud SDKs. It never calls a model.

## Public model

Call `rank_offers(offers, need, evaluated_at=..., reliability=..., profile=DEFAULT_PROFILE)`.

Inputs are immutable `RankingOffer` values that have already passed buyer-side
eligibility. Ineligible offers never receive a rank. The recommendation is the
first eligible ranked offer, or `NO_RECOMMENDATION` when the eligible set is empty.

## Numeric representation

- `SCORE_SCALE = 1_000_000` score micros.
- All arithmetic is integer. Weighted contribution is
  `(component_micros * weight_micros + 500_000) // 1_000_000`.
- Lower-is-better attributes (total, shuttle minutes, distance) use cohort min-max
  inversion. Equal cohort values receive `1_000_000`.
- Missing scored components add a `50_000` penalty and are never treated as
  favorable. A missing hard requirement makes the offer ineligible.

## Profile `airport_parking_v1`

Weight version `1.0`. Weights are non-negative, each at most `500_000`, and sum
to `1_000_000`:

| Component                | Weight  |
| ------------------------ | ------- |
| price_value              | 350_000 |
| reliability_trust        | 200_000 |
| cancellation_flexibility | 150_000 |
| shuttle_convenience      | 120_000 |
| distance_value           | 80_000  |
| coverage_fit             | 60_000  |
| add_on_fit               | 40_000  |

Reliability is a buyer-side registry fact with evidence, not supplier prose.
Seeded simulation values: ParkDirect `700_000`, SkyShield `950_000`,
TerminalFlex `850_000`.

Cancellation: `free_until_24h = 1_000_000`, `free_until_48h = 700_000`,
`non_refundable = 0`. Refund `none` cannot improve the component.

Coverage uses the disclosed requirement and lot type. Add-on fit is set overlap
of representable requested features (`ev_charging` in the seeded JFK fixture).
Unrepresentable accessibility remains unconfirmed and is not scored as a hit.

Evidence coverage is unique Offer evidence classes / 4, expressed in score micros.
It is a tie-break fact, not a weighted component. Recency is `UNAVAILABLE` unless
the trusted reliability input carries `observed_at`.

## Tie-breakers

1. Higher evidence coverage
2. Longer remaining validity at evaluation time
3. Lower all-in total
4. Lexicographically smaller Offer ID

## Fit thresholds

- `STRONG`: score ≥ `800_000`, evidence coverage ≥ `750_000`, no penalty
- `GOOD`: score ≥ `650_000`, evidence coverage ≥ `250_000`
- otherwise `FAIR` for an eligible recommendation

`NO_RECOMMENDATION` has no fit label.

## Explanation boundary

Drivers are the top positive stored contributions. The material downside compares
the winner with the runner-up across every supported ranked dimension, in this
fixed order, and reports the first positive disadvantage:

1. `total_minor` / `MINOR_CURRENCY`
2. `shuttle_minutes` / `MINUTES`
3. `distance_metres` / `METRES`
4. `coverage_fit` / `SCORE_MICROS`
5. `add_on_fit` / `SCORE_MICROS`
6. `cancellation` / `SCORE_MICROS`

Qualitative scored dimensions use the stored component micros. `None` is returned
only when the winner is not worse on any of those dimensions. Facts never include
prompts, chain-of-thought, buyer identity, or competitor data for a supplier.
Ranking exposes fixed-order primitive fingerprint material; the application hashes
it with the WP-04 canonical hasher.

The locked JFK golden vector (canonical contract fixtures, zero penalties) is
SkyShield `671_000` (recommended), ParkDirect `660_000`, TerminalFlex `535_000`.
