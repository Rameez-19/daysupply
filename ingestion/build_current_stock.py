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

## This is a VIEW, not a table, and that is the point

It used to be a table rebuilt by this script. That meant a health worker could
report receiving 200 paracetamol, watch the capture counter move, and watch
on-hand not move — because the batch table was computed hours earlier. The
product's claim is that capture updates stock, so stock has to be derived from
the ledger at read time.

**Cost, measured rather than assumed:** the view scans **149.6 MB** per query,
**$0.00085** at $6.25/TiB. A thousand dashboard queries a day is **$0.85/day**,
about **$26/month**, and `app/bq.py` caches reads on top of that. At this volume
the correctness is worth far more than the compute. If the ledger grew by two
orders of magnitude this would need revisiting — a materialised view, or an
incremental merge — but it is nowhere near that.

## Receipts with no expiry date

A captured receipt has no expiry date: nobody says "and it expires in March"
into a phone. The old build filtered `expiry_date IS NOT NULL`, which would
have silently dropped every captured receipt from the batch table while still
counting it in the ledger balance — the reconciliation would break permanently
and on-hand still would not move. Making this a view without noticing that
would have produced a view that did not work.

So batches with an unknown expiry are **included, and ordered last**. FEFO
consumes soonest-expiring first; a batch whose expiry we do not know cannot be
claimed to expire soon, so it is consumed after every dated batch. That is the
conservative reading and it keeps the ledger reconciling exactly.
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

# Everything that takes units off a shelf. Defined once here and reused in the
# reconciliation below, so the batch arithmetic and the balance check can never
# disagree about what counts as consumption.
#
# `dispatched` is stock that has left the donor on an approved transfer. It is
# deliberately not `dispensed` — nobody handed it to a patient — and it must be
# netted out or the donor would appear to still hold units that are physically
# on a vehicle. Stock in transit belongs to neither facility until a receipt is
# recorded at the other end.
#
# `lost` is breakage, spoilage, spillage and theft — one of the three core LMIS
# data items and the one most systems cannot see. It has to net out for the same
# reason: a broken vial is off the shelf whether or not anyone recorded why. The
# reason itself rides in `resource_subtype`, so losses can be counted by cause
# without a separate table.
CONSUMING_EVENT_TYPES = ("dispensed", "expired", "dispatched", "lost")
CONSUMING_EVENT_TYPES_SQL = (
    "(" + ", ".join(f"'{e}'" for e in CONSUMING_EVENT_TYPES) + ")")

BUILD = f"""
CREATE OR REPLACE VIEW {CURRENT_STOCK}
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
    SUM(IF(event_type = 'dispensed',  quantity, 0)) AS total_dispensed,
    SUM(IF(event_type = 'expired',    quantity, 0)) AS total_expired,
    SUM(IF(event_type = 'dispatched', quantity, 0)) AS total_dispatched,
    SUM(quantity)                                   AS total_consumed
  FROM {STOCK_EVENTS}
  WHERE event_type IN {CONSUMING_EVENT_TYPES_SQL}
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
    -- NULLS LAST is load-bearing. A captured receipt has no expiry date, and
    -- BigQuery sorts NULLs first by default, which would consume the batch we
    -- know least about before the ones we know are about to expire — the exact
    -- opposite of FEFO. Unknown expiry goes last.
    SUM(quantity) OVER (
      PARTITION BY facility_id, item_id
      ORDER BY expiry_date NULLS LAST, event_id
      ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS cumulative_qty
  FROM {STOCK_EVENTS}
  -- Undated receipts are included, not filtered. Excluding them would drop
  -- every captured receipt from the batch view while still counting it in the
  -- ledger balance, so the two could never reconcile.
  WHERE event_type = 'received'
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
  -- NULL for an undated batch: unknown, not "expires today". A captured
  -- receipt must never be treated as expired stock on the strength of a
  -- missing field.
  DATE_DIFF(b.expiry_date, a.today, DAY)      AS days_to_expiry,
  IFNULL(b.expiry_date <= a.today, FALSE)     AS is_expired,
  b.expiry_date IS NULL                       AS expiry_unknown,
  a.today                                     AS as_of_date
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
         SUM(IF(event_type = 'received', quantity, 0))
           - SUM(IF(event_type IN {CONSUMING_EVENT_TYPES_SQL}, quantity, 0))
             AS balance
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

    print("Creating the current_stock VIEW (FEFO batch attribution) ...")
    print("  Derived from the ledger at read time, so a capture moves "
          "on-hand immediately rather than at the next rebuild.")
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
    print("\nOK — batch quantities reconcile with the ledger exactly, and "
          "will keep doing so as captures arrive, because the view is "
          "computed from the ledger rather than copied from it.")


if __name__ == "__main__":
    try:
        run()
    except Exception as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        sys.exit(1)
