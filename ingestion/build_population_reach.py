"""How many people this reaches — counted once, and stated at three scopes.

Impact has to be a number, and the number has to survive being checked. This
module derives it from data already loaded and is explicit about the one way it
could easily have been inflated by a factor of three.

## The trap: catchments are nested, not additive

`population_served` comes from Rural Health Statistics 2017, which publishes,
per State/UT, the *average rural population covered by* a sub-centre, a PHC and
a CHC. Those three catchments **cover the same people**. A villager is served by
a sub-centre, which reports to a PHC, which refers to a CHC. Summing
`population_served` across all 200,438 facilities would count most of rural
India three times and produce something like 2.4 billion.

**So only PHCs are counted.** PHC catchments tile the rural population once,
which is exactly the level this system operates at. Sub-centres (163,131 of
them) and CHCs are excluded from the reach figure entirely — not because they
do not matter, but because counting them would be counting the same people
again.

**The tiling check.** Summing the PHC catchment across all 24,759 rural PHCs in
the directory gives 793.7 million against a Census 2011 rural population of
833.7 million — **95.2%**. That is what a correct, once-only tiling should look
like: close to the whole rural population, slightly under because state averages
times state counts do not perfectly reproduce a national total. Had the figure
come out at two or three times the rural population, the method would have been
wrong. This check is the reason to believe the number.

## What is counted and what is assumed

**Counted, from published sources:**

* Which facilities exist, where, and of what type — the national facility
  directory, 200,438 rows, 29,733 of them PHCs.
* The average rural population covered by a PHC in each State/UT — Rural Health
  Statistics 2017, on a Census 2011 population base.
* Which districts have real demand data — the five HMIS 2019-20 state files.

**Assumed, and the assumption is the same one the source makes:**

* That each PHC in a state serves that state's average. **There is no published
  per-facility catchment anywhere in India**, so a state x facility-type average
  is the finest granularity that exists. Real catchments vary widely within a
  state; the total is sound, any individual facility's figure is an average.

**Deliberately excluded:**

* **Urban PHCs.** The RHS figure is an average *rural* population. Applying it
  to the 4,974 urban PHCs would be a category error, so urban PHCs contribute
  zero to the reach figure. This makes the number smaller, and it is the correct
  treatment. 32 of the 200 operating facilities are urban and are not counted.
* **Sub-centres, CHCs, district and state hospitals** — nested catchments, as
  above.

**Direction of error.** The population base is Census 2011, now fifteen years
old, and India's rural population has grown since. The figure therefore
**understates** current reach. Nothing here is rounded up, and no growth factor
has been applied.
"""

from __future__ import annotations

import os
import sys

from google.cloud import bigquery

PROJECT = os.getenv("GCP_PROJECT", "daysupply")
DATASET = os.getenv("BQ_DATASET", "daysupply")
LOCATION = os.getenv("BQ_LOCATION", "asia-south1")

FACILITIES = f"`{PROJECT}.{DATASET}.facilities`"
DEMAND_REFERENCE = f"`{PROJECT}.{DATASET}.demand_reference`"
POPULATION_REACH = f"`{PROJECT}.{DATASET}.population_reach`"

# Census of India 2011, rural population. The base the RHS averages are built on.
CENSUS_2011_RURAL = 833_748_852
# A correct once-only tiling should land near, and below, the census total.
TILING_MIN = 0.80
TILING_MAX = 1.05

BUILD = f"""
CREATE OR REPLACE TABLE {POPULATION_REACH} AS
WITH rural_phc AS (
  -- The only facility type counted, and only its rural members. See module
  -- docstring: nested catchments would otherwise triple-count.
  SELECT facility_id, admin_l1, admin_l2, population_served,
         is_forecast_facility
  FROM {FACILITIES}
  WHERE country_code = 'IN'
    AND facility_type = 'phc'
    AND location_type = 'rural'
    AND population_served IS NOT NULL
),
hmis_districts AS (
  SELECT DISTINCT admin_l1, district_key FROM {DEMAND_REFERENCE}
),
tiers AS (
  SELECT
    1 AS tier_order,
    'operating' AS tier,
    'PHCs with live forecasts, stock positions and transfer recommendations'
      AS description,
    COUNT(*) AS phcs,
    COUNT(DISTINCT admin_l1) AS states,
    COUNT(DISTINCT CONCAT(admin_l1, '|', admin_l2)) AS districts,
    SUM(population_served) AS population
  FROM rural_phc WHERE is_forecast_facility

  UNION ALL

  SELECT
    2, 'demand_data_footprint',
    'PHCs in districts where real HMIS demand data is loaded and seasonality '
      'is measured',
    COUNT(*), COUNT(DISTINCT r.admin_l1),
    COUNT(DISTINCT CONCAT(r.admin_l1, '|', r.admin_l2)),
    SUM(r.population_served)
  FROM rural_phc r
  JOIN hmis_districts h
    ON h.admin_l1 = r.admin_l1
   AND h.district_key = UPPER(TRIM(r.admin_l2))

  UNION ALL

  SELECT
    3, 'national_directory',
    'Every rural PHC in the national facility directory — the addressable '
      'network, already loaded',
    COUNT(*), COUNT(DISTINCT admin_l1),
    COUNT(DISTINCT CONCAT(admin_l1, '|', admin_l2)),
    SUM(population_served)
  FROM rural_phc
)
SELECT
  tier_order, tier, description, phcs, states, districts, population,
  CAST(ROUND(SAFE_DIVIDE(population, NULLIF(phcs, 0))) AS INT64)
    AS mean_catchment,
  ROUND(100 * SAFE_DIVIDE(population, {CENSUS_2011_RURAL}), 2)
    AS pct_of_census_2011_rural,
  {CENSUS_2011_RURAL} AS census_2011_rural_india,
  CURRENT_TIMESTAMP() AS generated_at
FROM tiers
ORDER BY tier_order
"""


def run() -> None:
    client = bigquery.Client(project=PROJECT, location=LOCATION)

    print("Building population_reach (rural PHC catchments, counted once) ...")
    client.query(BUILD).result()

    rows = list(client.query(f"SELECT * FROM {POPULATION_REACH} "
                             "ORDER BY tier_order").result())
    for r in rows:
        print(f"\n  {r.tier}")
        print(f"    {r.description}")
        print(f"    {r.phcs:,} rural PHCs · {r.districts} districts · "
              f"{r.states} states")
        print(f"    population reached: {r.population:,} "
              f"({r.population / 1e6:,.1f} million)")
        print(f"    mean catchment: {r.mean_catchment:,} per PHC")

    national = rows[-1]
    share = national.population / CENSUS_2011_RURAL
    print(f"\n  Tiling check — the reason to believe the method:")
    print(f"    national rural PHC catchment:  {national.population:,}")
    print(f"    Census 2011 rural India:       {CENSUS_2011_RURAL:,}")
    print(f"    ratio:                         {share:.3f}")

    if not TILING_MIN <= share <= TILING_MAX:
        raise SystemExit(
            f"PHC catchments sum to {share:.2f}x the rural population. A "
            f"correct once-only tiling lands in [{TILING_MIN}, {TILING_MAX}]. "
            "Above it, catchments are being double-counted; well below it, "
            "facilities are missing population.")

    print(f"    -> within [{TILING_MIN}, {TILING_MAX}]: each person is counted "
          "once, and the total is slightly conservative.")

    # What summing every facility type would have produced, stated explicitly
    # so the discarded figure is on the record rather than merely avoided.
    naive = next(iter(client.query(f"""
        SELECT SUM(population_served) AS naive,
               COUNT(*) AS facilities
        FROM {FACILITIES}
        WHERE country_code = 'IN' AND population_served IS NOT NULL
    """).result()))
    print(f"\n  For comparison, the figure NOT used:")
    print(f"    summing all {naive.facilities:,} facilities of every type: "
          f"{naive.naive:,} ({naive.naive / CENSUS_2011_RURAL:.2f}x the rural "
          "population of India)")
    print("    Rejected: sub-centre, PHC and CHC catchments cover the same "
          "people.")

    print("\n  Excluded from the reach figure:")
    for r in client.query(f"""
        SELECT
          COUNTIF(facility_type = 'phc' AND location_type = 'urban') AS urban_phc,
          COUNTIF(facility_type = 'phc' AND location_type IS NULL) AS phc_no_loc,
          COUNTIF(facility_type = 'sub_cen') AS sub_centres,
          COUNTIF(facility_type = 'chc')     AS chcs,
          COUNTIF(facility_type IN ('dis_h', 's_t_h')) AS hospitals
        FROM {FACILITIES} WHERE country_code = 'IN'
    """).result():
        print(f"    urban PHCs (rural average would not apply): {r.urban_phc:,}")
        print(f"    PHCs with no location type:                 {r.phc_no_loc:,}")
        print(f"    sub-centres (nested inside PHC catchments): {r.sub_centres:,}")
        print(f"    CHCs (PHC catchments nest inside these):    {r.chcs:,}")
        print(f"    district / state hospitals:                 {r.hospitals:,}")

    print("\nOK — reach is counted once, from published sources, on a "
          "Census 2011 base that understates rather than inflates.")


if __name__ == "__main__":
    try:
        run()
    except Exception as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        sys.exit(1)
