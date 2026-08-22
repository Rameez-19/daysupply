"""Block 2 — Load Brazilian facility data into BigQuery.

Sources: Data/Brazil/cnes_estabelecimentos.csv  (632,726 rows, semicolon, latin-1)
         Data/Brazil/cnes_coord.csv              (574,172 rows, comma, UTF-8)
         Data/Brazil/brazil_municipalities_population.csv

Target:  BigQuery `daysupply.facilities`

Join gotchas handled:
  1. CNES codes: strip leading zeros on both sides
  2. IBGE codes: population file is 7-digit, CNES is 6-digit (truncate check digit)
  3. Brazilian decimals: comma as decimal separator — checked
  4. Encoding: cnes_estabelecimentos is latin-1
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

DATA_DIR = Path(__file__).resolve().parent.parent / "Data" / "Brazil"
ESTAB_CSV = DATA_DIR / "cnes_estabelecimentos.csv"
COORD_CSV = DATA_DIR / "cnes_coord.csv"
POP_CSV = DATA_DIR / "brazil_municipalities_population.csv"

# Demo municipalities (from §5)
DEMO_MUNICIPALITIES = os.getenv(
    "DEMO_MUNICIPALITIES_BR",
    "Conselheiro Lafaiete,Pará de Minas",
).split(",")


# ---------------------------------------------------------------------------
# Population lookup
# ---------------------------------------------------------------------------
def _load_population_lookup() -> dict:
    """Return {ibge_6digit -> population} for year 2022."""
    df = pd.read_csv(POP_CSV)
    df_2022 = df[df["year"] == 2022].copy()
    print(f"  Population rows (2022): {len(df_2022):,}")

    # Truncate 7-digit IBGE to 6 digits (drop check digit)
    df_2022["ibge_6"] = df_2022["id_municipality"].astype(str).str[:6]
    return dict(zip(df_2022["ibge_6"], df_2022["population"]))


# ---------------------------------------------------------------------------
# Main loader
# ---------------------------------------------------------------------------
def load_brazil_facilities(dry_run: bool = False) -> pd.DataFrame:
    """Parse, join, transform, and (optionally) upload Brazilian facility data."""

    # --- 1. Load establishments ---
    print(f"Reading {ESTAB_CSV} ...")
    estab = pd.read_csv(ESTAB_CSV, sep=";", encoding="latin-1", low_memory=False)
    print(f"  Raw rows: {len(estab):,}")

    # Filter: active primary care (TP_UNIDADE 1=Posto de Saúde, 2=Centro de Saúde/UBS)
    mask = (estab["TP_UNIDADE"].isin([1, 2])) & (estab["CO_MOTIVO_DESAB"].isna())
    primary = estab[mask].copy()
    print(f"  After primary-care filter: {len(primary):,}")
    assert len(primary) > 50_000, f"Expected 50k+ rows, got {len(primary)}"

    # --- 2. Join coordinates ---
    print(f"Reading {COORD_CSV} ...")
    coord = pd.read_csv(COORD_CSV)
    print(f"  Coord rows: {len(coord):,}")

    # Strip leading zeros on CNES codes for join (gotcha #1)
    primary["cnes_key"] = primary["CO_CNES"].astype(str).str.lstrip("0")
    coord["cnes_key"] = coord["co_cnes"].astype(str).str.lstrip("0")

    # Keep only needed coord columns, deduplicate
    coord_slim = coord[["cnes_key", "municipio", "uf", "lat", "long"]].drop_duplicates(
        subset="cnes_key"
    )

    merged = primary.merge(coord_slim, on="cnes_key", how="left")
    print(f"  After coord join: {len(merged):,}")
    assert len(merged) == len(primary), (
        f"Join changed row count: {len(primary)} -> {len(merged)}"
    )

    # --- 3. Population lookup ---
    pop_lookup = _load_population_lookup()

    # IBGE 6-digit key (gotcha #2 — already 6-digit in CNES)
    merged["ibge_6"] = merged["CO_IBGE"].astype(str).str[:6]
    merged["population"] = merged["ibge_6"].map(pop_lookup)

    pop_hit = merged["population"].notna().sum()
    print(f"  Population matched: {pop_hit:,} / {len(merged):,}")

    # --- 4. Handle decimal separators in coords (gotcha #3) ---
    # Check if lat/long use comma decimals
    for col in ["lat", "long", "NU_LATITUDE", "NU_LONGITUDE"]:
        if col in merged.columns:
            if merged[col].dtype == object:
                merged[col] = merged[col].astype(str).str.replace(",", ".", regex=False)
            merged[col] = pd.to_numeric(merged[col], errors="coerce")

    # Prefer coord file lat/long, fall back to establishment file
    merged["final_lat"] = merged["lat"].fillna(merged.get("NU_LATITUDE"))
    merged["final_long"] = merged["long"].fillna(merged.get("NU_LONGITUDE"))

    # --- 5. Build output ---
    out = pd.DataFrame()
    out["facility_id"] = "BR-" + merged["cnes_key"]
    out["country_code"] = "BR"
    out["name"] = merged["NO_FANTASIA"].fillna("Unknown")
    out["admin_l1"] = merged["uf"].fillna("")
    out["admin_l2"] = merged["municipio"].fillna("")
    out["admin_l3"] = None  # Brazil doesn't have L3
    out["facility_type"] = merged["TP_UNIDADE"].map(
        {1: "Posto de Saúde", 2: "Centro de Saúde/UBS"}
    ).fillna("Unknown")
    out["latitude"] = merged["final_lat"]
    out["longitude"] = merged["final_long"]
    out["population_served"] = merged["population"].astype("Int64")

    # Demo flag
    out["is_demo_facility"] = out["admin_l2"].isin(DEMO_MUNICIPALITIES)
    demo_count = out["is_demo_facility"].sum()
    print(f"  Demo facilities (Brazil): {demo_count}")

    # Stats
    null_coords = out[out["latitude"].isna() | out["longitude"].isna()]
    print(f"  Missing coordinates: {len(null_coords)}")

    print(f"  Final rows: {len(out):,}")
    assert len(out) == len(primary), "Row count mismatch after transform"

    if dry_run:
        print("\n[DRY RUN] Not uploading to BigQuery.")
        print(out[out["is_demo_facility"]].head(5).to_string())
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
    job.result()

    table = client.get_table(FULL_TABLE)
    print(f"  BigQuery row count (total table): {table.num_rows:,}")

    return out


# ---------------------------------------------------------------------------
if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    load_brazil_facilities(dry_run=dry)
