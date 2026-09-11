"""The national picture, for someone who has to decide something.

## Who this is for

Not a district officer — they have Today, which answers "what is failing at my
facilities and what do I do". This answers the question a ministry or state
official asks: **is the network holding, where is it not, and what is coming.**

The brief names three things — *medicines, patient footfall, and resource
utilisation* — and the challenge names *medicine stocks, bed availability, and
medical personnel attendance*. A landing page showing only medicines
under-serves that, which is what it was doing.

## Five questions, in the order a decision-maker asks them

1. **Is the network holding right now?** Three resources, one line each.
2. **Where is the risk concentrated?** A national number is useless without
   knowing which districts carry it.
3. **What is coming?** Early warnings, labelled by whether they lead the demand,
   coincide with it, or are a planned campaign.
4. **Could we absorb a shock?** The resilience headroom — this is the "one step
   ahead" question, and it is the one nothing else in Indian public health
   supply currently answers.
5. **What is already queued?** Recommended transfers awaiting a decision.

## One round trip, not nine

Every BigQuery job costs roughly 1.3 seconds of submission overhead before it
reads a single byte — measured, on a query scanning 0 MB. Nine panels fetched
separately would be nine floors stacked, and the page would take fifteen
seconds to say anything.

So this is **one query**, with each panel as an independent subquery. It costs
about what the slowest panel would have cost alone.
"""

from __future__ import annotations

import os

from google.cloud import bigquery

from app.bq import run_query

PROJECT = os.getenv("GCP_PROJECT", "daysupply")
DATASET = os.getenv("BQ_DATASET", "daysupply")
D = f"{PROJECT}.{DATASET}"

# How many districts to name when showing where risk sits. Enough to act on,
# few enough to read.
TOP_N = 5

# The bar chart can carry more rows than the table it replaced could.
CHART_N = 10


def _scoped(state: str, column: str = "state") -> str:
    """A scope predicate for one table's own state column.

    Takes the column name rather than rewriting a finished predicate.
    `recommendations` calls its column `to_state`, and an earlier version got
    there with `where.replace('state', 'to_state')` — which also renamed the
    bound parameter to `@to_state` and made every scoped request fail with
    "Query parameter 'to_state' not found". The same string-replace shortcut
    had already been removed from `app/surge.py` for the same reason.
    """
    return "TRUE" if not state else f"{column} = @state"


def national_picture(state: str = "") -> dict:
    """Everything the executive view needs, in a single round trip."""
    where = _scoped(state)
    rec_where = _scoped(state, "to_state")
    params = ([bigquery.ScalarQueryParameter("state", "STRING", state)]
              if state else [])

    rows = run_query(f"""
    WITH medicine_names AS (
      -- "P01BA" is a code from the model. "Chloroquine, Primaquine" is the
      -- thing a district officer recognises. Unscoped on purpose: a medicine's
      -- name does not change by state.
      SELECT atc_class,
             STRING_AGG(DISTINCT item_name, ', ' ORDER BY item_name) AS names
      FROM `{D}.reorder_status`
      GROUP BY atc_class
    )
    SELECT
      -- 1. Is it holding? Medicines.
      (SELECT AS STRUCT
         COUNT(*) AS tracked,
         COUNTIF(needs_reorder) AS below_reorder,
         COUNTIF(status = 'stocked_out') AS stocked_out,
         COUNTIF(ven_class = 'Vital' AND needs_reorder) AS vital_short,
         COUNT(DISTINCT facility_id) AS facilities,
         COUNT(DISTINCT district) AS districts,
         -- Districts carrying at least one shortage. A national count of short
         -- lines does not say whether the problem is concentrated or spread.
         COUNT(DISTINCT IF(needs_reorder, district, NULL)) AS districts_short,
         SUM(on_hand) AS units_on_hand
       FROM `{D}.reorder_status` WHERE {where}) AS medicines,

      -- Beds. Capacity is the IPHS norm; occupancy is generated and disclosed.
      (SELECT AS STRUCT
         COUNT(*) AS facilities,
         SUM(bed_capacity) AS capacity,
         ROUND(AVG(occupancy_rate), 3) AS mean_occupancy,
         COUNTIF(status = 'over_capacity') AS over_capacity,
         COUNTIF(status = 'under_pressure') AS under_pressure,
         SUM(turned_away) AS turned_away
       FROM `{D}.bed_status` WHERE {where}) AS beds,

      -- Personnel. Only vacancy is real here, and only at state-and-cadre
      -- grain: `vacancy_rate` takes 20 distinct values across all 800 rows,
      -- one per state and cadre from RHS 2021-22 (23 across 928 in 2017). `days_none_present` and
      -- `mean_present` come from a fixed-seed random propensity in
      -- generate_bed_personnel.py, so the sentence this used to build --
      -- "in 875 cases a role had a day with nobody on duty" -- was a random
      -- number, and covered 94% of all rows besides.
      (SELECT AS STRUCT
         COUNT(DISTINCT facility_id) AS facilities,
         COUNT(*) AS facility_cadres,
         COUNT(DISTINCT CONCAT(state, '|', cadre)) AS roles,
         SUM(sanctioned_posts) AS posts,
         -- Weighted by establishment, so a tiny badly-vacant cadre does not
         -- outvote a large one.
         ROUND(SAFE_DIVIDE(SUM(vacancy_rate * sanctioned_posts),
                           SUM(IF(vacancy_rate IS NULL, 0,
                                  sanctioned_posts))), 3) AS mean_vacancy,
         (SELECT AS STRUCT cadre, ROUND(100 * v, 1) AS pct FROM (
            SELECT cadre, SAFE_DIVIDE(SUM(vacancy_rate * sanctioned_posts),
                                      SUM(IF(vacancy_rate IS NULL, 0,
                                             sanctioned_posts))) AS v
            FROM `{D}.staff_status` WHERE {where}
            GROUP BY cadre ORDER BY v DESC LIMIT 1)) AS worst_role
       FROM `{D}.staff_status` WHERE {where}) AS personnel,

      -- 2. Where is it concentrated?
      ARRAY(SELECT AS STRUCT district, state, short, vital_short, stocked_out
            FROM (
              SELECT district, ANY_VALUE(state) AS state,
                     COUNTIF(needs_reorder) AS short,
                     COUNTIF(ven_class = 'Vital' AND needs_reorder) AS vital_short,
                     COUNTIF(status = 'stocked_out') AS stocked_out
              FROM `{D}.reorder_status` WHERE {where}
              GROUP BY district
              HAVING short > 0
              ORDER BY vital_short DESC, stocked_out DESC, short DESC
              LIMIT {CHART_N})) AS worst_districts,

      -- When does it actually run out? The single most decision-useful cut:
      -- a count of lines short is a number, a timeline is a plan. Buckets are
      -- ordered and mutually exclusive, and `days_of_cover` is NULL where
      -- there is no demand history to divide by — those are excluded rather
      -- than dropped into the healthiest bucket, which would flatter us.
      ARRAY(SELECT AS STRUCT bucket, sort_order, n
            FROM (
              SELECT
                CASE
                  WHEN on_hand <= 0 THEN 'Already out'
                  WHEN days_of_cover <= 7 THEN '7 days or less'
                  WHEN days_of_cover <= 14 THEN '8 to 14 days'
                  WHEN days_of_cover <= 30 THEN '15 to 30 days'
                  ELSE 'More than 30 days'
                END AS bucket,
                CASE
                  WHEN on_hand <= 0 THEN 1
                  WHEN days_of_cover <= 7 THEN 2
                  WHEN days_of_cover <= 14 THEN 3
                  WHEN days_of_cover <= 30 THEN 4
                  ELSE 5
                END AS sort_order,
                COUNT(*) AS n
              FROM `{D}.reorder_status`
              WHERE {where} AND (days_of_cover IS NOT NULL OR on_hand <= 0)
              GROUP BY bucket, sort_order
              ORDER BY sort_order)) AS cover_buckets,

      -- Criticality, not just count. A fifth of Desirable lines short is a
      -- different problem from a fifth of Vital lines short.
      ARRAY(SELECT AS STRUCT ven_class, tracked, short, pct
            FROM (
              SELECT ven_class,
                     COUNT(*) AS tracked,
                     COUNTIF(needs_reorder) AS short,
                     ROUND(100 * SAFE_DIVIDE(COUNTIF(needs_reorder), COUNT(*)), 1) AS pct
              FROM `{D}.reorder_status`
              WHERE {where}
              GROUP BY ven_class
              ORDER BY CASE ven_class WHEN 'Vital' THEN 1
                                      WHEN 'Essential' THEN 2 ELSE 3 END)) AS ven_breakdown,

      -- 3. What is coming? Labelled, so an early warning is not confused with
      --    a deworming campaign.
      -- One warning per district-month-driver, NOT per ATC class.
      --
      -- P01BA and P01BF are different antimalarial classes driven by the same
      -- confirmed-malaria signal, so a surge in one district produced two rows
      -- that were identical in every field a reader could see: same district,
      -- same month, same driver, same multiplier. The panel showed the same
      -- warning twice and looked broken. The data was right; the grouping was
      -- wrong. The classes affected are now named on the card instead, which
      -- is the thing that actually differed.
      ARRAY(SELECT AS STRUCT district_key, month, atc_classes, class_count,
                              medicines, surge_multiplier, signal_indicator,
                              signal_class, signal_means
            FROM (
              SELECT s.district_key, s.month,
                     STRING_AGG(DISTINCT s.atc_class, ', '
                                ORDER BY s.atc_class) AS atc_classes,
                     COUNT(DISTINCT s.atc_class) AS class_count,
                     -- NULL where a surging class has no tracked item; the
                     -- card falls back to the code rather than inventing one.
                     STRING_AGG(DISTINCT mn.names, ', '
                                ORDER BY mn.names) AS medicines,
                     MAX(s.surge_multiplier) AS surge_multiplier,
                     l.demand_driver AS signal_indicator,
                     l.signal_class, l.means AS signal_means,
                     CASE l.signal_class WHEN 'leading' THEN 1
                                         WHEN 'coincident' THEN 2 ELSE 3 END AS rank_
              FROM `{D}.surge_signals` s
              LEFT JOIN `{D}.signal_labels` l ON l.atc_class = s.atc_class
              LEFT JOIN medicine_names mn ON mn.atc_class = s.atc_class
              WHERE s.is_surge {'' if not state else 'AND s.state = @state'}
              GROUP BY s.district_key, s.month, l.demand_driver,
                       l.signal_class, l.means
              ORDER BY rank_, surge_multiplier DESC
              LIMIT {TOP_N})) AS early_warnings,

      -- 4. Could we absorb a shock? The resilience headroom.
      ARRAY(SELECT AS STRUCT multiplier, holds, total,
                             ROUND(100 * SAFE_DIVIDE(holds, total), 1) AS pct
            FROM (
              SELECT multiplier, COUNTIF(absorbs) AS holds, COUNT(*) AS total
              FROM `{D}.network_absorption` WHERE {where}
              GROUP BY multiplier ORDER BY multiplier)) AS absorption,

      -- Facilities that cannot be resupplied in time under surge: the ones a
      -- purchase order cannot save.
      (SELECT COUNTIF(lead_time_decisive)
       FROM `{D}.surge_supply_impact` WHERE {where}) AS transfer_only,

      -- 5. What is queued?
      (SELECT AS STRUCT
         COUNT(*) AS recommended,
         SUM(quantity) AS units,
         COUNTIF(ven_class = 'Vital') AS vital
       FROM `{D}.recommendations`
       WHERE {rec_where}) AS action_queue,

      -- Standing scale, so the reader knows what the numbers are a slice of.
      (SELECT AS STRUCT phcs, districts, states, population
       FROM `{D}.population_reach` WHERE tier = 'demand_data_footprint') AS reach
    """, params, cache_key=f"exec:{state}", ttl=300)

    if not rows:
        return {"error": "no data"}
    r = dict(rows[0])
    r["scope"] = state or "All India"
    r["headline"] = _headline(r)
    return r


def _headline(r: dict) -> dict:
    """One sentence per resource, in the terms a decision-maker uses.

    Percentages, not raw counts: "597 of 2,794" means nothing at a glance,
    "21% of tracked stock lines are below their reorder point" does.
    """
    med = r.get("medicines") or {}
    beds = r.get("beds") or {}
    staff = r.get("personnel") or {}
    tracked = med.get("tracked") or 0
    short = med.get("below_reorder") or 0
    absorb3 = next((a["pct"] for a in (r.get("absorption") or [])
                    if a["multiplier"] == 3.0), None)

    # Written for someone who runs health services, not someone who wrote the
    # schema. "Stock line below its reorder point" is the model's phrase for
    # "medicine running low", and only one of those is worth reading twice.
    return {
        "medicines": (
            f"{short:,} of the {tracked:,} medicines we track are running low "
            f"({100 * short / tracked:.0f}%), and {med.get('vital_short', 0)} "
            "of those are life-saving."
            if tracked else "No medicines are being tracked here yet."),
        "beds": (
            f"{beds.get('turned_away', 0):,} patients were turned away in the "
            f"last 30 days of reporting at {beds.get('over_capacity', 0)} health centres. Beds "
            f"are {100 * (beds.get('mean_occupancy') or 0):.0f}% full on "
            "average."
            if beds.get("facilities") else "No bed data here yet."),
        "personnel": (
            f"{100 * (staff.get('mean_vacancy') or 0):.0f}% of "
            f"{staff.get('posts') or 0:,} sanctioned posts are unfilled across "
            f"{staff.get('facilities', 0)} health centres"
            + (f", and {(staff.get('worst_role') or {}).get('cadre')} is the "
               f"hardest role to fill at "
               f"{(staff.get('worst_role') or {}).get('pct')}%."
               if (staff.get("worst_role") or {}).get("cadre") else ".")
            if staff.get("facilities") else "No staffing data here yet."),
        "resilience": (
            f"If demand suddenly tripled, only {absorb3}% of district medicine "
            "stocks could cope using supplies already nearby."
            if absorb3 is not None else "Not enough data to work this out."),
        "transfer_only": (
            f"{r.get('transfer_only', 0)} medicines would run out before a new "
            "order could physically reach the health centre. Ordering cannot "
            "fix these — only moving stock that already exists."),
    }
