"""Load sanctioned, in-position and vacant staffing into `daysupply.staffing`.

Source: **Rural Health Statistics 2021-22**, manpower as on **31 March 2022**,
extracted from the published PDF by `ingestion/extract_rhs_2122.py` into
`Data/India/*_2021-22.csv`. Every file shares one schema — State/UT,
Required [R], Sanctioned [S], In Position [P], Vacant [S-P], Shortfall [R-P] —
for 36 states plus an All India row.

**The vacancy rates are real, and they are the point.** A post that is vacant
cannot be attended, so the vacancy rate from this data sets the ceiling on
staffing before anything else is said about it. Nationally as on 31 March 2022,
vacancy being the source's own definition (state-wise vacant posts summed with
surplus states ignored, over sanctioned):

| Cadre | Sanctioned | In position | Vacant |
|---|---|---|---|
| Doctor (allopathic), PHC | 39,669 | 30,640 | 23.8% |
| Nursing staff, PHC | 45,310 | 36,079 | 23.8% |
| Nursing staff, CHC | 54,698 | 43,854 | 22.3% |
| Pharmacist, PHC | 24,906 | 19,359 | 23.2% |
| Pharmacist, CHC | 9,160 | 7,776 | 18.8% |
| Health assistant [M+F], PHC | 17,796 | 11,329 | 37.0% |

An earlier draft of this table derived "sanctioned" as in-position plus vacant,
which overstates it wherever a state is in surplus or reports no sanctioned
figure; four of its six rows were wrong. These are the summed sanctioned
columns, which `extract_rhs_2122.py` checks against each table's All India
row. The run summary below prints a second rate — sanctioned minus in-position
over all states — which nets surplus against deficit and reads lower.

Pharmacists, PHC and CHC together, are now sanctioned **above** requirement
(34,066 against 30,415). The 2017 edition had them below it (29,315 against
31,274), which the pitch cited; that claim does not survive the refresh.

Three things to know before using it.

**Granularity is state-level, not facility-level**, exactly like
`population_served`. Per-facility sanctioned strength is a state x cadre
average and is an assumption, not a measurement. `vacancy_rate` therefore takes
one distinct value per state and cadre, which is why no figure derived from it
may be reported per district or per facility. See `Data/README.md`.

**Denominators no longer differ between files.** The 2017 edition published
Nursing and Pharmacist as PHC *and* CHC combined, so those two had to be
divided by PHCs plus CHCs; dividing them by PHCs alone overstated per-PHC
staffing by about 18%. The 2021-22 edition publishes PHC and CHC separately,
so every row here carries exactly one facility type and the hazard is gone.

**Health assistants are one cadre now.** The 2017 edition split them male and
female (46.0% and 34.4% vacant); 2021-22 publishes "Health Assistant at PHCs"
combined at 37.0%. The split is not carried forward from the older edition,
because mixing vintages inside one table to preserve a headline figure is worse
than losing the figure. Male and female health assistants remain distinct
*items* for voice capture — what a worker can report is a different question
from what the establishment sanctions.

**Vintage.** A newer edition exists and has been obtained: "Health Dynamics
of India (Infrastructure & Human Resources) 2023-24", as on 31 March 2024,
saved as Data/India/health-dynamics-2023-24.pdf. It is not used: its tables
were converted to vector outlines when the PDF was produced. Every page carries
one real text object, the running header, and tens of thousands of drawn paths,
so no parser can read the numbers; only rendering plus OCR or hand
transcription could. On 2026-09-15 the decision was to stay on 2021-22 rather
than transcribe. The 2022-23 edition was never located in a downloadable form.
The
source year is carried on every row so nothing can quote this as current.
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
# The year the manpower position was taken, not the edition label: RHS 2021-22
# reports as on 31 March 2022.
SOURCE_YEAR = 2022

# file -> (cadre, which facility types the posts belong to)
#
# Every entry now carries exactly one facility type. Nursing and Pharmacist
# appear twice, once per type, because the source publishes them separately —
# which is what removes the combined-denominator hazard the 2017 loader had to
# warn about.
FILES: dict[str, tuple[str, tuple[str, ...]]] = {
    "allo-doc-PHCS_2021-22": ("Doctor (allopathic)", ("phc",)),
    "nursing-staff-PHCS_2021-22": ("Nursing staff", ("phc",)),
    "nursing-staff-CHCS_2021-22": ("Nursing staff", ("chc",)),
    "pharmacists-PHCS_2021-22": ("Pharmacist", ("phc",)),
    "pharmacists-CHCS_2021-22": ("Pharmacist", ("chc",)),
    "assistant-PHCS_2021-22": ("Health assistant", ("phc",)),
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
        print(f"  {stem:32s} {len(df):>3} states, "
              f"cadre={cadre} ({'+'.join(types)})")
    return pd.DataFrame(records)


def run() -> None:
    print("Reading Rural Health Statistics 2021-22 staffing files "
          "(as on 31 March 2022) ...")
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
