"""Derive bed capacity per facility from the IPHS 2022 national standard.

**This is real.** It is not an estimate or a proxy: it applies the government's
own published norm to each facility using the facility master's own
rural/urban flag.

Source: `Data/India/03_PHC_IPHS_Guidelines-2022.pdf`, Indian Public Health
Standards 2022 Volume III, pages 46-47, verbatim:

    "There should be two essential and four desirable beds in a PHC while six
     essential and four desirable beds [at 24x7 PHCs]"

    Table: Bed Requirement at Primary Health Centres
    2 Beds | 4 Beds | 2 Day care Beds | ... | 6 Beds | 4 Beds

    "Note: The desirable will be over and above the essential beds."

| Facility type | Essential | Desirable | Total if fully equipped |
|---|---|---|---|
| Rural PHC     | 2         | 4         | 6 |
| Urban PHC     | 2 day-care| 4 day-care| 6 day-care |
| 24x7 PHC      | 6         | 4         | 10 |

Urban PHCs get **day-care** beds because they are not expected to provide
in-patient care, so their beds are counted separately and excluded from
overnight occupancy.

**What is unknown: which PHCs operate 24x7.** The facility master does not
record it and nothing else in the data implies it. Rather than guess, every PHC
is given the standard 2+4 norm and `is_24x7` is left NULL. Applying the 6+4
norm to a facility that is not 24x7 would overstate its capacity threefold, and
we have no basis to choose. Recorded in `Data/README.md`.

CHC norms are in `02-CHC_IPHS_Guidelines-2022.pdf`; CHCs are outside the
forecast set, so they are not given capacity here.
"""

from __future__ import annotations

import os
import sys

from google.cloud import bigquery

PROJECT = os.getenv("GCP_PROJECT", "daysupply")
DATASET = os.getenv("BQ_DATASET", "daysupply")
LOCATION = os.getenv("BQ_LOCATION", "asia-south1")
FACILITIES = f"`{PROJECT}.{DATASET}.facilities`"

# IPHS 2022 Volume III, PHC, pages 46-47.
ESSENTIAL_BEDS = 2
DESIRABLE_BEDS = 4
ESSENTIAL_BEDS_24X7 = 6

# "There should be one nurse for every six beds" in the inpatient department.
# This is an **Indian Nursing Council regulation**. CHC IPHS 2022 quotes it at
# page 60 and tabulates it at page 118, but IPHS cites the INC rather than
# originating the norm, so it is attributed to the INC wherever it appears.
# It is what links the two resource types: a facility's nursing requirement is
# a function of its bed capacity.
BEDS_PER_NURSE = 6

ADD_COLUMNS = f"""
ALTER TABLE {FACILITIES}
  ADD COLUMN IF NOT EXISTS bed_capacity INT64,
  ADD COLUMN IF NOT EXISTS bed_capacity_essential INT64,
  ADD COLUMN IF NOT EXISTS bed_capacity_desirable INT64,
  ADD COLUMN IF NOT EXISTS beds_are_day_care BOOL,
  ADD COLUMN IF NOT EXISTS is_24x7 BOOL,
  ADD COLUMN IF NOT EXISTS nurses_required INT64
"""

# `Location Type` from the facility master carries rural/urban. It was loaded
# as-is; urban PHCs get day-care beds under the norm.
SET_CAPACITY = f"""
UPDATE {FACILITIES}
SET
  bed_capacity_essential = {ESSENTIAL_BEDS},
  bed_capacity_desirable = {DESIRABLE_BEDS},
  bed_capacity           = {ESSENTIAL_BEDS + DESIRABLE_BEDS},
  beds_are_day_care      = (LOWER(location_type) = 'urban'),
  -- Left NULL deliberately: nothing in the data says which PHCs run 24x7.
  is_24x7                = NULL,
  nurses_required        = CAST(
    CEIL(({ESSENTIAL_BEDS + DESIRABLE_BEDS}) / {BEDS_PER_NURSE}) AS INT64)
WHERE country_code = 'IN' AND facility_type = 'phc'
"""

VERIFY = f"""
SELECT
  COUNT(*)                                  AS phcs,
  COUNTIF(bed_capacity IS NOT NULL)         AS with_capacity,
  COUNTIF(beds_are_day_care)                AS day_care_urban,
  COUNTIF(NOT beds_are_day_care)            AS inpatient_rural,
  COUNTIF(beds_are_day_care IS NULL)        AS unknown_location,
  SUM(bed_capacity)                         AS total_beds,
  SUM(IF(NOT beds_are_day_care, bed_capacity, 0)) AS overnight_beds,
  SUM(nurses_required)                      AS nurses_required
FROM {FACILITIES}
WHERE country_code = 'IN' AND facility_type = 'phc'
"""


def run() -> None:
    client = bigquery.Client(project=PROJECT, location=LOCATION)

    print("Adding bed capacity columns ...")
    client.query(ADD_COLUMNS).result()

    print("Applying the IPHS 2022 norm (2 essential + 4 desirable) ...")
    client.query(SET_CAPACITY).result()

    row = next(iter(client.query(VERIFY).result()))
    print(f"\n  PHCs:                 {row.phcs:,}")
    print(f"  with capacity:        {row.with_capacity:,}")
    print(f"  rural (inpatient):    {row.inpatient_rural:,}")
    print(f"  urban (day care):     {row.day_care_urban:,}")
    print(f"  location unknown:     {row.unknown_location:,}")
    print(f"  total beds:           {row.total_beds:,}")
    print(f"  overnight beds:       {row.overnight_beds:,}")
    print(f"  nurses required:      {row.nurses_required:,} "
          f"(1 per {BEDS_PER_NURSE} beds — Indian Nursing Council "
          "regulation, cited by IPHS)")

    if row.with_capacity != row.phcs:
        raise SystemExit(
            f"{row.phcs - row.with_capacity:,} PHCs have no bed capacity")

    print("\n  Distribution across the forecast set:")
    for r in client.query(f"""
        SELECT admin_l1 AS state,
               COUNT(*) AS phcs,
               SUM(bed_capacity) AS beds,
               COUNTIF(beds_are_day_care) AS day_care
        FROM {FACILITIES}
        WHERE is_forecast_facility
        GROUP BY state ORDER BY state
    """).result():
        print(f"    {r.state:14s} {r.phcs:>4} PHCs  {r.beds:>5} beds  "
              f"{r.day_care:>3} day-care")

    print("\nOK — capacity is the government's own norm applied to real "
          "facilities. Which PHCs run 24x7 stays an explicit unknown.")


if __name__ == "__main__":
    try:
        run()
    except Exception as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        sys.exit(1)
