"""Transfer fulfilment state — the lifecycle a recommendation moves through.

`recommendations` answers *what should move*. This answers *what actually
moved*, and they are different questions that change at different rates.

## Why this is a separate table

`build_supply_plan.py` rebuilds `recommendations` with `CREATE OR REPLACE
TABLE` every time the plan is regenerated. A fulfilment status written into
that table would be destroyed on the next rebuild — a district officer would
approve a transfer, the plan would refresh overnight, and the approval would
vanish. Fulfilment state has to outlive the plan that suggested it.

There is also a name collision worth knowing about: `recommendations.status`
already exists and holds the **receiver's stock status** (`stocked_out`,
`critical`, `reorder`, `ok`) copied from `reorder_status`. It has nothing to do
with fulfilment. The column here is `fulfilment_status`, deliberately.

## The lifecycle

    recommended -> approved -> dispatched -> received

* **recommended** — the engine suggested it. Implicit; no row exists yet.
* **approved** — a human said yes. Stock has not moved.
* **dispatched** — it left the donor. A `dispatched` ledger event is written,
  and the donor's on-hand falls immediately.
* **received** — it arrived. A `received` ledger event is written at the
  recipient, and their on-hand rises.

Dispatch and receipt are separate because **stock in transit belongs to
neither facility**, and pretending otherwise is how supply chains lose track of
it. Between the two states the units are out of the donor and not yet at the
recipient, which is the truth.

## No retraction

Consistent with HANDOVER §9e: rows written by streaming insert cannot be
DML-deleted for up to ~90 minutes, so a retract button would appear to work and
silently not. A transfer that should not have happened is corrected by a
compensating movement, never by deleting the record of it.
"""

from __future__ import annotations

import os
import sys

from google.cloud import bigquery

PROJECT = os.getenv("GCP_PROJECT", "daysupply")
DATASET = os.getenv("BQ_DATASET", "daysupply")
LOCATION = os.getenv("BQ_LOCATION", "asia-south1")

FULFILMENT = f"`{PROJECT}.{DATASET}.transfer_fulfilment`"

# The order matters: a transfer may only move forward through these.
LIFECYCLE = ("recommended", "approved", "dispatched", "received")

SCHEMA = [
    bigquery.SchemaField("recommendation_id", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("fulfilment_status", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("from_facility_id", "STRING"),
    bigquery.SchemaField("to_facility_id", "STRING"),
    bigquery.SchemaField("item_id", "STRING"),
    bigquery.SchemaField("quantity", "INT64"),
    bigquery.SchemaField("approved_at", "TIMESTAMP"),
    bigquery.SchemaField("dispatched_at", "TIMESTAMP"),
    bigquery.SchemaField("received_at", "TIMESTAMP"),
    # The ledger events this transfer produced, so the two can be reconciled.
    bigquery.SchemaField("dispatch_event_id", "STRING"),
    bigquery.SchemaField("receipt_event_id", "STRING"),
    bigquery.SchemaField("updated_at", "TIMESTAMP"),
]


def run() -> None:
    client = bigquery.Client(project=PROJECT, location=LOCATION)
    table_id = f"{PROJECT}.{DATASET}.transfer_fulfilment"

    try:
        existing = client.get_table(table_id)
        print(f"transfer_fulfilment already exists: {existing.num_rows:,} rows")
        print("  Not recreated — this table holds real approvals and must "
              "survive plan rebuilds.")
    except Exception:
        table = bigquery.Table(table_id, schema=SCHEMA)
        table.clustering_fields = ["fulfilment_status", "to_facility_id"]
        client.create_table(table)
        print(f"Created {table_id}")
        print(f"  lifecycle: {' -> '.join(LIFECYCLE)}")

    print("\nOK — fulfilment state lives outside the plan, so approving a "
          "transfer survives the next rebuild of `recommendations`.")


if __name__ == "__main__":
    try:
        run()
    except Exception as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        sys.exit(1)
