"""Pre-aggregate dashboard geography into a small summary table.

The dropdowns need state and district lists with facility counts. Computing
those by aggregating 200,438 rows costs 1.7-6.5s on a cold BigQuery slot, and
with Cloud Run at `--min-instances 0` every first visitor pays it. A judge
opening the live URL is always a first visitor.

This builds `daysupply.geo_summary` — one row per state and one per district,
roughly 700 rows — so the dropdown queries read a table small enough to return
in well under a second. `facilities` remains the source of truth; this is a
derived cache and is rebuilt whenever the facility master is reloaded.
"""

from __future__ import annotations

import os
import sys
import time

from google.cloud import bigquery

PROJECT = os.getenv("GCP_PROJECT", "daysupply")
DATASET = os.getenv("BQ_DATASET", "daysupply")
LOCATION = os.getenv("BQ_LOCATION", "asia-south1")

FACILITIES = f"`{PROJECT}.{DATASET}.facilities`"
GEO_SUMMARY = f"`{PROJECT}.{DATASET}.geo_summary`"

BUILD_SQL = f"""
CREATE OR REPLACE TABLE {GEO_SUMMARY}
CLUSTER BY level, state
AS
SELECT
  'state'                        AS level,
  admin_l1                       AS state,
  CAST(NULL AS STRING)           AS district,
  COUNT(*)                       AS facility_count,
  COUNTIF(facility_type = 'phc') AS phc_count,
  COUNT(DISTINCT admin_l2)       AS district_count,
  COUNTIF(is_demo_facility)      AS demo_count,
  SUM(population_served)         AS population_served
FROM {FACILITIES}
WHERE country_code = 'IN' AND admin_l1 != ''
GROUP BY state

UNION ALL

SELECT
  'district'                     AS level,
  admin_l1                       AS state,
  admin_l2                       AS district,
  COUNT(*)                       AS facility_count,
  COUNTIF(facility_type = 'phc') AS phc_count,
  0                              AS district_count,
  COUNTIF(is_demo_facility)      AS demo_count,
  SUM(population_served)         AS population_served
FROM {FACILITIES}
WHERE country_code = 'IN' AND admin_l1 != '' AND admin_l2 != ''
GROUP BY state, district
"""


def build() -> None:
    client = bigquery.Client(project=PROJECT, location=LOCATION)

    print("Building geo_summary ...")
    started = time.perf_counter()
    job = client.query(BUILD_SQL)
    job.result()
    print(f"  built in {time.perf_counter() - started:.1f}s, "
          f"{job.total_bytes_processed / 1024 ** 2:.1f} MB scanned")

    checks = client.query(f"""
        SELECT
          COUNTIF(level = 'state')                    AS states,
          COUNTIF(level = 'district')                 AS district_rows,
          COUNT(DISTINCT IF(level = 'district', district, NULL)) AS district_names,
          SUM(IF(level = 'state', facility_count, 0)) AS facilities
        FROM {GEO_SUMMARY}
    """)
    row = next(iter(checks.result()))
    print(f"  states:            {row.states}")
    print(f"  district rows:     {row.district_rows}  (state x district pairs)")
    print(f"  distinct district names: {row.district_names}")
    print(f"  facilities:        {row.facilities:,}")

    # 668 district names, but 701 (state, district) pairs — 33 district names
    # occur in more than one state, and the dropdown is always state-scoped.
    if row.states != 37 or row.district_names != 668:
        raise SystemExit(
            f"FAILED: expected 37 states and 668 district names, "
            f"got {row.states} and {row.district_names}"
        )
    if row.facilities != 200_438:
        raise SystemExit(
            f"FAILED: facility total is {row.facilities:,}, expected 200,438"
        )

    # Confirm the read path is actually fast now.
    started = time.perf_counter()
    warm = client.query(
        f"SELECT state, facility_count FROM {GEO_SUMMARY} WHERE level = 'state'"
    )
    list(warm.result())
    print(f"\nOK — dropdown read: {time.perf_counter() - started:.2f}s, "
          f"{warm.total_bytes_processed / 1024:.1f} KB scanned")


if __name__ == "__main__":
    try:
        build()
    except Exception as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        sys.exit(1)
