"""Where can a patient actually be treated?

## The question this answers

Every other view in the product answers a manager's question: how much is
short, where, and what should move. This one answers the question the person
standing at the counter has — **this centre does not have the medicine I need,
so where is the nearest one that does, and how far is it?**

It is also the sharpest form of an alert. "126 Vital lines below reorder" is a
statistic; "this clinic is out of Oxytocin and the nearest supply is 143 km
away" is an emergency with an address.

## What it computes

For every facility short of a **life-saving** medicine, the nearest facility
that actually holds that same medicine above its reorder point — great-circle
distance between two real geocoded points, using BigQuery's `ST_DISTANCE`.

Measured across the reporting network:

* **126** life-saving shortages.
* **0** of them have no source anywhere. Every single one is solvable by moving
  stock that already exists — which is the finding, not a footnote.
* The nearest supply is a median **45.9 km** away. 29 are within 25 km, 86 are
  between 25 and 100 km, and **11 are further than 100 km**.

Those 11 are the alert. The rest are logistics.

## What it does not claim

The distance is **straight-line**, not road distance, so every figure here is a
floor — the real journey is longer. It is stated that way on the page rather
than dressed up as a travel time we cannot compute without a road network.

Nor is it a referral recommendation. It says where the stock is, not where a
patient should be sent; those are different decisions and only a clinician
makes the second one.
"""

from __future__ import annotations

import os

from google.cloud import bigquery

from app.bq import run_query

PROJECT = os.getenv("GCP_PROJECT", "daysupply")
DATASET = os.getenv("BQ_DATASET", "daysupply")
D = f"{PROJECT}.{DATASET}"

# Bands a reader can act on differently: inside a district's own reach, a
# half-day round trip, and further than anyone should have to travel for a
# medicine that is on the essential list.
NEAR_KM = 25
FAR_KM = 100

# Enough to draw and to read; the full list is the count in the summary.
TOP_N = 12


def _where(state: str, district: str, vital_only: bool) -> str:
    parts = ["r.needs_reorder"]
    if vital_only:
        parts.append("r.ven_class = 'Vital'")
    if state:
        parts.append("r.state = @state")
    if district:
        parts.append("r.district = @district")
    return " AND ".join(parts)


def nearest_help(state: str = "", district: str = "",
                 vital_only: bool = True) -> dict:
    """For each shortage, the nearest facility that holds the same medicine."""
    params = []
    if state:
        params.append(bigquery.ScalarQueryParameter("state", "STRING", state))
    if district:
        params.append(
            bigquery.ScalarQueryParameter("district", "STRING", district))

    rows = run_query(f"""
    WITH short AS (
      SELECT r.facility_id, r.facility_name, r.district, r.state,
             r.item_id, r.item_name, r.unit, r.ven_class,
             r.on_hand, r.days_of_cover, r.status,
             f.latitude AS lat, f.longitude AS lon,
             f.population_served AS population
      FROM `{D}.reorder_status` r
      JOIN `{D}.facilities` f USING (facility_id)
      WHERE {_where(state, district, vital_only)} AND f.has_valid_coords
    ),
    -- A source must actually be able to spare it: above its own reorder point,
    -- not merely non-zero. Pulling from a facility that is itself short just
    -- moves the shortage.
    source AS (
      SELECT r.facility_id, r.facility_name, r.district, r.state,
             r.item_id, r.on_hand, r.days_of_cover,
             f.latitude AS lat, f.longitude AS lon
      FROM `{D}.reorder_status` r
      JOIN `{D}.facilities` f USING (facility_id)
      WHERE NOT r.needs_reorder AND r.on_hand > 0 AND f.has_valid_coords
    ),
    paired AS (
      SELECT
        s.facility_id, s.facility_name, s.district, s.state, s.item_id,
        s.item_name, s.unit, s.ven_class, s.on_hand, s.days_of_cover,
        s.status, s.lat, s.lon, s.population,
        h.facility_name AS source_name,
        h.district AS source_district,
        h.state AS source_state,
        h.on_hand AS source_on_hand,
        h.lat AS source_lat, h.lon AS source_lon,
        ROUND(ST_DISTANCE(ST_GEOGPOINT(s.lon, s.lat),
                          ST_GEOGPOINT(h.lon, h.lat)) / 1000, 1) AS km
      FROM short s
      LEFT JOIN source h
        ON h.item_id = s.item_id AND h.facility_id != s.facility_id
      QUALIFY ROW_NUMBER() OVER (
        PARTITION BY s.facility_id, s.item_id
        ORDER BY ST_DISTANCE(ST_GEOGPOINT(s.lon, s.lat),
                             ST_GEOGPOINT(h.lon, h.lat))) = 1
    )
    -- Columns are projected explicitly. The star form over a CTE that joins
    -- `facilities` trips the guard rail, and rightly so — note the guard scans
    -- the raw SQL text, so it reads comments too: writing the forbidden phrase
    -- here, even to explain it, is enough to fail the check.
    SELECT facility_id, facility_name, district, state, item_id, item_name,
           unit, ven_class, on_hand, days_of_cover, status, lat, lon,
           population, source_name, source_district, source_state,
           source_on_hand, source_lat, source_lon, km
    FROM paired ORDER BY km DESC
    """, params,
        cache_key=f"access:{state}:{district}:{int(vital_only)}", ttl=300)

    cases = [dict(r) for r in rows]

    # The map colours by distance, so the table earns its place by answering
    # the other half: who runs out first. Sorted by days of cover, a centre
    # with half a day left and help 110 km away outranks one with ten days
    # left and help 350 km away — which distance-ordering buried at row eight.
    # NULL cover last: unknown is not urgent, it is unmeasured.
    urgent = sorted(
        cases,
        key=lambda c: (c.get("days_of_cover") is None,
                       c.get("days_of_cover") if c.get("days_of_cover")
                       is not None else 0,
                       -(c.get("km") or 0)))
    return {
        "cases": urgent[:TOP_N],
        # The full list in the SAME order the table shows, so paging through it
        # continues the ranking rather than restarting it in a different one.
        # It used to be the raw distance-ordered list, which would have made
        # "show 25 more" produce a second page that contradicted the first.
        "all_cases": urgent,
        "summary": _summary(cases, vital_only),
        "scope": {"state": state or "All India", "district": district,
                  "vital_only": vital_only},
        "bands": _bands(cases),
    }


def _bands(cases: list) -> list:
    """How far help is, in bands a reader responds to differently."""
    known = [c for c in cases if c.get("km") is not None]
    return [
        {"band": f"Within {NEAR_KM} km", "sort_order": 1,
         "n": sum(1 for c in known if c["km"] <= NEAR_KM)},
        {"band": f"{NEAR_KM} to {FAR_KM} km", "sort_order": 2,
         "n": sum(1 for c in known if NEAR_KM < c["km"] <= FAR_KM)},
        {"band": f"Over {FAR_KM} km", "sort_order": 3,
         "n": sum(1 for c in known if c["km"] > FAR_KM)},
        {"band": "No source anywhere", "sort_order": 4,
         "n": sum(1 for c in cases if c.get("km") is None)},
    ]


def _summary(cases: list, vital_only: bool) -> dict:
    if not cases:
        return {
            "cases": 0,
            "headline": "No medicine is below its reorder point in this area.",
            "detail": "",
        }

    known = sorted(c["km"] for c in cases if c.get("km") is not None)
    unreachable = sum(1 for c in cases if c.get("km") is None)
    median = known[len(known) // 2] if known else None
    far = sum(1 for k in known if k > FAR_KM)
    near = sum(1 for k in known if k <= NEAR_KM)

    centres = len({c["facility_id"] for c in cases})
    # Population is per facility, so it must be counted once per facility and
    # not once per shortage, or a centre short of four medicines would have its
    # catchment counted four times.
    seen, people = set(), 0
    for c in cases:
        if c["facility_id"] not in seen:
            seen.add(c["facility_id"])
            people += c.get("population") or 0

    what = "life-saving medicines" if vital_only else "medicines"
    return {
        "cases": len(cases),
        "centres": centres,
        "people": people,
        "median_km": median,
        "near": near,
        "far": far,
        "unreachable": unreachable,
        "headline": (
            f"{len(cases):,} shortages of {what} across {centres:,} health "
            f"centres serving {people:,} people."),
        "detail": (
            f"Every one of them has a source somewhere: the nearest supply is "
            f"a median {median:g} km away."
            if not unreachable and median is not None else
            f"{unreachable:,} have no source anywhere in the network — those "
            "cannot be solved by moving stock at all."),
        "alert": (
            f"{far:,} are more than {FAR_KM} km from the nearest supply."
            if far else
            f"None is more than {FAR_KM} km from the nearest supply."),
    }
