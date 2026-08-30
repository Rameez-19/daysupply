"""Build the supply-chain decision tables: reorder status and transfers.

This is the consultant-grade layer. It replaces a flat "14 days of cover"
threshold with the reorder point a public health supply chain actually uses,
ranks the resulting alerts the way a pharmacist would, and turns them into
specific transfers between named facilities.

Written to two tables so the dashboard reads a precomputed answer rather than
running this on every request:

* `daysupply.reorder_status`  — one row per facility x item
* `daysupply.recommendations` — one row per proposed transfer

---

**Reorder point** (Block C step 9)

    reorder_point = avg_daily_demand x lead_time_days + safety_stock
    safety_stock  = Z x demand_std_dev x sqrt(lead_time_days)

`avg_daily_demand` is the trained ARIMA_PLUS forecast. `demand_std_dev` is the
observed daily standard deviation from the ledger. `lead_time_days` is the
distance-derived proxy from `set_lead_times.py`. Z = 1.65, a 95% service level,
configurable via `SERVICE_LEVEL_Z`.

The flat threshold treated every facility identically. This does not: a PHC
145 km from its warehouse reorders at a materially higher stock level than one
2 km away, because it has to survive longer before the resupply lands.

**VEN weighting** (step 10)

Vital / Essential / Desirable, per WHO and MoHFW practice. Two facilities at
the same days of cover are not equally urgent: running out of a vital medicine
is a different event from running out of a desirable one. Priority is
`ven_weight x shortfall`, so a vital drug outranks a desirable one at equal
cover, and the ordering never depends on cover alone.

**FEFO** (step 11)

A batch is eligible only if it survives the journey plus a usable period at the
destination — `lead_time_days + 30`. Sending stock that expires on arrival
converts one facility's waste into another's, which is worse than doing nothing
because it also burns transport.

Which batch moves needs care. Plain "soonest expiring" is the right rule for
*issuing to a patient*, but for *redistribution* it would move the one batch
the donor is about to consume anyway and leave the stock it cannot use sitting
there. So a batch's risk is computed from its position in the FEFO queue:

    days_before_reached = units_expiring_earlier / donor_daily_demand
    consumable          = max(0, days_to_expiry - days_before_reached) x demand
    at_risk             = max(0, batch_qty - consumable)

Transfers prefer the **soonest-expiring at-risk batch** — FEFO ordering applied
to the stock the donor genuinely cannot consume in time. Where nothing is at
risk it falls back to the soonest-expiring batch outright. `waste_avoided_units`
is then a real quantity: units that would have been written off had they stayed.

Across the current position 245,134 units (7.5% of stock on hand) are at risk
by this definition, and 72,408 units were actually written off over the year.

**Therapeutic substitution** (step 12)

Where no donor holds the exact item, donors holding a different item in the
same **ATC level 4** chemical subgroup are considered — the first *five*
characters of the code, e.g. `C09AA` for ACE inhibitors.

Level 4 and not level 3. Matching on four characters put Zinc Sulphate
(`A12CB01`) and Magnesium sulphate (`A12CC02`) in the same bucket, because ATC
level 3 `A12C` is "other mineral supplements" — a heterogeneous group, not a
therapeutic class. Offering magnesium to a facility short of zinc is not a
substitution, it is a different drug. Level 4 is the granularity at which two
substances are genuinely interchangeable.

Substitution rows carry `is_substitution = TRUE` plus both the requested and
the supplied item name, and the UI states that clinical suitability must be
confirmed. Nothing may present a substitute as the requested item.
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
STOCK_EVENTS = f"`{PROJECT}.{DATASET}.stock_events`"
CURRENT_STOCK = f"`{PROJECT}.{DATASET}.current_stock`"
MODEL = f"`{PROJECT}.{DATASET}.demand_forecast`"
REORDER_STATUS = f"`{PROJECT}.{DATASET}.reorder_status`"
RECOMMENDATIONS = f"`{PROJECT}.{DATASET}.recommendations`"

# 1.65 standard deviations — a 95% service level.
SERVICE_LEVEL_Z = float(os.getenv("SERVICE_LEVEL_Z", "1.65"))
HORIZON = 30
TRANSFER_MAX_KM = float(os.getenv("TRANSFER_MAX_KM", "150"))
# Stock must remain usable this long after arrival to be worth moving.
USABLE_DAYS_AFTER_ARRIVAL = 30
# Target position after a transfer, as a multiple of the reorder point.
TARGET_MULTIPLE = 1.5
# The old flat rule, retained only to quantify what changed.
LEGACY_THRESHOLD_DAYS = 14

VEN_WEIGHT = ("CASE ven_class WHEN 'Vital' THEN 3.0 "
              "WHEN 'Essential' THEN 2.0 ELSE 1.0 END")

# The reorder-point expression, written once and reused so the threshold, the
# boolean and the priority score can never drift apart.
REORDER_EXPR = (
    "d.avg_daily_demand * f.lead_time_days "
    f"+ {SERVICE_LEVEL_Z} * IFNULL(o.demand_std_dev, 0) "
    "* SQRT(f.lead_time_days)"
)

BUILD_REORDER = f"""
CREATE OR REPLACE TABLE {REORDER_STATUS}
CLUSTER BY facility_id, item_id
AS
WITH forecast AS (
  SELECT
    SPLIT(series_id, '|')[OFFSET(0)] AS facility_id,
    SPLIT(series_id, '|')[OFFSET(1)] AS item_id,
    AVG(forecast_value)              AS avg_daily_demand
  FROM ML.FORECAST(MODEL {MODEL}, STRUCT({HORIZON} AS horizon))
  GROUP BY facility_id, item_id
),
observed AS (
  SELECT
    facility_id,
    item_id,
    STDDEV_SAMP(quantity) AS demand_std_dev,
    COUNT(*)              AS observed_days
  FROM {STOCK_EVENTS}
  WHERE event_type = 'dispensed'
  GROUP BY facility_id, item_id
),
stock AS (
  SELECT
    facility_id,
    item_id,
    SUM(remaining_qty)                               AS on_hand,
    MIN(IF(remaining_qty > 0, expiry_date, NULL))    AS soonest_expiry,
    MIN(IF(remaining_qty > 0, days_to_expiry, NULL)) AS days_to_soonest_expiry
  FROM {CURRENT_STOCK}
  GROUP BY facility_id, item_id
)
SELECT
  f.facility_id,
  f.name                   AS facility_name,
  f.admin_l1               AS state,
  f.admin_l2               AS district,
  f.lead_time_days,
  f.distance_to_hq_km,
  f.lead_time_is_estimated,
  i.item_id,
  i.display_name           AS item_name,
  i.unit,
  i.ven_class,
  i.atc_code,
  -- ATC level 4 (chemical subgroup), not level 3. See the module
  -- docstring: level 3 groups drugs that are not interchangeable.
  SUBSTR(i.atc_code, 1, 5) AS atc_class,
  IFNULL(s.on_hand, 0)     AS on_hand,
  s.soonest_expiry,
  s.days_to_soonest_expiry,
  ROUND(d.avg_daily_demand, 2)          AS avg_daily_demand,
  ROUND(IFNULL(o.demand_std_dev, 0), 2) AS demand_std_dev,
  ROUND({SERVICE_LEVEL_Z} * IFNULL(o.demand_std_dev, 0)
        * SQRT(f.lead_time_days), 1)    AS safety_stock,
  ROUND({REORDER_EXPR}, 1)              AS reorder_point,
  ROUND(d.avg_daily_demand * {LEGACY_THRESHOLD_DAYS}, 1) AS legacy_threshold,
  ROUND(SAFE_DIVIDE(IFNULL(s.on_hand, 0),
                    NULLIF(d.avg_daily_demand, 0)), 1) AS days_of_cover,
  IFNULL(s.on_hand, 0) <= ({REORDER_EXPR})            AS needs_reorder,
  ROUND(({VEN_WEIGHT}) * GREATEST(0, 1 - SAFE_DIVIDE(
    IFNULL(s.on_hand, 0), NULLIF({REORDER_EXPR}, 0))), 3) AS priority_score,
  CASE
    WHEN IFNULL(s.on_hand, 0) <= 0 THEN 'stocked_out'
    WHEN SAFE_DIVIDE(IFNULL(s.on_hand, 0), NULLIF(d.avg_daily_demand, 0))
         <= f.lead_time_days THEN 'critical'
    WHEN IFNULL(s.on_hand, 0) <= ({REORDER_EXPR}) THEN 'reorder'
    ELSE 'ok'
  END AS status,
  o.observed_days
FROM forecast d
JOIN {FACILITIES} f ON f.facility_id = d.facility_id
JOIN {ITEMS} i      ON i.item_id = d.item_id
LEFT JOIN observed o ON o.facility_id = d.facility_id AND o.item_id = d.item_id
LEFT JOIN stock s    ON s.facility_id = d.facility_id AND s.item_id = d.item_id
WHERE f.is_forecast_facility AND f.lead_time_days IS NOT NULL
"""

BUILD_RECOMMENDATIONS = f"""
CREATE OR REPLACE TABLE {RECOMMENDATIONS}
CLUSTER BY to_facility_id
AS
WITH deficit AS (
  SELECT * FROM {REORDER_STATUS}
  WHERE needs_reorder AND avg_daily_demand > 0
),
donor AS (
  SELECT r.*, r.on_hand - r.reorder_point AS spare_units
  FROM {REORDER_STATUS} r
  WHERE r.on_hand > r.reorder_point * {TARGET_MULTIPLE}
),
batch_risk AS (
  SELECT
    s.facility_id, s.item_id, s.batch_id, s.expiry_date, s.days_to_expiry,
    s.remaining_qty,
    IFNULL(SUM(s.remaining_qty) OVER (
      PARTITION BY s.facility_id, s.item_id
      ORDER BY s.expiry_date, s.batch_id
      ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
    ), 0) AS units_expiring_earlier,
    r.avg_daily_demand
  FROM {CURRENT_STOCK} s
  JOIN {REORDER_STATUS} r
    ON r.facility_id = s.facility_id AND r.item_id = s.item_id
  WHERE s.remaining_qty > 0
),
donor_batch AS (
  SELECT
    facility_id, item_id, batch_id, expiry_date, days_to_expiry, remaining_qty,
    at_risk_units,
    -- FEFO among the stock the donor cannot consume in time; if nothing is at
    -- risk, fall back to the soonest-expiring batch.
    ROW_NUMBER() OVER (
      PARTITION BY facility_id, item_id
      ORDER BY at_risk_units > 0 DESC, expiry_date, batch_id
    ) AS fefo_rank
  FROM (
    SELECT
      *,
      GREATEST(0, remaining_qty - GREATEST(0,
        avg_daily_demand * days_to_expiry - units_expiring_earlier
      )) AS at_risk_units
    FROM batch_risk
  )
),
paired AS (
  SELECT
    d.facility_id      AS to_facility_id,
    d.facility_name    AS to_facility_name,
    d.state            AS to_state,
    d.district         AS to_district,
    d.item_id          AS requested_item_id,
    d.item_name        AS requested_item_name,
    d.ven_class,
    d.unit,
    d.on_hand          AS receiver_on_hand,
    d.avg_daily_demand AS receiver_daily_demand,
    d.reorder_point    AS receiver_reorder_point,
    d.days_of_cover    AS receiver_cover_before,
    d.lead_time_days   AS receiver_lead_time,
    d.priority_score,
    d.status,
    s.facility_id      AS from_facility_id,
    s.facility_name    AS from_facility_name,
    s.item_id          AS supplied_item_id,
    s.item_name        AS supplied_item_name,
    s.on_hand          AS donor_on_hand,
    s.avg_daily_demand AS donor_daily_demand,
    s.days_of_cover    AS donor_cover_before,
    s.spare_units,
    s.item_id != d.item_id AS is_substitution,
    ROUND(ST_DISTANCE(
      ST_GEOGPOINT(fd.longitude, fd.latitude),
      ST_GEOGPOINT(fs.longitude, fs.latitude)) / 1000.0, 1) AS distance_km,
    b.batch_id       AS fefo_batch_id,
    b.expiry_date    AS fefo_expiry_date,
    b.days_to_expiry AS fefo_days_to_expiry,
    b.remaining_qty  AS fefo_batch_qty,
    b.at_risk_units  AS fefo_at_risk_units
  FROM deficit d
  JOIN donor s
    ON s.facility_id != d.facility_id
   AND (s.item_id = d.item_id
        OR (s.atc_class IS NOT NULL AND s.atc_class = d.atc_class))
  JOIN {FACILITIES} fd ON fd.facility_id = d.facility_id
  JOIN {FACILITIES} fs ON fs.facility_id = s.facility_id
  JOIN donor_batch b
    ON b.facility_id = s.facility_id AND b.item_id = s.item_id
   AND b.fefo_rank = 1
  WHERE fd.has_valid_coords AND fs.has_valid_coords
    AND ST_DISTANCE(ST_GEOGPOINT(fd.longitude, fd.latitude),
                    ST_GEOGPOINT(fs.longitude, fs.latitude)) / 1000.0
        <= {TRANSFER_MAX_KM}
    AND b.days_to_expiry >= d.lead_time_days + {USABLE_DAYS_AFTER_ARRIVAL}
),
sized AS (
  SELECT
    *,
    CAST(GREATEST(0, LEAST(
      receiver_reorder_point * {TARGET_MULTIPLE} - receiver_on_hand,
      spare_units,
      fefo_batch_qty
    )) AS INT64) AS quantity
  FROM paired
),
ranked AS (
  SELECT
    *,
    ROW_NUMBER() OVER (
      PARTITION BY to_facility_id, requested_item_id
      ORDER BY is_substitution, distance_km, fefo_days_to_expiry,
               from_facility_id
    ) AS rn
  FROM sized
  -- A transfer has to be worth the journey. Moving three tablets 20 km leaves
  -- the receiver exactly as short as it was, so require at least one full day
  -- of the receiver's own demand.
  WHERE quantity >= GREATEST(1, CAST(CEIL(receiver_daily_demand) AS INT64))
)
SELECT
  GENERATE_UUID() AS recommendation_id,
  to_facility_id, to_facility_name, to_state, to_district,
  from_facility_id, from_facility_name,
  requested_item_id, requested_item_name,
  supplied_item_id, supplied_item_name,
  is_substitution,
  ven_class, unit, priority_score, status,
  quantity, distance_km,
  fefo_batch_id, fefo_expiry_date, fefo_days_to_expiry,
  receiver_cover_before,
  ROUND(SAFE_DIVIDE(receiver_on_hand + quantity,
                    NULLIF(receiver_daily_demand, 0)), 1)
    AS receiver_cover_after,
  donor_cover_before,
  ROUND(SAFE_DIVIDE(donor_on_hand - quantity,
                    NULLIF(donor_daily_demand, 0)), 1) AS donor_cover_after,
  -- Units moved that the donor could not have consumed before this batch
  -- expired, and which would therefore have been written off in place.
  CAST(LEAST(quantity, fefo_at_risk_units) AS INT64) AS waste_avoided_units,
  CURRENT_TIMESTAMP() AS generated_at
FROM ranked
WHERE rn = 1
"""


BUILD_SUBSTITUTES = f"""
CREATE OR REPLACE TABLE `{PROJECT}.{DATASET}.substitutes`
CLUSTER BY facility_id
AS
-- For every item a facility needs to reorder, the therapeutic alternatives it
-- already holds. Same ATC subgroup, same facility, in stock above that
-- alternative's own reorder point. This is what a pharmacist can act on today,
-- without waiting for any transfer.
SELECT
  d.facility_id,
  d.facility_name,
  d.state,
  d.district,
  d.item_id            AS requested_item_id,
  d.item_name          AS requested_item_name,
  d.ven_class          AS requested_ven_class,
  d.on_hand            AS requested_on_hand,
  d.days_of_cover      AS requested_days_of_cover,
  a.item_id            AS alternative_item_id,
  a.item_name          AS alternative_item_name,
  a.ven_class          AS alternative_ven_class,
  a.atc_code           AS alternative_atc_code,
  a.on_hand            AS alternative_on_hand,
  a.days_of_cover      AS alternative_days_of_cover,
  a.unit,
  d.atc_class,
  ROW_NUMBER() OVER (
    PARTITION BY d.facility_id, d.item_id ORDER BY a.days_of_cover DESC
  ) AS rank_by_cover
FROM {REORDER_STATUS} d
JOIN {REORDER_STATUS} a
  ON a.facility_id = d.facility_id
 AND a.item_id != d.item_id
 AND a.atc_class IS NOT NULL
 AND a.atc_class = d.atc_class
WHERE d.needs_reorder
  AND a.on_hand > a.reorder_point
"""


def run() -> None:
    client = bigquery.Client(project=PROJECT, location=LOCATION)

    print(f"Building reorder_status (Z={SERVICE_LEVEL_Z}) ...")
    client.query(BUILD_REORDER).result()
    row = next(iter(client.query(f"""
        SELECT COUNT(*) AS rows_out,
               COUNTIF(needs_reorder) AS needing_reorder,
               COUNTIF(status = 'stocked_out') AS stocked_out,
               COUNTIF(status = 'critical') AS critical,
               ROUND(AVG(reorder_point), 1) AS avg_reorder_point,
               ROUND(AVG(legacy_threshold), 1) AS avg_legacy,
               COUNTIF(needs_reorder AND on_hand > legacy_threshold)
                 AS caught_only_by_new_rule,
               COUNTIF(NOT needs_reorder AND on_hand <= legacy_threshold)
                 AS flagged_only_by_old_rule
        FROM {REORDER_STATUS}
    """).result()))
    print(f"  facility-item rows:  {row.rows_out:,}")
    print(f"  needing reorder:     {row.needing_reorder:,}")
    print(f"    stocked out:       {row.stocked_out:,}")
    print(f"    critical:          {row.critical:,}")
    print(f"  mean reorder point:  {row.avg_reorder_point:,} units")
    print(f"  mean flat-14 point:  {row.avg_legacy:,} units")
    print(f"  caught ONLY by the lead-time rule: "
          f"{row.caught_only_by_new_rule:,}")
    print(f"  flagged ONLY by the old flat rule: "
          f"{row.flagged_only_by_old_rule:,}")

    print("\nBuilding recommendations (FEFO, ATC substitution) ...")
    client.query(BUILD_RECOMMENDATIONS).result()
    rec = next(iter(client.query(f"""
        SELECT COUNT(*) AS n,
               COUNTIF(is_substitution) AS substitutions,
               SUM(quantity) AS units,
               SUM(waste_avoided_units) AS waste_avoided,
               ROUND(AVG(distance_km), 1) AS avg_km,
               COUNT(DISTINCT to_facility_id) AS receivers,
               COUNT(DISTINCT from_facility_id) AS donors
        FROM {RECOMMENDATIONS}
    """).result()))
    print(f"  recommendations:     {rec.n:,}")
    print(f"    substitutions:     {rec.substitutions:,}")
    print(f"    receivers/donors:  {rec.receivers}/{rec.donors}")
    print(f"  units to move:       {rec.units:,}")
    print(f"  waste avoided:       {rec.waste_avoided:,} units")
    print(f"  mean distance:       {rec.avg_km} km")

    print("\nBuilding same-facility therapeutic substitutes ...")
    client.query(BUILD_SUBSTITUTES).result()
    sub = next(iter(client.query(f"""
        SELECT COUNT(*) AS n,
               COUNT(DISTINCT CONCAT(facility_id, '|', requested_item_id))
                 AS covered_deficits
        FROM `{PROJECT}.{DATASET}.substitutes`
    """).result()))
    print(f"  alternatives found:  {sub.n:,}")
    print(f"  deficits with an in-stock alternative: {sub.covered_deficits:,}")

    if row.rows_out == 0:
        raise SystemExit("reorder_status is empty")

    # A transfer that pushes the donor below its own reorder point is the one
    # thing this engine must never propose.
    bad = next(iter(client.query(f"""
        SELECT COUNTIF(donor_cover_after < 0) AS negative_donor
        FROM {RECOMMENDATIONS}
    """).result()))
    if bad.negative_donor:
        raise SystemExit(
            f"{bad.negative_donor} transfers would push a donor negative")

    print("\nOK — supply plan built.")


if __name__ == "__main__":
    try:
        run()
    except Exception as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        sys.exit(1)
