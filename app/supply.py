"""Alerts, transfers, substitutes and reporting — all read from BigQuery.

Everything here comes from tables built by `ingestion/build_supply_plan.py` and
`ingestion/build_facility_metrics.py`. There is no fallback path that invents an
alert or a transfer: if the tables are unavailable the endpoint says so.

The heavy joins run once at build time rather than on every request, so a
district officer opening the dashboard reads a precomputed answer.
"""

from __future__ import annotations

import os

from google.cloud import bigquery

from app.bq import run_query

PROJECT = os.getenv("GCP_PROJECT", "daysupply")
DATASET = os.getenv("BQ_DATASET", "daysupply")

REORDER_STATUS = f"`{PROJECT}.{DATASET}.reorder_status`"
RECOMMENDATIONS = f"`{PROJECT}.{DATASET}.recommendations`"
SUBSTITUTES = f"`{PROJECT}.{DATASET}.substitutes`"
REPORTING = f"`{PROJECT}.{DATASET}.facility_reporting`"
IMPACT_METRICS = f"`{PROJECT}.{DATASET}.impact_metrics`"

# Vital > Essential > Desirable. Used for display ordering only; the ranking
# itself is baked into priority_score at build time.
VEN_ORDER = {"Vital": 0, "Essential": 1, "Desirable": 2}


def _scope(state: str, district: str, facility_id: str,
           facility_column: str = "facility_id",
           state_column: str = "state",
           district_column: str = "district"):
    where: list[str] = []
    params: list[bigquery.ScalarQueryParameter] = []
    if facility_id:
        where.append(f"{facility_column} = @facility_id")
        params.append(bigquery.ScalarQueryParameter(
            "facility_id", "STRING", facility_id))
    else:
        if state:
            where.append(f"{state_column} = @state")
            params.append(
                bigquery.ScalarQueryParameter("state", "STRING", state))
        if district:
            where.append(f"{district_column} = @district")
            params.append(bigquery.ScalarQueryParameter(
                "district", "STRING", district))
    return (" AND ".join(where) or "TRUE"), params


def get_alerts(state: str = "", district: str = "", facility_id: str = "",
               limit: int = 50) -> list[dict]:
    """Open stock-out alerts, ranked by VEN-weighted shortfall.

    A vital medicine outranks a desirable one at the same days of cover,
    because running out of them are not the same event.
    """
    where, params = _scope(state, district, facility_id)
    params.append(bigquery.ScalarQueryParameter("lim", "INT64", limit))
    return run_query(
        f"""
        SELECT
          facility_id, facility_name, state, district,
          item_id, item_name, unit, ven_class,
          on_hand, avg_daily_demand, days_of_cover,
          reorder_point, safety_stock, legacy_threshold,
          lead_time_days, distance_to_hq_km, lead_time_is_estimated,
          priority_score, status,
          days_to_soonest_expiry, soonest_expiry
        FROM {REORDER_STATUS}
        WHERE needs_reorder AND {where}
        ORDER BY priority_score DESC, days_of_cover
        LIMIT @lim
        """,
        params,
        cache_key=f"alerts:{state}:{district}:{facility_id}:{limit}",
    )


def get_recommendations(state: str = "", district: str = "",
                        facility_id: str = "", limit: int = 50) -> list[dict]:
    """Transfer recommendations: FEFO batch, ATC substitution labelled."""
    where, params = _scope(
        state, district, facility_id,
        facility_column="to_facility_id",
        state_column="to_state",
        district_column="to_district",
    )
    params.append(bigquery.ScalarQueryParameter("lim", "INT64", limit))
    return run_query(
        f"""
        SELECT
          recommendation_id,
          from_facility_id, from_facility_name,
          to_facility_id, to_facility_name, to_state, to_district,
          requested_item_id, requested_item_name,
          supplied_item_id, supplied_item_name, is_substitution,
          ven_class, unit, quantity, distance_km,
          fefo_batch_id, fefo_expiry_date, fefo_days_to_expiry,
          waste_avoided_units,
          receiver_cover_before, receiver_cover_after,
          donor_cover_before, donor_cover_after,
          priority_score, status
        FROM {RECOMMENDATIONS}
        WHERE {where}
        ORDER BY priority_score DESC, distance_km
        LIMIT @lim
        """,
        params,
        cache_key=f"recs:{state}:{district}:{facility_id}:{limit}",
    )


def get_substitutes(state: str = "", district: str = "",
                    facility_id: str = "", limit: int = 50) -> list[dict]:
    """ATC-equivalent items a facility already holds for something it is short of.

    These are alternatives, never replacements for the requested item, and the
    caller must present both names.
    """
    where, params = _scope(state, district, facility_id)
    params.append(bigquery.ScalarQueryParameter("lim", "INT64", limit))
    return run_query(
        f"""
        SELECT
          facility_id, facility_name, state, district,
          requested_item_id, requested_item_name, requested_ven_class,
          requested_on_hand, requested_days_of_cover,
          alternative_item_id, alternative_item_name, alternative_ven_class,
          alternative_atc_code, alternative_on_hand, alternative_days_of_cover,
          unit, atc_class
        FROM {SUBSTITUTES}
        WHERE rank_by_cover <= 3 AND {where}
        ORDER BY requested_days_of_cover, alternative_days_of_cover DESC
        LIMIT @lim
        """,
        params,
        cache_key=f"subs:{state}:{district}:{facility_id}:{limit}",
    )


def substitution_constraint() -> dict:
    """Why the substitution list is empty, when it is.

    An empty list with no explanation reads as a broken feature. It is not:
    substitution is working correctly and finding nothing, for a reason that is
    a property of the catalogue rather than of the code.

    A substitute has to be a *different* item, in the *same* ATC level-4 class,
    at the *same* facility, held above that alternative's own reorder point.
    Level 4 is deliberate — level 3 paired Zinc Sulphate with Magnesium
    Sulphate, which is clinically wrong, and a regression test pins the stricter
    rule. The cost of that correctness is reach: of the 39 forecast items, only
    one ATC level-4 class contains two of them, so there is almost nothing to
    substitute *between*.

    Reported rather than hidden, the same way staff reallocation reports why it
    returns nothing.
    """
    rows = run_query(f"""
        SELECT
          COUNT(DISTINCT atc_class)                       AS classes,
          COUNTIF(items_in_class > 1)                     AS classes_with_a_pair
        FROM (
          SELECT atc_class, COUNT(DISTINCT item_id) AS items_in_class
          FROM {REORDER_STATUS}
          WHERE atc_class IS NOT NULL
          GROUP BY atc_class
        )
    """, cache_key="subs:constraint")
    row = rows[0] if rows else {"classes": 0, "classes_with_a_pair": 0}
    return {
        "forecast_atc_classes": row["classes"],
        "classes_containing_two_forecast_items": row["classes_with_a_pair"],
        "why": (
            "A substitute must be a different item in the same ATC level-4 "
            "class, held at the same facility above its own reorder point. "
            f"Only {row['classes_with_a_pair']} of {row['classes']} ATC classes "
            "in the forecast set contain two forecast items at all, so there "
            "is almost nothing to substitute between. Matching at ATC level 3 "
            "would produce far more candidates and some of them would be "
            "clinically wrong — it paired Zinc Sulphate with Magnesium "
            "Sulphate — so the stricter rule is kept and the reach is the "
            "price. Widening the forecast item set, not loosening the ATC "
            "level, is what would make this fire."),
    }


def get_reporting(state: str = "", district: str = "",
                  facility_id: str = "", limit: int = 200) -> dict:
    """Reporting consistency per facility, plus the scope summary."""
    where, params = _scope(state, district, facility_id)
    params.append(bigquery.ScalarQueryParameter("lim", "INT64", limit))

    rows = run_query(
        f"""
        SELECT
          facility_id, facility_name, state, district,
          periods_expected, periods_reported, reporting_consistency,
          last_report, days_since_last_report, reporting_status
        FROM {REPORTING}
        WHERE {where}
        ORDER BY reporting_consistency, days_since_last_report DESC
        LIMIT @lim
        """,
        params,
        cache_key=f"reporting:{state}:{district}:{facility_id}:{limit}",
    )

    summary_where, summary_params = _scope(state, district, facility_id)
    summary = run_query(
        f"""
        SELECT
          COUNT(*)                                     AS facilities,
          COUNTIF(reporting_status = 'complete')       AS complete,
          COUNTIF(reporting_status = 'partial')        AS partial,
          COUNTIF(reporting_status = 'silent')         AS silent,
          ROUND(AVG(reporting_consistency), 3)         AS mean_consistency
        FROM {REPORTING}
        WHERE {summary_where}
        """,
        summary_params,
        cache_key=f"reporting-sum:{state}:{district}:{facility_id}",
    )
    return {"summary": summary[0] if summary else {}, "facilities": rows}


def get_summary(state: str = "", district: str = "",
                facility_id: str = "") -> dict:
    """Headline counts for the dashboard — all real, none fabricated."""
    where, params = _scope(state, district, facility_id)
    status = run_query(
        f"""
        SELECT
          COUNT(*)                                   AS tracked_series,
          COUNTIF(needs_reorder)                     AS open_alerts,
          COUNTIF(status = 'stocked_out')            AS stocked_out,
          COUNTIF(status = 'critical')               AS critical,
          COUNTIF(needs_reorder AND ven_class = 'Vital')     AS vital_alerts,
          COUNTIF(needs_reorder AND on_hand > legacy_threshold)
                                                     AS caught_by_lead_time_rule,
          COUNT(DISTINCT facility_id)                AS facilities,
          COUNT(DISTINCT item_id)                    AS items
        FROM {REORDER_STATUS}
        WHERE {where}
        """,
        params,
        cache_key=f"supply-sum:{state}:{district}:{facility_id}",
    )

    rec_where, rec_params = _scope(
        state, district, facility_id,
        facility_column="to_facility_id",
        state_column="to_state",
        district_column="to_district",
    )
    transfers = run_query(
        f"""
        SELECT
          COUNT(*)                       AS pending_transfers,
          IFNULL(SUM(quantity), 0)       AS units_to_move,
          IFNULL(SUM(waste_avoided_units), 0) AS waste_avoided_units,
          COUNTIF(is_substitution)       AS substitutions
        FROM {RECOMMENDATIONS}
        WHERE {rec_where}
        """,
        rec_params,
        cache_key=f"transfer-sum:{state}:{district}:{facility_id}",
    )

    row = status[0] if status else {}
    rec = transfers[0] if transfers else {}
    return {
        "tracked_series": int(row.get("tracked_series") or 0),
        "open_alerts": int(row.get("open_alerts") or 0),
        "stocked_out": int(row.get("stocked_out") or 0),
        "critical": int(row.get("critical") or 0),
        "vital_alerts": int(row.get("vital_alerts") or 0),
        "caught_by_lead_time_rule": int(row.get("caught_by_lead_time_rule") or 0),
        "facilities_tracked": int(row.get("facilities") or 0),
        "items_tracked": int(row.get("items") or 0),
        "pending_transfers": int(rec.get("pending_transfers") or 0),
        "units_to_move": int(rec.get("units_to_move") or 0),
        "waste_avoided_units": int(rec.get("waste_avoided_units") or 0),
        "substitutions": int(rec.get("substitutions") or 0),
    }


def get_impact() -> dict:
    """Network impact metrics, including the FEFO counterfactual.

    `waste_avoided_by_fefo_units` is measured by replaying the same year's
    ledger under first-in-first-out issuing and differencing the write-offs.
    It is a property of the whole network over a year, not of any one
    recommendation — the per-transfer `waste_avoided_units` on current
    recommendations is legitimately zero, because FEFO at the facility has
    already consumed everything short-dated.
    """
    rows = run_query(
        f"""
        SELECT as_of_date, units_dispensed, units_unmet, unmet_share,
               units_expired_fefo, units_expired_fifo,
               waste_avoided_by_fefo_units, waste_avoided_share
        FROM {IMPACT_METRICS}
        ORDER BY as_of_date DESC
        LIMIT 1
        """,
        cache_key="impact",
    )
    return rows[0] if rows else {}


def lead_time_contrast(state: str = "", district: str = "") -> dict:
    """The nearest and furthest PHC from their district warehouse, paired.

    The same medicine at two facilities, with reorder points that differ only
    because one is further from its warehouse. This is the clearest single
    illustration of what the lead-time rule changes.
    """
    where, params = _scope(state, district, "")
    rows = run_query(
        f"""
        WITH ranked AS (
          SELECT
            facility_name, state, district, item_name, unit, ven_class,
            distance_to_hq_km, lead_time_days, avg_daily_demand,
            demand_std_dev, safety_stock, reorder_point, legacy_threshold,
            on_hand, days_of_cover, lead_time_is_estimated,
            ROW_NUMBER() OVER (ORDER BY distance_to_hq_km)      AS nearest,
            ROW_NUMBER() OVER (ORDER BY distance_to_hq_km DESC) AS furthest
          FROM {REORDER_STATUS}
          WHERE {where}
            AND avg_daily_demand > 0
            AND NOT lead_time_is_estimated
            AND item_id = (
              SELECT item_id FROM {REORDER_STATUS}
              WHERE {where}
              GROUP BY item_id
              ORDER BY COUNT(*) DESC, item_id
              LIMIT 1
            )
        )
        SELECT * FROM ranked WHERE nearest = 1 OR furthest = 1
        """,
        # `where` appears twice in the SQL but references the same named
        # parameters; BigQuery rejects the list if they are supplied twice.
        params,
        cache_key=f"contrast:{state}:{district}",
    )
    near = next((r for r in rows if r["nearest"] == 1), None)
    far = next((r for r in rows if r["furthest"] == 1), None)
    if not near or not far or near["facility_name"] == far["facility_name"]:
        return {}

    # Comparing the two facilities' reorder points directly would conflate two
    # different things: they are further apart *and* they serve different
    # numbers of patients. To isolate distance, recompute the remote
    # facility's own reorder point as if it sat next to the warehouse. The
    # difference is then attributable to lead time alone.
    z = float(os.getenv("SERVICE_LEVEL_Z", "1.65"))
    near_lead = near["lead_time_days"]
    demand = far["avg_daily_demand"] or 0
    std = far["demand_std_dev"] or 0
    if_near = demand * near_lead + z * std * (near_lead ** 0.5)

    return {
        "item_name": near["item_name"],
        "unit": near["unit"],
        "ven_class": near["ven_class"],
        "nearest": near,
        "furthest": far,
        # What the remote facility's own reorder point would be at the near
        # facility's lead time — the like-for-like comparison.
        "furthest_reorder_if_near": round(if_near, 1),
        "extra_units_from_distance": round(far["reorder_point"] - if_near, 1),
        "extra_lead_days": far["lead_time_days"] - near_lead,
        # And what the flat rule would have set for the remote facility.
        "furthest_flat_threshold": far["legacy_threshold"],
        "flat_rule_shortfall": round(
            far["reorder_point"] - far["legacy_threshold"], 1),
    }
