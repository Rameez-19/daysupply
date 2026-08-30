"""Build `daysupply.current_stock` — on-hand by facility, item and batch.

`stock_events` is an append-only ledger. This collapses it into the position
each facility actually holds, **batch by batch**, which is what FEFO needs: you
cannot prefer the soonest-expiring units without knowing which units expire
when.

**How consumption is attributed.** Batches leave stock two ways: dispensed to a
patient, or written off at expiry. Both happen in expiry order, so both can be
netted against the same running total. Order a facility-item's receipts by
expiry, take the running total, and compare it with everything that has left:
a batch is fully gone if the running total up to and including it is still
below the total consumed, partly gone if consumption lands inside it, untouched
beyond that. That is FEFO applied retrospectively over the whole ledger, in one
pass, with no row-by-row simulation.

The `expired` term matters. Without it the arithmetic implies expired units
were handed to patients, which both overstates dispensing and hides waste.

Rebuild this whenever `stock_events` changes.
"""

from __future__ import annotations

import os
import sys

from google.cloud import bigquery

PROJECT = os.getenv("GCP_PROJECT", "daysupply")
DATASET = os.getenv("BQ_DATASET", "daysupply")
LOCATION = os.getenv("BQ_LOCATION", "asia-south1")

STOCK_EVENTS = f"`{PROJECT}.{DATASET}.stock_events`"
CURRENT_STOCK = f"`{PROJECT}.{DATASET}.current_stock`"

BUILD = f"""
CREATE OR REPLACE TABLE {CURRENT_STOCK}
CLUSTER BY facility_id, item_id
AS
WITH
-- The ledger's "today": the last day any event was recorded.
as_of AS (
  SELECT MAX(DATE(event_ts)) AS today FROM {STOCK_EVENTS}
),
consumed AS (
  SELECT
    facility_id,
    item_id,
    SUM(IF(event_type = 'dispensed', quantity, 0)) AS total_dispensed,
    SUM(IF(event_type = 'expired',   quantity, 0)) AS total_expired,
    SUM(quantity)                                  AS total_consumed
  FROM {STOCK_EVENTS}
  WHERE event_type IN ('dispensed', 'expired')
  GROUP BY facility_id, item_id
),
batches AS (
  SELECT
    facility_id,
    item_id,
    event_id                AS batch_id,
    DATE(event_ts)          AS received_date,
    expiry_date,
    quantity                AS batch_qty,
    -- Running total in expiry order: FEFO consumes in exactly this sequence.
    SUM(quantity) OVER (
      PARTITION BY facility_id, item_id
      ORDER BY expiry_date, event_id
      ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS cumulative_qty
  FROM {STOCK_EVENTS}
  WHERE event_type = 'received' AND expiry_date IS NOT NULL
)
SELECT
  b.facility_id,
  b.item_id,
  b.batch_id,
  b.received_date,
  b.expiry_date,
  b.batch_qty,
  -- Units of this batch still on the shelf.
  CAST(GREATEST(0, LEAST(
    b.batch_qty,
    b.cumulative_qty - IFNULL(d.total_consumed, 0)
  )) AS INT64) AS remaining_qty,
  DATE_DIFF(b.expiry_date, a.today, DAY) AS days_to_expiry,
  b.expiry_date <= a.today               AS is_expired,
  a.today                                AS as_of_date
FROM batches b
CROSS JOIN as_of a
LEFT JOIN consumed d
  ON d.facility_id = b.facility_id AND d.item_id = b.item_id
WHERE GREATEST(0, LEAST(
        b.batch_qty,
        b.cumulative_qty - IFNULL(d.total_consumed, 0))) > 0
"""

VERIFY = f"""
SELECT
  COUNT(*)                                    AS batch_rows,
  COUNT(DISTINCT facility_id)                 AS facilities,
  COUNT(DISTINCT CONCAT(facility_id, '|', item_id)) AS series,
  SUM(remaining_qty)                          AS units_on_hand,
  COUNTIF(is_expired)                         AS expired_batches,
  SUM(IF(is_expired, remaining_qty, 0))       AS expired_units,
  COUNTIF(NOT is_expired AND days_to_expiry <= 90) AS expiring_90d_batches,
  SUM(IF(NOT is_expired AND days_to_expiry <= 90, remaining_qty, 0))
                                              AS expiring_90d_units,
  COUNTIF(NOT is_expired AND days_to_expiry <= 180) AS expiring_180d_batches,
  MAX(as_of_date)                             AS as_of
FROM {CURRENT_STOCK}
"""

# The ledger balance must equal the sum of remaining batch quantities.
RECONCILE = f"""
WITH ledger AS (
  SELECT facility_id, item_id,
         SUM(IF(event_type = 'received',  quantity, 0))
           - SUM(IF(event_type = 'dispensed', quantity, 0))
           - SUM(IF(event_type = 'expired',   quantity, 0)) AS balance
  FROM {STOCK_EVENTS}
  GROUP BY facility_id, item_id
),
batched AS (
  SELECT facility_id, item_id, SUM(remaining_qty) AS batched
  FROM {CURRENT_STOCK}
  GROUP BY facility_id, item_id
)
SELECT COUNTIF(IFNULL(b.batched, 0) != l.balance) AS mismatches,
       COUNT(*) AS compared
FROM ledger l
LEFT JOIN batched b USING (facility_id, item_id)
"""


def run() -> None:
    client = bigquery.Client(project=PROJECT, location=LOCATION)

    print("Building current_stock (FEFO batch attribution) ...")
    client.query(BUILD).result()

    row = next(iter(client.query(VERIFY).result()))
    print(f"  as of:              {row.as_of}")
    print(f"  batch rows:         {row.batch_rows:,}")
    print(f"  facilities:         {row.facilities}")
    print(f"  facility-item pairs:{row.series:,}")
    print(f"  units on hand:      {row.units_on_hand:,}")
    print(f"  expired batches:    {row.expired_batches:,} "
          f"({row.expired_units:,} units)")
    print(f"  expiring <=90 days: {row.expiring_90d_batches:,} "
          f"({row.expiring_90d_units:,} units)")
    print(f"  expiring <=180 days:{row.expiring_180d_batches:,} batches")

    check = next(iter(client.query(RECONCILE).result()))
    print(f"\n  reconciliation: {check.mismatches} mismatches "
          f"across {check.compared:,} facility-item pairs")
    if check.mismatches:
        raise SystemExit(
            f"{check.mismatches} facility-item pairs where batch quantities do "
            "not sum to the ledger balance"
        )
    print("\nOK — batch quantities reconcile with the ledger exactly.")


if __name__ == "__main__":
    try:
        run()
    except Exception as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        sys.exit(1)
