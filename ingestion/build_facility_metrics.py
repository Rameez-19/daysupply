"""Per-facility reporting consistency and network impact metrics.

**Reporting consistency** (Block C step 13)

A PHC is expected to submit a stock count every `REPORT_PERIOD_DAYS`. This
measures how many of the last 90 days' expected reports actually arrived.

It matters more than it looks. Every dashboard above the facility inherits the
quality of what the facility sends, so a district officer looking at a healthy
map has no way to tell a well-stocked district from one that simply stopped
reporting. Making non-reporting visible is the point: it is the root cause the
whole product is built around, and evaluations of comparable systems — South
Africa's Stock Visibility System among them — document compliance decaying a
few months after rollout rather than holding steady.

The score is computed from the ledger, not assumed: a facility that did not
report has no `count` events in that period, and the absence is the measurement.

**Impact metrics**

Two numbers the district officer can act on, both derived:

* units at risk of expiring unused, from `current_stock` and forecast demand
* units of waste FEFO avoids, measured in `generate_usage.py` by running the
  same year's ledger under first-in-first-out and differencing the write-offs
"""

from __future__ import annotations

import os
import sys

from google.cloud import bigquery

PROJECT = os.getenv("GCP_PROJECT", "daysupply")
DATASET = os.getenv("BQ_DATASET", "daysupply")
LOCATION = os.getenv("BQ_LOCATION", "asia-south1")

FACILITIES = f"`{PROJECT}.{DATASET}.facilities`"
STOCK_EVENTS = f"`{PROJECT}.{DATASET}.stock_events`"
CURRENT_STOCK = f"`{PROJECT}.{DATASET}.current_stock`"
REORDER_STATUS = f"`{PROJECT}.{DATASET}.reorder_status`"
RECOMMENDATIONS = f"`{PROJECT}.{DATASET}.recommendations`"
REPORTING = f"`{PROJECT}.{DATASET}.facility_reporting`"

REPORT_PERIOD_DAYS = 30
WINDOW_DAYS = 90

BUILD_REPORTING = f"""
CREATE OR REPLACE TABLE {REPORTING}
CLUSTER BY state, district
AS
WITH as_of AS (
  SELECT MAX(DATE(event_ts)) AS today FROM {STOCK_EVENTS}
),
reports AS (
  SELECT
    e.facility_id,
    -- Which of the last three 30-day periods this report falls in.
    DIV(DATE_DIFF(a.today, DATE(e.event_ts), DAY), {REPORT_PERIOD_DAYS})
      AS period_index
  FROM {STOCK_EVENTS} e
  CROSS JOIN as_of a
  WHERE e.event_type = 'count'
    AND DATE(e.event_ts) > DATE_SUB(a.today, INTERVAL {WINDOW_DAYS} DAY)
),
reported AS (
  SELECT facility_id, COUNT(DISTINCT period_index) AS periods_reported
  FROM reports
  WHERE period_index < {WINDOW_DAYS // REPORT_PERIOD_DAYS}
  GROUP BY facility_id
),
last_seen AS (
  SELECT facility_id, MAX(DATE(event_ts)) AS last_report
  FROM {STOCK_EVENTS}
  WHERE event_type = 'count'
  GROUP BY facility_id
)
SELECT
  f.facility_id,
  f.name        AS facility_name,
  f.admin_l1    AS state,
  f.admin_l2    AS district,
  {WINDOW_DAYS // REPORT_PERIOD_DAYS} AS periods_expected,
  IFNULL(r.periods_reported, 0)       AS periods_reported,
  ROUND(IFNULL(r.periods_reported, 0)
        / {WINDOW_DAYS // REPORT_PERIOD_DAYS}, 2) AS reporting_consistency,
  l.last_report,
  DATE_DIFF(a.today, l.last_report, DAY) AS days_since_last_report,
  CASE
    WHEN IFNULL(r.periods_reported, 0) = 0 THEN 'silent'
    WHEN r.periods_reported < {WINDOW_DAYS // REPORT_PERIOD_DAYS} THEN 'partial'
    ELSE 'complete'
  END AS reporting_status,
  a.today AS as_of_date
FROM {FACILITIES} f
CROSS JOIN as_of a
LEFT JOIN reported r  ON r.facility_id = f.facility_id
LEFT JOIN last_seen l ON l.facility_id = f.facility_id
WHERE f.is_forecast_facility
"""


def run() -> None:
    client = bigquery.Client(project=PROJECT, location=LOCATION)

    print("Building facility_reporting ...")
    client.query(BUILD_REPORTING).result()
    row = next(iter(client.query(f"""
        SELECT COUNT(*) AS facilities,
               COUNTIF(reporting_status = 'complete') AS complete,
               COUNTIF(reporting_status = 'partial')  AS partial,
               COUNTIF(reporting_status = 'silent')   AS silent,
               ROUND(AVG(reporting_consistency), 2)   AS mean_consistency
        FROM {REPORTING}
    """).result()))
    print(f"  facilities:        {row.facilities}")
    print(f"  complete:          {row.complete}")
    print(f"  partial:           {row.partial}")
    print(f"  silent:            {row.silent}")
    print(f"  mean consistency:  {row.mean_consistency:.0%}")

    if row.facilities == 0:
        raise SystemExit("facility_reporting is empty")

    print("\nWorst reporters (district officer's follow-up list):")
    for r in client.query(f"""
        SELECT facility_name, state, district, reporting_consistency,
               days_since_last_report
        FROM {REPORTING}
        ORDER BY reporting_consistency, days_since_last_report DESC
        LIMIT 5
    """).result():
        print(f"  {r.facility_name[:22]:24s} {r.district[:14]:16s} "
              f"{r.reporting_consistency:.0%}  last report "
              f"{r.days_since_last_report}d ago")

    print("\nOK — reporting consistency computed from the ledger.")


if __name__ == "__main__":
    try:
        run()
    except Exception as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        sys.exit(1)
