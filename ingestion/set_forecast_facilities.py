"""Mark the ~200 PHCs that carry generated usage history and a trained model.

Two flags, two different jobs:

* `is_demo_facility` — 7,092 PHCs across five states. The reach story.
* `is_forecast_facility` — ~200 PHCs. The forecasting story.

The forecast set is drawn **only from Telangana**, and that is a data
constraint, not a preference. `demand_reference` holds HMIS 2019-20 monthly
indicators for 31 Telangana districts and nowhere else, because only
`Telangana.xls` has been parsed. Seasonality for the usage generator comes from
a real join against that table, so a facility outside Telangana has no real
demand signal to join to. Rather than fall back to a synthetic seasonal curve
for those facilities, the forecast set is restricted to where the real signal
exists.

All 817 Telangana PHCs join to `demand_reference` on a case-insensitive
district match, so the sample is drawn from a fully covered population.
Selection is deterministic: the N PHCs with the lowest `FARM_FINGERPRINT` of
their id, evenly spread across districts.
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

FORECAST_STATE = "Telangana"
TARGET_COUNT = 200

ADD_COLUMN = f"""
ALTER TABLE {FACILITIES}
ADD COLUMN IF NOT EXISTS is_forecast_facility BOOL
"""

# Evenly spread across districts so the demo has neighbouring facilities to
# recommend transfers between, rather than 200 PHCs in one district.
SELECT_AND_FLAG = f"""
UPDATE {FACILITIES} AS f
SET is_forecast_facility = (f.facility_id IN (
  SELECT facility_id FROM (
    SELECT
      facility_id,
      ROW_NUMBER() OVER (
        PARTITION BY admin_l2
        ORDER BY FARM_FINGERPRINT(facility_id)
      ) AS rank_in_district
    FROM {FACILITIES}
    WHERE country_code = 'IN'
      AND admin_l1 = @state
      AND facility_type = 'phc'
      AND latitude IS NOT NULL
      AND longitude IS NOT NULL
      AND population_served IS NOT NULL
      AND UPPER(TRIM(admin_l2)) IN (
        SELECT DISTINCT UPPER(TRIM(admin_l2)) FROM {DEMAND_REF}
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
  COUNT(DISTINCT admin_l2)                 AS districts,
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
  AND UPPER(TRIM(f.admin_l2)) NOT IN (
    SELECT DISTINCT UPPER(TRIM(admin_l2)) FROM {DEMAND_REF}
  )
"""


def run() -> None:
    client = bigquery.Client(project=PROJECT, location=LOCATION)

    print("Adding is_forecast_facility column ...")
    client.query(ADD_COLUMN).result()

    print(f"Flagging {TARGET_COUNT} {FORECAST_STATE} PHCs ...")
    job = client.query(
        SELECT_AND_FLAG,
        job_config=bigquery.QueryJobConfig(query_parameters=[
            bigquery.ScalarQueryParameter("state", "STRING", FORECAST_STATE),
            bigquery.ScalarQueryParameter("n", "INT64", TARGET_COUNT),
        ]),
    )
    job.result()

    row = next(iter(client.query(VERIFY).result()))
    print(f"  forecast facilities: {row.forecast_facilities}")
    print(f"  districts:           {row.districts}")
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
