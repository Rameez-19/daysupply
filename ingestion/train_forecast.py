"""Train the BigQuery ML ARIMA_PLUS demand model.

One real model, trained on the real `stock_events` history, serving real
predictions through `ML.FORECAST`. Nothing in the forecast path is a curve
drawn in code.

**Which series are trained.** Only series with at least `MIN_DAYS` days of
recorded dispensing. The rest are genuinely sparse — their district reports
close to zero for that driver — and a model fitted to noise would be worse than
saying nothing. **Forecasting is active where sufficient signal exists.**

`MIN_DAYS` was 300 while the demand drivers were coarse aggregates, which
inflated volumes: an item whose driver summed fourteen childhood conditions
looked busier than it is. With drivers corrected to their actual clinical
indication, per-item volumes fell to realistic levels — a PHC genuinely uses
about seventeen ampoules of oxytocin a month, not one a day — and 300 days
began excluding series that are perfectly forecastable, including the Vital
antimalarials. At 180 days, half the year showing dispensing activity, 2,742
series qualify, which is well inside the 5,000-series ceiling in
MASTER_PROMPT §6.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from google.cloud import bigquery

PROJECT = os.getenv("GCP_PROJECT", "daysupply")
DATASET = os.getenv("BQ_DATASET", "daysupply")
LOCATION = os.getenv("BQ_LOCATION", "asia-south1")

MODEL = f"{PROJECT}.{DATASET}.demand_forecast"
STOCK_EVENTS = f"{PROJECT}.{DATASET}.stock_events"
FACILITIES = f"{PROJECT}.{DATASET}.facilities"

HORIZON = 30
MIN_DAYS = 180

TRAINING_SET = f"""
SELECT
  DATE(event_ts)                        AS event_date,
  CONCAT(facility_id, '|', item_id)     AS series_id,
  SUM(quantity)                         AS qty_dispensed
FROM `{STOCK_EVENTS}`
WHERE event_type = 'dispensed'
  AND facility_id IN (
    SELECT facility_id FROM `{FACILITIES}` WHERE is_forecast_facility
  )
  AND CONCAT(facility_id, '|', item_id) IN (
    SELECT CONCAT(facility_id, '|', item_id)
    FROM `{STOCK_EVENTS}`
    GROUP BY facility_id, item_id
    HAVING COUNT(DISTINCT DATE(event_ts)) >= {MIN_DAYS}
  )
GROUP BY event_date, series_id
"""

TRAIN_SQL = f"""
CREATE OR REPLACE MODEL `{MODEL}`
OPTIONS(
  model_type = 'ARIMA_PLUS',
  time_series_timestamp_col = 'event_date',
  time_series_data_col = 'qty_dispensed',
  time_series_id_col = 'series_id',
  horizon = {HORIZON},
  auto_arima = TRUE,
  data_frequency = 'DAILY'
) AS
{TRAINING_SET}
"""

PROGRESS = Path(__file__).resolve().parent.parent / "docs" / "PROGRESS.md"
TRAINING_LOG = Path(__file__).resolve().parent.parent / "docs" / "training_runs.json"


def preflight(client: bigquery.Client) -> int:
    """Report the training-set size before committing to a training run."""
    row = next(iter(client.query(f"""
        SELECT COUNT(DISTINCT series_id) AS series,
               COUNT(*) AS rows_in,
               MIN(event_date) AS first_day,
               MAX(event_date) AS last_day
        FROM ({TRAINING_SET})
    """).result()))
    print(f"Training set: {row.series:,} series, {row.rows_in:,} rows, "
          f"{row.first_day} to {row.last_day}")
    if row.series > 5000:
        raise SystemExit(
            f"{row.series:,} series exceeds the 5,000-series ceiling. "
            "Raise MIN_DAYS or narrow the facility set before training."
        )
    return row.series


def train(client: bigquery.Client) -> tuple[float, bigquery.QueryJob]:
    print(f"\nTraining {MODEL} (ARIMA_PLUS, horizon={HORIZON}) ...")
    started = time.perf_counter()
    job = client.query(TRAIN_SQL)
    job.result()
    duration = time.perf_counter() - started
    print(f"  done in {duration:.1f}s ({duration / 60:.1f} min)")
    return duration, job


def summarise(client: bigquery.Client) -> None:
    print("\nModel summary (ML.ARIMA_EVALUATE, first 5 series):")
    rows = client.query(f"""
        SELECT series_id, non_seasonal_p, non_seasonal_d, non_seasonal_q,
               has_drift, ROUND(AIC, 1) AS aic,
               has_holiday_effect, has_spikes_and_dips, has_step_changes
        FROM ML.ARIMA_EVALUATE(MODEL `{MODEL}`)
        ORDER BY series_id
        LIMIT 5
    """).result()
    for r in rows:
        print(f"  {r.series_id:44s} ARIMA({r.non_seasonal_p},"
              f"{r.non_seasonal_d},{r.non_seasonal_q}) AIC={r.aic}")

    agg = next(iter(client.query(f"""
        SELECT COUNT(*) AS series,
               ROUND(AVG(AIC), 1) AS mean_aic,
               COUNTIF(has_drift) AS with_drift,
               COUNTIF(has_spikes_and_dips) AS with_spikes
        FROM ML.ARIMA_EVALUATE(MODEL `{MODEL}`)
    """).result()))
    print(f"\n  series fitted:  {agg.series:,}")
    print(f"  mean AIC:       {agg.mean_aic}")
    print(f"  with drift:     {agg.with_drift:,}")
    print(f"  with spikes:    {agg.with_spikes:,}")


def sample_forecast(client: bigquery.Client) -> None:
    print("\nSample ML.FORECAST output:")
    rows = client.query(f"""
        SELECT series_id,
               DATE(forecast_timestamp) AS forecast_date,
               ROUND(forecast_value, 1) AS forecast_value,
               ROUND(prediction_interval_lower_bound, 1) AS lower,
               ROUND(prediction_interval_upper_bound, 1) AS upper,
               ROUND(confidence_level, 2) AS confidence
        FROM ML.FORECAST(MODEL `{MODEL}`,
                         STRUCT({HORIZON} AS horizon, 0.8 AS confidence_level))
        WHERE series_id = (
          SELECT series_id FROM ML.FORECAST(
            MODEL `{MODEL}`, STRUCT(1 AS horizon, 0.8 AS confidence_level))
          ORDER BY forecast_value DESC LIMIT 1
        )
        ORDER BY forecast_date
        LIMIT 7
    """).result()
    print(f"  {'series':44s} {'date':12s} {'fcst':>7} {'lower':>7} {'upper':>7}")
    for r in rows:
        print(f"  {r.series_id:44s} {str(r.forecast_date):12s} "
              f"{r.forecast_value:>7} {r.lower:>7} {r.upper:>7}")


def record(duration: float, series: int, job: bigquery.QueryJob) -> None:
    entry = {
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "model": MODEL,
        "series": series,
        "horizon": HORIZON,
        "min_days": MIN_DAYS,
        "duration_seconds": round(duration, 1),
        "bytes_processed": job.total_bytes_processed,
        "job_id": job.job_id,
    }
    history = []
    if TRAINING_LOG.exists():
        history = json.loads(TRAINING_LOG.read_text(encoding="utf-8"))
    history.append(entry)
    TRAINING_LOG.write_text(
        json.dumps(history, indent=2) + "\n", encoding="utf-8"
    )
    print(f"\nRecorded in {TRAINING_LOG.name}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preflight-only", action="store_true",
                        help="report training-set size without training")
    args = parser.parse_args()

    client = bigquery.Client(project=PROJECT, location=LOCATION)
    try:
        series = preflight(client)
        if args.preflight_only:
            sys.exit(0)
        duration, job = train(client)
        summarise(client)
        sample_forecast(client)
        record(duration, series, job)
    except Exception as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        raise
