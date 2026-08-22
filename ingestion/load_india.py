"""Block 2 — Load Indian facility data into BigQuery.

Source:  Data/India/geocode_health_centre.csv       (200,438 rows)
         Data/India/rural-population-centre_2017.csv (state-level averages)

Target:  BigQuery `daysupply.facilities`

Demo districts: Mahbubnagar + Ranga Reddy (Telangana) — configurable.
"""

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

DATA_DIR = Path(__file__).resolve().parent.parent / "Data" / "India"
FACILITY_CSV = DATA_DIR / "geocode_health_centre.csv"
POPULATION_CSV = DATA_DIR / "rural-population-centre_2017.csv"

# Demo districts — change here or via env
DEMO_DISTRICTS = os.getenv(
    "DEMO_DISTRICTS_IN", "Mahbubnagar,Ranga Reddy"
).split(",")
DEMO_STATE = os.getenv("DEMO_STATE_IN", "Telangana")


# ---------------------------------------------------------------------------
# Population lookup
# ---------------------------------------------------------------------------
def _load_population_lookup() -> dict:
    """Return {state -> {facility_type -> avg_population}}.

    The CSV has state-level averages for sub-centres, PHCs, and CHCs.
    Column names are long; we map them to our facility types.
    """
    df = pd.read_csv(POPULATION_CSV)
    lookup = {}
    col_map = {
        "Average Rural Population [Census 2011] covered by a Sub Centre": "sub_cen",
        "Average Rural Population [Census 2011] covered by a PHC": "phc",
        "Average Rural Population [Census 2011] covered by a CHC": "chc",
    }
    for _, row in df.iterrows():
        state = row["State/ UT"].strip()
        pops = {}
        for col, ftype in col_map.items():
            try:
                pops[ftype] = int(row[col])
            except (ValueError, TypeError):
                pops[ftype] = None
        lookup[state] = pops
    return lookup


def _estimate_population(state: str, facility_type: str,
                         pop_lookup: dict) -> int | None:
    """Best-effort population estimate for a facility."""
    ftype = facility_type.lower().strip()
    state_data = pop_lookup.get(state)
    if state_data is None:
        # Try partial match (some names differ slightly)
        for k, v in pop_lookup.items():
            if k.lower() in state.lower() or state.lower() in k.lower():
                state_data = v
                break
    if state_data is None:
        return None
    # Map dis_h and s_t_h to CHC-level as approximation
    if ftype in ("dis_h", "s_t_h"):
        return state_data.get("chc")
    return state_data.get(ftype)


# ---------------------------------------------------------------------------
# Main loader
# ---------------------------------------------------------------------------
def load_india_facilities(dry_run: bool = False) -> pd.DataFrame:
    """Parse, transform, and (optionally) upload Indian facility data."""

    print(f"Reading {FACILITY_CSV} ...")
    df = pd.read_csv(FACILITY_CSV, low_memory=False)
    print(f"  Raw rows: {len(df):,}")
    assert len(df) > 200_000, f"Expected 200k+ rows, got {len(df)}"

    # Population lookup
    pop_lookup = _load_population_lookup()

    # Build output dataframe matching the BigQuery schema
    out = pd.DataFrame()
    out["facility_id"] = "IN-" + df.index.astype(str)
    out["country_code"] = "IN"
    out["name"] = df["Facility Name"].fillna("Unknown")
    out["admin_l1"] = df["State Name"].fillna("")
    out["admin_l2"] = df["District Name"].fillna("")
    out["admin_l3"] = df["Subdistrict Name"]  # nullable
    out["facility_type"] = df["Facility Type"].fillna("unknown")
    out["latitude"] = pd.to_numeric(df["Latitude"], errors="coerce")
    out["longitude"] = pd.to_numeric(df["Longitude"], errors="coerce")

    # Population estimate
    out["population_served"] = df.apply(
        lambda r: _estimate_population(
            r["State Name"] if pd.notna(r["State Name"]) else "",
            r["Facility Type"] if pd.notna(r["Facility Type"]) else "",
            pop_lookup,
        ),
        axis=1,
    )
    out["population_served"] = out["population_served"].astype("Int64")

    # Demo facility flag
    out["is_demo_facility"] = (
        (out["admin_l1"] == DEMO_STATE)
        & (out["admin_l2"].isin(DEMO_DISTRICTS))
    )
    demo_count = out["is_demo_facility"].sum()
    print(f"  Demo facilities (India): {demo_count}")

    # Stats
    null_coords = out[out["latitude"].isna() | out["longitude"].isna()]
    print(f"  Missing coordinates: {len(null_coords)}")
    demo_null = null_coords[null_coords["is_demo_facility"]]
    print(f"  Missing coords in demo set: {len(demo_null)}")

    print(f"  Final rows: {len(out):,}")
    assert len(out) == len(df), "Row count mismatch after transform"

    if dry_run:
        print("\n[DRY RUN] Not uploading to BigQuery.")
        print(out.head(3).to_string())
        return out

    # Upload to BigQuery
    print(f"\nUploading to {FULL_TABLE} ...")
    client = bigquery.Client(project=PROJECT)

    job_config = bigquery.LoadJobConfig(
        write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
        schema=[
            bigquery.SchemaField("facility_id", "STRING"),
            bigquery.SchemaField("country_code", "STRING"),
            bigquery.SchemaField("name", "STRING"),
            bigquery.SchemaField("admin_l1", "STRING"),
            bigquery.SchemaField("admin_l2", "STRING"),
            bigquery.SchemaField("admin_l3", "STRING"),
            bigquery.SchemaField("facility_type", "STRING"),
            bigquery.SchemaField("latitude", "FLOAT64"),
            bigquery.SchemaField("longitude", "FLOAT64"),
            bigquery.SchemaField("population_served", "INT64"),
            bigquery.SchemaField("is_demo_facility", "BOOL"),
        ],
    )

    job = client.load_table_from_dataframe(out, FULL_TABLE, job_config=job_config)
    job.result()  # Wait for completion

    # Verify
    table = client.get_table(FULL_TABLE)
    print(f"  BigQuery row count (total table): {table.num_rows:,}")

    return out


# ---------------------------------------------------------------------------
if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    load_india_facilities(dry_run=dry)
