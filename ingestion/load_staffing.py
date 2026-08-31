"""Load sanctioned, in-position and vacant staffing into `daysupply.staffing`.

Source: Rural Health Statistics 2017, `Data/India/*_2017.csv`. Every file shares
one schema — State/UT, Required [R], Sanctioned [S], In Position [P],
Vacant [S-P], Shortfall [R-P] — for 36 states plus an All India row.

**The vacancy rates are real, and they are the point.** A post that is vacant
cannot be attended, so the vacancy rate from this data sets the ceiling on
attendance before any behaviour is modelled. Nationally in 2017:

| Cadre | Sanctioned | In position | Vacant |
|---|---|---|---|
| Doctor (allopathic), PHC | 33,968 | 27,124 | 20.1% |
| Nursing staff, PHC+CHC | 77,956 | 70,738 | 9.3% |
| Pharmacist, PHC+CHC | 29,315 | 25,193 | 14.1% |
| Health assistant (male), PHC | 22,753 | 12,288 | 46.0% |
| Health assistant (female), PHC | 21,748 | 14,267 | 34.4% |

Two things to know before using it.

**Granularity is state-level, not facility-level**, exactly like
`population_served`. Per-facility sanctioned strength is a state x cadre
average and is an assumption, not a measurement. See `Data/README.md`.

**Denominators differ between files.** `allo-doc-PHCS` and the two
`assistant-*-PHCS` files count PHC posts, so they divide by PHCs. But
`nursing-staff-PHCS-CHCS` and `pharmacists-PHCS-CHCS` are PHC **and** CHC
combined, so they must divide by PHCs plus CHCs. Dividing those two by PHCs
alone would overstate per-PHC staffing by about 18%.

**Vintage.** This is the 2017 edition. MoHFW now publishes the same series as
"Health Dynamics of India (Infrastructure and Human Resources)". The 2017 data
is internally consistent and adequate for setting a vacancy baseline; it should
be refreshed before any real deployment, and the vintage is carried on every
row so nothing can quote it as current.
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
TABLE = f"{PROJECT}.{DATASET}.staffing"
FACILITIES = f"`{PROJECT}.{DATASET}.facilities`"

DATA_DIR = Path(__file__).resolve().parent.parent / "Data" / "India"
SOURCE_YEAR = 2017

# file -> (cadre, which facility types the posts belong to)
FILES: dict[str, tuple[str, tuple[str, ...]]] = {
    "allo-doc-PHCS_2017": ("Doctor (allopathic)", ("phc",)),
    "nursing-staff-PHCS-CHCS_2017": ("Nursing staff", ("phc", "chc")),
    "pharmacists-PHCS-CHCS_2017": ("Pharmacist", ("phc", "chc")),
    "assistant-male-PHCS_2017": ("Health assistant (male)", ("phc",)),
    "assistant-female-PHCS_2017": ("Health assistant (female)", ("phc",)),
}

SCHEMA = [
    bigquery.SchemaField("state", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("cadre", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("applies_to_facility_types", "STRING", mode="REPEATED"),
    bigquery.SchemaField("required", "INT64"),
    bigquery.SchemaField("sanctioned", "INT64"),
    bigquery.SchemaField("in_position", "INT64"),
    bigquery.SchemaField("vacant", "INT64"),
    bigquery.SchemaField("vacancy_rate", "FLOAT64"),
    bigquery.SchemaField("source_year", "INT64", mode="REQUIRED"),
    bigquery.SchemaField("source_file", "STRING", mode="REQUIRED"),
]


def _num(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def build() -> pd.DataFrame:
    records: list[dict] = []
    for stem, (cadre, types) in FILES.items():
        path = DATA_DIR / f"{stem}.csv"
        if not path.exists():
            raise SystemExit(f"Missing staffing file: {path}")
        df = pd.read_csv(path)
        state = df["State/ UT"].astype(str).str.strip()
        df = df[~state.str.lower().str.contains("all india")]
        state = state[df.index]

        required = _num(df["Required - [R]"])
        sanctioned = _num(df["Sanctioned - [S]"])
        in_position = _num(df["In Position - [P]"])

        for i in df.index:
            s, p = sanctioned.get(i), in_position.get(i)
            vacant = (s - p) if pd.notna(s) and pd.notna(p) else None
            rate = (vacant / s) if vacant is not None and s and s > 0 else None
            records.append({
                "state": state[i],
                "cadre": cadre,
                "applies_to_facility_types": list(types),
                "required": None if pd.isna(required.get(i)) else int(required[i]),
                "sanctioned": None if pd.isna(s) else int(s),
                "in_position": None if pd.isna(p) else int(p),
                "vacant": None if vacant is None else int(vacant),
                "vacancy_rate": None if rate is None else round(float(rate), 4),
                "source_year": SOURCE_YEAR,
                "source_file": f"{stem}.csv",
            })
        print(f"  {stem:32s} {len(df):>3} states, cadre={cadre}")
    return pd.DataFrame(records)


def run() -> None:
    print("Reading Rural Health Statistics 2017 staffing files ...")
    frame = build()

    client = bigquery.Client(project=PROJECT, location=LOCATION)
    client.load_table_from_dataframe(
        frame, TABLE,
        job_config=bigquery.LoadJobConfig(
            schema=SCHEMA,
            write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
        ),
    ).result()

    print(f"\nLoaded {len(frame):,} rows to {TABLE}")
    for r in client.query(f"""
        SELECT cadre,
               COUNT(*) AS states,
               COUNTIF(sanctioned IS NULL) AS missing_sanctioned,
               SUM(sanctioned) AS sanctioned,
               SUM(in_position) AS in_position,
               ROUND(SAFE_DIVIDE(SUM(sanctioned) - SUM(in_position),
                                 SUM(sanctioned)) * 100, 1) AS vacancy_pct
        FROM `{TABLE}` GROUP BY cadre ORDER BY cadre
    """).result():
        print(f"  {r.cadre:28s} {r.states:>3} states  "
              f"sanctioned {r.sanctioned:>7,}  in post {r.in_position:>7,}  "
              f"vacancy {r.vacancy_pct:>5}%  ({r.missing_sanctioned} missing)")

    total = next(iter(client.query(
        f"SELECT COUNT(*) AS n FROM `{TABLE}`").result())).n
    if total != len(frame):
        raise SystemExit(f"Loaded {total} rows, built {len(frame)}")

    # A negative vacancy is real, not a parse error: contractual NHM staff can
    # put more people in post than there are sanctioned regular posts.
    over = list(client.query(f"""
        SELECT state, cadre, sanctioned, in_position
        FROM `{TABLE}` WHERE in_position > sanctioned
        ORDER BY in_position - sanctioned DESC LIMIT 5
    """).result())
    if over:
        print(f"\n  {len(over)} state-cadre rows have more staff in post than "
              "sanctioned posts (contractual NHM staff over and above "
              "sanctioned strength) — kept as reported:")
        for r in over:
            print(f"    {r.state:20s} {r.cadre:24s} "
                  f"{r.in_position:,} in post vs {r.sanctioned:,} sanctioned")

    print("\nOK — vacancy rates are real and set the attendance ceiling.")


if __name__ == "__main__":
    try:
        run()
    except Exception as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        sys.exit(1)
