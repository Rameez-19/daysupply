"""Bed pressure and staffing status, and what each one implies.

Beds and personnel deliberately produce *different* outputs from medicines,
because the resources behave differently:

* **Medicines transfer.** A deficit at one facility is met by a surplus at
  another, which is what `build_supply_plan.py` already does.
* **Beds do not transfer.** You cannot move a bed to a patient in useful time.
  Bed pressure is a *referral* signal: which facility nearby has capacity
  tonight. So this builds `bed_referrals`, not bed transfers.
* **Personnel are reported as they are, not moved.** `staff_status` is the
  sanctioned establishment and its vacancy from Rural Health Statistics
  2021-22, one row per forecast PHC and cadre.

  It used to be built *from* generated attendance events, with real vacancy
  only LEFT JOINed on — so the one real figure depended on a simulated one
  being present, and every column readers saw beside it (`mean_present`,
  `days_none_present`, `status`) came from a fixed-seed random propensity.
  It is now driven by `facility_staffing`, and none of those columns exist.

  The staff reallocation engine went with them. It proposed moves by
  differencing two generated attendance figures. The real answer to "can we
  move staff?" is structural and lives in `app/resources.py`: most cadres are
  sanctioned one post per centre, so nobody can be lent without leaving a
  centre empty.

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

# The date the RHS 2021-22 manpower position was taken. `staff_status` used to
# stamp MAX(event_ts) from the generated ledger, which dated a 2022 survey to
# last week.
STAFF_AS_OF = "2022-03-31"

# Nothing generated may reach the table readers see; `run()` refuses to finish
# if any of these columns reappear.
GENERATED_COLUMNS = {"mean_present", "attendance_vs_sanctioned",
                     "days_none_present", "days_reported", "status"}

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
-- Anchored to the bed ledger's own last day. It took MAX over every
-- resource_event, so medicine captures on 2-3 September slid the bed window
-- five days past the end of the bed data: 392 turned away became 339 on a
-- rebuild, and nothing about beds had changed. One vertical's activity must
-- not move another's window.
WITH as_of AS (
  SELECT MAX(DATE(event_ts)) AS today FROM {RESOURCE_EVENTS}
  WHERE resource_type = 'bed'
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
SELECT
  s.facility_id,
  f.name       AS facility_name,
  f.admin_l1   AS state,
  f.admin_l2   AS district,
  f.latitude,
  f.longitude,
  f.bed_capacity,
  f.nurses_required,
  -- Health assistants have no single item. Capture keeps male and female
  -- apart; the 2021-22 establishment publishes them combined. NULL rather
  -- than pinning the combined cadre to one of the two.
  CASE s.cadre
    WHEN 'Doctor (allopathic)' THEN 'STAFF-DOCTOR'
    WHEN 'Nursing staff'       THEN 'STAFF-NURSE'
    WHEN 'Pharmacist'          THEN 'STAFF-PHARMACIST'
  END AS item_id,
  s.cadre,
  s.sanctioned_posts,
  s.expected_in_position,
  s.vacancy_rate,
  -- INC 1:6 against nurses in position. This was computed against generated
  -- `mean_present`. In-position is the RHS state rate applied to this
  -- centre's sanctioned posts: an estimate, but not a random one.
  IF(s.cadre = 'Nursing staff',
     GREATEST(f.nurses_required - s.expected_in_position, 0),
     NULL) AS nurses_short_of_bed_norm,
  DATE '{STAFF_AS_OF}' AS as_of_date
FROM {FACILITY_STAFFING} s
JOIN {FACILITIES} f ON f.facility_id = s.facility_id
-- The same 200 centres the medicine vertical forecasts, so every page counts
-- one population.
WHERE f.is_forecast_facility
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

    print("\nBuilding staff_status (establishment, RHS 2021-22) ...")
    client.query(BUILD_STAFF_STATUS).result()
    for r in client.query(f"""
        SELECT cadre,
               COUNT(*) AS facilities,
               SUM(sanctioned_posts) AS posts,
               ROUND(100 * SAFE_DIVIDE(
                 SUM(vacancy_rate * sanctioned_posts),
                 SUM(IF(vacancy_rate IS NULL, 0, sanctioned_posts))), 1)
                 AS vacancy_pct,
               COUNTIF(vacancy_rate IS NULL) AS no_figure
        FROM {STAFF_STATUS} GROUP BY cadre ORDER BY cadre
    """).result():
        print(f"  {r.cadre:28s} {r.facilities:>4} facs  posts {r.posts:>5}  "
              f"vacancy {r.vacancy_pct}%  ({r.no_figure} with no RHS figure)")

    cols = {c.name for c in client.get_table(STAFF_STATUS.strip("`")).schema}
    leaked = cols & GENERATED_COLUMNS
    if leaked:
        raise SystemExit(
            f"staff_status carries generated columns: {sorted(leaked)}")

    # Dropped, not left stale: every row in it was a move between two
    # generated attendance figures.
    client.query(f"DROP TABLE IF EXISTS {STAFF_REALLOCATION}").result()
    print("  staff_reallocation dropped (it differenced generated attendance)")

    print("\nOK — beds route referrals, medicines transfer, and staffing "
          "reports its real establishment rather than a simulated roster.")


if __name__ == "__main__":
    try:
        run()
    except Exception as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        sys.exit(1)
