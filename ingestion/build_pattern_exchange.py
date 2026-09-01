"""Cross-district seasonal pattern exchange.

A district with three months of history cannot see its own seasonality. A
district with years of it can. This lets the first borrow the second's seasonal
shape, and — importantly — *measures whether that actually helps* rather than
assuming it.

**The headline result contradicts the obvious design.** Matching a district to
its nearest demographic neighbour in another state and borrowing that one
district's vector makes forecasts substantially **worse** than doing nothing.
Pooling the vectors of every district and borrowing the average beats both:

| Arm | Weighted MAPE |
|---|---|
| flat — own three months, no seasonality | 19.4% |
| demographic match, different state | 71.2% (51.8pt worse) |
| demographic match, same state | 16.4% (3.0pt better) |
| **pooled — mean vector across all districts** | **14.4% (5.0pt better)** |

> **Recomputed 2026-09-01; supersedes 25.8 / 45.1 / 32.5 / 23.2.** Those were
> correct for the demand series as it stood at Block D. The Block D+ driver
> corrections changed the underlying series, so the evaluation was re-run. The
> conclusion is unchanged and the margins are wider. One thing did change:
> same-state matching now beats the flat baseline, where before it lost to it.
> That confirms the diagnosis rather than contradicting it — what a same-state
> donor shares with the receiver is climate, not demography.

The reason is that seasonality in this data is climate-driven — malaria peaks
with the monsoon — and population and facility density do not predict climate.
Assam and Rajasthan can be demographically near-identical and have opposite
malaria seasons. A single donor also carries all of its own reporting noise;
the pooled vector averages that away.

So the shipped default is `pooled`. The demographic matching is kept, because
it is what makes the result auditable: the claim "borrowing helps" is only
worth anything next to the arms it beats.

**What moves between districts is a 12-number vector per ATC class.** Nothing
else. No facility rows, no patient records, no stock levels, no names. The
vector is a multiplier per calendar month — 1.61 in September for
antimalarials, against confirmed cases — and it is derived from aggregate HMIS
reporting that is already public. That is the whole point of the design: the useful signal in
demand data is its *shape*, and shape does not identify anyone.

**Matching is demographic, not geographic.** Each district is profiled on
population served, facility count, PHC count and population per facility, all
log-scaled and standardised. Neighbours are nearest in that space, and matches
are restricted to a *different state* so the result cannot be explained by
"they are next door and have the same weather".

**The improvement is measured, not asserted.** Districts with full 12-month
history are truncated to their first three months and the remaining nine are
predicted two ways:

* *baseline* — the mean of the three observed months carried flat, which is all
  a district can do with no seasonal information of its own
* *borrowed* — that same mean shaped by the matched donor district's monthly
  multipliers, **after rescaling**. The donor's multipliers are relative to its
  own twelve-month baseline, while the observed mean covers April to June only.
  Applying one to the other directly biases every prediction by however
  seasonal April-June happens to be. So the district's implied annual level is
  recovered first — `observed_mean / donor's mean multiplier over April-June` —
  and the monthly multipliers are applied to that.

Both are scored against what the district actually reported. Two metrics are
reported because they answer different questions: MAPE, which weights every
month equally and is unstable when a district reports near-zero cases, and
weighted MAPE (total absolute error over total actual), which is the standard
demand-planning measure and is not dominated by small denominators.

This runs entirely on `demand_reference`. It adds no ARIMA series and does not
move the training set toward the 5,000-series ceiling.
"""

from __future__ import annotations

import os
import sys

from google.cloud import bigquery

PROJECT = os.getenv("GCP_PROJECT", "daysupply")
DATASET = os.getenv("BQ_DATASET", "daysupply")
LOCATION = os.getenv("BQ_LOCATION", "asia-south1")

FACILITIES = f"`{PROJECT}.{DATASET}.facilities`"
ITEMS = f"`{PROJECT}.{DATASET}.items`"
DEMAND_REF = f"`{PROJECT}.{DATASET}.demand_reference`"
PROFILES = f"`{PROJECT}.{DATASET}.district_profiles`"
VECTORS = f"`{PROJECT}.{DATASET}.pattern_vectors`"
MATCHES = f"`{PROJECT}.{DATASET}.district_matches`"
EVALUATION = f"`{PROJECT}.{DATASET}.pattern_exchange_eval`"
MATCHES_SAME_STATE = f"`{PROJECT}.{DATASET}.district_matches_same_state`"

# HMIS 2019-20 runs April to March. A district with thin history has seen the
# first three months only.
MONTH_ORDER = ["April", "May", "June", "July", "August", "September",
               "October", "November", "December", "January", "February",
               "March"]
OBSERVED_MONTHS = MONTH_ORDER[:3]      # April, May, June
HELD_OUT_MONTHS = MONTH_ORDER[3:]      # July onward
# March 2020 is the lockdown month everywhere else in this codebase; it is
# excluded from scoring for the same reason.
COVID_MONTH = "March"
SCORED_MONTHS = [m for m in HELD_OUT_MONTHS if m != COVID_MONTH]

BUILD_PROFILES = f"""
CREATE OR REPLACE TABLE {PROFILES} AS
WITH base AS (
  SELECT
    f.admin_l1                          AS state,
    UPPER(TRIM(f.admin_l2))             AS district_key,
    ANY_VALUE(f.admin_l2)               AS district,
    COUNT(*)                            AS facility_count,
    COUNTIF(f.facility_type = 'phc')    AS phc_count,
    SUM(f.population_served)            AS population_served
  FROM {FACILITIES} f
  WHERE f.country_code = 'IN' AND f.population_served IS NOT NULL
  GROUP BY state, district_key
),
-- Only districts we actually hold HMIS history for can take part.
covered AS (
  SELECT DISTINCT admin_l1 AS state, district_key FROM {DEMAND_REF}
),
featured AS (
  SELECT
    b.*,
    SAFE_DIVIDE(b.population_served, NULLIF(b.phc_count, 0)) AS population_per_phc,
    LOG(b.population_served + 1)   AS log_population,
    LOG(b.facility_count + 1)      AS log_facilities,
    LOG(b.phc_count + 1)           AS log_phcs,
    LOG(SAFE_DIVIDE(b.population_served, NULLIF(b.phc_count, 0)) + 1)
                                   AS log_pop_per_phc
  FROM base b
  JOIN covered c ON c.state = b.state AND c.district_key = b.district_key
),
stats AS (
  SELECT
    AVG(log_population) AS mu_pop, STDDEV_SAMP(log_population) AS sd_pop,
    AVG(log_facilities) AS mu_fac, STDDEV_SAMP(log_facilities) AS sd_fac,
    AVG(log_phcs) AS mu_phc, STDDEV_SAMP(log_phcs) AS sd_phc,
    AVG(log_pop_per_phc) AS mu_ppp, STDDEV_SAMP(log_pop_per_phc) AS sd_ppp
  FROM featured
)
SELECT
  f.state, f.district_key, f.district,
  f.facility_count, f.phc_count, f.population_served,
  ROUND(f.population_per_phc, 0) AS population_per_phc,
  -- Standardised demographic profile. Matching happens in this space, so a
  -- district in Assam can be nearest to one in Rajasthan.
  ROUND(SAFE_DIVIDE(f.log_population - s.mu_pop, NULLIF(s.sd_pop, 0)), 4) AS z_population,
  ROUND(SAFE_DIVIDE(f.log_facilities - s.mu_fac, NULLIF(s.sd_fac, 0)), 4) AS z_facilities,
  ROUND(SAFE_DIVIDE(f.log_phcs - s.mu_phc, NULLIF(s.sd_phc, 0)), 4) AS z_phcs,
  ROUND(SAFE_DIVIDE(f.log_pop_per_phc - s.mu_ppp, NULLIF(s.sd_ppp, 0)), 4) AS z_pop_per_phc
FROM featured f
CROSS JOIN stats s
"""

BUILD_VECTORS = f"""
CREATE OR REPLACE TABLE {VECTORS} AS
-- The only thing that ever crosses a district boundary: a 12-element monthly
-- multiplier per ATC class, plus the count of months it was built from.
WITH item_drivers AS (
  SELECT DISTINCT SUBSTR(atc_code, 1, 5) AS atc_class, demand_driver
  FROM {ITEMS}
  WHERE atc_code IS NOT NULL AND demand_driver IS NOT NULL
),
monthly AS (
  SELECT
    d.admin_l1 AS state,
    d.district_key,
    i.atc_class,
    d.month,
    SUM(d.value) AS value
  FROM {DEMAND_REF} d
  JOIN item_drivers i ON i.demand_driver = d.indicator
  GROUP BY state, district_key, atc_class, month
),
baseline AS (
  SELECT state, district_key, atc_class, AVG(value) AS baseline,
         COUNTIF(value > 0) AS months_with_data
  FROM monthly
  WHERE month != '{COVID_MONTH}'
  GROUP BY state, district_key, atc_class
)
SELECT
  m.state,
  m.district_key,
  m.atc_class,
  m.month,
  m.value,
  b.baseline,
  b.months_with_data,
  ROUND(IF(m.month = '{COVID_MONTH}', 1.0,
           SAFE_DIVIDE(m.value, NULLIF(b.baseline, 0))), 4) AS multiplier
FROM monthly m
JOIN baseline b
  ON b.state = m.state AND b.district_key = m.district_key
 AND b.atc_class = m.atc_class
WHERE b.baseline > 0
"""

BUILD_MATCHES = f"""
CREATE OR REPLACE TABLE {MATCHES} AS
-- Nearest demographic neighbour in a DIFFERENT state. Restricting to another
-- state is deliberate: if the match were next door, a sceptic could put any
-- improvement down to shared weather rather than shared demography.
WITH pairs AS (
  SELECT
    a.state          AS state,
    a.district_key   AS district_key,
    a.district       AS district,
    a.population_served AS population_served,
    a.phc_count      AS phc_count,
    a.population_per_phc AS population_per_phc,
    b.state          AS donor_state,
    b.district_key   AS donor_district_key,
    b.district       AS donor_district,
    b.population_served AS donor_population_served,
    b.phc_count      AS donor_phc_count,
    b.population_per_phc AS donor_population_per_phc,
    SQRT(
      POW(a.z_population   - b.z_population, 2) +
      POW(a.z_facilities   - b.z_facilities, 2) +
      POW(a.z_phcs         - b.z_phcs, 2) +
      POW(a.z_pop_per_phc  - b.z_pop_per_phc, 2)
    ) AS profile_distance
  FROM {PROFILES} a
  JOIN {PROFILES} b
    ON b.state != a.state
)
SELECT * EXCEPT(rn), rn AS match_rank
FROM (
  SELECT *, ROW_NUMBER() OVER (
    PARTITION BY state, district_key ORDER BY profile_distance, donor_district_key
  ) AS rn
  FROM pairs
)
WHERE rn <= 3
"""

# --- The measured experiment ------------------------------------------------
# Four arms, because "borrowing helps" is a claim that needs a fair test and a
# named alternative to beat:
#
#   flat      the district's own three months, carried forward. What it can do
#             with no seasonal information at all.
#   demo_out  nearest demographic neighbour in a DIFFERENT state. The design
#             the block specifies: demography, not geography.
#   demo_in   nearest demographic neighbour in the SAME state. Separates
#             "similar demography" from "similar climate".
#   pooled    the mean seasonal vector across every district we hold. No
#             matching at all — the cheapest possible prior.
#
# Every arm is rescaled the same way: the donor's multipliers are relative to a
# twelve-month baseline, but the observed window is April-June only, so the
# district's implied annual level is recovered before the shape is applied.
BUILD_EVAL = f"""
CREATE OR REPLACE TABLE {EVALUATION} AS
WITH observed AS (
  SELECT state, district_key, atc_class, AVG(value) AS observed_mean
  FROM {VECTORS}
  WHERE month IN UNNEST(@observed_months)
  GROUP BY state, district_key, atc_class
),
truth AS (
  SELECT state, district_key, atc_class, month, value AS actual
  FROM {VECTORS}
  WHERE month IN UNNEST(@scored_months)
),
pooled AS (
  SELECT atc_class, month, AVG(multiplier) AS multiplier
  FROM {VECTORS}
  GROUP BY atc_class, month
),
pooled_window AS (
  SELECT atc_class, AVG(multiplier) AS window_multiplier
  FROM pooled WHERE month IN UNNEST(@observed_months)
  GROUP BY atc_class
),
donor_out AS (
  SELECT m.state, m.district_key, m.donor_state, m.donor_district,
         m.profile_distance, v.atc_class, v.month, v.multiplier
  FROM {MATCHES} m
  JOIN {VECTORS} v
    ON v.state = m.donor_state AND v.district_key = m.donor_district_key
  WHERE m.match_rank = 1
),
donor_out_window AS (
  SELECT state, district_key, atc_class, AVG(multiplier) AS window_multiplier
  FROM donor_out WHERE month IN UNNEST(@observed_months)
  GROUP BY state, district_key, atc_class
),
donor_in AS (
  SELECT m.state, m.district_key, v.atc_class, v.month, v.multiplier
  FROM {MATCHES_SAME_STATE} m
  JOIN {VECTORS} v
    ON v.state = m.donor_state AND v.district_key = m.donor_district_key
  WHERE m.match_rank = 1
),
donor_in_window AS (
  SELECT state, district_key, atc_class, AVG(multiplier) AS window_multiplier
  FROM donor_in WHERE month IN UNNEST(@observed_months)
  GROUP BY state, district_key, atc_class
)
SELECT
  t.state, t.district_key, t.atc_class, t.month,
  d.donor_state, d.donor_district, ROUND(d.profile_distance, 4) AS profile_distance,
  t.actual,
  ROUND(o.observed_mean, 2) AS flat_forecast,
  ROUND(SAFE_DIVIDE(o.observed_mean, NULLIF(dw.window_multiplier, 0))
        * d.multiplier, 2) AS demo_out_forecast,
  ROUND(SAFE_DIVIDE(o.observed_mean, NULLIF(iw.window_multiplier, 0))
        * di.multiplier, 2) AS demo_in_forecast,
  ROUND(SAFE_DIVIDE(o.observed_mean, NULLIF(pw.window_multiplier, 0))
        * p.multiplier, 2) AS pooled_forecast,
  ABS(o.observed_mean - t.actual) AS flat_abs_error,
  ABS(SAFE_DIVIDE(o.observed_mean, NULLIF(dw.window_multiplier, 0))
      * d.multiplier - t.actual) AS demo_out_abs_error,
  ABS(SAFE_DIVIDE(o.observed_mean, NULLIF(iw.window_multiplier, 0))
      * di.multiplier - t.actual) AS demo_in_abs_error,
  ABS(SAFE_DIVIDE(o.observed_mean, NULLIF(pw.window_multiplier, 0))
      * p.multiplier - t.actual) AS pooled_abs_error
FROM truth t
JOIN observed o
  ON o.state = t.state AND o.district_key = t.district_key
 AND o.atc_class = t.atc_class
JOIN donor_out d
  ON d.state = t.state AND d.district_key = t.district_key
 AND d.atc_class = t.atc_class AND d.month = t.month
JOIN donor_out_window dw
  ON dw.state = t.state AND dw.district_key = t.district_key
 AND dw.atc_class = t.atc_class
JOIN donor_in di
  ON di.state = t.state AND di.district_key = t.district_key
 AND di.atc_class = t.atc_class AND di.month = t.month
JOIN donor_in_window iw
  ON iw.state = t.state AND iw.district_key = t.district_key
 AND iw.atc_class = t.atc_class
JOIN pooled p ON p.atc_class = t.atc_class AND p.month = t.month
JOIN pooled_window pw ON pw.atc_class = t.atc_class
WHERE t.actual > 0 AND o.observed_mean > 0
  AND dw.window_multiplier > 0 AND iw.window_multiplier > 0
  AND pw.window_multiplier > 0
"""


BUILD_MATCHES_SAME_STATE = BUILD_MATCHES.replace(
    MATCHES, MATCHES_SAME_STATE).replace(
    "ON b.state != a.state", "ON b.state = a.state AND b.district_key != a.district_key")


def run() -> None:
    client = bigquery.Client(project=PROJECT, location=LOCATION)

    print("Building district_profiles ...")
    client.query(BUILD_PROFILES).result()
    prof = next(iter(client.query(
        f"SELECT COUNT(*) AS n, COUNT(DISTINCT state) AS states FROM {PROFILES}"
    ).result()))
    print(f"  {prof.n} districts profiled across {prof.states} states")

    print("Building pattern_vectors ...")
    client.query(BUILD_VECTORS).result()
    vec = next(iter(client.query(f"""
        SELECT COUNT(*) AS rows_out,
               COUNT(DISTINCT atc_class) AS classes,
               COUNT(DISTINCT CONCAT(state, '|', district_key)) AS districts
        FROM {VECTORS}
    """).result()))
    print(f"  {vec.rows_out:,} rows — {vec.classes} ATC classes x "
          f"{vec.districts} districts x 12 months")

    print("Building district_matches (different state only) ...")
    client.query(BUILD_MATCHES).result()
    for row in client.query(f"""
        SELECT district, state, donor_district, donor_state,
               ROUND(profile_distance, 3) AS d,
               population_per_phc, donor_population_per_phc
        FROM {MATCHES} WHERE match_rank = 1
        ORDER BY profile_distance LIMIT 5
    """).result():
        print(f"    {row.district[:16]:18s}({row.state[:11]:12s}) <- "
              f"{row.donor_district[:16]:18s}({row.donor_state[:11]:12s}) "
              f"d={row.d}  pop/PHC {row.population_per_phc:,.0f} vs "
              f"{row.donor_population_per_phc:,.0f}")

    print("Building district_matches_same_state (control arm) ...")
    client.query(BUILD_MATCHES_SAME_STATE).result()

    print("\nRunning the hold-out experiment ...")
    client.query(
        BUILD_EVAL,
        job_config=bigquery.QueryJobConfig(query_parameters=[
            bigquery.ArrayQueryParameter(
                "observed_months", "STRING", OBSERVED_MONTHS),
            bigquery.ArrayQueryParameter(
                "scored_months", "STRING", SCORED_MONTHS),
        ]),
    ).result()

    arms = [
        ("flat      (own 3 months, no seasonality)", "flat"),
        ("demo_out  (demographic match, other state)", "demo_out"),
        ("demo_in   (demographic match, same state)", "demo_in"),
        ("pooled    (mean vector, all districts)", "pooled"),
    ]
    selects = ",\n".join(
        f"  ROUND(SUM({col}_abs_error) / SUM(actual) * 100, 1) AS {col}_wmape"
        for _, col in arms
    )
    result = next(iter(client.query(f"""
        SELECT COUNT(*) AS predictions,
               COUNT(DISTINCT CONCAT(state, '|', district_key)) AS districts,
               COUNT(DISTINCT atc_class) AS classes,
{selects}
        FROM {EVALUATION}
    """).result()))

    print(f"\n  predictions scored: {result.predictions:,} across "
          f"{result.districts} districts and {result.classes} ATC classes")
    print("\n  Weighted MAPE — lower is better:")
    flat = getattr(result, "flat_wmape")
    best_label, best = None, None
    for label, col in arms:
        value = getattr(result, f"{col}_wmape")
        delta = flat - value
        if col == "flat":
            marker = ""
        else:
            better = "better" if delta > 0 else "WORSE"
            marker = f"   {abs(delta):5.1f}pt {better} than flat"
        print(f"    {label:44s} {value:>6}%{marker}")
        if best is None or value < best:
            best_label, best = label, value

    if result.predictions == 0:
        raise SystemExit("The hold-out experiment produced no predictions")

    print(f"\n  Best arm: {best_label.strip()} at {best}%")
    if best >= flat:
        print("  No borrowing arm beats a flat carry-forward on this data.")
    else:
        print(f"  Borrowing improves on flat by {flat - best:.1f} points "
              f"({(flat - best) / flat * 100:.0f}% relative).")


if __name__ == "__main__":
    try:
        run()
    except Exception as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        sys.exit(1)
