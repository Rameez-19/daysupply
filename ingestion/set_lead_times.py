"""Derive replenishment lead time per facility from distance to district HQ.

**This is a documented proxy, not a measurement.** India does not publish
facility-level replenishment lead times anywhere. What the facility master does
give us is real coordinates for every facility, including the district and
state hospitals that sit at the district headquarters where the drug warehouse
is. Distance from a PHC to its district HQ is therefore real; the conversion
from distance to days is an assumption, and is labelled as one everywhere it
surfaces. See `Data/README.md` §11.

**District HQ proxy.** The warehouse is taken to be the district hospital.
Where a district has none, the fallback chain is state hospital, then community
health centre. Among candidates of the best available type, the one closest to
the district's facility centroid is chosen — the most central facility is the
most likely to sit in the district town.

**Distance to days.**

    lead_time_days = clamp(7 + 0.08 x distance_km, 7, 30)

Seven days is order processing and picking, which every facility pays whatever
its distance. The 0.08 slope puts a PHC 20 km out at 9 days and one 200 km out
at 23 days, which is the spread this system exists to act on: the remote
facility must reorder two weeks earlier for the same stock position.

**Implausible distances.** Some coordinates are wrong in ways a bounding-box
check cannot catch — inside India, but hundreds of kilometres from their own
district. Across the forecast set the distance distribution is orderly to the
95th percentile (97 km) and then jumps to 2,230 km, which is further than
Rajasthan is wide. Districts are not that large. Any distance over
`MAX_PLAUSIBLE_KM` is treated as a bad coordinate rather than a remote facility:
the district's median PHC distance is substituted and the row is marked
`lead_time_is_estimated`, so nothing downstream mistakes it for a measurement.

**Coordinate validity.** The facility master contains real errors: 224 rows
have a latitude outside +/-90, 248 a longitude outside +/-180, and 287 more sit
inside the valid globe but outside India — several with latitude and longitude
transposed. They are flagged `has_valid_coords = FALSE` and excluded from all
distance maths. They are **not** corrected: inferring that a Mizoram row reading
92.41, 23.25 was meant to be 23.25, 92.41 is a guess, and this file does not put
guesses into a government dataset. No forecast facility is affected.

`indent_cycle_days` is a flat 30 — the standard monthly PHC indent — and is not
derived from anything. It is stored so the reorder logic reads from data rather
than a constant.
"""

from __future__ import annotations

import os
import sys

from google.cloud import bigquery

PROJECT = os.getenv("GCP_PROJECT", "daysupply")
DATASET = os.getenv("BQ_DATASET", "daysupply")
LOCATION = os.getenv("BQ_LOCATION", "asia-south1")
FACILITIES = f"`{PROJECT}.{DATASET}.facilities`"

BASE_LEAD_DAYS = 7
DAYS_PER_KM = 0.08
MIN_LEAD_DAYS = 7
MAX_LEAD_DAYS = 30
INDENT_CYCLE_DAYS = 30

# Beyond this, the coordinate is wrong rather than the facility remote.
MAX_PLAUSIBLE_KM = 200

# Warehouse proxy, best first.
HQ_TYPE_PRIORITY = "['dis_h', 's_t_h', 'chc']"

# India's bounding box. Anything outside it is bad data, not a facility.
VALID_COORDS = ("latitude BETWEEN 6 AND 38 AND longitude BETWEEN 68 AND 98")

ADD_COLUMNS = f"""
ALTER TABLE {FACILITIES}
  ADD COLUMN IF NOT EXISTS has_valid_coords BOOL,
  ADD COLUMN IF NOT EXISTS lead_time_days INT64,
  ADD COLUMN IF NOT EXISTS indent_cycle_days INT64,
  ADD COLUMN IF NOT EXISTS district_hq_id STRING,
  ADD COLUMN IF NOT EXISTS distance_to_hq_km FLOAT64,
  ADD COLUMN IF NOT EXISTS lead_time_is_estimated BOOL
"""

FLAG_COORDS = f"""
UPDATE {FACILITIES}
SET has_valid_coords = (
  latitude IS NOT NULL AND longitude IS NOT NULL AND {VALID_COORDS})
WHERE country_code = 'IN'
"""

COMPUTE = f"""
CREATE OR REPLACE TEMP TABLE hq AS
WITH centroid AS (
  SELECT admin_l1, admin_l2,
         AVG(latitude) AS lat, AVG(longitude) AS lon
  FROM {FACILITIES}
  WHERE country_code = 'IN' AND has_valid_coords
  GROUP BY admin_l1, admin_l2
),
candidates AS (
  SELECT
    f.admin_l1, f.admin_l2, f.facility_id, f.name, f.facility_type,
    f.latitude, f.longitude,
    -- Rank by type preference, then by closeness to the district centroid.
    CASE f.facility_type WHEN 'dis_h' THEN 1 WHEN 's_t_h' THEN 2
         WHEN 'chc' THEN 3 ELSE 9 END AS type_rank,
    ST_DISTANCE(
      ST_GEOGPOINT(f.longitude, f.latitude),
      ST_GEOGPOINT(c.lon, c.lat)
    ) AS metres_from_centroid
  FROM {FACILITIES} f
  JOIN centroid c
    ON c.admin_l1 = f.admin_l1 AND c.admin_l2 = f.admin_l2
  WHERE f.country_code = 'IN'
    AND f.facility_type IN UNNEST({HQ_TYPE_PRIORITY})
    AND f.has_valid_coords
)
SELECT admin_l1, admin_l2, facility_id AS hq_id, name AS hq_name,
       facility_type AS hq_type, latitude AS hq_lat, longitude AS hq_lon
FROM (
  SELECT *, ROW_NUMBER() OVER (
    PARTITION BY admin_l1, admin_l2
    ORDER BY type_rank, metres_from_centroid, facility_id
  ) AS rn
  FROM candidates
)
WHERE rn = 1;

CREATE OR REPLACE TEMP TABLE raw_distance AS
SELECT
  f.facility_id,
  f.admin_l1,
  f.admin_l2,
  h.hq_id,
  ROUND(ST_DISTANCE(ST_GEOGPOINT(f.longitude, f.latitude),
                    ST_GEOGPOINT(h.hq_lon, h.hq_lat)) / 1000.0, 1) AS km
FROM {FACILITIES} f
JOIN hq h
  ON f.admin_l1 = h.admin_l1 AND f.admin_l2 = h.admin_l2
WHERE f.country_code = 'IN' AND f.has_valid_coords;

-- Median distance among the plausible rows, per district, as the fallback for
-- rows whose coordinates put them impossibly far from their own HQ.
CREATE OR REPLACE TEMP TABLE district_median AS
SELECT admin_l1, admin_l2,
       APPROX_QUANTILES(km, 2)[OFFSET(1)] AS median_km
FROM raw_distance
WHERE km <= {MAX_PLAUSIBLE_KM}
GROUP BY admin_l1, admin_l2;

CREATE OR REPLACE TEMP TABLE resolved AS
SELECT
  r.facility_id,
  r.hq_id,
  r.km > {MAX_PLAUSIBLE_KM} AS estimated,
  IF(r.km > {MAX_PLAUSIBLE_KM}, IFNULL(m.median_km, 25.0), r.km) AS km
FROM raw_distance r
LEFT JOIN district_median m
  ON m.admin_l1 = r.admin_l1 AND m.admin_l2 = r.admin_l2;

UPDATE {FACILITIES} f
SET
  district_hq_id = s.hq_id,
  distance_to_hq_km = s.km,
  lead_time_is_estimated = s.estimated,
  lead_time_days = LEAST({MAX_LEAD_DAYS}, GREATEST({MIN_LEAD_DAYS},
    CAST(ROUND({BASE_LEAD_DAYS} + {DAYS_PER_KM} * s.km) AS INT64))),
  indent_cycle_days = {INDENT_CYCLE_DAYS}
FROM resolved s
WHERE f.facility_id = s.facility_id;
"""

VERIFY = f"""
SELECT
  COUNT(*)                              AS forecast_facilities,
  COUNTIF(lead_time_days IS NULL)       AS missing_lead_time,
  MIN(lead_time_days)                   AS min_lead,
  MAX(lead_time_days)                   AS max_lead,
  ROUND(AVG(lead_time_days), 1)         AS avg_lead,
  ROUND(MIN(distance_to_hq_km), 1)      AS min_km,
  ROUND(MAX(distance_to_hq_km), 1)      AS max_km,
  COUNTIF(lead_time_is_estimated)       AS estimated
FROM {FACILITIES}
WHERE is_forecast_facility
"""

CONTRAST = f"""
SELECT name, admin_l1, admin_l2, distance_to_hq_km, lead_time_days
FROM {FACILITIES}
WHERE is_forecast_facility AND distance_to_hq_km IS NOT NULL
ORDER BY distance_to_hq_km
LIMIT 3
"""

CONTRAST_FAR = CONTRAST.replace("ORDER BY distance_to_hq_km\n",
                                "ORDER BY distance_to_hq_km DESC\n")


def run() -> None:
    client = bigquery.Client(project=PROJECT, location=LOCATION)

    print("Adding lead-time columns ...")
    client.query(ADD_COLUMNS).result()

    print("Flagging coordinate validity ...")
    flag = client.query(FLAG_COORDS)
    flag.result()
    bad = next(iter(client.query(f"""
        SELECT COUNTIF(NOT has_valid_coords) AS n,
               COUNTIF(NOT has_valid_coords AND is_demo_facility) AS demo
        FROM {FACILITIES} WHERE country_code = 'IN'
    """).result()))
    print(f"  {bad.n:,} facilities have unusable coordinates "
          f"({bad.demo} of them demo facilities) — excluded from distance maths")

    print("Computing district HQ and lead times ...")
    client.query(COMPUTE).result()

    row = next(iter(client.query(VERIFY).result()))
    print(f"\n  forecast facilities: {row.forecast_facilities}")
    print(f"  missing lead time:   {row.missing_lead_time}")
    print(f"  distance to HQ:      {row.min_km} - {row.max_km} km")
    print(f"  lead time:           {row.min_lead} - {row.max_lead} days "
          f"(mean {row.avg_lead})")
    print(f"  distance estimated:  {row.estimated} "
          "(coordinate implausible, district median used)")

    if row.missing_lead_time:
        raise SystemExit(
            f"{row.missing_lead_time} forecast facilities have no lead time")
    if row.min_lead == row.max_lead:
        raise SystemExit(
            "Lead time is constant across facilities — the whole point is that "
            "a remote PHC reorders earlier than a nearby one")

    print("\n  Closest to district HQ:")
    for r in client.query(CONTRAST).result():
        print(f"    {r.name[:22]:24s} {r.admin_l2[:14]:16s} "
              f"{r.distance_to_hq_km:>6} km -> {r.lead_time_days} days")
    print("  Furthest from district HQ:")
    for r in client.query(CONTRAST_FAR).result():
        print(f"    {r.name[:22]:24s} {r.admin_l2[:14]:16s} "
              f"{r.distance_to_hq_km:>6} km -> {r.lead_time_days} days")

    print("\nOK — lead times derived. This is a distance proxy, not measured.")


if __name__ == "__main__":
    try:
        run()
    except Exception as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        sys.exit(1)
