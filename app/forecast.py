"""Demand forecasting served from the trained BigQuery ML ARIMA_PLUS model.

Every number returned here comes from `ML.FORECAST` against
`daysupply.demand_forecast`, or from the real `stock_events` history. There are
no generated curves in this module and none anywhere else in the forecast path.

Training lives in `ingestion/train_forecast.py`, not here — a request handler
should never be able to start a training job.
"""

from __future__ import annotations

import logging
import os

from google.cloud import bigquery

from app.bq import run_query

log = logging.getLogger(__name__)

PROJECT = os.getenv("GCP_PROJECT", os.getenv("GOOGLE_CLOUD_PROJECT", "daysupply"))
DATASET = os.getenv("BQ_DATASET", "daysupply")

MODEL = f"`{PROJECT}.{DATASET}.demand_forecast`"
STOCK_EVENTS = f"`{PROJECT}.{DATASET}.stock_events`"
ITEMS = f"`{PROJECT}.{DATASET}.items`"
FACILITIES = f"`{PROJECT}.{DATASET}.facilities`"

HORIZON = 30
CONFIDENCE = 0.8


class ForecastUnavailable(RuntimeError):
    """The model holds no forecast for the requested series."""


def _settings(horizon: int, confidence: float = CONFIDENCE) -> str:
    """Literal settings struct for ML.FORECAST.

    BigQuery requires this struct to be literal constants, so it cannot be
    passed as query parameters. Both values are coerced and bounded here so
    nothing from a request reaches the SQL text unchecked.
    """
    horizon = max(1, min(int(horizon), HORIZON))
    confidence = min(max(float(confidence), 0.01), 0.99)
    return f"STRUCT({horizon} AS horizon, {confidence} AS confidence_level)"


def get_forecast_daily_demand(facility_id: str, item_id: str) -> float:
    """Mean forecast daily demand over the horizon, from ML.FORECAST."""
    rows = run_query(
        f"""
        SELECT AVG(forecast_value) AS daily_demand
        FROM ML.FORECAST(MODEL {MODEL}, {_settings(HORIZON)})
        WHERE series_id = @series_id
        """,
        [
            bigquery.ScalarQueryParameter("series_id", "STRING",
                                          f"{facility_id}|{item_id}"),
        ],
        cache_key=f"fcst:daily:{facility_id}:{item_id}",
    )
    value = rows[0].get("daily_demand") if rows else None
    if value is None:
        raise ForecastUnavailable(
            f"No trained series for {facility_id}|{item_id}. "
            "Forecasting is active only where sufficient history exists."
        )
    return float(value)


def get_forecast_series(facility_id: str, item_id: str,
                        history_days: int = 30,
                        horizon: int = 7) -> dict:
    """Real history plus real ML.FORECAST predictions for one series.

    Returns the shape the dashboard chart expects. The `historical` and
    `forecast` arrays are padded so a single x-axis carries both, with the
    join point duplicated so the two lines meet.
    """
    series_id = f"{facility_id}|{item_id}"

    history = run_query(
        f"""
        SELECT DATE(event_ts) AS day, SUM(quantity) AS qty
        FROM {STOCK_EVENTS}
        WHERE facility_id = @facility_id
          AND item_id = @item_id
          AND event_type = 'dispensed'
          AND DATE(event_ts) > DATE_SUB(
                (SELECT MAX(DATE(event_ts)) FROM {STOCK_EVENTS}),
                INTERVAL @days DAY)
        GROUP BY day
        ORDER BY day
        """,
        [
            bigquery.ScalarQueryParameter("facility_id", "STRING", facility_id),
            bigquery.ScalarQueryParameter("item_id", "STRING", item_id),
            bigquery.ScalarQueryParameter("days", "INT64", history_days),
        ],
        cache_key=f"fcst:hist:{series_id}:{history_days}",
    )

    predictions = run_query(
        f"""
        SELECT DATE(forecast_timestamp) AS day,
               forecast_value,
               prediction_interval_lower_bound AS lower,
               prediction_interval_upper_bound AS upper
        FROM ML.FORECAST(MODEL {MODEL}, {_settings(horizon)})
        WHERE series_id = @series_id
        ORDER BY day
        """,
        [
            bigquery.ScalarQueryParameter("series_id", "STRING", series_id),
        ],
        cache_key=f"fcst:pred:{series_id}:{horizon}",
    )

    if not predictions:
        raise ForecastUnavailable(
            f"No trained series for {series_id}. Forecasting is active only "
            "where sufficient history exists."
        )

    labels = [d["day"].strftime("%b %d") for d in history]
    historical = [int(d["qty"]) for d in history]
    forecast: list[float | None] = [None] * len(historical)

    # Duplicate the last observed point so the two lines join instead of
    # showing a gap.
    if historical:
        forecast[-1] = float(historical[-1])

    for row in predictions[:horizon]:
        labels.append(row["day"].strftime("%b %d"))
        historical.append(None)
        forecast.append(round(float(row["forecast_value"]), 1))

    lower = [None] * len(history) + [
        round(float(r["lower"]), 1) for r in predictions[:horizon]
    ]
    upper = [None] * len(history) + [
        round(float(r["upper"]), 1) for r in predictions[:horizon]
    ]

    return {
        "series_id": series_id,
        "labels": labels,
        "historical": historical,
        "forecast": forecast,
        "lower": lower,
        "upper": upper,
        "confidence_level": CONFIDENCE,
        "source": "BigQuery ML ARIMA_PLUS",
    }


def pick_series(state: str = "", district: str = "",
                facility_id: str = "") -> dict | None:
    """Highest-volume trained series in the current filter scope.

    The chart needs a concrete facility and item. This picks the busiest
    trained series the user is currently looking at, so the chart always shows
    a real series rather than an arbitrary one.
    """
    where = ["f.is_forecast_facility"]
    params: list[bigquery.ScalarQueryParameter] = []
    if facility_id:
        where.append("f.facility_id = @facility_id")
        params.append(bigquery.ScalarQueryParameter(
            "facility_id", "STRING", facility_id))
    else:
        if state:
            where.append("f.admin_l1 = @state")
            params.append(
                bigquery.ScalarQueryParameter("state", "STRING", state))
        if district:
            where.append("f.admin_l2 = @district")
            params.append(bigquery.ScalarQueryParameter(
                "district", "STRING", district))

    rows = run_query(
        f"""
        SELECT e.facility_id, e.item_id, f.name AS facility_name,
               i.display_name AS item_name, i.unit,
               SUM(e.quantity) AS total
        FROM {STOCK_EVENTS} e
        JOIN {FACILITIES} f ON f.facility_id = e.facility_id
        JOIN {ITEMS} i ON i.item_id = e.item_id
        WHERE {' AND '.join(where)}
        GROUP BY e.facility_id, e.item_id, facility_name, item_name, i.unit
        ORDER BY total DESC
        LIMIT 1
        """,
        params,
        cache_key=f"fcst:pick:{state}:{district}:{facility_id}",
    )
    return rows[0] if rows else None


def compute_days_of_cover(on_hand: int, forecast_daily_demand: float) -> float:
    if forecast_daily_demand <= 0:
        return float("inf")
    return float(on_hand) / forecast_daily_demand


def check_alert(facility_id: str, item_id: str, on_hand: int,
                threshold_days: int) -> dict | None:
    try:
        daily_demand = get_forecast_daily_demand(facility_id, item_id)
    except ForecastUnavailable:
        return None
    cover = compute_days_of_cover(on_hand, daily_demand)
    if cover >= threshold_days:
        return None
    return {
        "facility_id": facility_id,
        "item_id": item_id,
        "days_of_cover": round(cover, 1),
        "threshold": threshold_days,
        "status": "active",
        "daily_demand": round(daily_demand, 2),
    }


# ===== What the model is, and what rests on it =====
#
# ARIMA_PLUS is the most load-bearing thing in this system and the least
# visible. Every shortage on every page is a consequence of it:
#
#   ML.FORECAST(demand_forecast)              2,794 trained series
#     -> demand_baseline.avg_daily_demand     = AVG(forecast_value)
#       -> reorder_status (view)
#            reorder_point = avg_daily_demand x lead_time
#                          + 1.65 x sigma x SQRT(lead_time)
#         -> needs_reorder, days_of_cover, shortfall
#           -> the shortage list, the action queue, the transfer
#              recommendations, the map arcs, the alerts
#
# The Plan ahead page answers "what is coming for this medicine class in this
# district", which is a different question at a different grain and is served
# by the pattern exchange. Neither replaces the other, and the danger of
# showing two forecasts is that they read as competing opinions. This panel
# therefore leads with the chain rather than with the curve.

CHAIN_SQL = f"""
SELECT
  (SELECT AS STRUCT
     COUNT(*) AS series,
     COUNTIF(EXISTS(SELECT 1 FROM UNNEST(seasonal_periods) s
                    WHERE CAST(s AS STRING) != 'NO_SEASONALITY')) AS seasonal,
     COUNTIF(has_drift) AS drift,
     COUNT(DISTINCT FORMAT('%d,%d,%d', non_seasonal_p, non_seasonal_d,
                           non_seasonal_q)) AS distinct_orders
   FROM ML.ARIMA_EVALUATE(MODEL {MODEL})) AS model,

  -- The orders auto-ARIMA actually settled on. Twelve different ones across
  -- 2,794 series is the evidence that each was fitted rather than stamped
  -- with a single global order.
  ARRAY(SELECT AS STRUCT arima_order, seasonality, n
        FROM (
          SELECT FORMAT('(%d,%d,%d)', non_seasonal_p, non_seasonal_d,
                        non_seasonal_q) AS arima_order,
                 IF(EXISTS(SELECT 1 FROM UNNEST(seasonal_periods) s
                           WHERE CAST(s AS STRING) != 'NO_SEASONALITY'),
                    'Weekly', 'None') AS seasonality,
                 COUNT(*) AS n
          FROM ML.ARIMA_EVALUATE(MODEL {MODEL})
          GROUP BY arima_order, seasonality
          ORDER BY n DESC
          LIMIT 6)) AS orders,

  (SELECT AS STRUCT
     COUNT(*) AS lines,
     COUNTIF(needs_reorder) AS shortages,
     COUNT(DISTINCT facility_id) AS facilities
   FROM `{PROJECT}.{DATASET}.reorder_status`) AS downstream,

  (SELECT COUNT(*) FROM `{PROJECT}.{DATASET}.recommendations`) AS transfers
"""


def model_evidence() -> dict:
    """The trained model's own description of itself, plus what depends on it.

    Every figure is read back out of BigQuery — `ML.ARIMA_EVALUATE` for the
    model, `reorder_status` and `recommendations` for the chain. Nothing here
    is a constant typed into the page.
    """
    rows = run_query(CHAIN_SQL, cache_key="model:evidence", ttl=900)
    if not rows:
        return {"empty": True}

    r = dict(rows[0])
    m = dict(r["model"]) if r.get("model") else {}
    d = dict(r["downstream"]) if r.get("downstream") else {}
    series = m.get("series") or 0
    seasonal = m.get("seasonal") or 0

    return {
        "empty": False,
        "model": {
            "name": "BigQuery ML ARIMA_PLUS",
            "table": f"{PROJECT}.{DATASET}.demand_forecast",
            "series": series,
            "seasonal": seasonal,
            "seasonal_pct": round(100 * seasonal / series, 1) if series else 0,
            "drift": m.get("drift") or 0,
            "distinct_orders": m.get("distinct_orders") or 0,
            "horizon": HORIZON,
            "confidence": CONFIDENCE,
        },
        "orders": [dict(x) for x in (r.get("orders") or [])],
        "chain": [
            {"step": "ML.FORECAST",
             "detail": f"{series:,} series, each fitted on its own",
             "figure": f"{series:,}", "label": "trained series"},
            {"step": "demand_baseline",
             "detail": "AVG(forecast_value) becomes avg_daily_demand",
             "figure": f"{d.get('lines') or 0:,}", "label": "facility-item lines"},
            {"step": "reorder_status",
             "detail": "reorder point = demand \u00d7 lead time "
                       "+ 1.65 \u00d7 \u03c3 \u00d7 \u221alead time",
             "figure": f"{d.get('facilities') or 0:,}", "label": "facilities"},
            {"step": "What needs acting on",
             "detail": "every shortage on every page is downstream of the model",
             "figure": f"{d.get('shortages') or 0:,}", "label": "shortages"},
            {"step": "Transfer recommendations",
             "detail": "each one sized against the forecast it is covering",
             "figure": f"{r.get('transfers') or 0:,}", "label": "moves"},
        ],
    }
