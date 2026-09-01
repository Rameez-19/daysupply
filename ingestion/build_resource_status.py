"""Bed pressure and staffing status, and what each one implies.

Beds and personnel deliberately produce *different* outputs from medicines,
because the resources behave differently:

* **Medicines transfer.** A deficit at one facility is met by a surplus at
  another, which is what `build_supply_plan.py` already does.
* **Beds do not transfer.** You cannot move a bed to a patient in useful time.
  Bed pressure is a *referral* signal: which facility nearby has capacity
  tonight. So this builds `bed_referrals`, not bed transfers.
* **Personnel transfer, but as people, not units.** A facility with nobody in a
  cadre needs a person reassigned from a facility that has slack, within
  reasonable travelling distance. That is a redistribution problem of the same
  shape as medicines, so it reuses the same distance and donor-protection
  logic.

  Two things limit it, and both are real rather than defects:

  **Four of the five cadres have an establishment of one post.** A PHC is
  sanctioned one doctor, one pharmacist, one male and one female health
  assistant. No facility can donate its only doctor, so a doctor vacancy cannot
  be answered by reallocation at all — it needs recruitment. Only nursing, at
  about 2.5 sanctioned posts, can ever have someone to spare.

  **The forecast facilities are deliberately far apart.** They were chosen to
  span 116 districts for geographic reach, so the nearest nursing-short and
  nursing-adequate pair is over 1,200 km apart — far beyond any sensible staff
  reassignment. The engine is correct and returns nothing, which is the honest
  answer for this facility set. A district-dense deployment would produce
  candidates; this one cannot.

Rule-based throughout, no ARIMA — see `generate_bed_personnel.py` for why.
"""

from __future__ import annotations

import os
import sys

from google.cloud import bigquery

PROJECT = os.getenv("GCP_PROJECT", "daysupply")
DATASET = os.getenv("BQ_DATASET", "daysupply")
LOCATION = os.getenv("BQ_LOCATION", "asia-south1")

FACILITIES = f"`{PROJECT}.{DATASET}.facilities`"
RESOURCE_EVENTS = f"`{PROJECT}.{DATASET}.resource_events`"
FACILITY_STAFFING = f"`{PROJECT}.{DATASET}.facility_staffing`"
BED_STATUS = f"`{PROJECT}.{DATASET}.bed_status`"
BED_REFERRALS = f"`{PROJECT}.{DATASET}.bed_referrals`"
STAFF_STATUS = f"`{PROJECT}.{DATASET}.staff_status`"
STAFF_REALLOCATION = f"`{PROJECT}.{DATASET}.staff_reallocation`"

# Recent window used for the current picture.
WINDOW_DAYS = 30
# Above this mean occupancy a facility is under pressure and should be routed
# around rather than referred to.
PRESSURE_THRESHOLD = 0.80
# A referral is only sensible within a reasonable journey.
REFERRAL_MAX_KM = 50.0
# Staff reallocation travels further than a patient would, but not indefinitely.
REALLOCATION_MAX_KM = 60.0

BUILD_BED_STATUS = f"""
CREATE OR REPLACE TABLE {BED_STATUS}
CLUSTER BY state, district
AS
WITH as_of AS (
  SELECT MAX(DATE(event_ts)) AS today FROM {RESOURCE_EVENTS}
),
recent AS (
  SELECT
    e.facility_id,
    ANY_VALUE(e.item_id)     AS bed_type,
    ANY_VALUE(e.capacity)    AS capacity,
    AVG(IF(e.event_type = 'occupancy', e.quantity, NULL))   AS mean_occupied,
    MAX(IF(e.event_type = 'occupancy', e.quantity, NULL))   AS peak_occupied,
    SUM(IF(e.event_type = 'turned_away', e.quantity, 0))    AS turned_away,
    COUNTIF(e.event_type = 'occupancy')                     AS days_reported
  FROM {RESOURCE_EVENTS} e
  CROSS JOIN as_of a
  WHERE e.resource_type = 'bed'
    AND DATE(e.event_ts) > DATE_SUB(a.today, INTERVAL {WINDOW_DAYS} DAY)
  GROUP BY e.facility_id
)
SELECT
  f.facility_id,
  f.name        AS facility_name,
  f.admin_l1    AS state,
  f.admin_l2    AS district,
  f.latitude,
  f.longitude,
  r.bed_type,
  f.beds_are_day_care,
  CAST(r.capacity AS INT64)                       AS bed_capacity,
  ROUND(r.mean_occupied, 2)                       AS mean_occupied,
  CAST(r.peak_occupied AS INT64)                  AS peak_occupied,
  ROUND(SAFE_DIVIDE(r.mean_occupied, NULLIF(r.capacity, 0)), 3)
                                                  AS occupancy_rate,
  GREATEST(CAST(r.capacity AS INT64) - CAST(ROUND(r.mean_occupied) AS INT64), 0)
                                                  AS free_beds,
  r.turned_away,
  r.days_reported,
  CASE
    WHEN r.turned_away > 0 THEN 'over_capacity'
    WHEN SAFE_DIVIDE(r.mean_occupied, NULLIF(r.capacity, 0))
         >= {PRESSURE_THRESHOLD} THEN 'under_pressure'
    ELSE 'has_capacity'
  END AS status,
  (SELECT today FROM as_of) AS as_of_date
FROM recent r
JOIN {FACILITIES} f ON f.facility_id = r.facility_id
"""

# Beds are not transferable. The useful output is: for a facility that is full,
# which nearby facility can take the patient tonight.
BUILD_BED_REFERRALS = f"""
CREATE OR REPLACE TABLE {BED_REFERRALS}
CLUSTER BY from_facility_id
AS
WITH full_facilities AS (
  SELECT * FROM {BED_STATUS} WHERE status IN ('over_capacity', 'under_pressure')
),
available AS (
  SELECT * FROM {BED_STATUS}
  WHERE status = 'has_capacity' AND free_beds > 0 AND NOT beds_are_day_care
)
SELECT
  f.facility_id        AS from_facility_id,
  f.facility_name      AS from_facility_name,
  f.state, f.district,
  f.bed_capacity       AS from_capacity,
  f.mean_occupied      AS from_occupied,
  f.occupancy_rate     AS from_occupancy_rate,
  f.turned_away        AS from_turned_away,
  f.status             AS from_status,
  a.facility_id        AS to_facility_id,
  a.facility_name      AS to_facility_name,
  a.free_beds          AS to_free_beds,
  a.occupancy_rate     AS to_occupancy_rate,
  ROUND(ST_DISTANCE(ST_GEOGPOINT(f.longitude, f.latitude),
                    ST_GEOGPOINT(a.longitude, a.latitude)) / 1000.0, 1)
                       AS distance_km,
  ROW_NUMBER() OVER (
    PARTITION BY f.facility_id
    ORDER BY ST_DISTANCE(ST_GEOGPOINT(f.longitude, f.latitude),
                         ST_GEOGPOINT(a.longitude, a.latitude))
  ) AS referral_rank
FROM full_facilities f
JOIN available a
  ON a.facility_id != f.facility_id
 AND ST_DISTANCE(ST_GEOGPOINT(f.longitude, f.latitude),
                 ST_GEOGPOINT(a.longitude, a.latitude)) / 1000.0
     <= {REFERRAL_MAX_KM}
QUALIFY referral_rank <= 3
"""

BUILD_STAFF_STATUS = f"""
CREATE OR REPLACE TABLE {STAFF_STATUS}
CLUSTER BY state, district
AS
WITH as_of AS (
  SELECT MAX(DATE(event_ts)) AS today FROM {RESOURCE_EVENTS}
),
recent AS (
  SELECT
    e.facility_id,
    e.item_id,
    ANY_VALUE(e.resource_subtype) AS cadre,
    ANY_VALUE(e.capacity)         AS sanctioned_posts,
    AVG(e.quantity)               AS mean_present,
    COUNTIF(e.quantity = 0)       AS days_none_present,
    COUNT(*)                      AS days_reported
  FROM {RESOURCE_EVENTS} e
  CROSS JOIN as_of a
  WHERE e.resource_type = 'personnel' AND e.event_type = 'attendance'
    AND DATE(e.event_ts) > DATE_SUB(a.today, INTERVAL {WINDOW_DAYS} DAY)
  GROUP BY e.facility_id, e.item_id
)
SELECT
  f.facility_id,
  f.name       AS facility_name,
  f.admin_l1   AS state,
  f.admin_l2   AS district,
  f.latitude,
  f.longitude,
  f.bed_capacity,
  f.nurses_required,
  r.item_id,
  r.cadre,
  CAST(r.sanctioned_posts AS INT64)         AS sanctioned_posts,
  s.expected_in_position,
  s.vacancy_rate,
  ROUND(r.mean_present, 2)                  AS mean_present,
  ROUND(SAFE_DIVIDE(r.mean_present, NULLIF(r.sanctioned_posts, 0)), 3)
                                            AS attendance_vs_sanctioned,
  r.days_none_present,
  r.days_reported,
  -- Nursing carries a second requirement from bed capacity: the Indian
  -- Nursing Council 1:6 ratio, which IPHS cites rather than originates.
  IF(r.item_id = 'STAFF-NURSE',
     GREATEST(f.nurses_required - CAST(ROUND(r.mean_present) AS INT64), 0),
     NULL) AS nurses_short_of_bed_norm,
  CASE
    WHEN r.mean_present < 0.5 THEN 'unstaffed'
    WHEN SAFE_DIVIDE(r.mean_present, NULLIF(r.sanctioned_posts, 0)) < 0.5
      THEN 'critically_short'
    WHEN SAFE_DIVIDE(r.mean_present, NULLIF(r.sanctioned_posts, 0)) < 0.8
      THEN 'short'
    ELSE 'adequate'
  END AS status,
  (SELECT today FROM as_of) AS as_of_date
FROM recent r
JOIN {FACILITIES} f ON f.facility_id = r.facility_id
LEFT JOIN {FACILITY_STAFFING} s
  ON s.facility_id = r.facility_id AND s.cadre = r.cadre
"""

# Personnel do transfer — as people, within travelling distance, from a
# facility with slack. Same shape as the medicine engine: never strand the
# donor.
BUILD_STAFF_REALLOCATION = f"""
CREATE OR REPLACE TABLE {STAFF_REALLOCATION}
CLUSTER BY to_facility_id
AS
WITH short AS (
  SELECT * FROM {STAFF_STATUS}
  WHERE status IN ('unstaffed', 'critically_short')
),
spare AS (
  SELECT * FROM {STAFF_STATUS}
  WHERE status = 'adequate' AND mean_present >= 2
)
SELECT
  d.facility_id     AS to_facility_id,
  d.facility_name   AS to_facility_name,
  d.state, d.district,
  d.item_id, d.cadre,
  d.sanctioned_posts AS to_sanctioned,
  d.mean_present     AS to_present,
  d.status           AS to_status,
  s.facility_id     AS from_facility_id,
  s.facility_name   AS from_facility_name,
  s.mean_present    AS from_present,
  s.sanctioned_posts AS from_sanctioned,
  -- One person at a time, and only if the donor keeps at least one.
  1 AS staff_to_move,
  ROUND(s.mean_present - 1, 2) AS from_present_after,
  ROUND(d.mean_present + 1, 2) AS to_present_after,
  ROUND(ST_DISTANCE(ST_GEOGPOINT(d.longitude, d.latitude),
                    ST_GEOGPOINT(s.longitude, s.latitude)) / 1000.0, 1)
                    AS distance_km,
  ROW_NUMBER() OVER (
    PARTITION BY d.facility_id, d.item_id
    ORDER BY ST_DISTANCE(ST_GEOGPOINT(d.longitude, d.latitude),
                         ST_GEOGPOINT(s.longitude, s.latitude))
  ) AS rn
FROM short d
JOIN spare s
  ON s.item_id = d.item_id
 AND s.facility_id != d.facility_id
 AND ST_DISTANCE(ST_GEOGPOINT(d.longitude, d.latitude),
                 ST_GEOGPOINT(s.longitude, s.latitude)) / 1000.0
     <= {REALLOCATION_MAX_KM}
QUALIFY rn = 1
"""


def run() -> None:
    client = bigquery.Client(project=PROJECT, location=LOCATION)

    print("Building bed_status ...")
    client.query(BUILD_BED_STATUS).result()
    row = next(iter(client.query(f"""
        SELECT COUNT(*) AS facilities,
               COUNTIF(status = 'has_capacity')   AS has_capacity,
               COUNTIF(status = 'under_pressure') AS under_pressure,
               COUNTIF(status = 'over_capacity')  AS over_capacity,
               ROUND(AVG(occupancy_rate) * 100, 1) AS mean_occupancy_pct,
               SUM(turned_away) AS turned_away,
               SUM(bed_capacity) AS beds
        FROM {BED_STATUS}
    """).result()))
    print(f"  facilities:     {row.facilities}")
    print(f"  beds:           {row.beds}")
    print(f"  mean occupancy: {row.mean_occupancy_pct}%")
    print(f"  has capacity:   {row.has_capacity}")
    print(f"  under pressure: {row.under_pressure}")
    print(f"  over capacity:  {row.over_capacity}")
    print(f"  turned away (30d): {row.turned_away}")

    print("\nBuilding bed_referrals (beds do not transfer) ...")
    client.query(BUILD_BED_REFERRALS).result()
    ref = next(iter(client.query(f"""
        SELECT COUNT(*) AS options,
               COUNT(DISTINCT from_facility_id) AS facilities_needing_referral,
               ROUND(AVG(distance_km), 1) AS avg_km
        FROM {BED_REFERRALS}
    """).result()))
    print(f"  facilities needing a referral route: "
          f"{ref.facilities_needing_referral}")
    print(f"  referral options:                   {ref.options}")
    print(f"  mean distance:                      {ref.avg_km} km")

    print("\nBuilding staff_status ...")
    client.query(BUILD_STAFF_STATUS).result()
    for r in client.query(f"""
        SELECT cadre,
               COUNT(*) AS facilities,
               COUNTIF(status = 'unstaffed') AS unstaffed,
               COUNTIF(status = 'critically_short') AS critical,
               COUNTIF(status = 'short') AS short,
               ROUND(AVG(attendance_vs_sanctioned) * 100, 1) AS attendance_pct
        FROM {STAFF_STATUS} GROUP BY cadre ORDER BY cadre
    """).result():
        print(f"  {r.cadre:28s} {r.facilities:>4} facs  "
              f"unstaffed {r.unstaffed:>3}  critical {r.critical:>3}  "
              f"short {r.short:>3}  attendance {r.attendance_pct}%")

    print("\nBuilding staff_reallocation ...")
    client.query(BUILD_STAFF_REALLOCATION).result()
    alloc = next(iter(client.query(f"""
        SELECT COUNT(*) AS moves,
               COUNT(DISTINCT to_facility_id) AS receiving,
               ROUND(AVG(distance_km), 1) AS avg_km
        FROM {STAFF_REALLOCATION}
    """).result()))
    print(f"  reallocations proposed: {alloc.moves}")
    print(f"  facilities helped:      {alloc.receiving}")
    print(f"  mean distance:          {alloc.avg_km} km")

    bad = next(iter(client.query(f"""
        SELECT COUNTIF(from_present_after < 1) AS strands_donor
        FROM {STAFF_REALLOCATION}
    """).result()))
    if bad.strands_donor:
        raise SystemExit(
            f"{bad.strands_donor} reallocations would leave a donor unstaffed")

    if alloc.moves == 0:
        # Empty is a legitimate answer here, but it must be an explained one.
        diag = next(iter(client.query(f"""
            WITH short AS (
              SELECT * FROM {STAFF_STATUS}
              WHERE status IN ('unstaffed', 'critically_short')
            ),
            spare AS (
              SELECT * FROM {STAFF_STATUS}
              WHERE status = 'adequate' AND mean_present >= 2
            )
            SELECT
              (SELECT COUNT(*) FROM short) AS facilities_short,
              (SELECT COUNT(*) FROM spare) AS facilities_with_spare,
              (SELECT COUNT(DISTINCT cadre) FROM spare) AS cadres_with_spare,
              (SELECT ROUND(MIN(ST_DISTANCE(
                  ST_GEOGPOINT(d.longitude, d.latitude),
                  ST_GEOGPOINT(s.longitude, s.latitude)) / 1000), 0)
               FROM short d, spare s
               WHERE d.item_id = s.item_id
                 AND d.facility_id != s.facility_id) AS nearest_pair_km
        """).result()))
        print("\n  No reallocation is possible, and here is why:")
        print(f"    facilities short:            {diag.facilities_short}")
        print(f"    facilities able to donate:   {diag.facilities_with_spare} "
              f"(in {diag.cadres_with_spare} cadre — only nursing has more "
              "than one sanctioned post)")
        print(f"    nearest short/donor pair:    {diag.nearest_pair_km} km, "
              f"against a {REALLOCATION_MAX_KM:.0f} km limit")
        print("    The forecast set spans 116 districts for reach, so no two "
              "facilities are close enough.")
        print("    A doctor vacancy could not be solved this way regardless: "
              "a PHC is sanctioned one doctor.")

    print("\nOK — beds route referrals, personnel reallocate, medicines "
          "transfer. Three resources, one engine shape.")


if __name__ == "__main__":
    try:
        run()
    except Exception as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        sys.exit(1)
