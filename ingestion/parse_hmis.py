"""Parse HMIS 2019-20 monthly indicators into `daysupply.demand_reference`.

Source: `Data/India/<State>.xls`, MoHFW HMIS Standard Report C2.

These files are **not Excel**. They are SAS-generated HTML with an `.xls`
extension, `latin-1` encoded, 38-262 MB each, with a two-level column header:
level 0 is the month, level 1 splits Total / Public / Private / Urban / Rural.
Only the `Total [(A+B) or (C+D)]` column is read.

`admin_l1` is carried on every row. Without it districts collide: 33 district
names recur across states, and Delhi's "Central" is not Maharashtra's.

**Indicators are selected by item code, never by matching words in the label.**
The full file carries 368 distinct data items; the 21 drivers built from them
are defined in `ingestion/hmis_drivers.py`, each with its codes and the
clinical reason it drives the medicines assigned to it. Substring matching is
what previously made the malaria driver 99.8% blood-smear counts — it cannot
tell "Total Blood Smears Examined for Malaria" from "Malaria (RDT) test
positive".

**COVID window.** HMIS 2019-20 runs April 2019 to March 2020. India's national
lockdown began 25 March 2020, so March is a service-disruption artefact rather
than seasonality. Every consumer of this table (`generate_usage.py`,
`patterns.py`) computes its baseline from April-December and holds March at
that baseline. The March figure is still loaded — it is real data, and hiding it
here would make the decision invisible to the next reader.

Run:
    python -m ingestion.parse_hmis --state Delhi --dry-run
    python -m ingestion.parse_hmis                  # all five demo states
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

import pandas as pd
from google.cloud import bigquery

from ingestion.hmis_drivers import ALL_CODES, DRIVERS, driver_for_code

PROJECT = os.getenv("GCP_PROJECT", "daysupply")
DATASET = os.getenv("BQ_DATASET", "daysupply")
LOCATION = os.getenv("BQ_LOCATION", "asia-south1")
TABLE = f"{PROJECT}.{DATASET}.demand_reference"

DATA_DIR = Path(__file__).resolve().parent.parent / "Data" / "India"

# The five states flagged is_demo_facility.
DEMO_STATES = ["Telangana", "Maharashtra", "Rajasthan", "Delhi", "Assam"]

MONTHS = ["April", "May", "June", "July", "August", "September", "October",
          "November", "December", "January", "February", "March"]

TOTAL_COLUMN = "Total [(A+B) or (C+D)]"

# District spellings that differ between the HMIS files and the facility
# master. The source value is preserved in `admin_l2`; `district_key` carries
# the reconciled join key so nothing has to be silently rewritten.
DISTRICT_ALIASES = {
    "AHMADNAGAR": "AHMEDNAGAR",          # Maharashtra, 103 PHCs
}


def district_key(name: str) -> str:
    """Join key: uppercased, trimmed, with known spelling variants aligned."""
    key = " ".join(str(name).upper().split())
    return DISTRICT_ALIASES.get(key, key)


# Rows that are roll-ups, not districts.
NON_DISTRICT = {"district", "total", "grand total", "all districts", "state",
                "nan", ""}

SCHEMA = [
    bigquery.SchemaField("country_code", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("admin_l1", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("admin_l2", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("district_key", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("month", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("indicator", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("value", "FLOAT64", mode="REQUIRED"),
]


def clean_code(value) -> str:
    """HMIS item codes arrive quoted, e.g. \'11.1.1.a\'."""
    return str(value).strip().strip("'").strip()


def parse_state(state: str, path: Path | None = None) -> pd.DataFrame:
    """Parse one state file into the demand_reference shape."""
    path = path or (DATA_DIR / f"{state}.xls")
    if not path.exists():
        raise FileNotFoundError(f"HMIS file not found: {path}")

    size_mb = path.stat().st_size / 1024 ** 2
    print(f"  reading {path.name} ({size_mb:.0f} MB) ...", flush=True)
    started = time.perf_counter()
    with open(path, "r", encoding="latin-1") as handle:
        frame = pd.read_html(handle)[0]
    print(f"    parsed {len(frame):,} rows in "
          f"{time.perf_counter() - started:.0f}s", flush=True)

    districts = frame.iloc[:, 0]
    codes = frame.iloc[:, 1]

    month_columns = {
        month: (month, TOTAL_COLUMN)
        for month in MONTHS
        if (month, TOTAL_COLUMN) in frame.columns
    }
    missing = set(MONTHS) - set(month_columns)
    if missing:
        raise ValueError(f"{state}: missing month columns {sorted(missing)}")

    records: list[dict] = []
    seen_codes: set[str] = set()
    for position in range(len(frame)):
        district = districts.iloc[position]
        code = clean_code(codes.iloc[position])
        if pd.isna(district) or not code or code == "nan":
            continue
        district = str(district).strip()
        if district.lower() in NON_DISTRICT:
            continue
        indicator = driver_for_code(code)
        if indicator is None:
            continue
        seen_codes.add(code)

        for month, column in month_columns.items():
            value = pd.to_numeric(frame.iloc[position][column], errors="coerce")
            records.append({
                "country_code": "IN",
                "admin_l1": state,
                "admin_l2": district,
                "district_key": district_key(district),
                "month": month,
                "indicator": indicator,
                "value": 0.0 if pd.isna(value) else float(value),
            })

    if not records:
        raise ValueError(f"{state}: no matching indicator rows found")

    # HMIS splits malaria by species and inpatients by ward, so a district x
    # month x indicator appears on several rows. Sum them.
    result = (
        pd.DataFrame(records)
        .groupby(["country_code", "admin_l1", "admin_l2", "district_key",
                  "month", "indicator"], as_index=False)["value"]
        .sum()
    )
    missing = ALL_CODES - seen_codes
    if missing:
        print(f"    WARNING: {len(missing)} expected codes absent: "
              f"{', '.join(sorted(missing)[:8])}")
    print(f"    {result['admin_l2'].nunique()} districts, "
          f"{result['indicator'].nunique()} drivers, {len(result):,} rows")
    return result


def load(frames: list[pd.DataFrame], replace_states: list[str]) -> None:
    """Replace only the given states' rows, then verify."""
    client = bigquery.Client(project=PROJECT, location=LOCATION)
    combined = pd.concat(frames, ignore_index=True)

    try:
        client.get_table(TABLE)
        existing = [f.name for f in client.get_table(TABLE).schema]
        if "admin_l1" not in existing or "district_key" not in existing:
            # The original table predates multi-state coverage and cannot be
            # deleted from selectively without a state column.
            print("\nTable lacks admin_l1; recreating with the new schema.")
            client.delete_table(TABLE)
        else:
            print(f"\nClearing existing rows for {', '.join(replace_states)} ...")
            job = client.query(
                f"DELETE FROM `{TABLE}` WHERE admin_l1 IN UNNEST(@states)",
                job_config=bigquery.QueryJobConfig(query_parameters=[
                    bigquery.ArrayQueryParameter(
                        "states", "STRING", replace_states)
                ]),
            )
            job.result()
            print(f"  deleted {job.num_dml_affected_rows:,} rows")
    except Exception as exc:
        if "Not found" not in str(exc):
            raise

    print(f"Loading {len(combined):,} rows into {TABLE} ...")
    client.load_table_from_dataframe(
        combined, TABLE,
        job_config=bigquery.LoadJobConfig(
            schema=SCHEMA,
            write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
        ),
    ).result()

    rows = list(client.query(f"""
        SELECT admin_l1,
               COUNT(*) AS rows_loaded,
               COUNT(DISTINCT admin_l2) AS districts,
               COUNT(DISTINCT indicator) AS indicators,
               COUNT(DISTINCT month) AS months
        FROM `{TABLE}`
        GROUP BY admin_l1
        ORDER BY admin_l1
    """).result())

    print("\nBigQuery verification:")
    total = 0
    for row in rows:
        total += row.rows_loaded
        print(f"  {row.admin_l1:14s} {row.districts:>4} districts  "
              f"{row.indicators:>3} indicators  {row.months:>3} months  "
              f"{row.rows_loaded:>7,} rows")
    print(f"  {'TOTAL':14s} {total:>34,} rows")

    for row in rows:
        if row.months != 12:
            raise SystemExit(
                f"{row.admin_l1} has {row.months} months, expected 12")
        if row.indicators != len(DRIVERS):
            raise SystemExit(
                f"{row.admin_l1} has {row.indicators} drivers, "
                f"expected {len(DRIVERS)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", action="append",
                        help="state to parse; repeatable. Default: all five")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    states = args.state or DEMO_STATES
    print(f"Parsing HMIS for: {', '.join(states)}")

    parsed = []
    for state in states:
        try:
            parsed.append(parse_state(state))
        except Exception as exc:
            print(f"FAILED on {state}: {exc}", file=sys.stderr)
            raise

    if args.dry_run:
        combined = pd.concat(parsed, ignore_index=True)
        print(f"\n[DRY RUN] {len(combined):,} rows, not uploaded.")
        print(combined.head(5).to_string())
        sys.exit(0)

    load(parsed, states)
