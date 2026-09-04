"""The supply chain as geography, because distance is what makes it a problem.

## Why a map earns its place here

Every other view answers "how much" — how many lines are short, how many
patients were turned away. A map answers **"how far"**, and in redistribution
that is the whole question. A district holding surplus antimalarials 40 km from
a district that is stocked out is a different situation from the same surplus
600 km away, and no table makes that difference legible at a glance.

It also makes the one claim this project cannot make in words land visually:
**145 facility-items would run out before a resupply order could physically
arrive.** Those cannot be fixed by ordering. On a map you can see the stock
that would save them, sitting inside the same district cluster.

## Three layers, three different questions

* **Risk** — where is stock short right now, weighted by Vital lines.
* **Headroom** — could the district absorb a 3x spike from stock it already
  holds? This is the resilience question, and the one that separates a district
  that is coping from a district that is one outbreak away from failing.
* **Flow** — the recommended cross-district moves, drawn as arcs. This is the
  "automated cross-district resource redistribution" the brief asks for, shown
  as the thing it actually is: stock travelling a measured distance.

## Coordinates are real

All 116 reporting districts resolve to coordinates, from 199,805 geocoded
facilities in the facility register. Nothing here is placed by hand. A district
centroid is the mean of its facilities' coordinates, which is the centre of
care rather than the geometric centre of the polygon — appropriate, because we
are mapping supply, not territory.

One round trip, as with the executive view: the BigQuery job submission floor
is about 1.3 seconds, so three layers fetched separately would be three floors
stacked.
"""

from __future__ import annotations

import os

from google.cloud import bigquery

from app.bq import run_query

PROJECT = os.getenv("GCP_PROJECT", "daysupply")
DATASET = os.getenv("BQ_DATASET", "daysupply")
D = f"{PROJECT}.{DATASET}"

# The spike a district is asked to absorb from stock already inside it. 3x is
# the figure used everywhere else in the project, so the map agrees with the
# executive view rather than quietly adopting its own threshold.
ABSORPTION_MULTIPLIER = 3.0


def _scoped(state: str, column: str = "state") -> str:
    """Scope predicate against one table's own state column.

    Takes the column name rather than rewriting a finished predicate — the
    `where.replace('state', 'to_state')` shortcut has broken this codebase
    twice by renaming the bound parameter along with the column.
    """
    return "TRUE" if not state else f"{column} = @state"


def supply_map(state: str = "") -> dict:
    """District nodes and redistribution arcs, in a single round trip."""
    where = _scoped(state)
    params = ([bigquery.ScalarQueryParameter("state", "STRING", state)]
              if state else [])

    rows = run_query(f"""
    WITH coords AS (
      SELECT admin_l1 AS state, admin_l2 AS district,
             ROUND(AVG(latitude), 5) AS lat,
             ROUND(AVG(longitude), 5) AS lon,
             COUNT(*) AS facilities_in_register
      FROM `{D}.facilities`
      WHERE has_valid_coords
      GROUP BY state, district
    ),
    risk AS (
      SELECT state, district,
             COUNT(*) AS tracked,
             COUNTIF(needs_reorder) AS short,
             COUNTIF(ven_class = 'Vital' AND needs_reorder) AS vital_short,
             COUNTIF(status = 'stocked_out') AS stocked_out,
             COUNT(DISTINCT facility_id) AS reporting_facilities,
             SUM(on_hand) AS units_on_hand
      FROM `{D}.reorder_status`
      WHERE {where}
      GROUP BY state, district
    ),
    headroom AS (
      SELECT state, district,
             ROUND(100 * SAFE_DIVIDE(COUNTIF(absorbs), COUNT(*)), 1) AS pct_hold,
             COUNT(*) AS positions
      FROM `{D}.network_absorption`
      WHERE multiplier = {ABSORPTION_MULTIPLIER} AND {where}
      GROUP BY state, district
    ),
    flows AS (
      -- The donor district comes from the facility register; `recommendations`
      -- stores only the donor facility id.
      -- `status` here is the RECEIVER's stock condition, not a lifecycle
      -- state: 'stocked_out' | 'critical' | 'reorder'. Filtering it to
      -- 'recommended' matched nothing and emptied the whole layer. It is kept
      -- and ranked instead, so an arc is coloured by how badly the receiving
      -- district needs what is being sent.
      SELECT f.admin_l1 AS from_state, f.admin_l2 AS from_district,
             r.to_state, r.to_district,
             COUNT(*) AS moves,
             SUM(r.quantity) AS units,
             COUNTIF(r.ven_class = 'Vital') AS vital_moves,
             ROUND(MAX(r.distance_km), 1) AS km,
             ROUND(MAX(r.priority_score), 3) AS top_priority,
             MIN(CASE r.status WHEN 'stocked_out' THEN 1
                               WHEN 'critical' THEN 2 ELSE 3 END) AS severity
      FROM `{D}.recommendations` r
      JOIN `{D}.facilities` f ON f.facility_id = r.from_facility_id
      WHERE {_scoped(state, 'r.to_state')}
      GROUP BY from_state, from_district, r.to_state, r.to_district
    )
    SELECT
      ARRAY(
        SELECT AS STRUCT
          k.state, k.district, c.lat, c.lon,
          k.tracked, k.short, k.vital_short, k.stocked_out,
          k.reporting_facilities, k.units_on_hand,
          h.pct_hold, h.positions
        FROM risk k
        JOIN coords c USING (state, district)
        LEFT JOIN headroom h USING (state, district)
        ORDER BY k.vital_short DESC, k.stocked_out DESC
      ) AS districts,
      ARRAY(
        SELECT AS STRUCT
          fl.from_state, fl.from_district, fl.to_state, fl.to_district,
          fl.moves, fl.units, fl.vital_moves, fl.km, fl.top_priority,
          fl.severity,
          a.lat AS from_lat, a.lon AS from_lon,
          b.lat AS to_lat, b.lon AS to_lon
        FROM flows fl
        JOIN coords a ON a.state = fl.from_state AND a.district = fl.from_district
        JOIN coords b ON b.state = fl.to_state AND b.district = fl.to_district
        -- A move inside one district is real but has nothing to draw.
        WHERE NOT (fl.from_district = fl.to_district
                   AND fl.from_state = fl.to_state)
        ORDER BY fl.units DESC
      ) AS flows
    """, params, cache_key=f"map:{state}", ttl=300)

    if not rows:
        return {"districts": [], "flows": [], "scope": state or "All India"}

    r = dict(rows[0])
    districts = [dict(d) for d in (r.get("districts") or [])]
    flows = [dict(f) for f in (r.get("flows") or [])]
    return {
        "districts": districts,
        "flows": flows,
        "scope": state or "All India",
        "summary": _summary(districts, flows),
    }


def _summary(districts: list, flows: list) -> dict:
    """What the map shows, in words, so the legend is not the only guide."""
    if not districts:
        return {"headline": "No district in scope is reporting stock."}

    at_risk = [d for d in districts if (d.get("vital_short") or 0) > 0]
    fragile = [d for d in districts
               if d.get("pct_hold") is not None and d["pct_hold"] < 35]
    units = sum(f.get("units") or 0 for f in flows)
    longest = max((f.get("km") or 0 for f in flows), default=0)

    return {
        "districts": len(districts),
        "districts_with_vital_short": len(at_risk),
        "fragile_districts": len(fragile),
        "flows": len(flows),
        "units_in_flight": units,
        "longest_km": longest,
        "headline": (
            f"{len(at_risk)} of {len(districts)} districts are short on at "
            f"least one Vital line. {len(fragile)} could not absorb a "
            f"{ABSORPTION_MULTIPLIER:g}x spike from stock they already hold."),
        "flow_headline": (
            f"{len(flows)} cross-district moves are recommended, carrying "
            f"{units:,} units; the longest runs {longest:,.0f} km."
            if flows else
            "No cross-district move is recommended in this scope."),
    }
