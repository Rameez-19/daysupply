"""Generalise `stock_events` to `resource_events` with a resource dimension.

The brief asks for medicine stocks, bed availability *and* personnel
attendance. Those are three resources moving through one supply chain, not
three products, so they share one event table, one capture pipeline and one
redistribution engine. Adding the dimension later — after surge detection was
built on top — would have meant rebuilding surge.

**Nothing about the medicine path changes.** Every existing row becomes
`resource_type = 'medicine'`, and a view named `stock_events` is left behind so
anything still reading the old name keeps working. The migration asserts row
counts and quantity totals match on both sides before it will finish.

Run:
    python -m ingestion.migrate_resource_events --dry-run
    python -m ingestion.migrate_resource_events
"""

from __future__ import annotations

import argparse
import os
import sys

from google.cloud import bigquery

PROJECT = os.getenv("GCP_PROJECT", "daysupply")
DATASET = os.getenv("BQ_DATASET", "daysupply")
LOCATION = os.getenv("BQ_LOCATION", "asia-south1")

STOCK_EVENTS = f"{PROJECT}.{DATASET}.stock_events"
RESOURCE_EVENTS = f"{PROJECT}.{DATASET}.resource_events"

RESOURCE_TYPES = ("medicine", "bed", "personnel")

# `resource_type` leads the clustering key: almost every query filters on it
# first, and the three types have very different row counts.
BUILD = f"""
CREATE OR REPLACE TABLE `{RESOURCE_EVENTS}`
PARTITION BY DATE(event_ts)
CLUSTER BY resource_type, facility_id, item_id
AS
SELECT
  event_id,
  'medicine'      AS resource_type,
  facility_id,
  item_id         AS item_id,
  event_type,
  quantity,
  event_ts,
  source,
  confidence,
  raw_transcript,
  expiry_date,
  CAST(NULL AS STRING)  AS resource_subtype,
  CAST(NULL AS FLOAT64) AS capacity
FROM `{STOCK_EVENTS}`
"""

# Anything still reading `stock_events` keeps working, and keeps seeing exactly
# what it saw before: medicines only, same columns, same names.
BUILD_VIEW = f"""
CREATE OR REPLACE VIEW `{STOCK_EVENTS}` AS
SELECT
  event_id, facility_id, item_id, event_type, quantity, event_ts,
  source, confidence, raw_transcript, expiry_date
FROM `{RESOURCE_EVENTS}`
WHERE resource_type = 'medicine'
"""


def verify(client: bigquery.Client, before: dict) -> None:
    after = dict(next(iter(client.query(f"""
        SELECT COUNT(*) AS events, SUM(quantity) AS qty,
               COUNT(DISTINCT facility_id) AS facilities,
               COUNT(DISTINCT item_id) AS items,
               COUNT(DISTINCT event_type) AS event_types
        FROM `{RESOURCE_EVENTS}`
        WHERE resource_type = 'medicine'
    """).result())))
    print("\nMedicine path, before -> after:")
    ok = True
    for key, was in before.items():
        now = after.get(key)
        match = "OK" if was == now else "MISMATCH"
        if was != now:
            ok = False
        print(f"  {key:12s} {was:>12,} -> {now:>12,}  {match}")
    if not ok:
        raise SystemExit("Migration changed the medicine data. Refusing.")

    view = dict(next(iter(client.query(f"""
        SELECT COUNT(*) AS events, SUM(quantity) AS qty
        FROM `{STOCK_EVENTS}`
    """).result())))
    if view["events"] != before["events"] or view["qty"] != before["qty"]:
        raise SystemExit("The stock_events view does not match the original.")
    print(f"  stock_events view: {view['events']:,} rows, "
          f"{view['qty']:,} units — identical")


def run(dry_run: bool = False) -> None:
    client = bigquery.Client(project=PROJECT, location=LOCATION)

    table = client.get_table(STOCK_EVENTS)
    if table.table_type == "VIEW":
        print("stock_events is already the compatibility view; "
              "resource_events exists. Nothing to migrate.")
        return

    before = dict(next(iter(client.query(f"""
        SELECT COUNT(*) AS events, SUM(quantity) AS qty,
               COUNT(DISTINCT facility_id) AS facilities,
               COUNT(DISTINCT item_id) AS items,
               COUNT(DISTINCT event_type) AS event_types
        FROM `{STOCK_EVENTS}`
    """).result())))
    print("Before migration:")
    for key, value in before.items():
        print(f"  {key:12s} {value:>12,}")

    if dry_run:
        print("\n[DRY RUN] Nothing written.")
        return

    print(f"\nBuilding {RESOURCE_EVENTS} ...")
    client.query(BUILD).result()

    built = client.get_table(RESOURCE_EVENTS)
    print(f"  rows:         {built.num_rows:,}")
    print(f"  partitioning: {built.time_partitioning.field}")
    print(f"  clustering:   {built.clustering_fields}")

    print(f"\nReplacing {STOCK_EVENTS} with a compatibility view ...")
    client.delete_table(STOCK_EVENTS)
    client.query(BUILD_VIEW).result()

    verify(client, before)
    print("\nOK — medicine path unchanged; bed and personnel can now be added.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    try:
        run(dry_run=args.dry_run)
    except Exception as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        sys.exit(1)
