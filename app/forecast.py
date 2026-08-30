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
