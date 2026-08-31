"""Block A — Load the full Indian facility master into BigQuery.

Source:  Data/India/geocode_health_centre.csv        (200,438 rows, 37 states,
                                                      668 districts)
         Data/India/rural-population-centre_2017.csv (state-level averages)

Target:  BigQuery `daysupply.facilities`, dataset location asia-south1.

Every row is loaded. Nothing is sampled and nothing is filtered. The row count
of the load is asserted against the row count of the source file and the script
fails loudly on any mismatch — silent row loss is the most likely bug here.

Run:
    python -m ingestion.load_facilities --dry-run   # parse and report only
    python -m ingestion.load_facilities             # parse, load, verify
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import pandas as pd
from google.cloud import bigquery

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
PROJECT = os.getenv("GCP_PROJECT", "daysupply")
DATASET = "daysupply"
TABLE = "facilities"
FULL_TABLE = f"{PROJECT}.{DATASET}.{TABLE}"
LOCATION = "asia-south1"

COUNTRY_CODE = "IN"

DATA_DIR = Path(__file__).resolve().parent.parent / "Data" / "India"
FACILITY_CSV = DATA_DIR / "geocode_health_centre.csv"
POPULATION_CSV = DATA_DIR / "rural-population-centre_2017.csv"

# Demo facilities: PHCs in these five states. Everything else is loaded and
# searchable but carries no generated usage history.
DEMO_STATES = {"Telangana", "Maharashtra", "Rajasthan", "Delhi", "Assam"}
DEMO_FACILITY_TYPE = "phc"

SCHEMA = [
    bigquery.SchemaField("facility_id", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("country_code", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("name", "STRING"),
    bigquery.SchemaField("admin_l1", "STRING"),
    bigquery.SchemaField("admin_l2", "STRING"),
    bigquery.SchemaField("admin_l3", "STRING"),
    bigquery.SchemaField("facility_type", "STRING"),
    bigquery.SchemaField("location_type", "STRING"),
    bigquery.SchemaField("latitude", "FLOAT64"),
    bigquery.SchemaField("longitude", "FLOAT64"),
    bigquery.SchemaField("population_served", "INT64"),
    bigquery.SchemaField("is_demo_facility", "BOOL", mode="REQUIRED"),
]


class LoadError(RuntimeError):
    """Raised when an ingestion invariant is violated."""


# ---------------------------------------------------------------------------
# Population — state-level averages, applied per facility type
# ---------------------------------------------------------------------------
# The 2017 rural population file is state-level, not facility-level: one row per
# State/UT giving the average rural population covered by a sub-centre, a PHC
# and a CHC. There is no per-facility catchment published anywhere, so
# population_served is that state x facility-type average. See Data/README.md.
POP_COLUMNS = {
    "sub_cen": "Average Rural Population [Census 2011] covered by a Sub Centre",
    "phc": "Average Rural Population [Census 2011] covered by a PHC",
    "chc": "Average Rural Population [Census 2011] covered by a CHC",
}

# District and state hospitals have no published catchment average. They serve
# at least a CHC-sized population, so the CHC average is used as a floor.
POP_TYPE_FALLBACK = {"dis_h": "chc", "s_t_h": "chc"}

# Facility-master spellings that differ from the population file's spellings.
STATE_ALIASES = {
    "A & N Islands": "A & N Island",
    "Andhra Pradesh Old": "Andhra Pradesh",
    "Telangana": "Telangana",
}


def _load_population_lookup() -> dict[str, dict[str, int | None]]:
    """Return {state_name -> {facility_type -> average_population}}."""
    df = pd.read_csv(POPULATION_CSV)
    lookup: dict[str, dict[str, int | None]] = {}
    for _, row in df.iterrows():
        state = str(row["State/ UT"]).strip()
        if state.lower() == "all india":
            continue
        pops: dict[str, int | None] = {}
        for ftype, col in POP_COLUMNS.items():
            value = pd.to_numeric(row[col], errors="coerce")
            pops[ftype] = None if pd.isna(value) else int(value)
        lookup[state] = pops
    return lookup


def _population_series(states: pd.Series, types: pd.Series,
                       lookup: dict) -> pd.Series:
    """Vectorised population lookup over the whole facility master."""
    resolved_state = states.fillna("").str.strip().map(
        lambda s: STATE_ALIASES.get(s, s)
    )
    resolved_type = (
        types.fillna("").str.strip().str.lower()
        .map(lambda t: POP_TYPE_FALLBACK.get(t, t))
    )

    # Flatten the lookup to a (state, type) -> population mapping so this is a
    # single vectorised join rather than 200,438 dict lookups.
    flat = {
        (state, ftype): pop
        for state, pops in lookup.items()
        for ftype, pop in pops.items()
    }
    pairs = pd.MultiIndex.from_arrays([resolved_state, resolved_type])
    values = [flat.get(key) for key in pairs]
    return pd.Series(values, index=states.index, dtype="Int64")


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------
def build_facilities() -> tuple[pd.DataFrame, int]:
    """Parse the facility master into the BigQuery schema.

    Returns the dataframe and the source row count, which must match.
    """
    if not FACILITY_CSV.exists():
        raise LoadError(f"Facility master not found: {FACILITY_CSV}")

    print(f"Reading {FACILITY_CSV.name} ...")
    df = pd.read_csv(FACILITY_CSV, low_memory=False)
    source_rows = len(df)
    print(f"  Source rows: {source_rows:,}")

    lookup = _load_population_lookup()

    out = pd.DataFrame(index=df.index)
    out["facility_id"] = "IN-" + df.index.astype(str)
    out["country_code"] = COUNTRY_CODE
    out["name"] = df["Facility Name"].fillna("Unknown").astype(str)
    out["admin_l1"] = df["State Name"].fillna("").astype(str).str.strip()
    out["admin_l2"] = df["District Name"].fillna("").astype(str).str.strip()
    out["admin_l3"] = df["Subdistrict Name"].where(
        df["Subdistrict Name"].notna(), None
    )
    out["facility_type"] = (
        df["Facility Type"].fillna("unknown").astype(str).str.strip().str.lower()
    )
    # Rural or urban. The IPHS bed norm gives urban PHCs day-care beds rather
    # than in-patient ones, so this drives bed capacity. Two source rows carry
    # "Public", a value belonging to a different column; they are left NULL.
    out["location_type"] = (
        df["Location Type"].astype(str).str.strip().str.lower()
        .where(lambda s: s.isin(["rural", "urban"]))
    )
    out["latitude"] = pd.to_numeric(df["Latitude"], errors="coerce")
    out["longitude"] = pd.to_numeric(df["Longitude"], errors="coerce")
    out["population_served"] = _population_series(
        df["State Name"], df["Facility Type"], lookup
    )
    out["is_demo_facility"] = (
        out["admin_l1"].isin(DEMO_STATES)
        & (out["facility_type"] == DEMO_FACILITY_TYPE)
    )

    # --- Invariants -------------------------------------------------------
    if len(out) != source_rows:
        raise LoadError(
            f"Transform changed the row count: {source_rows:,} -> {len(out):,}"
        )
    if out["facility_id"].duplicated().any():
        dupes = int(out["facility_id"].duplicated().sum())
        raise LoadError(f"{dupes:,} duplicate facility_id values")

    # --- Report -----------------------------------------------------------
    missing_coords = int(
        (out["latitude"].isna() | out["longitude"].isna()).sum()
    )
    missing_pop = int(out["population_served"].isna().sum())
    print(f"  States:            {out['admin_l1'].nunique()}")
    print(f"  Districts:         {out['admin_l2'].nunique()}")
    print(f"  Facility types:    {out['facility_type'].nunique()}")
    print(f"  Missing coords:    {missing_coords:,}")
    print(f"  Missing population:{missing_pop:,}")
    print(f"  Demo facilities:   {int(out['is_demo_facility'].sum()):,}")

    if missing_pop:
        unmatched = (
            out.loc[out["population_served"].isna(), ["admin_l1", "facility_type"]]
            .value_counts()
            .head(10)
        )
        print("  Population gaps (state, type):")
        for (state, ftype), count in unmatched.items():
            print(f"    {state} / {ftype}: {count:,}")

    return out, source_rows


# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------
def _ensure_dataset(client: bigquery.Client) -> None:
    ref = bigquery.DatasetReference(PROJECT, DATASET)
    try:
        dataset = client.get_dataset(ref)
        if dataset.location != LOCATION:
            raise LoadError(
                f"Dataset {DATASET} is in {dataset.location}, expected {LOCATION}"
            )
    except Exception as exc:  # dataset missing
        if isinstance(exc, LoadError):
            raise
        print(f"Creating dataset {DATASET} in {LOCATION} ...")
        dataset = bigquery.Dataset(ref)
        dataset.location = LOCATION
        client.create_dataset(dataset)


def load_facilities(dry_run: bool = False) -> pd.DataFrame:
    out, source_rows = build_facilities()

    if dry_run:
        print("\n[DRY RUN] Nothing written to BigQuery.")
        print(out.head(3).to_string())
        return out

    client = bigquery.Client(project=PROJECT, location=LOCATION)
    _ensure_dataset(client)

    # Replace only this country's rows so the load is idempotent and re-running
    # can never double-count. Other countries in the table are left untouched.
    try:
        client.get_table(FULL_TABLE)
        print(f"\nClearing existing {COUNTRY_CODE} rows from {TABLE} ...")
        delete = client.query(
            f"DELETE FROM `{FULL_TABLE}` WHERE country_code = @cc",
            job_config=bigquery.QueryJobConfig(
                query_parameters=[
                    bigquery.ScalarQueryParameter("cc", "STRING", COUNTRY_CODE)
                ]
            ),
        )
        delete.result()
        print(f"  Deleted {delete.num_dml_affected_rows:,} rows")
    except Exception as exc:
        if "Not found" not in str(exc):
            raise
        print(f"\nTable {TABLE} does not exist yet; it will be created.")

    print(f"Loading {len(out):,} rows into {FULL_TABLE} ...")
    job = client.load_table_from_dataframe(
        out,
        FULL_TABLE,
        job_config=bigquery.LoadJobConfig(
            schema=SCHEMA,
            write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
        ),
    )
    job.result()

    verify(client, source_rows)
    return out


def verify(client: bigquery.Client, expected_rows: int) -> None:
    """Assert what actually landed in BigQuery. Fails loudly on mismatch."""
    sql = f"""
    SELECT
      COUNT(*)                          AS rows_loaded,
      COUNT(DISTINCT admin_l1)          AS states,
      COUNT(DISTINCT admin_l2)          AS districts,
      COUNTIF(is_demo_facility)         AS demo_facilities,
      COUNTIF(population_served IS NULL) AS missing_population,
      COUNTIF(latitude IS NULL OR longitude IS NULL) AS missing_coords
    FROM `{FULL_TABLE}`
    WHERE country_code = @cc
    """
    row = next(iter(client.query(
        sql,
        job_config=bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("cc", "STRING", COUNTRY_CODE)
            ]
        ),
    ).result()))

    print("\nBigQuery verification:")
    print(f"  rows_loaded:        {row.rows_loaded:,}")
    print(f"  states:             {row.states}")
    print(f"  districts:          {row.districts}")
    print(f"  demo_facilities:    {row.demo_facilities:,}")
    print(f"  missing_population: {row.missing_population:,}")
    print(f"  missing_coords:     {row.missing_coords:,}")

    if row.rows_loaded != expected_rows:
        raise LoadError(
            "ROW COUNT MISMATCH: source file has "
            f"{expected_rows:,} rows, BigQuery has {row.rows_loaded:,}"
        )
    print(f"\nOK — {row.rows_loaded:,} rows match the source file exactly.")


# ---------------------------------------------------------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true",
                        help="parse and report without writing to BigQuery")
    args = parser.parse_args()
    try:
        load_facilities(dry_run=args.dry_run)
    except LoadError as exc:
        print(f"\nFAILED: {exc}", file=sys.stderr)
        sys.exit(1)
