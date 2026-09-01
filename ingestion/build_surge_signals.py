"""Surge detection: when a district's demand departs from the pooled pattern.

Block D established that the useful transferable signal between districts is a
twelve-number seasonal vector per ATC class, and that the **pooled** vector —
the mean across all districts — beats both a flat baseline and a demographically
matched donor. That pooled vector is therefore the network's best statement of
what a normal month looks like. A surge is a month that departs from it.

    expected(district, class, month) = baseline(district, class)
                                     x pooled_multiplier(class, month)
    residual                         = observed - expected

`baseline` is the district's own twelve-month mean, so the expectation is
already scaled to how much malaria (or diarrhoea, or hypertension) that district
actually has. What the pooled vector contributes is only the *shape* of the
year. A surge is then "more than this district's own level, seasonally adjusted,
can explain".

## Why not a plain standardised residual

The obvious next step is a standardised residual and a 3-sigma rule:

    z_classical = (r - mean(r)) / stddev(r)

It does not work here, and the reason is arithmetic rather than clinical.

**Each series has exactly twelve monthly observations.** For a sample of size
n, the largest attainable standardised residual is bounded at

    z_max = (n - 1) / sqrt(n) = 11 / sqrt(12) = 3.175

(The bound holds for a deviation from the sample *mean*. Dividing the raw
residual by its standard deviation without centring it first is not a
standardised residual and is not bounded — an early version of this module did
exactly that and the ceiling assertion below caught it at 3.45.)

A single extreme month inflates the very standard deviation it is measured
against. Running the classical z over this data produces a wall of values at
3.0-3.1 and nothing above: a genuine 12x outbreak and a mild 4x bump score
identically, and a "3-sigma" threshold is within 0.07 of being unattainable.
That is not a threshold, it is a ceiling. It is reported for transparency but
it is not what fires.

**What fires is the modified z-score** (Iglewicz & Hoaglin, *How to Detect and
Handle Outliers*, ASQC 1993, section 4.4), which replaces mean and standard
deviation with median and median absolute deviation:

    MAD          = median(|r - median(r)|)
    modified_z   = 0.6745 x (r - median(r)) / MAD

The median and MAD are unaffected by the outlier being tested, so the statistic
is unbounded and a 12x month scores far above a 4x month. The 0.6745 factor is
the 0.75 quantile of the standard normal, which makes MAD a consistent estimator
of sigma for normally distributed data, so the score is on a familiar scale.
Iglewicz and Hoaglin recommend **3.5** as the cut, and that is the default here.

## Three conditions, not one

A statistical test alone will flag a district that went from three cases to
twelve. That is a large modified z and clinically nothing. A surge must clear
all three of:

| Condition | Default | Why |
|---|---|---|
| `modified_z >= SURGE_Z` | 3.5 | Iglewicz-Hoaglin; the statistical test |
| `observed / expected >= SURGE_MIN_RATIO` | 1.5 | materially more, not a rounding artefact |
| `observed >= SURGE_MIN_ABSOLUTE` | 100 | enough events to be worth acting on |

All three are environment-configurable (`SURGE_Z`, `SURGE_MIN_RATIO`,
`SURGE_MIN_ABSOLUTE`) and all three are recorded on every row, so a reviewer can
see which condition excluded a near miss.

**MAD can be zero** in a series that barely moves. Where it is, the modified z
is undefined; those rows are excluded and counted rather than silently passed.

## The surge multiplier is what reaches the supply chain

`surge_multiplier = observed / expected` is the operative number. It is not the
detection statistic — it is how much more demand than planned actually arrived,
and `build_surge_supply.py` runs it back through the reorder-point arithmetic.
"""

from __future__ import annotations

import os
import sys

from google.cloud import bigquery

PROJECT = os.getenv("GCP_PROJECT", "daysupply")
DATASET = os.getenv("BQ_DATASET", "daysupply")
LOCATION = os.getenv("BQ_LOCATION", "asia-south1")

PATTERN_VECTORS = f"`{PROJECT}.{DATASET}.pattern_vectors`"
REORDER_STATUS = f"`{PROJECT}.{DATASET}.reorder_status`"
SURGE_SIGNALS = f"`{PROJECT}.{DATASET}.surge_signals`"

# Iglewicz & Hoaglin's recommended cut for the modified z-score.
SURGE_Z = float(os.getenv("SURGE_Z", "3.5"))
# Materiality: a surge must be at least half again the seasonal expectation.
SURGE_MIN_RATIO = float(os.getenv("SURGE_MIN_RATIO", "1.5"))
# Actionability: below this many driver events in the month there is nothing to
# resupply against.
SURGE_MIN_ABSOLUTE = float(os.getenv("SURGE_MIN_ABSOLUTE", "100"))

# 0.75 quantile of the standard normal. Makes MAD a consistent estimator of
# sigma, so the modified z is on the same scale as an ordinary z.
MAD_CONSISTENCY = 0.6745

# n = 12 monthly observations per series.
SERIES_MONTHS = 12
CLASSICAL_Z_CEILING = (SERIES_MONTHS - 1) / SERIES_MONTHS ** 0.5

BUILD = f"""
CREATE OR REPLACE TABLE {SURGE_SIGNALS}
CLUSTER BY state, district_key, atc_class
AS
WITH pooled AS (
  -- The shipped pattern-exchange default: the mean multiplier across every
  -- district, per ATC class per calendar month.
  SELECT atc_class, month, AVG(multiplier) AS pooled_multiplier
  FROM {PATTERN_VECTORS}
  GROUP BY atc_class, month
),
resid AS (
  SELECT
    v.state, v.district_key, v.atc_class, v.month,
    v.value                                    AS observed,
    v.baseline,
    v.months_with_data,
    p.pooled_multiplier,
    v.baseline * p.pooled_multiplier           AS expected,
    v.value - v.baseline * p.pooled_multiplier AS residual
  FROM {PATTERN_VECTORS} v
  JOIN pooled p USING (atc_class, month)
  WHERE v.baseline > 0
),
centred AS (
  SELECT
    *,
    -- Median and MAD are computed within the series, so the month under test
    -- cannot inflate its own yardstick.
    PERCENTILE_CONT(residual, 0.5)
      OVER (PARTITION BY state, district_key, atc_class) AS median_residual,
    STDDEV_SAMP(residual)
      OVER (PARTITION BY state, district_key, atc_class) AS sd_residual,
    AVG(residual)
      OVER (PARTITION BY state, district_key, atc_class) AS mean_residual
  FROM resid
),
with_mad AS (
  SELECT
    *,
    PERCENTILE_CONT(ABS(residual - median_residual), 0.5)
      OVER (PARTITION BY state, district_key, atc_class) AS mad
  FROM centred
)
SELECT
  state,
  district_key,
  atc_class,
  month,
  ROUND(observed, 1)            AS observed,
  ROUND(expected, 1)            AS expected,
  ROUND(baseline, 1)            AS baseline,
  ROUND(pooled_multiplier, 4)   AS pooled_multiplier,
  ROUND(residual, 1)            AS residual,
  months_with_data,

  -- Reported for transparency; bounded at 3.175 with n = 12 and therefore not
  -- the operative test. See the module docstring.
  ROUND(SAFE_DIVIDE(residual - mean_residual, NULLIF(sd_residual, 0)), 2)
                                AS z_classical,

  -- The operative statistic.
  ROUND({MAD_CONSISTENCY} * SAFE_DIVIDE(residual - median_residual,
                                        NULLIF(mad, 0)), 2) AS z_modified,
  ROUND(mad, 2)                 AS mad,

  ROUND(SAFE_DIVIDE(observed, NULLIF(expected, 0)), 2) AS surge_multiplier,

  -- Every condition kept on the row so a near miss is explainable.
  ({MAD_CONSISTENCY} * SAFE_DIVIDE(residual - median_residual,
                                   NULLIF(mad, 0)) >= {SURGE_Z})
                                AS passes_statistic,
  (SAFE_DIVIDE(observed, NULLIF(expected, 0)) >= {SURGE_MIN_RATIO})
                                AS passes_ratio,
  (observed >= {SURGE_MIN_ABSOLUTE})
                                AS passes_magnitude,
  (mad IS NULL OR mad = 0)      AS mad_undefined,

  (mad > 0
   AND {MAD_CONSISTENCY} * SAFE_DIVIDE(residual - median_residual, mad)
       >= {SURGE_Z}
   AND SAFE_DIVIDE(observed, NULLIF(expected, 0)) >= {SURGE_MIN_RATIO}
   AND observed >= {SURGE_MIN_ABSOLUTE})  AS is_surge,

  {SURGE_Z}            AS threshold_z,
  {SURGE_MIN_RATIO}    AS threshold_ratio,
  {SURGE_MIN_ABSOLUTE} AS threshold_absolute
FROM with_mad
"""

SUMMARY = f"""
SELECT
  COUNT(*)                        AS series_months,
  COUNT(DISTINCT district_key)    AS districts,
  COUNT(DISTINCT atc_class)       AS atc_classes,
  COUNTIF(mad_undefined)          AS mad_undefined,
  COUNTIF(is_surge)               AS surges,
  COUNTIF(passes_statistic)       AS pass_stat,
  COUNTIF(passes_statistic AND NOT passes_ratio)     AS stat_but_small_ratio,
  COUNTIF(passes_statistic AND passes_ratio
          AND NOT passes_magnitude)                  AS stat_but_too_few,
  ROUND(MAX(z_classical), 2)      AS max_z_classical,
  ROUND(MAX(z_modified), 2)       AS max_z_modified,
  ROUND(MAX(surge_multiplier), 2) AS max_multiplier
FROM {SURGE_SIGNALS}
"""


def run() -> None:
    client = bigquery.Client(project=PROJECT, location=LOCATION)

    print(f"Building surge_signals "
          f"(modified z >= {SURGE_Z}, ratio >= {SURGE_MIN_RATIO}, "
          f"observed >= {SURGE_MIN_ABSOLUTE:.0f}) ...")
    client.query(BUILD).result()

    s = next(iter(client.query(SUMMARY).result()))
    print(f"\n  series-months scored:   {s.series_months:,}")
    print(f"  districts:              {s.districts}")
    print(f"  ATC classes:            {s.atc_classes}")
    print(f"  MAD undefined (excl.):  {s.mad_undefined:,}")
    print(f"\n  passed the statistic:   {s.pass_stat:,}")
    print(f"    rejected, ratio < {SURGE_MIN_RATIO}: {s.stat_but_small_ratio:,}")
    print(f"    rejected, too few events: {s.stat_but_too_few:,}")
    print(f"  SURGES:                 {s.surges:,}")

    print(f"\n  max classical z:        {s.max_z_classical}  "
          f"(ceiling for n={SERIES_MONTHS} is {CLASSICAL_Z_CEILING:.3f})")
    print(f"  max modified z:         {s.max_z_modified}")
    print(f"  max multiplier:         {s.max_multiplier}x")

    if (s.max_z_classical is not None
            and s.max_z_classical > CLASSICAL_Z_CEILING + 0.01):
        raise SystemExit(
            f"classical z {s.max_z_classical} exceeds the arithmetic ceiling "
            f"{CLASSICAL_Z_CEILING:.3f} — the series are not 12 months long")

    print("\n  Surges by ATC class:")
    for r in client.query(f"""
        SELECT atc_class, COUNTIF(is_surge) AS surges,
               COUNT(DISTINCT IF(is_surge, district_key, NULL)) AS districts,
               ROUND(MAX(IF(is_surge, surge_multiplier, NULL)), 1) AS peak
        FROM {SURGE_SIGNALS}
        GROUP BY atc_class HAVING surges > 0 ORDER BY surges DESC
    """).result():
        print(f"    {r.atc_class:8s} {r.surges:>4} surge-months  "
              f"{r.districts:>3} districts  peak {r.peak}x")

    print("\n  Largest surges that a stocked district would actually feel:")
    for r in client.query(f"""
        SELECT s.state, s.district_key, s.atc_class, s.month,
               CAST(s.observed AS INT64) AS observed,
               CAST(s.expected AS INT64) AS expected,
               s.surge_multiplier, s.z_modified, s.z_classical,
               COUNT(DISTINCT r.facility_id) AS facilities
        FROM {SURGE_SIGNALS} s
        JOIN {REORDER_STATUS} r
          ON UPPER(r.district) = s.district_key AND r.atc_class = s.atc_class
        WHERE s.is_surge
        GROUP BY 1,2,3,4,5,6,7,8,9
        ORDER BY s.surge_multiplier DESC LIMIT 10
    """).result():
        print(f"    {r.district_key[:16]:18s} {r.atc_class} {r.month:10s} "
              f"{r.observed:>6,} vs {r.expected:>6,} expected  "
              f"{r.surge_multiplier:>5}x  mod-z {r.z_modified:>6}  "
              f"classical-z {r.z_classical:>5}  {r.facilities} facilities")

    print("\nOK — surge is a departure from the pooled seasonal expectation, "
          "not a departure from flat.")


if __name__ == "__main__":
    try:
        run()
    except Exception as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        sys.exit(1)
