"""Generate `stock_events` for the forecast facilities.

Every number here is anchored to something real wherever a real anchor exists,
and where one does not, this file says so rather than inventing a plausible
curve.

**Real inputs**

* *Which facilities* — the 200 PHCs flagged `is_forecast_facility`, all real
  rows from the government facility master.
* *Demand scale* — each item's `demand_driver` names an HMIS 2019-20 indicator.
  A facility's baseline load is that district's real reported patient volume for
  that indicator, divided by the real number of PHCs in the district. District
  volumes vary 12x to 1750x across Telangana, so this carries genuine
  geographic variation.
* *Seasonality* — the month-by-month shape of the same real HMIS series. Malaria
  peaks in the monsoon in the districts where it really peaks.

**Generated inputs, and why**

* *Within-district facility variation* — `population_served` is a state x
  facility-type average (see `Data/README.md` §2), so it is identical for every
  Telangana PHC and carries no within-state information. There is no published
  per-facility catchment. A deterministic log-normal multiplier per facility
  stands in for unobservable catchment differences.
* *Day-of-week shape* — no HMIS data is daily. Weekday/weekend pattern applied
  from standard PHC operating practice.
* *Daily noise* — Poisson around the expected value.
* *Units per patient* — how many tablets one patient consumes. Clinical dosing
  convention, not data.

**COVID handling.** HMIS 2019-20 runs April 2019 to March 2020. India's national
lockdown began 25 March 2020, so the March figure is a service-disruption
artefact, not seasonality. April 2019 - February 2020 are used as reported;
**March is replaced by the April-December mean.** Dropping April-December's tail
entirely would have discarded two clean months (January, February 2020) for no
reason — the disruption is confined to March.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import date

import numpy as np
import pandas as pd
from google.cloud import bigquery

PROJECT = os.getenv("GCP_PROJECT", "daysupply")
DATASET = os.getenv("BQ_DATASET", "daysupply")
LOCATION = os.getenv("BQ_LOCATION", "asia-south1")

FACILITIES = f"`{PROJECT}.{DATASET}.facilities`"
ITEMS = f"`{PROJECT}.{DATASET}.items`"
DEMAND_REF = f"`{PROJECT}.{DATASET}.demand_reference`"
STOCK_EVENTS = f"{PROJECT}.{DATASET}.stock_events"

SEED = 20260830
DAYS = 365
END_DATE = date(2026, 8, 29)

MONTH_NAMES = ["January", "February", "March", "April", "May", "June", "July",
               "August", "September", "October", "November", "December"]
# The month whose reported value is a lockdown artefact rather than seasonality.
COVID_MONTH = "March"
CLEAN_BASELINE_MONTHS = MONTH_NAMES[3:12]  # April - December

# Units one patient consumes per encounter. Clinical dosing convention.
UNITS_PER_PATIENT_BY_UNIT = {
    "tablet": 30.0,    # one month of a chronic oral medicine
    "capsule": 15.0,
    "sachet": 4.0,
    "vial": 1.0,
    "bottle": 1.0,
    "tube": 1.0,
    "inhaler": 1.0,
    "unit": 1.0,
    "patch": 1.0,
}
# Acute courses are shorter than a chronic month's supply.
ACUTE_DRIVERS = {"Malaria", "Childhood Diseases", "Inpatient counts"}
ACUTE_UNITS_PER_PATIENT = 10.0

# Monday..Sunday. PHC outpatient load is heaviest early in the week and
# minimal on Sunday.
DOW_FACTORS = np.array([1.25, 1.15, 1.05, 1.05, 1.00, 0.75, 0.20])

# Resupply. PHCs indent from the district warehouse on a monthly cycle, so
# `received` events are emitted alongside `dispensed` ones and on-hand is a
# real ledger computation — SUM(received) - SUM(dispensed) — rather than a
# number reconstructed after the fact.
#
# The indent is a **top-up to a target stock level**, which is how public
# health supply chains actually order: the facility asks for the difference
# between what it holds and what it should hold. Ordering a fixed multiple of
# demand instead would compound, and every facility would drift into permanent
# surplus.
INDENT_CYCLE_DAYS = 30
TARGET_COVER_DAYS = 40          # one cycle plus ten days of buffer
# Engineered demo scenarios, applied to the most recent cycles only. These are
# supply-side failures: the facility orders correctly and the warehouse under-
# or over-delivers, which is the failure mode this product exists to catch.
DEFICIT_FILL_RATE = 0.35        # chronically short-supplied -> runs out
SURPLUS_FILL_RATE = 2.30        # over-supplied -> becomes the donor
SCENARIO_CYCLES = 3

# Baseline daily units at an average PHC for items with no HMIS driver.
FLAT_BASE_DAILY = {
    "PARACETAMOL": 140.0,
    "IBUPROFEN": 60.0,
    "FERROUS-SALT-A-FOLIC-ACID-B": 110.0,
    "OXYTOCIN": 4.0,
    "MAGNESIUM-SULPHATE": 1.5,
    "SALBUTAMOL": 12.0,
}

SCHEMA = [
    bigquery.SchemaField("event_id", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("facility_id", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("item_id", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("event_type", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("quantity", "INT64", mode="REQUIRED"),
    bigquery.SchemaField("event_ts", "TIMESTAMP", mode="REQUIRED"),
    bigquery.SchemaField("source", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("confidence", "FLOAT64"),
    bigquery.SchemaField("raw_transcript", "STRING"),
]


# ---------------------------------------------------------------------------
# Real inputs
# ---------------------------------------------------------------------------
def fetch_inputs(client: bigquery.Client):
    facilities = client.query(f"""
        SELECT facility_id, admin_l2 AS district, population_served
        FROM {FACILITIES}
        WHERE is_forecast_facility
        ORDER BY facility_id
    """).to_dataframe()

    items = client.query(f"""
        SELECT item_id, display_name, unit, demand_driver, ven_class
        FROM {ITEMS}
        WHERE is_forecast_item
        ORDER BY item_id
    """).to_dataframe()

    # PHCs per district — the real denominator turning a district's reported
    # patient volume into a per-facility load.
    phc_counts = client.query(f"""
        SELECT UPPER(TRIM(admin_l2)) AS district_key, COUNT(*) AS phcs
        FROM {FACILITIES}
        WHERE country_code = 'IN' AND admin_l1 = 'Telangana'
          AND facility_type = 'phc'
        GROUP BY district_key
    """).to_dataframe()

    # Real HMIS monthly series, with the Apr-Dec baseline used for the
    # seasonal multiplier.
    hmis = client.query(f"""
        WITH baseline AS (
          SELECT UPPER(TRIM(admin_l2)) AS district_key, indicator,
                 AVG(value) AS baseline
          FROM {DEMAND_REF}
          WHERE month IN UNNEST(@clean_months)
          GROUP BY district_key, indicator
        )
        SELECT
          UPPER(TRIM(d.admin_l2)) AS district_key,
          d.indicator,
          d.month,
          d.value,
          b.baseline
        FROM {DEMAND_REF} d
        JOIN baseline b
          ON UPPER(TRIM(d.admin_l2)) = b.district_key
         AND d.indicator = b.indicator
    """, job_config=bigquery.QueryJobConfig(query_parameters=[
        bigquery.ArrayQueryParameter(
            "clean_months", "STRING", CLEAN_BASELINE_MONTHS)
    ])).to_dataframe()

    return facilities, items, phc_counts, hmis


def build_seasonality(hmis: pd.DataFrame) -> dict:
    """(district, indicator) -> 12 monthly multipliers, index 0 = January."""
    table: dict[tuple[str, str], np.ndarray] = {}
    for (district, indicator), grp in hmis.groupby(["district_key", "indicator"]):
        baseline = grp["baseline"].iloc[0]
        multipliers = np.ones(12)
        if baseline and baseline > 0:
            by_month = dict(zip(grp["month"], grp["value"]))
            for idx, month in enumerate(MONTH_NAMES):
                if month == COVID_MONTH:
                    continue  # lockdown artefact — hold at baseline
                value = by_month.get(month)
                if value is not None and not pd.isna(value):
                    multipliers[idx] = value / baseline
        # Keep the shape sane if a district reports erratically.
        table[(district, indicator)] = np.clip(multipliers, 0.25, 4.0)
    return table


def build_scale(hmis: pd.DataFrame, phc_counts: pd.DataFrame) -> dict:
    """(district, indicator) -> real monthly patients per PHC."""
    phcs = dict(zip(phc_counts["district_key"], phc_counts["phcs"]))
    scale: dict[tuple[str, str], float] = {}
    for (district, indicator), grp in hmis.groupby(["district_key", "indicator"]):
        baseline = grp["baseline"].iloc[0]
        count = phcs.get(district, 0)
        if baseline and count:
            scale[(district, indicator)] = float(baseline) / count
    return scale


# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------
def generate(dry_run: bool = False) -> None:
    client = bigquery.Client(project=PROJECT, location=LOCATION)

    print("Fetching real inputs ...")
    facilities, items, phc_counts, hmis = fetch_inputs(client)
    print(f"  forecast facilities: {len(facilities)}")
    print(f"  forecast items:      {len(items)}")
    print(f"  HMIS rows:           {len(hmis)}")

    if facilities.empty or items.empty:
        raise SystemExit("No forecast facilities or items — run the setup steps")

    seasonality = build_seasonality(hmis)
    scale = build_scale(hmis, phc_counts)

    # Items sharing a driver split that driver's patients between them.
    driver_counts = items["demand_driver"].value_counts().to_dict()

    rng = np.random.default_rng(SEED)
    dates = pd.date_range(end=END_DATE, periods=DAYS, freq="D")
    month_index = dates.month.values - 1
    dow_index = dates.dayofweek.values
    dow = DOW_FACTORS[dow_index]
    days_in_month = dates.days_in_month.values

    # Deterministic per-facility catchment multiplier. Generated — see module
    # docstring. Facilities are ordered by facility_id and the seed is fixed,
    # so a given facility gets the same multiplier on every run.
    size_rng = np.random.default_rng(SEED + 1)
    facility_multiplier = np.exp(size_rng.normal(0, 0.35, len(facilities)))

    deficit_targets, surplus_targets = _pick_scenarios(facilities)
    scenario = {fid: "deficit" for fid in deficit_targets}
    scenario.update({fid: "surplus" for fid in surplus_targets})
    print(f"  deficit facilities: {', '.join(deficit_targets)}")
    print(f"  donor facilities:   {', '.join(surplus_targets)}")

    print(f"\nGenerating {len(facilities)} facilities x {len(items)} items "
          f"x {DAYS} days = "
          f"{len(facilities) * len(items) * DAYS:,} rows ...")

    chunks: list[pd.DataFrame] = []
    total_rows = 0
    unmet_units = 0
    unmatched: set[tuple[str, str]] = set()

    for f_idx, facility in facilities.reset_index(drop=True).iterrows():
        district_key = str(facility["district"]).upper().strip()
        fac_mult = facility_multiplier[f_idx]

        for _, item in items.iterrows():
            driver = item["demand_driver"]
            unit = item["unit"]

            if driver and not pd.isna(driver):
                key = (district_key, driver)
                monthly_patients = scale.get(key)
                season = seasonality.get(key)
                if monthly_patients is None or season is None:
                    unmatched.add(key)
                    continue
                share = 1.0 / driver_counts.get(driver, 1)
                per_patient = (
                    ACUTE_UNITS_PER_PATIENT if driver in ACUTE_DRIVERS
                    else UNITS_PER_PATIENT_BY_UNIT.get(unit, 1.0)
                )
                base_daily = (
                    monthly_patients * share * per_patient / days_in_month
                )
                seasonal = season[month_index]
            else:
                # Flat baseline — no HMIS indicator counts these patients.
                base_daily = np.full(
                    DAYS, FLAT_BASE_DAILY.get(item["item_id"], 20.0)
                )
                seasonal = np.ones(DAYS)

            expected = base_daily * seasonal * dow * fac_mult
            expected = np.clip(expected, 0.0, None)
            demand = rng.poisson(expected)

            fid = facility["facility_id"]
            iid = item["item_id"]

            # Run the ledger: receive on the indent cycle, dispense what is
            # actually on the shelf. A facility that runs out cannot dispense.
            dispensed, receipts, unmet = _run_ledger(
                demand, scenario.get(fid, "normal")
            )
            unmet_units += unmet

            keep = dispensed > 0
            if keep.any():
                chunks.append(pd.DataFrame({
                    "event_id": [
                        f"seed-d-{fid}-{iid}-{d:%Y%m%d}" for d in dates[keep]
                    ],
                    "facility_id": fid,
                    "item_id": iid,
                    "event_type": "dispensed",
                    "quantity": dispensed[keep].astype("int64"),
                    "event_ts": dates[keep],
                    "source": "seed",
                    "confidence": 1.0,
                    "raw_transcript": None,
                }))
                total_rows += int(keep.sum())

            if receipts:
                days = [dates[i] for i, _ in receipts]
                chunks.append(pd.DataFrame({
                    "event_id": [
                        f"seed-r-{fid}-{iid}-{d:%Y%m%d}" for d in days
                    ],
                    "facility_id": fid,
                    "item_id": iid,
                    "event_type": "received",
                    "quantity": np.array([q for _, q in receipts],
                                         dtype="int64"),
                    "event_ts": pd.DatetimeIndex(days),
                    "source": "seed",
                    "confidence": 1.0,
                    "raw_transcript": None,
                }))
                total_rows += len(receipts)

        if (f_idx + 1) % 50 == 0:
            print(f"  {f_idx + 1}/{len(facilities)} facilities, "
                  f"{total_rows:,} rows")

    if unmatched:
        raise SystemExit(
            "Missing HMIS series for: " + ", ".join(sorted(
                f"{d}/{i}" for d, i in unmatched)[:10])
        )

    frame = pd.concat(chunks, ignore_index=True)
    frame["event_ts"] = pd.to_datetime(frame["event_ts"], utc=True)
    print(f"\nBuilt {len(frame):,} rows")
    print(f"  quantity: min={frame['quantity'].min()}, "
          f"mean={frame['quantity'].mean():.1f}, "
          f"max={frame['quantity'].max()}")
    print(f"  series:   {frame.groupby(['facility_id','item_id']).ngroups:,}")
    served = int(frame.loc[frame["event_type"] == "dispensed", "quantity"].sum())
    print(f"  unmet demand: {unmet_units:,} units "
          f"({unmet_units / max(served + unmet_units, 1):.1%} of demand) — "
          "patients turned away because stock had run out")

    if dry_run:
        print("\n[DRY RUN] Nothing written to BigQuery.")
        print(frame.head(5).to_string())
        return

    _write(client, frame)


def _pick_scenarios(facilities: pd.DataFrame):
    """Choose facilities to push into deficit, each with a same-district donor.

    Pairing inside a district guarantees the donor is close enough to be a
    legitimate transfer candidate, so the demo always has a recommendation.
    """
    ordered = facilities.sort_values("facility_id").reset_index(drop=True)
    deficit, surplus = [], []
    for _, grp in ordered.groupby("district"):
        if len(grp) >= 2 and len(deficit) < 3:
            deficit.append(grp.iloc[0]["facility_id"])
            surplus.append(grp.iloc[1]["facility_id"])
    return deficit, surplus


def _run_ledger(demand: np.ndarray, mode: str):
    """Walk one facility-item ledger through a year of indent cycles.

    Returns `(dispensed, receipts, unmet)`:

    * `dispensed` — units actually handed over, which is demand capped by what
      is on the shelf. **A facility that has run out dispenses nothing**, so
      the ledger can never go negative and a stock-out shows up as unmet
      demand rather than as impossible negative stock.
    * `receipts` — `(day_index, quantity)` per indent.
    * `unmet` — units of demand that could not be served. This is the number
      the whole product exists to drive down.

    The indent tops stock back up to `TARGET_COVER_DAYS`, planned against the
    previous cycle's actual consumption — the information a real pharmacist
    has. The warehouse then fills that order in full, short, or over.
    """
    days = len(demand)
    dispensed = np.zeros(days, dtype=np.int64)
    receipts: list[tuple[int, int]] = []
    cycle_starts = list(range(0, days, INDENT_CYCLE_DAYS))
    total_cycles = len(cycle_starts)
    stock = 0.0
    unmet = 0

    for n, start in enumerate(cycle_starts):
        end = min(start + INDENT_CYCLE_DAYS, days)
        window = demand[start:end]
        if window.size == 0:
            continue

        # Plan against last cycle's actual consumption; the first indent has
        # no history and uses the cycle it is about to cover.
        if n == 0:
            rate = float(window.mean())
        else:
            previous = dispensed[max(0, start - INDENT_CYCLE_DAYS):start]
            rate = float(previous.mean()) if previous.size else float(window.mean())

        ordered = max(0.0, rate * TARGET_COVER_DAYS - stock)

        fill_rate = 1.0
        if n >= total_cycles - SCENARIO_CYCLES:
            if mode == "deficit":
                fill_rate = DEFICIT_FILL_RATE
            elif mode == "surplus":
                fill_rate = SURPLUS_FILL_RATE

        quantity = int(round(ordered * fill_rate))
        if quantity > 0:
            receipts.append((start, quantity))
            stock += quantity

        # Serve the cycle day by day, capped by stock on the shelf.
        # `available` is what remains before each day's demand is met.
        consumed_before = np.cumsum(window) - window
        available = np.clip(stock - consumed_before, 0, None)
        served = np.minimum(window, available).astype(np.int64)
        dispensed[start:end] = served
        unmet += int(window.sum() - served.sum())
        stock -= float(served.sum())

    return dispensed, receipts, unmet


def _write(client: bigquery.Client, frame: pd.DataFrame) -> None:
    print(f"\nWriting to {STOCK_EVENTS} "
          "(partitioned by DATE(event_ts), clustered by facility_id) ...")
    job = client.load_table_from_dataframe(
        frame,
        STOCK_EVENTS,
        job_config=bigquery.LoadJobConfig(
            schema=SCHEMA,
            write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
            time_partitioning=bigquery.TimePartitioning(
                type_=bigquery.TimePartitioningType.DAY, field="event_ts"
            ),
            clustering_fields=["facility_id"],
        ),
    )
    job.result()

    table = client.get_table(STOCK_EVENTS)
    print(f"  rows:         {table.num_rows:,}")
    print(f"  partitioning: {table.time_partitioning.field}")
    print(f"  clustering:   {table.clustering_fields}")

    if table.num_rows != len(frame):
        raise SystemExit(
            f"ROW COUNT MISMATCH: built {len(frame):,}, "
            f"BigQuery has {table.num_rows:,}"
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    try:
        generate(dry_run=args.dry_run)
    except Exception as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        raise
