"""Network stock health and shortage ranking, computed from real data.

These two figures used to be arrays written into `web/app.js`:

    data: [60 + (seed%10), 22 - (seed%5), 18 - (seed%5)]       # health mix
    data: [1200+(days*10), 850+(days*8), 600+(days*5), ...]    # shortages

Both are now derived: on-hand comes from the real `stock_events` ledger, daily
demand from the trained ARIMA_PLUS model, and days of cover from the two.
"""

from __future__ import annotations

import os

from google.cloud import bigquery

from app.bq import run_query

PROJECT = os.getenv("GCP_PROJECT", "daysupply")
DATASET = os.getenv("BQ_DATASET", "daysupply")

MODEL = f"`{PROJECT}.{DATASET}.demand_forecast`"
STOCK_EVENTS = f"`{PROJECT}.{DATASET}.stock_events`"
ITEMS = f"`{PROJECT}.{DATASET}.items`"
FACILITIES = f"`{PROJECT}.{DATASET}.facilities`"

HORIZON = 30
# Days of cover below which a facility-item is in trouble. Block C replaces
# this flat number with a lead-time-aware reorder point.
CRITICAL_DAYS = 7
LOW_DAYS = 14

# On-hand is a real ledger balance: everything received less everything
# dispensed, over the append-only `stock_events` table. `received` events come
# from the monthly indent cycle the generator emits alongside dispensing.
ON_HAND_SQL = """
    SELECT
      facility_id,
      item_id,
      SUM(IF(event_type = 'received', quantity, 0))
        - SUM(IF(event_type = 'dispensed', quantity, 0)) AS on_hand
    FROM {events}
    GROUP BY facility_id, item_id
"""



def _scope(state: str, district: str, facility_id: str):
    where = ["f.is_forecast_facility"]
    params: list[bigquery.ScalarQueryParameter] = []
    if facility_id:
        where.append("f.facility_id = @facility_id")
        params.append(
            bigquery.ScalarQueryParameter("facility_id", "STRING", facility_id))
    else:
        if state:
            where.append("f.admin_l1 = @state")
            params.append(
                bigquery.ScalarQueryParameter("state", "STRING", state))
        if district:
            where.append("f.admin_l2 = @district")
            params.append(
                bigquery.ScalarQueryParameter("district", "STRING", district))
    return " AND ".join(where), params


def network_health(state: str = "", district: str = "",
                   facility_id: str = "") -> dict:
    """Days-of-cover mix and the largest item-level deficits in scope."""
    where, params = _scope(state, district, facility_id)
    # ML.FORECAST requires literal constants in its settings struct, so
    # HORIZON is interpolated rather than parameterised. It is a module
    # constant, never request input.
    params += [
        bigquery.ScalarQueryParameter("critical", "INT64", CRITICAL_DAYS),
        bigquery.ScalarQueryParameter("low", "INT64", LOW_DAYS),
    ]

    # Shared by both queries: real ledger balance joined to model demand.
    cover_cte = f"""
    WITH demand AS (
      SELECT
        SPLIT(series_id, '|')[OFFSET(0)] AS facility_id,
        SPLIT(series_id, '|')[OFFSET(1)] AS item_id,
        AVG(forecast_value)              AS daily_demand
      FROM ML.FORECAST(MODEL {MODEL}, STRUCT({HORIZON} AS horizon))
      GROUP BY facility_id, item_id
    ),
    on_hand AS (
      {ON_HAND_SQL.format(events=STOCK_EVENTS)}
    ),
    cover AS (
      SELECT
        i.display_name,
        i.ven_class,
        i.unit,
        d.daily_demand,
        GREATEST(IFNULL(h.on_hand, 0), 0) AS on_hand,
        SAFE_DIVIDE(GREATEST(IFNULL(h.on_hand, 0), 0),
                    NULLIF(d.daily_demand, 0)) AS days_of_cover
      FROM demand d
      JOIN {FACILITIES} f ON f.facility_id = d.facility_id
      JOIN {ITEMS} i ON i.item_id = d.item_id
      LEFT JOIN on_hand h
        ON h.facility_id = d.facility_id AND h.item_id = d.item_id
      WHERE {where}
    )
    """

    summary = run_query(
        cover_cte + """
        SELECT
          COUNTIF(days_of_cover < @critical) AS critical,
          COUNTIF(days_of_cover >= @critical
                  AND days_of_cover < @low)  AS low,
          COUNTIF(days_of_cover >= @low)     AS healthy,
          COUNT(*)                           AS total,
          ROUND(AVG(days_of_cover), 1)       AS mean_cover
        FROM cover
        """,
        params,
        cache_key=f"health:{state}:{district}:{facility_id}",
    )
    row = summary[0] if summary else {}

    shortages = run_query(
        cover_cte + """
        SELECT
          display_name AS item_name,
          ven_class,
          unit,
          ROUND(SUM(GREATEST(daily_demand * @low - on_hand, 0)))
            AS deficit_units,
          COUNTIF(days_of_cover < @low) AS facilities_affected
        FROM cover
        GROUP BY item_name, ven_class, unit
        HAVING deficit_units > 0 AND facilities_affected > 0
        ORDER BY deficit_units DESC
        LIMIT 6
        """,
        params,
        cache_key=f"shortages:{state}:{district}:{facility_id}",
    )

    return {
        "healthy": int(row.get("healthy") or 0),
        "low": int(row.get("low") or 0),
        "critical": int(row.get("critical") or 0),
        "total_series": int(row.get("total") or 0),
        "mean_days_of_cover": row.get("mean_cover"),
        "shortages": [
            {
                "item_name": s["item_name"],
                "ven_class": s["ven_class"],
                "unit": s["unit"],
                "deficit_units": int(s["deficit_units"]),
                "facilities_affected": int(s["facilities_affected"]),
            }
            for s in shortages
        ],
        "on_hand_basis": (
            "On-hand is the ledger balance: received less dispensed across "
            "stock_events."
        ),
        "source": "BigQuery ML ARIMA_PLUS + stock_events",
    }
