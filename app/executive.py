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


def _scoped(state: str) -> tuple[str, list]:
    if not state:
        return "TRUE", []
    return "state = @state", [
        bigquery.ScalarQueryParameter("state", "STRING", state)]


def national_picture(state: str = "") -> dict:
    """Everything the executive view needs, in a single round trip."""
    where, params = _scoped(state)

    rows = run_query(f"""
    SELECT
      -- 1. Is it holding? Medicines.
      (SELECT AS STRUCT
         COUNT(*) AS tracked,
         COUNTIF(needs_reorder) AS below_reorder,
         COUNTIF(status = 'stocked_out') AS stocked_out,
         COUNTIF(ven_class = 'Vital' AND needs_reorder) AS vital_short,
         COUNT(DISTINCT facility_id) AS facilities,
         COUNT(DISTINCT district) AS districts,
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

      -- Personnel. Vacancy is real (RHS 2017); attendance is generated.
      (SELECT AS STRUCT
         COUNT(DISTINCT facility_id) AS facilities,
         COUNT(*) AS facility_cadres,
         COUNTIF(days_none_present > 0) AS cadres_with_a_gap,
         ROUND(AVG(vacancy_rate), 3) AS mean_vacancy
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
              LIMIT {TOP_N})) AS worst_districts,

      -- 3. What is coming? Labelled, so an early warning is not confused with
      --    a deworming campaign.
      ARRAY(SELECT AS STRUCT district_key, month, atc_class, surge_multiplier,
                              signal_indicator, signal_class, signal_means
            FROM (
              SELECT s.district_key, s.month, s.atc_class, s.surge_multiplier,
                     l.demand_driver AS signal_indicator,
                     l.signal_class, l.means AS signal_means,
                     CASE l.signal_class WHEN 'leading' THEN 1
                                         WHEN 'coincident' THEN 2 ELSE 3 END AS rank_
              FROM `{D}.surge_signals` s
              LEFT JOIN `{D}.signal_labels` l ON l.atc_class = s.atc_class
              WHERE s.is_surge {'' if not state else 'AND s.state = @state'}
              ORDER BY rank_, s.surge_multiplier DESC
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
       WHERE {where.replace('state', 'to_state')}) AS action_queue,

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

    return {
        "medicines": (
            f"{short:,} of {tracked:,} stock lines are below their reorder "
            f"point ({100 * short / tracked:.0f}%), including "
            f"{med.get('vital_short', 0)} Vital."
            if tracked else "No medicine lines in scope."),
        "beds": (
            f"{beds.get('turned_away', 0):,} patients turned away over the "
            f"year at {beds.get('over_capacity', 0)} facilities; mean "
            f"occupancy {100 * (beds.get('mean_occupancy') or 0):.0f}%."
            if beds.get("facilities") else "No bed data in scope."),
        "personnel": (
            f"Mean vacancy {100 * (staff.get('mean_vacancy') or 0):.0f}% "
            f"across {staff.get('facilities', 0)} facilities; "
            f"{staff.get('cadres_with_a_gap', 0)} facility-cadres had a day "
            "with nobody present."
            if staff.get("facilities") else "No personnel data in scope."),
        "resilience": (
            f"Only {absorb3}% of district-medicine-class positions could "
            "absorb a 3x demand spike from stock already inside the district."
            if absorb3 is not None else "Absorption not computed for scope."),
        "transfer_only": (
            f"{r.get('transfer_only', 0)} facility-items would run out before "
            "a resupply order could physically arrive. Those cannot be fixed "
            "by ordering — only by moving stock that already exists."),
    }
