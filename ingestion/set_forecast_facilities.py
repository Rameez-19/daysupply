"""Mark the ~200 PHCs that carry generated usage history and a trained model.

Two flags, two different jobs:

* `is_demo_facility` — 7,092 PHCs across five states. The reach story.
* `is_forecast_facility` — ~200 PHCs. The forecasting story.

The forecast set spans **all five demo states** — Telangana, Maharashtra,
Rajasthan, Delhi and Assam — because `demand_reference` now holds real HMIS
2019-20 indicators for all five (137 districts). Seasonality comes from a real
join against that table, so a facility is only eligible where a real demand
signal exists to join to; 6,989 of the 7,092 demo PHCs qualify.

Selection is deterministic and spread across states and districts: PHCs are
ranked by `FARM_FINGERPRINT` of their id within each district, then the
lowest-ranked are taken round-robin so no single district dominates. Every
district that contributes gets at least one facility, which keeps
same-district transfer pairs available for the redistribution demo.
"""

from __future__ import annotations

import os
import sys

from google.cloud import bigquery

PROJECT = os.getenv("GCP_PROJECT", "daysupply")
DATASET = os.getenv("BQ_DATASET", "daysupply")
LOCATION = os.getenv("BQ_LOCATION", "asia-south1")
FACILITIES = f"`{PROJECT}.{DATASET}.facilities`"
DEMAND_REF = f"`{PROJECT}.{DATASET}.demand_reference`"

FORECAST_STATES = ["Telangana", "Maharashtra", "Rajasthan", "Delhi", "Assam"]
TARGET_COUNT = 200

ADD_COLUMN = f"""
ALTER TABLE {FACILITIES}
ADD COLUMN IF NOT EXISTS is_forecast_facility BOOL
"""

# Spread across states and districts so the demo has neighbouring facilities to
# recommend transfers between, rather than 200 PHCs in one district. Ranking
# within district first, then ordering by that rank, fills one facility per
# district before taking a second from any of them.
SELECT_AND_FLAG = f"""
UPDATE {FACILITIES} AS f
SET is_forecast_facility = (f.facility_id IN (
  SELECT facility_id FROM (
    SELECT
      facility_id,
      ROW_NUMBER() OVER (
        PARTITION BY admin_l1, admin_l2
        ORDER BY FARM_FINGERPRINT(facility_id)
      ) AS rank_in_district
    FROM {FACILITIES}
    WHERE country_code = 'IN'
      AND admin_l1 IN UNNEST(@states)
      AND facility_type = 'phc'
      AND latitude IS NOT NULL
      AND longitude IS NOT NULL
      AND population_served IS NOT NULL
      AND EXISTS (
        SELECT 1 FROM {DEMAND_REF} d
        WHERE d.admin_l1 = {FACILITIES}.admin_l1
          AND d.district_key = UPPER(TRIM({FACILITIES}.admin_l2))
      )
  )
  ORDER BY rank_in_district, facility_id
  LIMIT @n
))
WHERE country_code = 'IN'
"""

VERIFY = f"""
SELECT
  COUNT(*)                                 AS forecast_facilities,
  COUNT(DISTINCT admin_l1)                 AS states,
  COUNT(DISTINCT CONCAT(admin_l1, '|', admin_l2)) AS districts,
  COUNTIF(population_served IS NULL)       AS missing_population,
  COUNTIF(latitude IS NULL)                AS missing_coords,
  MIN(population_served)                   AS min_pop,
  MAX(population_served)                   AS max_pop
FROM {FACILITIES}
WHERE is_forecast_facility
"""

# Every forecast facility must join to real HMIS data. If this returns
# anything, the seasonality for those facilities would not be real.
UNJOINABLE = f"""
SELECT COUNT(*) AS n
FROM {FACILITIES} f
WHERE f.is_forecast_facility
  AND NOT EXISTS (
    SELECT 1 FROM {DEMAND_REF} d
    WHERE d.admin_l1 = f.admin_l1
      AND d.district_key = UPPER(TRIM(f.admin_l2))
  )
"""

PER_STATE = f"""
SELECT admin_l1, COUNT(*) AS n, COUNT(DISTINCT admin_l2) AS districts
FROM {FACILITIES} WHERE is_forecast_facility
GROUP BY admin_l1 ORDER BY admin_l1
"""


def run() -> None:
    client = bigquery.Client(project=PROJECT, location=LOCATION)

    print("Adding is_forecast_facility column ...")
    client.query(ADD_COLUMN).result()

    print(f"Flagging {TARGET_COUNT} PHCs across "
          f"{', '.join(FORECAST_STATES)} ...")
    job = client.query(
        SELECT_AND_FLAG,
        job_config=bigquery.QueryJobConfig(query_parameters=[
            bigquery.ArrayQueryParameter("states", "STRING", FORECAST_STATES),
            bigquery.ScalarQueryParameter("n", "INT64", TARGET_COUNT),
        ]),
    )
    job.result()

    row = next(iter(client.query(VERIFY).result()))
    print(f"  forecast facilities: {row.forecast_facilities}")
    print(f"  states:              {row.states}")
    print(f"  districts:           {row.districts}")
    for per in client.query(PER_STATE).result():
        print(f"    {per.admin_l1:14s} {per.n:>4} PHCs across "
              f"{per.districts} districts")
    print(f"  missing population:  {row.missing_population}")
    print(f"  missing coords:      {row.missing_coords}")
    print(f"  population range:    {row.min_pop:,} - {row.max_pop:,}")

    unjoinable = next(iter(client.query(UNJOINABLE).result())).n
    print(f"  without HMIS data:   {unjoinable}")

    if row.forecast_facilities != TARGET_COUNT:
        raise SystemExit(
            f"Expected {TARGET_COUNT} forecast facilities, "
            f"got {row.forecast_facilities}"
        )
    if unjoinable:
        raise SystemExit(
            f"{unjoinable} forecast facilities have no HMIS district match — "
            "their seasonality could not be real"
        )
    if row.missing_population or row.missing_coords:
        raise SystemExit("Forecast facilities must have population and coords")

    print(f"\nOK — {row.forecast_facilities} PHCs across {row.districts} "
          "districts, all joinable to real HMIS data.")


if __name__ == "__main__":
    try:
        run()
    except Exception as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        sys.exit(1)
