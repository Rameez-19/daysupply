"""Backfill `location_type` onto the facility master.

The original loader dropped the source file's `Location Type` column. It is
needed now because the IPHS bed norm distinguishes rural PHCs (in-patient beds)
from urban PHCs (day-care beds only).

This backfills rather than re-running `load_facilities.py`, because a full
reload deletes and re-appends every row and would take with it the columns
added by later steps — `is_forecast_facility`, `lead_time_days`,
`bed_capacity` and the rest. `load_facilities.py` has been updated too, so a
future clean rebuild includes the column from the start.

Source values are `Rural` (191,996), `Urban` (8,440) and two rows reading
`Public`, which is a defect in the source: `Public` is a value of the
*Type Of Facility* column that has leaked into this one. Those two are loaded
as-is and left unclassified rather than being assigned a location.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pandas as pd
from google.cloud import bigquery

PROJECT = os.getenv("GCP_PROJECT", "daysupply")
DATASET = os.getenv("BQ_DATASET", "daysupply")
LOCATION = os.getenv("BQ_LOCATION", "asia-south1")
FACILITIES = f"{PROJECT}.{DATASET}.facilities"
STAGING = f"{PROJECT}.{DATASET}._location_type_staging"

CSV = Path(__file__).resolve().parent.parent / "Data" / "India" / \
    "geocode_health_centre.csv"

VALID = {"rural", "urban"}


def run() -> None:
    client = bigquery.Client(project=PROJECT, location=LOCATION)

    print(f"Reading {CSV.name} ...")
    df = pd.read_csv(CSV, low_memory=False)
    out = pd.DataFrame({
        "facility_id": "IN-" + df.index.astype(str),
        "location_type": df["Location Type"].astype(str).str.strip().str.lower(),
    })
    # Anything that is not rural or urban is a source defect, not a location.
    unknown = ~out["location_type"].isin(VALID)
    print(f"  rows: {len(out):,}")
    print(f"  rural: {(out['location_type'] == 'rural').sum():,}")
    print(f"  urban: {(out['location_type'] == 'urban').sum():,}")
    print(f"  unclassifiable: {unknown.sum():,} "
          f"({sorted(out.loc[unknown, 'location_type'].unique())})")
    out.loc[unknown, "location_type"] = None

    print("\nAdding column and staging ...")
    client.query(
        f"ALTER TABLE `{FACILITIES}` "
        "ADD COLUMN IF NOT EXISTS location_type STRING"
    ).result()

    client.load_table_from_dataframe(
        out, STAGING,
        job_config=bigquery.LoadJobConfig(
            schema=[
                bigquery.SchemaField("facility_id", "STRING"),
                bigquery.SchemaField("location_type", "STRING"),
            ],
            write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
        ),
    ).result()

    job = client.query(f"""
        UPDATE `{FACILITIES}` f
        SET location_type = s.location_type
        FROM `{STAGING}` s
        WHERE f.facility_id = s.facility_id AND f.country_code = 'IN'
    """)
    job.result()
    print(f"  updated {job.num_dml_affected_rows:,} rows")

    client.delete_table(STAGING, not_found_ok=True)

    row = next(iter(client.query(f"""
        SELECT COUNT(*) AS total,
               COUNTIF(location_type = 'rural') AS rural,
               COUNTIF(location_type = 'urban') AS urban,
               COUNTIF(location_type IS NULL)   AS unknown
        FROM `{FACILITIES}` WHERE country_code = 'IN'
    """).result()))
    print(f"\n  total {row.total:,}  rural {row.rural:,}  "
          f"urban {row.urban:,}  unclassified {row.unknown:,}")
    if row.rural + row.urban + row.unknown != row.total:
        raise SystemExit("Location type counts do not reconcile")
    print("\nOK")


if __name__ == "__main__":
    try:
        run()
    except Exception as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        sys.exit(1)
