"""Today v2 — the supply chain as a scorecard, not a pile of counts.

## What is different, and why

v1 grew by accretion: every finding that proved interesting got a panel, and
the page ended up answering fifteen questions of unequal importance in no
particular order. This is a deliberate scorecard instead.

Public-health logistics has a settled way of grading a supply chain, and it is
not "how many things are short". It is five questions, in this order:

1. **Availability** — what share of what we track is actually there? This is
   the service level, the number a programme is judged on, and the only one
   here where higher is better. Leading with it changes the reader's frame from
   "how many problems" to "how well is this working".
2. **Failure** — what has already run out? Availability of 90% with the missing
   10% being life-saving is a different situation from 90% with the gap in
   vitamins.
3. **Forward risk** — what runs out next, and when? A count is a snapshot; a
   date is a plan.
4. **Equity** — is this concentrated in a few districts or systemic? The
   national average hides both, and the response differs completely.
5. **Resilience** — could it take a shock? Every other number describes today.

## Rates, not counts

Counts are not comparable across scopes: 597 short means nothing until you know
whether it is out of 600 or 6,000, and a district with more facilities will
always look worse. Every headline here is a rate with the count kept beside it,
so Telangana and Assam can be read on the same scale.

## The four visuals answer four different questions

**When** (time to stock-out), **what** (which medicines, by name, in the most
places), **where** (districts plotted by exposure against ability to cope), and
**how robust** (absorption at 2x, 3x, 5x). Four questions, four forms — nothing
here is the same chart twice with a different filter.

The quadrant is the one that earns its place hardest. Shortage and resilience
are usually read separately, and separately they mislead: a district can be
short and able to cover itself from stock next door, or comfortable today and
unable to survive any surge. Plotted together, the districts that are both
badly short *and* unable to cope separate out visibly — Lakhimpur sits at 91.7%
short with 0% able to absorb a tripling, which no ranked list on the v1 page
puts in front of anyone.

One round trip, as everywhere else: the BigQuery job floor is ~1.3s, so six
panels fetched separately would be six floors stacked.
"""

from __future__ import annotations

import os

from google.cloud import bigquery

from app.bq import run_query

PROJECT = os.getenv("GCP_PROJECT", "daysupply")
DATASET = os.getenv("BQ_DATASET", "daysupply")
D = f"{PROJECT}.{DATASET}"

# The spike a district is asked to absorb from stock it already holds. Same 3x
# used by the executive view and the map, so the three cannot disagree.
ABSORPTION_MULTIPLIER = 3.0

# Below this share of positions holding, a district is "could not cope".
FRAGILE_BELOW = 35.0

# A district with three tracked medicines can read 100% short on one bad line.
# Rates need a floor under the denominator or the chart shows noise as crisis.
MIN_LINES_FOR_RATE = 8

# How many bars a reader can compare without counting them.
TOP_N = 10


def _predicates(state: str, district: str, vital_only: bool,
                state_col: str = "state", district_col: str = "district",
                ven_col: str = "ven_class") -> str:
    """Build a WHERE body against one table's own column names.

    Takes column names rather than rewriting a finished predicate. The
    `where.replace('state', 'to_state')` shortcut has broken this codebase
    twice by renaming the bound parameter along with the column, so it is not
    available here by construction.
    """
    parts = []
    if state:
        parts.append(f"{state_col} = @state")
    if district:
        parts.append(f"{district_col} = @district")
    if vital_only:
        parts.append(f"{ven_col} = 'Vital'")
    return " AND ".join(parts) if parts else "TRUE"


def scorecard(state: str = "", district: str = "",
              vital_only: bool = False) -> dict:
    """Everything Today v2 needs, in a single round trip."""
    rs = _predicates(state, district, vital_only)
    na = _predicates(state, district, vital_only)

    params = []
    if state:
        params.append(bigquery.ScalarQueryParameter("state", "STRING", state))
    if district:
        params.append(
            bigquery.ScalarQueryParameter("district", "STRING", district))

    rows = run_query(f"""
    SELECT
      -- 1-5. The scorecard itself. Everything is a rate with its count beside
      -- it, so scopes of different sizes can be compared honestly.
      (SELECT AS STRUCT
         COUNT(*) AS tracked,
         COUNTIF(NOT needs_reorder) AS available,
         COUNTIF(needs_reorder) AS short,
         COUNTIF(status = 'stocked_out') AS stocked_out,
         COUNTIF(ven_class = 'Vital') AS vital_tracked,
         COUNTIF(ven_class = 'Vital' AND NOT needs_reorder) AS vital_available,
         COUNTIF(ven_class = 'Vital' AND needs_reorder) AS vital_short,
         -- Forward risk: already gone, or gone inside a week.
         COUNTIF(on_hand <= 0 OR days_of_cover <= 7) AS at_risk_week,
         COUNT(DISTINCT facility_id) AS facilities,
         COUNT(DISTINCT district) AS districts,
         COUNT(DISTINCT IF(needs_reorder, district, NULL)) AS districts_short,
         COUNT(DISTINCT state) AS states,
         SUM(on_hand) AS units_on_hand
       FROM `{D}.reorder_status` WHERE {rs}) AS scorecard,

      -- WHEN. Ordered, mutually exclusive. Medicines with no usage history are
      -- excluded rather than dropped into the healthiest bucket, which would
      -- flatter the picture.
      ARRAY(SELECT AS STRUCT bucket, sort_order, n
            FROM (
              SELECT
                CASE WHEN on_hand <= 0 THEN 'Already out'
                     WHEN days_of_cover <= 7 THEN 'Within a week'
                     WHEN days_of_cover <= 14 THEN '1 to 2 weeks'
                     WHEN days_of_cover <= 30 THEN '2 to 4 weeks'
                     ELSE 'More than a month' END AS bucket,
                CASE WHEN on_hand <= 0 THEN 1
                     WHEN days_of_cover <= 7 THEN 2
                     WHEN days_of_cover <= 14 THEN 3
                     WHEN days_of_cover <= 30 THEN 4
                     ELSE 5 END AS sort_order,
                COUNT(*) AS n
              FROM `{D}.reorder_status`
              WHERE {rs} AND (days_of_cover IS NOT NULL OR on_hand <= 0)
              GROUP BY bucket, sort_order
              ORDER BY sort_order)) AS timeline,

      -- WHAT. By medicine name, because "Vitamin A is short in 49 health
      -- centres" is a sentence somebody can act on and an ATC code is not.
      ARRAY(SELECT AS STRUCT item_name, ven_class, centres, districts
            FROM (
              SELECT item_name, ANY_VALUE(ven_class) AS ven_class,
                     COUNT(DISTINCT facility_id) AS centres,
                     COUNT(DISTINCT district) AS districts
              FROM `{D}.reorder_status`
              WHERE {rs} AND needs_reorder
              GROUP BY item_name
              ORDER BY centres DESC, districts DESC
              LIMIT {TOP_N})) AS worst_medicines,

      -- WHERE. Exposure against ability to cope. Read separately these two
      -- mislead; together they separate the districts that are both badly
      -- short and unable to help themselves.
      ARRAY(SELECT AS STRUCT district, state, pct_short, pct_cope, tracked,
                             vital_short
            FROM (
              SELECT s.district, s.state, s.tracked, s.vital_short,
                     ROUND(100 * SAFE_DIVIDE(s.short, s.tracked), 1) AS pct_short,
                     ROUND(100 * SAFE_DIVIDE(c.holds, c.positions), 1) AS pct_cope
              FROM (
                SELECT district, ANY_VALUE(state) AS state,
                       COUNT(*) AS tracked, COUNTIF(needs_reorder) AS short,
                       COUNTIF(ven_class = 'Vital' AND needs_reorder) AS vital_short
                FROM `{D}.reorder_status` WHERE {rs}
                GROUP BY district
                HAVING tracked >= {MIN_LINES_FOR_RATE}) s
              JOIN (
                SELECT district, COUNTIF(absorbs) AS holds, COUNT(*) AS positions
                FROM `{D}.network_absorption`
                WHERE multiplier = {ABSORPTION_MULTIPLIER} AND {na}
                GROUP BY district) c
              USING (district))) AS districts_plot,

      -- HOW ROBUST.
      ARRAY(SELECT AS STRUCT multiplier, holds, total,
                             ROUND(100 * SAFE_DIVIDE(holds, total), 1) AS pct
            FROM (
              SELECT multiplier, COUNTIF(absorbs) AS holds, COUNT(*) AS total
              FROM `{D}.network_absorption` WHERE {na}
              GROUP BY multiplier ORDER BY multiplier)) AS absorption,

      -- What a purchase order cannot save.
      (SELECT COUNTIF(lead_time_decisive)
       FROM `{D}.surge_supply_impact`
       WHERE {_predicates(state, district, vital_only)}) AS transfer_only,

      -- Queued decisions, for the scope line.
      (SELECT AS STRUCT COUNT(*) AS recommended, SUM(quantity) AS units,
              COUNTIF(ven_class = 'Vital') AS vital
       FROM `{D}.recommendations`
       WHERE {_predicates(state, district, vital_only,
                          state_col='to_state', district_col='to_district')})
        AS queue
    """, params,
        cache_key=f"v2:{state}:{district}:{int(vital_only)}", ttl=300)

    if not rows:
        return {"error": "no data"}

    r = dict(rows[0])
    r["scope"] = {
        "state": state or "All India",
        "district": district,
        "vital_only": vital_only,
    }
    r["grades"] = _grades(r)
    return r


def _grades(r: dict) -> dict:
    """Turn each headline into a rate plus a plain verdict.

    A percentage with no verdict is a number a specialist can grade and nobody
    else can: the page has to say whether 78.6% is good, or it has not
    communicated anything. Thresholds are stated here once so the wording and
    the colour cannot drift apart.
    """
    s = r.get("scorecard") or {}
    tracked = s.get("tracked") or 0
    vital_tracked = s.get("vital_tracked") or 0
    districts = s.get("districts") or 0

    def rate(num, den):
        return round(100 * num / den, 1) if den else None

    availability = rate(s.get("available") or 0, tracked)
    vital_availability = rate(s.get("vital_available") or 0, vital_tracked)
    out_rate = rate(s.get("stocked_out") or 0, tracked)
    week_rate = rate(s.get("at_risk_week") or 0, tracked)
    spread = rate(s.get("districts_short") or 0, districts)
    absorb3 = next((a["pct"] for a in (r.get("absorption") or [])
                    if a["multiplier"] == ABSORPTION_MULTIPLIER), None)

    def band(value, good, fair, higher_is_better=True):
        """`good`/`fair` are the two cut points, read in the natural direction."""
        if value is None:
            return "unknown"
        if higher_is_better:
            return "ok" if value >= good else "warn" if value >= fair else "bad"
        return "ok" if value <= good else "warn" if value <= fair else "bad"

    return {
        "availability": {
            "pct": availability, "count": s.get("available"), "of": tracked,
            "tone": band(availability, 90, 75),
            "says": _say_availability(availability)},
        "vital_availability": {
            "pct": vital_availability, "count": s.get("vital_available"),
            "of": vital_tracked, "tone": band(vital_availability, 95, 85),
            "says": ("Life-saving medicines should be the last thing to run "
                     "short, not the same as everything else."
                     if vital_availability is not None
                     and availability is not None
                     and vital_availability <= availability
                     else "Life-saving medicines are being protected ahead of "
                          "the rest, which is what should happen.")},
        "stocked_out": {
            "pct": out_rate, "count": s.get("stocked_out"), "of": tracked,
            "tone": band(out_rate, 1, 5, higher_is_better=False),
            "says": "Nothing on the shelf at all today."},
        "at_risk_week": {
            "pct": week_rate, "count": s.get("at_risk_week"), "of": tracked,
            "tone": band(week_rate, 5, 15, higher_is_better=False),
            "says": "Gone within seven days at the current rate of use."},
        "spread": {
            "pct": spread, "count": s.get("districts_short"), "of": districts,
            "tone": band(spread, 25, 60, higher_is_better=False),
            "says": _say_spread(spread)},
        "resilience": {
            "pct": absorb3, "tone": band(absorb3, 70, FRAGILE_BELOW),
            "says": _say_resilience(absorb3)},
    }


def _say_availability(pct: float | None) -> str:
    if pct is None:
        return "Nothing is being tracked here yet."
    if pct >= 90:
        return "Healthy. Most medicines are where they should be."
    if pct >= 75:
        return "Under strain. One medicine in four or five is running low."
    return "Poor. A large share of the medicine list is running low."


def _say_spread(pct: float | None) -> str:
    if pct is None:
        return "No districts in view."
    if pct <= 25:
        return "Concentrated in a few districts, so it can be fixed locally."
    if pct <= 60:
        return "Spread across many districts, not just a few bad ones."
    return "Systemic. Almost every district is affected, so this is not a "\
           "local problem to delegate."


def _say_resilience(pct: float | None) -> str:
    if pct is None:
        return "Not enough data to work this out."
    if pct >= 70:
        return "Most district stocks could cope if demand tripled."
    if pct >= FRAGILE_BELOW:
        return "Many district stocks could not cope if demand tripled."
    return "Low. Most district stocks could not cope if demand tripled."
