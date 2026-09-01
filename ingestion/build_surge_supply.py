"""What a surge does to the supply answer.

Detecting a surge is not the deliverable. Changing the reorder arithmetic is.
This module takes `surge_multiplier` from `build_surge_signals.py` and runs it
back through the same reorder-point formula `build_supply_plan.py` uses, so the
surge and the steady state are computed the same way and are comparable line by
line.

    reorder_point = avg_daily_demand x lead_time + Z x sigma x sqrt(lead_time)

Under a surge of multiplier m:

    mu_surge    = avg_daily_demand x m
    sigma_surge = demand_std_dev  x m

**Scaling sigma proportionally is an assumption and it is the conservative
one.** If case arrivals were Poisson, variance would scale with the mean and
sigma would scale with sqrt(m) — a smaller safety stock. Outbreak arrivals are
overdispersed and clustered rather than Poisson, so variability grows at least
as fast as the level. Proportional scaling is defensible on those grounds and
errs towards holding more stock. The alternative is available as
`SURGE_SIGMA_EXPONENT` (1.0 proportional, 0.5 Poisson).

## Lead time is what decides the answer

The reorder point tells a facility to order. Whether ordering *helps* is a
different question, and under surge it is usually the binding one:

    days_to_stockout = on_hand / mu_surge

If `days_to_stockout < lead_time_days`, the facility runs out **before** a
central indent can physically arrive. Reordering is still correct, but it
cannot be the answer for this episode. The only thing that reaches the facility
in time is stock that is already inside the district. The table carries this as
`lead_time_decisive`, and the UI is required to say so in those words rather
than showing an order quantity and implying the problem is handled.

This is why a 19-day facility and a 4-day facility respond completely
differently to the same surge, and it is the single most important operational
consequence of the whole model.

## Network absorption

The facility-level question is "does this PHC hold". The district-level
question is "does the district hold", and it is the one a district programme
officer actually asks. For a district, an ATC class and a hypothetical
multiplier k:

    absorption_days = district_on_hand / (district_daily_demand x k)
    absorbs         = absorption_days >= slowest facility lead time

The district absorbs the spike if the stock already inside it can carry every
facility through until outside resupply can land at the slowest of them. This
deliberately pools stock across the district, because lateral transfer is
exactly what makes pooled stock reachable — it is the capacity that
redistribution unlocks, which is the claim the whole system rests on.
"""

from __future__ import annotations

import os
import sys

from google.cloud import bigquery

PROJECT = os.getenv("GCP_PROJECT", "daysupply")
DATASET = os.getenv("BQ_DATASET", "daysupply")
LOCATION = os.getenv("BQ_LOCATION", "asia-south1")

REORDER_STATUS = f"`{PROJECT}.{DATASET}.reorder_status`"
SURGE_SIGNALS = f"`{PROJECT}.{DATASET}.surge_signals`"
SURGE_SUPPLY = f"`{PROJECT}.{DATASET}.surge_supply_impact`"
NETWORK_ABSORPTION = f"`{PROJECT}.{DATASET}.network_absorption`"

# Same service level as the steady-state plan, so the two are comparable.
SERVICE_LEVEL_Z = float(os.getenv("SERVICE_LEVEL_Z", "1.65"))
# 1.0 = sigma scales with the level (overdispersed arrivals, the default).
# 0.5 = sigma scales with sqrt of the level (Poisson arrivals).
SURGE_SIGMA_EXPONENT = float(os.getenv("SURGE_SIGMA_EXPONENT", "1.0"))

# Multipliers offered by scenario mode.
SCENARIO_MULTIPLIERS = (2.0, 3.0, 5.0)

BUILD_SUPPLY_IMPACT = f"""
CREATE OR REPLACE TABLE {SURGE_SUPPLY}
CLUSTER BY state, district, atc_class
AS
WITH surge AS (
  SELECT state, district_key, atc_class, month,
         surge_multiplier, z_modified, observed, expected
  FROM {SURGE_SIGNALS}
  WHERE is_surge
),
joined AS (
  SELECT
    r.*,
    s.month           AS surge_month,
    s.surge_multiplier,
    s.z_modified,
    s.observed        AS driver_observed,
    s.expected        AS driver_expected,
    r.avg_daily_demand * s.surge_multiplier AS mu_surge,
    IFNULL(r.demand_std_dev, 0)
      * POW(s.surge_multiplier, {SURGE_SIGMA_EXPONENT}) AS sigma_surge
  FROM {REORDER_STATUS} r
  JOIN surge s
    ON UPPER(r.district) = s.district_key
   AND r.atc_class = s.atc_class
  WHERE r.atc_class IS NOT NULL
    AND r.avg_daily_demand > 0
)
SELECT
  facility_id, facility_name, state, district,
  item_id, item_name, unit, ven_class, atc_class,
  lead_time_days, lead_time_is_estimated, distance_to_hq_km,
  surge_month, surge_multiplier, z_modified,
  CAST(driver_observed AS INT64) AS driver_observed,
  CAST(driver_expected AS INT64) AS driver_expected,

  on_hand,
  -- Steady state, exactly as build_supply_plan.py computed it.
  avg_daily_demand,
  reorder_point,
  days_of_cover,
  needs_reorder,
  status                                        AS status_baseline,

  -- Under surge.
  ROUND(mu_surge, 2)                            AS avg_daily_demand_surge,
  ROUND(mu_surge * lead_time_days
        + {SERVICE_LEVEL_Z} * sigma_surge * SQRT(lead_time_days), 1)
                                                AS reorder_point_surge,
  ROUND(SAFE_DIVIDE(on_hand, mu_surge), 1)      AS days_of_cover_surge,
  ROUND(SAFE_DIVIDE(on_hand, mu_surge), 1)      AS days_to_stockout,

  (on_hand < mu_surge * lead_time_days
   + {SERVICE_LEVEL_Z} * sigma_surge * SQRT(lead_time_days))
                                                AS needs_reorder_surge,

  -- A facility that runs out before an indent can arrive cannot be helped by
  -- ordering. Only stock already inside the district reaches it in time.
  (SAFE_DIVIDE(on_hand, mu_surge) < lead_time_days)
                                                AS lead_time_decisive,

  -- Was fine at steady state, is not fine under surge. This is the set the
  -- early warning exists to surface.
  (NOT needs_reorder
   AND on_hand < mu_surge * lead_time_days
       + {SERVICE_LEVEL_Z} * sigma_surge * SQRT(lead_time_days))
                                                AS newly_at_risk,

  GREATEST(ROUND(mu_surge * lead_time_days
                 + {SERVICE_LEVEL_Z} * sigma_surge * SQRT(lead_time_days)
                 - on_hand, 0), 0)              AS shortfall_units,

  CASE
    WHEN SAFE_DIVIDE(on_hand, mu_surge) < lead_time_days
      THEN 'transfer_only'
    WHEN on_hand < mu_surge * lead_time_days
         + {SERVICE_LEVEL_Z} * sigma_surge * SQRT(lead_time_days)
      THEN 'reorder_now'
    ELSE 'holds'
  END                                           AS surge_action,

  {SERVICE_LEVEL_Z}       AS service_level_z,
  {SURGE_SIGMA_EXPONENT}  AS sigma_exponent
FROM joined
"""

# Absorption is evaluated for every district and ATC class that holds stock,
# at each scenario multiplier — including districts with no detected surge,
# because "what if" is the whole point of scenario mode.
BUILD_ABSORPTION = f"""
CREATE OR REPLACE TABLE {NETWORK_ABSORPTION}
CLUSTER BY state, district, atc_class
AS
WITH district_position AS (
  SELECT
    state, district, atc_class,
    COUNT(DISTINCT facility_id)        AS facilities,
    COUNT(*)                           AS stock_rows,
    SUM(on_hand)                       AS district_on_hand,
    ROUND(SUM(avg_daily_demand), 2)    AS district_daily_demand,
    MAX(lead_time_days)                AS slowest_lead_time,
    MIN(lead_time_days)                AS fastest_lead_time,
    ANY_VALUE(ven_class)               AS ven_class
  FROM {REORDER_STATUS}
  WHERE atc_class IS NOT NULL AND avg_daily_demand > 0
  GROUP BY state, district, atc_class
),
scenarios AS (
  SELECT * FROM UNNEST({list(SCENARIO_MULTIPLIERS)}) AS multiplier
)
SELECT
  d.state, d.district, d.atc_class, d.ven_class,
  d.facilities, d.stock_rows,
  d.district_on_hand, d.district_daily_demand,
  d.slowest_lead_time, d.fastest_lead_time,
  s.multiplier,
  ROUND(SAFE_DIVIDE(d.district_on_hand,
                    d.district_daily_demand * s.multiplier), 1)
                                       AS absorption_days,
  (SAFE_DIVIDE(d.district_on_hand, d.district_daily_demand * s.multiplier)
   >= d.slowest_lead_time)             AS absorbs,
  GREATEST(CAST(ROUND(d.district_daily_demand * s.multiplier
                      * d.slowest_lead_time - d.district_on_hand) AS INT64), 0)
                                       AS units_short,
  -- How large a spike this district could take before it stops absorbing.
  ROUND(SAFE_DIVIDE(d.district_on_hand,
                    d.district_daily_demand * d.slowest_lead_time), 2)
                                       AS max_multiplier_absorbed
FROM district_position d
CROSS JOIN scenarios s
"""


# Surge-aware redistribution differs from the steady-state engine in three
# ways, each of them a deliberate policy choice:
#
# 1. **The radius widens.** At steady state a 150 km transfer is hard to
#    justify against simply waiting for the next indent. Under surge, for a
#    facility that will stock out before an indent can arrive, a longer journey
#    is the only option that exists. SURGE_TRANSFER_MAX_KM defaults to 300.
#
# 2. **Vital items get first claim.** A donor's spare stock is finite. The
#    steady-state engine ranks candidates per receiver and can promise the same
#    units to several of them. Under scarcity that is not acceptable, so donor
#    stock is allocated cumulatively in VEN order and cut off when exhausted —
#    a Vital deficit outranks an Essential one for the same donor.
#
# 3. **The donor is protected against its own surge.** A donor in a surging
#    district is judged against its surge reorder point, not its steady one, so
#    the engine cannot strip a facility that is about to need the stock itself.
SURGE_TRANSFER_MAX_KM = float(os.getenv("SURGE_TRANSFER_MAX_KM", "300"))
TARGET_MULTIPLE = 1.5
USABLE_DAYS_AFTER_ARRIVAL = 30
VEN_RANK = ("CASE ven_class WHEN 'Vital' THEN 1 "
            "WHEN 'Essential' THEN 2 ELSE 3 END")

SURGE_RECOMMENDATIONS = f"`{PROJECT}.{DATASET}.surge_recommendations`"
FACILITIES = f"`{PROJECT}.{DATASET}.facilities`"
CURRENT_STOCK = f"`{PROJECT}.{DATASET}.current_stock`"

BUILD_SURGE_RECOMMENDATIONS = f"""
CREATE OR REPLACE TABLE {SURGE_RECOMMENDATIONS}
CLUSTER BY to_facility_id
AS
WITH deficit AS (
  SELECT * FROM {SURGE_SUPPLY} WHERE needs_reorder_surge
),
-- A donor is judged against its surge reorder point where it has one.
donor_floor AS (
  SELECT r.facility_id, r.item_id, r.item_name, r.atc_class, r.ven_class,
         r.facility_name, r.state, r.district,
         r.on_hand, r.avg_daily_demand, r.days_of_cover,
         IFNULL(MAX(s.reorder_point_surge), r.reorder_point) AS floor_units
  FROM {REORDER_STATUS} r
  LEFT JOIN {SURGE_SUPPLY} s
    ON s.facility_id = r.facility_id AND s.item_id = r.item_id
  GROUP BY r.facility_id, r.item_id, r.item_name, r.atc_class, r.ven_class,
           r.facility_name, r.state, r.district, r.on_hand,
           r.avg_daily_demand, r.days_of_cover, r.reorder_point
),
donor AS (
  SELECT *, on_hand - floor_units AS spare_units
  FROM donor_floor
  WHERE on_hand > floor_units AND on_hand - floor_units >= 1
),
paired AS (
  SELECT
    d.facility_id    AS to_facility_id,
    d.facility_name  AS to_facility_name,
    d.state          AS to_state,
    d.district       AS to_district,
    d.item_id        AS requested_item_id,
    d.item_name      AS requested_item_name,
    d.ven_class, d.unit, d.atc_class,
    d.surge_month, d.surge_multiplier,
    d.on_hand                AS receiver_on_hand,
    d.avg_daily_demand_surge AS receiver_daily_demand,
    d.reorder_point_surge    AS receiver_reorder_point,
    d.days_of_cover_surge    AS receiver_cover_before,
    d.lead_time_days         AS receiver_lead_time,
    d.lead_time_decisive,
    d.surge_action,
    s.facility_id    AS from_facility_id,
    s.facility_name  AS from_facility_name,
    s.item_id        AS supplied_item_id,
    s.item_name      AS supplied_item_name,
    s.on_hand        AS donor_on_hand,
    s.avg_daily_demand AS donor_daily_demand,
    s.days_of_cover  AS donor_cover_before,
    s.spare_units,
    s.item_id != d.item_id AS is_substitution,
    ROUND(ST_DISTANCE(ST_GEOGPOINT(fd.longitude, fd.latitude),
                      ST_GEOGPOINT(fs.longitude, fs.latitude)) / 1000.0, 1)
                     AS distance_km,
    b.batch_id       AS fefo_batch_id,
    b.expiry_date    AS fefo_expiry_date,
    b.days_to_expiry AS fefo_days_to_expiry,
    b.remaining_qty  AS fefo_batch_qty
  FROM deficit d
  JOIN donor s
    ON s.facility_id != d.facility_id
   AND (s.item_id = d.item_id
        OR (s.atc_class IS NOT NULL AND s.atc_class = d.atc_class))
  JOIN {FACILITIES} fd ON fd.facility_id = d.facility_id
  JOIN {FACILITIES} fs ON fs.facility_id = s.facility_id
  JOIN (
    SELECT facility_id, item_id, batch_id, expiry_date, days_to_expiry,
           remaining_qty,
           ROW_NUMBER() OVER (PARTITION BY facility_id, item_id
                              ORDER BY expiry_date, batch_id) AS fefo_rank
    FROM {CURRENT_STOCK} WHERE remaining_qty > 0
  ) b
    ON b.facility_id = s.facility_id AND b.item_id = s.item_id
   AND b.fefo_rank = 1
  WHERE fd.has_valid_coords AND fs.has_valid_coords
    AND ST_DISTANCE(ST_GEOGPOINT(fd.longitude, fd.latitude),
                    ST_GEOGPOINT(fs.longitude, fs.latitude)) / 1000.0
        <= {SURGE_TRANSFER_MAX_KM}
    AND b.days_to_expiry >= d.lead_time_days + {USABLE_DAYS_AFTER_ARRIVAL}
),
-- One donor-item, one best receiver pairing, then size the request.
best_pair AS (
  SELECT * EXCEPT(rn) FROM (
    SELECT *,
      CAST(GREATEST(0, LEAST(
        receiver_reorder_point * {TARGET_MULTIPLE} - receiver_on_hand,
        spare_units, fefo_batch_qty)) AS INT64) AS requested_quantity,
      ROW_NUMBER() OVER (
        PARTITION BY to_facility_id, requested_item_id, surge_month
        ORDER BY is_substitution, distance_km, fefo_days_to_expiry,
                 from_facility_id) AS rn
    FROM paired
  )
  WHERE rn = 1
),
-- Vital first. A donor's spare stock is finite, so claims are accumulated in
-- priority order and anything past the donor's capacity is not promised.
allocated AS (
  SELECT
    *,
    SUM(requested_quantity) OVER (
      PARTITION BY from_facility_id, supplied_item_id, surge_month
      ORDER BY {VEN_RANK}, lead_time_decisive DESC, receiver_cover_before,
               distance_km, to_facility_id
      ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS cumulative_claim,
    ROW_NUMBER() OVER (
      PARTITION BY from_facility_id, supplied_item_id, surge_month
      ORDER BY {VEN_RANK}, lead_time_decisive DESC, receiver_cover_before,
               distance_km, to_facility_id
    ) AS claim_rank
  FROM best_pair
  WHERE requested_quantity >= GREATEST(
    1, CAST(CEIL(receiver_daily_demand) AS INT64))
)
SELECT
  GENERATE_UUID() AS recommendation_id,
  to_facility_id, to_facility_name, to_state, to_district,
  from_facility_id, from_facility_name,
  requested_item_id, requested_item_name,
  supplied_item_id, supplied_item_name,
  is_substitution, ven_class, unit, atc_class,
  surge_month, surge_multiplier,
  lead_time_decisive,
  surge_action,
  claim_rank,
  requested_quantity,
  -- What the donor can actually honour once earlier claims are met.
  CAST(LEAST(requested_quantity,
             GREATEST(spare_units - (cumulative_claim - requested_quantity), 0))
       AS INT64) AS quantity,
  (cumulative_claim > spare_units) AS donor_partially_exhausted,
  distance_km, receiver_lead_time,
  fefo_batch_id, fefo_expiry_date, fefo_days_to_expiry,
  receiver_cover_before,
  ROUND(SAFE_DIVIDE(receiver_on_hand
        + LEAST(requested_quantity,
                GREATEST(spare_units - (cumulative_claim - requested_quantity),
                         0)),
        NULLIF(receiver_daily_demand, 0)), 1) AS receiver_cover_after,
  donor_cover_before,
  ROUND(SAFE_DIVIDE(donor_on_hand
        - LEAST(requested_quantity,
                GREATEST(spare_units - (cumulative_claim - requested_quantity),
                         0)),
        NULLIF(donor_daily_demand, 0)), 1) AS donor_cover_after,
  {SURGE_TRANSFER_MAX_KM} AS transfer_max_km,
  CURRENT_TIMESTAMP() AS generated_at
FROM allocated
WHERE LEAST(requested_quantity,
            GREATEST(spare_units - (cumulative_claim - requested_quantity), 0))
      >= 1
"""


def run() -> None:
    client = bigquery.Client(project=PROJECT, location=LOCATION)

    print(f"Building surge_supply_impact (Z={SERVICE_LEVEL_Z}, "
          f"sigma exponent {SURGE_SIGMA_EXPONENT}) ...")
    client.query(BUILD_SUPPLY_IMPACT).result()

    s = next(iter(client.query(f"""
        SELECT COUNT(*) AS rows_,
               COUNT(DISTINCT facility_id) AS facilities,
               COUNT(DISTINCT district)    AS districts,
               COUNT(DISTINCT atc_class)   AS classes,
               COUNTIF(needs_reorder)         AS reorder_baseline,
               COUNTIF(needs_reorder_surge)   AS reorder_surge,
               COUNTIF(newly_at_risk)         AS newly_at_risk,
               COUNTIF(lead_time_decisive)    AS transfer_only,
               SUM(shortfall_units)           AS shortfall
        FROM {SURGE_SUPPLY}
    """).result()))
    print(f"\n  facility-item-month rows:  {s.rows_:,}")
    print(f"  facilities / districts:    {s.facilities} / {s.districts}")
    print(f"  ATC classes:               {s.classes}")
    print(f"\n  needs reorder, steady:     {s.reorder_baseline:,}")
    print(f"  needs reorder, under surge:{s.reorder_surge:,}")
    print(f"  NEWLY at risk:             {s.newly_at_risk:,}")
    print(f"  lead time decisive:        {s.transfer_only:,} "
          f"(cannot be resupplied in time — transfer only)")
    print(f"  total shortfall:           {s.shortfall:,.0f} units")

    print("\nBuilding network_absorption "
          f"({', '.join(f'{m:g}x' for m in SCENARIO_MULTIPLIERS)}) ...")
    client.query(BUILD_ABSORPTION).result()

    print("\n  Can a district absorb the spike?")
    for r in client.query(f"""
        SELECT multiplier,
               COUNT(*) AS district_classes,
               COUNTIF(absorbs) AS absorbs,
               ROUND(100 * SAFE_DIVIDE(COUNTIF(absorbs), COUNT(*)), 1) AS pct,
               SUM(units_short) AS units_short
        FROM {NETWORK_ABSORPTION}
        GROUP BY multiplier ORDER BY multiplier
    """).result():
        print(f"    {r.multiplier:g}x  {r.absorbs:>4} of {r.district_classes:>4} "
              f"district-classes hold ({r.pct}%)  "
              f"{r.units_short:>9,} units short")

    print("\n  Lead time decides it — surge response by lead-time band:")
    for r in client.query(f"""
        SELECT CASE
                 WHEN lead_time_days <= 5  THEN '1. <= 5 days'
                 WHEN lead_time_days <= 10 THEN '2. 6-10 days'
                 WHEN lead_time_days <= 15 THEN '3. 11-15 days'
                 ELSE '4. > 15 days' END AS band,
               COUNT(*) AS rows_,
               COUNTIF(lead_time_decisive) AS transfer_only,
               ROUND(100 * SAFE_DIVIDE(COUNTIF(lead_time_decisive),
                                       COUNT(*)), 1) AS pct
        FROM {SURGE_SUPPLY}
        GROUP BY band ORDER BY band
    """).result():
        print(f"    {r.band:14s} {r.transfer_only:>4} of {r.rows_:>5} "
              f"can only be served laterally ({r.pct}%)")

    print(f"\nBuilding surge_recommendations "
          f"(radius {SURGE_TRANSFER_MAX_KM:.0f} km, Vital first) ...")
    client.query(BUILD_SURGE_RECOMMENDATIONS).result()

    t = next(iter(client.query(f"""
        SELECT COUNT(*) AS transfers,
               COUNT(DISTINCT to_facility_id)   AS receivers,
               COUNT(DISTINCT from_facility_id) AS donors,
               SUM(quantity)                    AS units,
               ROUND(AVG(distance_km), 1)       AS mean_km,
               ROUND(MAX(distance_km), 1)       AS max_km,
               COUNTIF(distance_km > 150)       AS beyond_steady_radius,
               COUNTIF(lead_time_decisive)      AS only_option,
               COUNTIF(donor_partially_exhausted) AS rationed,
               COUNTIF(is_substitution)         AS substitutions
        FROM {SURGE_RECOMMENDATIONS}
    """).result()))
    print(f"\n  transfers:                 {t.transfers:,}")
    print(f"  receivers / donors:        {t.receivers} / {t.donors}")
    print(f"  units to move:             {t.units:,}")
    print(f"  mean / max distance:       {t.mean_km} km / {t.max_km} km")
    print(f"  beyond the 150 km steady radius: {t.beyond_steady_radius} "
          f"(only reachable because the radius widened)")
    print(f"  where transfer is the ONLY option: {t.only_option}")
    print(f"  rationed by donor capacity: {t.rationed}")
    print(f"  substitutions:             {t.substitutions}")

    print("\n  Who gets served first (donor stock is finite):")
    for r in client.query(f"""
        SELECT ven_class, COUNT(*) AS transfers, SUM(quantity) AS units,
               ROUND(AVG(claim_rank), 2) AS mean_claim_rank,
               COUNTIF(donor_partially_exhausted) AS rationed
        FROM {SURGE_RECOMMENDATIONS}
        GROUP BY ven_class ORDER BY MIN({VEN_RANK})
    """).result():
        print(f"    {r.ven_class:12s} {r.transfers:>4} transfers  "
              f"{r.units:>7,} units  mean claim rank {r.mean_claim_rank}  "
              f"{r.rationed} rationed")

    print("\nOK — the surge changes the reorder point, lead time decides "
          "whether reordering can possibly work, and Vital claims stock first.")


if __name__ == "__main__":
    try:
        run()
    except Exception as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        sys.exit(1)
