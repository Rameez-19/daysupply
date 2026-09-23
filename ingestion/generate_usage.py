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
* *Units per driver event* — how much of a medicine one unit of its driver
  consumes: a 14-day zinc course is 14 tablets, one delivery needs about one
  ampoule of oxytocin. Clinical dosing convention combined with the share of
  that driver's patients who receive this particular drug. Stated per item in
  `ingestion/build_items.py` with its reasoning.
* *PHC share of district activity* — the generator divides a district total by
  the number of PHCs in it, so it needs to know how much of that activity a PHC
  actually sees. Sub-centres do much of antenatal care; district hospitals take
  most admissions. Per driver in `ingestion/hmis_drivers.py`.
* *Batch expiry* — no expiry data exists in any public Indian dataset. Each
  receipt is given a shelf life drawn from a fixed-seed distribution: most
  batches arrive with 12-24 months, **15% short-dated at 2-5 months**, and
  **4% "dumped" with 25-60 days** — what district warehouses really do when
  clearing their own near-expiry stock downward. Without that tail nothing can
  expire, FEFO has nothing to choose between, and waste avoided is always zero.

**Reporting behaviour.** A PHC is expected to submit a stock count every 30
days. Real programmes do not get 100% compliance, and evaluations of comparable
systems — South Africa's Stock Visibility System among them — document
compliance decaying a few months after rollout rather than staying flat. So
each facility is given a baseline compliance probability and a decay, and
`count` events appear only when it reports. The resulting
reporting-consistency score is therefore a real measurement over the ledger,
not an assumption: non-reporting is visible because the report is genuinely
absent.

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

from ingestion.hmis_drivers import phc_share

PROJECT = os.getenv("GCP_PROJECT", "daysupply")
DATASET = os.getenv("BQ_DATASET", "daysupply")
LOCATION = os.getenv("BQ_LOCATION", "asia-south1")

FACILITIES = f"`{PROJECT}.{DATASET}.facilities`"
ITEMS = f"`{PROJECT}.{DATASET}.items`"
DEMAND_REF = f"`{PROJECT}.{DATASET}.demand_reference`"
STOCK_EVENTS = f"{PROJECT}.{DATASET}.stock_events"
IMPACT_METRICS = f"{PROJECT}.{DATASET}.impact_metrics"

SEED = 20260830
DAYS = 365
END_DATE = date(2026, 8, 29)

MONTH_NAMES = ["January", "February", "March", "April", "May", "June", "July",
               "August", "September", "October", "November", "December"]
# The month whose reported value is a lockdown artefact rather than seasonality.
COVID_MONTH = "March"
CLEAN_BASELINE_MONTHS = MONTH_NAMES[3:12]  # April - December

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

# Warehouses do not fill every indent in full. Each facility gets a baseline
# reliability and each individual indent varies around it, which is why real
# essential-medicine availability sits near 45-51% rather than at 100%. Without
# this every facility would sit permanently above its reorder point and the
# alerting and redistribution logic would never be exercised by anything except
# the three engineered scenarios.
FILL_RELIABILITY = (0.68, 1.18)   # per-facility baseline, uniform
FILL_NOISE_SD = 0.14              # per-indent variation around it

# Batch shelf life at the point of receipt, in days.
SHELF_LIFE_NORMAL = (365, 730)     # 12-24 months
SHELF_LIFE_SHORT = (60, 150)       # 2-5 months
SHELF_LIFE_DUMPED = (25, 60)       # under two months
SHORT_DATED_SHARE = 0.15
# District warehouses clear their own near-expiry stock by pushing it down to
# facilities. It arrives with weeks of life, and a facility that cannot consume
# it in time writes it off. This tranche is why expiry waste exists at all, and
# why FEFO has something to choose between.
DUMPED_SHARE = 0.04

# Stock-count reporting. Compliance starts high and decays, which is the
# documented failure mode of these systems: the dashboard looks healthy for a
# few months and then quietly stops being fed.
REPORT_PERIOD_DAYS = 30
COMPLIANCE_START = (0.72, 0.99)    # per-facility baseline, uniform
COMPLIANCE_DECAY = (0.00, 0.055)   # probability lost per period

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
    # Only populated on `received` rows: the expiry of the batch that arrived.
    bigquery.SchemaField("expiry_date", "DATE"),
]


# ---------------------------------------------------------------------------
# Real inputs
# ---------------------------------------------------------------------------
RESOURCE_EVENTS = f"{PROJECT}.{DATASET}.resource_events"


def state_seed(state: str | None) -> int:
    """The random stream for a run.

    The original run draws every facility from one stream in facility_id
    order, so adding a facility anywhere in that order would change the draws
    for every facility after it. A state added later gets its own stream,
    offset by a stable hash of its name, so the original 200 stay bit-for-bit
    the same.
    """
    if not state:
        return SEED
    import zlib
    return SEED + 1_000_003 * (1 + zlib.crc32(state.encode("utf-8")) % 997)


# For a state added later only. The register lists 6 PHCs in Pratapgarh and 8
# in Siddharth Nagar against an Uttar Pradesh mean of 41 per district, so a
# district total divided by the register count gave one PHC about 3,000 iron
# tablets a day. A district listing fewer than this share of its state's mean
# is treated as under-counted in the register and its denominator is raised to
# the floor. The original five states keep their exact method so their figures
# stay reproducible; this is disclosed in Data/README.md.
PHC_FLOOR_SHARE = 0.5


def floor_phc_counts(phc_counts: pd.DataFrame, state: str) -> pd.DataFrame:
    out = phc_counts.copy()
    mask = out["state"] == state
    if not mask.any():
        return out
    floor = int(round(PHC_FLOOR_SHARE * out.loc[mask, "phcs"].mean()))
    raised = mask & (out["phcs"] < floor)
    for _, r in out[raised].iterrows():
        print(f"  {r['district_key']}: register lists {r['phcs']} PHCs, "
              f"denominator raised to {floor}")
    out.loc[raised, "phcs"] = floor
    return out


def fetch_inputs(client: bigquery.Client, state: str | None = None):
    only = "AND admin_l1 = @state" if state else ""
    facilities = client.query(f"""
        SELECT facility_id, admin_l1 AS state, admin_l2 AS district,
               UPPER(TRIM(admin_l2)) AS district_key, population_served
        FROM {FACILITIES}
        WHERE is_forecast_facility {only}
        ORDER BY facility_id
    """, job_config=bigquery.QueryJobConfig(query_parameters=(
        [bigquery.ScalarQueryParameter("state", "STRING", state)]
        if state else []))).to_dataframe()

    items = client.query(f"""
        SELECT item_id, display_name, unit, demand_driver, ven_class,
               units_per_driver_event
        FROM {ITEMS}
        WHERE is_forecast_item
        ORDER BY item_id
    """).to_dataframe()

    # PHCs per district — the real denominator turning a district's reported
    # patient volume into a per-facility load.
    phc_counts = client.query(f"""
        SELECT admin_l1 AS state, UPPER(TRIM(admin_l2)) AS district_key,
               COUNT(*) AS phcs
        FROM {FACILITIES}
        WHERE country_code = 'IN' AND facility_type = 'phc'
        GROUP BY state, district_key
    """).to_dataframe()

    # Real HMIS monthly series, with the Apr-Dec baseline used for the
    # seasonal multiplier.
    hmis = client.query(f"""
        WITH baseline AS (
          SELECT admin_l1 AS state, district_key, indicator,
                 AVG(value) AS baseline
          FROM {DEMAND_REF}
          WHERE month IN UNNEST(@clean_months)
          GROUP BY state, district_key, indicator
        )
        SELECT
          d.admin_l1 AS state,
          d.district_key,
          d.indicator,
          d.month,
          d.value,
          b.baseline
        FROM {DEMAND_REF} d
        JOIN baseline b
          ON d.admin_l1 = b.state
         AND d.district_key = b.district_key
         AND d.indicator = b.indicator
    """, job_config=bigquery.QueryJobConfig(query_parameters=[
        bigquery.ArrayQueryParameter(
            "clean_months", "STRING", CLEAN_BASELINE_MONTHS)
    ])).to_dataframe()

    return facilities, items, phc_counts, hmis


def build_seasonality(hmis: pd.DataFrame) -> dict:
    """(state, district, indicator) -> 12 monthly multipliers, Jan first."""
    table: dict[tuple[str, str, str], np.ndarray] = {}
    for (state, district, indicator), grp in hmis.groupby(
            ["state", "district_key", "indicator"]):
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
        table[(state, district, indicator)] = np.clip(multipliers, 0.25, 4.0)
    return table


def build_scale(hmis: pd.DataFrame, phc_counts: pd.DataFrame) -> dict:
    """(state, district, indicator) -> real monthly patients per PHC."""
    phcs = {
        (row.state, row.district_key): row.phcs
        for row in phc_counts.itertuples()
    }
    scale: dict[tuple[str, str, str], float] = {}
    for (state, district, indicator), grp in hmis.groupby(
            ["state", "district_key", "indicator"]):
        baseline = grp["baseline"].iloc[0]
        count = phcs.get((state, district), 0)
        if baseline and count:
            scale[(state, district, indicator)] = float(baseline) / count
    return scale


# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------
def generate(dry_run: bool = False, add_state: str | None = None) -> None:
    client = bigquery.Client(project=PROJECT, location=LOCATION)
    SEED = state_seed(add_state)  # noqa: N806 — shadows the module seed on purpose

    print("Fetching real inputs ...")
    facilities, items, phc_counts, hmis = fetch_inputs(client, add_state)
    print(f"  forecast facilities: {len(facilities)}")
    print(f"  forecast items:      {len(items)}")
    print(f"  HMIS rows:           {len(hmis)}")

    if facilities.empty or items.empty:
        raise SystemExit("No forecast facilities or items — run the setup steps")

    if add_state:
        phc_counts = floor_phc_counts(phc_counts, add_state)
    seasonality = build_seasonality(hmis)
    scale = build_scale(hmis, phc_counts)

    # Items sharing a driver split that driver's patients between them.

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

    # How reliably this facility's indents are filled by its warehouse.
    supply_rng = np.random.default_rng(SEED + 3)
    facility_reliability = supply_rng.uniform(*FILL_RELIABILITY,
                                              len(facilities))

    # Per-facility reporting behaviour, fixed by seed.
    report_rng = np.random.default_rng(SEED + 2)
    compliance_base = report_rng.uniform(*COMPLIANCE_START, len(facilities))
    compliance_decay = report_rng.uniform(*COMPLIANCE_DECAY, len(facilities))
    report_days = list(range(0, DAYS, REPORT_PERIOD_DAYS))
    report_draws = report_rng.random((len(facilities), len(report_days)))

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
    expired_units = 0
    fifo_expired_units = 0
    unmatched: set[tuple[str, str]] = set()

    for f_idx, facility in facilities.reset_index(drop=True).iterrows():
        district_key = str(facility["district_key"])
        state = str(facility["state"])
        fac_mult = facility_multiplier[f_idx]

        # Which periods this facility actually reported in.
        reported = [
            day_index
            for period, day_index in enumerate(report_days)
            if report_draws[f_idx, period] <
            max(0.05, compliance_base[f_idx] - compliance_decay[f_idx] * period)
        ]

        for _, item in items.iterrows():
            driver = item["demand_driver"]
            unit = item["unit"]

            if driver and not pd.isna(driver):
                key = (state, district_key, driver)
                monthly_events = scale.get(key)
                season = seasonality.get(key)
                if monthly_events is None or season is None:
                    unmatched.add(key)
                    continue
                # Units of this item consumed per unit of its driver, times the
                # share of the district's driver activity a PHC actually sees.
                rate = float(item["units_per_driver_event"] or 0.0)
                base_daily = (
                    monthly_events * phc_share(driver) * rate / days_in_month
                )
                seasonal = season[month_index]
            else:
                # No forecast item should reach here: every one now has a real
                # HMIS driver. Fail loudly rather than silently flat-lining.
                raise SystemExit(
                    f"{item['item_id']} is a forecast item with no driver")

            expected = base_daily * seasonal * dow * fac_mult
            expected = np.clip(expected, 0.0, None)
            demand = rng.poisson(expected)

            fid = facility["facility_id"]
            iid = item["item_id"]

            # Run the ledger: receive on the indent cycle, dispense what is
            # actually on the shelf. A facility that runs out cannot dispense.
            n_cycles = len(range(0, DAYS, INDENT_CYCLE_DAYS))
            draw = rng.random(n_cycles)
            shelf_lives = np.where(
                draw < DUMPED_SHARE,
                rng.integers(*SHELF_LIFE_DUMPED, size=n_cycles),
                np.where(
                    draw < DUMPED_SHARE + SHORT_DATED_SHARE,
                    rng.integers(*SHELF_LIFE_SHORT, size=n_cycles),
                    rng.integers(*SHELF_LIFE_NORMAL, size=n_cycles),
                ),
            )
            dispensed, receipts, expiries, unmet = _run_ledger(
                demand, scenario.get(fid, "normal"),
                reliability=facility_reliability[f_idx],
                rng=rng, shelf_lives=shelf_lives,
            )
            expired_units += sum(q for _, q in expiries)

            # Counterfactual: the same year issued first-in-first-out. Only the
            # FEFO run is written; this exists to measure what FEFO saves.
            _, _, fifo_expiries, _ = _run_ledger(
                demand, scenario.get(fid, "normal"),
                reliability=facility_reliability[f_idx],
                rng=np.random.default_rng(SEED + 4 + f_idx),
                shelf_lives=shelf_lives, policy="fifo",
            )
            fifo_expired_units += sum(q for _, q in fifo_expiries)
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
                    "expiry_date": pd.NaT,
                }))
                total_rows += int(keep.sum())

            # Stock counts: the facility reporting what it holds. Emitted only
            # for periods it actually reported.
            if reported:
                count_days = [dates[i] for i in reported]
                chunks.append(pd.DataFrame({
                    "event_id": [
                        f"seed-c-{fid}-{iid}-{d:%Y%m%d}" for d in count_days
                    ],
                    "facility_id": fid,
                    "item_id": iid,
                    "event_type": "count",
                    "quantity": 0,
                    "event_ts": pd.DatetimeIndex(count_days),
                    "source": "seed",
                    "confidence": 1.0,
                    "raw_transcript": None,
                    "expiry_date": pd.NaT,
                }))
                total_rows += len(count_days)

            if receipts:
                days = [dates[i] for i, _, _ in receipts]
                expiry = [
                    (dates[i] + pd.Timedelta(days=life)).date()
                    for i, _, life in receipts
                ]
                chunks.append(pd.DataFrame({
                    "event_id": [
                        f"seed-r-{fid}-{iid}-{d:%Y%m%d}" for d in days
                    ],
                    "facility_id": fid,
                    "item_id": iid,
                    "event_type": "received",
                    "quantity": np.array([q for _, q, _ in receipts],
                                         dtype="int64"),
                    "event_ts": pd.DatetimeIndex(days),
                    "source": "seed",
                    "confidence": 1.0,
                    "raw_transcript": None,
                    "expiry_date": expiry,
                }))
                total_rows += len(receipts)

            # Write-offs: stock that reached its expiry date unused. This is
            # the waste that FEFO and redistribution exist to reduce.
            if expiries:
                exp_days = [dates[i] for i, _ in expiries]
                chunks.append(pd.DataFrame({
                    "event_id": [
                        f"seed-x-{fid}-{iid}-{d:%Y%m%d}" for d in exp_days
                    ],
                    "facility_id": fid,
                    "item_id": iid,
                    "event_type": "expired",
                    "quantity": np.array([q for _, q in expiries],
                                         dtype="int64"),
                    "event_ts": pd.DatetimeIndex(exp_days),
                    "source": "seed",
                    "confidence": 1.0,
                    "raw_transcript": None,
                    "expiry_date": pd.NaT,
                }))
                total_rows += len(expiries)

        if (f_idx + 1) % 50 == 0:
            print(f"  {f_idx + 1}/{len(facilities)} facilities, "
                  f"{total_rows:,} rows")

    if unmatched:
        # A district that reported no confirmed malaria all year genuinely has
        # no antimalarial demand, and narrower drivers mean more such cases:
        # eclampsia and confirmed malaria are rare events, so some districts
        # report zero every month. Those facility-items get no events, fall
        # below the 300-day training threshold, and are simply not forecast —
        # which is the honest outcome, not an error.
        by_driver: dict[str, int] = {}
        for _, _, driver in unmatched:
            by_driver[driver] = by_driver.get(driver, 0) + 1
        print(f"\n  {len(unmatched)} district x driver combinations report "
              "zero all year, so no demand was generated for them:")
        for driver, n in sorted(by_driver.items(), key=lambda kv: -kv[1]):
            print(f"    {driver:48s} {n:>3} districts")

    frame = pd.concat(chunks, ignore_index=True)
    frame["event_ts"] = pd.to_datetime(frame["event_ts"], utc=True)
    frame["expiry_date"] = pd.to_datetime(
        frame["expiry_date"], errors="coerce").dt.date
    print(f"\nBuilt {len(frame):,} rows")
    print(f"  quantity: min={frame['quantity'].min()}, "
          f"mean={frame['quantity'].mean():.1f}, "
          f"max={frame['quantity'].max()}")
    print(f"  series:   {frame.groupby(['facility_id','item_id']).ngroups:,}")
    counts = frame[frame["event_type"] == "count"]
    if not counts.empty:
        per_facility = counts.groupby("facility_id")["event_ts"].nunique()
        expected = len(range(0, DAYS, REPORT_PERIOD_DAYS))
        rate = per_facility / expected
        print(f"  reporting: mean {rate.mean():.0%} of expected periods "
              f"(worst {rate.min():.0%}, best {rate.max():.0%})")
    served = int(frame.loc[frame["event_type"] == "dispensed", "quantity"].sum())
    print(f"  expired on shelf: {expired_units:,} units written off "
          "(never dispensed)")
    saved = fifo_expired_units - expired_units
    print(f"  same year issued FIFO instead: {fifo_expired_units:,} units "
          f"would have expired")
    print(f"  WASTE AVOIDED BY FEFO: {saved:,} units "
          f"({saved / max(fifo_expired_units, 1):.0%} of it)")
    print(f"  unmet demand: {unmet_units:,} units "
          f"({unmet_units / max(served + unmet_units, 1):.1%} of demand) — "
          "patients turned away because stock had run out")

    if dry_run:
        print("\n[DRY RUN] Nothing written to BigQuery.")
        print(frame.head(5).to_string())
        return

    if add_state:
        # The impact table describes the original network and is left alone;
        # the new state's rows are appended to the ledger the app reads.
        _append_state(client, frame, add_state)
        _merge_impact(client, frame, add_state, unmet_units, expired_units,
                      fifo_expired_units)
        return
    _write(client, frame)
    _write_impact(client, frame, unmet_units, expired_units,
                  fifo_expired_units)


def _append_state(client: bigquery.Client, frame: pd.DataFrame,
                  state: str) -> None:
    """Replace one state's generated medicine rows in `resource_events`.

    Only rows with `source = 'seed'` for that state's forecast facilities are
    deleted, so captured reports survive a rerun, and a check fails the run if
    any medicine row outside the state changed.
    """
    params = [bigquery.ScalarQueryParameter("state", "STRING", state)]
    scope = (f"facility_id IN (SELECT facility_id FROM {FACILITIES} "
             f"WHERE is_forecast_facility AND admin_l1 = @state)")
    count_sql = (f"SELECT COUNTIF(NOT ({scope})) AS others FROM `{RESOURCE_EVENTS}` "
                 f"WHERE resource_type = 'medicine'")
    cfg = bigquery.QueryJobConfig(query_parameters=params)
    before = next(iter(client.query(count_sql, job_config=cfg).result())).others

    client.query(f"DELETE FROM `{RESOURCE_EVENTS}` WHERE resource_type = 'medicine' "
                 f"AND source = 'seed' AND {scope}", job_config=cfg).result()

    out = frame.copy()
    out["resource_type"] = "medicine"
    out["resource_subtype"] = None
    out["capacity"] = None
    schema = client.get_table(RESOURCE_EVENTS).schema
    out = out[[f.name for f in schema]]
    print(f"\nAppending {len(out):,} rows for {state} to {RESOURCE_EVENTS} ...")
    client.load_table_from_dataframe(
        out, RESOURCE_EVENTS,
        job_config=bigquery.LoadJobConfig(
            schema=schema,
            write_disposition=bigquery.WriteDisposition.WRITE_APPEND),
    ).result()

    after = next(iter(client.query(count_sql, job_config=cfg).result())).others
    if after != before:
        raise SystemExit(f"Medicine rows outside {state} changed: "
                         f"{before:,} -> {after:,}")
    print(f"  medicine rows outside {state} unchanged ({after:,})")


def _write_impact(client, frame, unmet, expired, fifo_expired):
    """Record the network-level impact numbers as a one-row table.

    `waste_avoided_by_fefo_units` is a measured counterfactual, not an
    estimate: the same year's ledger is replayed issuing first-in-first-out
    instead of first-expiry-first-out, and the write-offs are differenced.
    """
    dispensed = int(frame.loc[frame["event_type"] == "dispensed",
                              "quantity"].sum())
    rows = [{
        "as_of_date": END_DATE.isoformat(),
        "units_dispensed": dispensed,
        "units_unmet": int(unmet),
        "unmet_share": round(unmet / max(dispensed + unmet, 1), 4),
        "units_expired_fefo": int(expired),
        "units_expired_fifo": int(fifo_expired),
        "waste_avoided_by_fefo_units": int(fifo_expired - expired),
        "waste_avoided_share": round(
            (fifo_expired - expired) / max(fifo_expired, 1), 4),
    }]
    client.load_table_from_json(
        rows, IMPACT_METRICS,
        job_config=bigquery.LoadJobConfig(
            schema=[
                bigquery.SchemaField("as_of_date", "DATE"),
                bigquery.SchemaField("units_dispensed", "INT64"),
                bigquery.SchemaField("units_unmet", "INT64"),
                bigquery.SchemaField("unmet_share", "FLOAT64"),
                bigquery.SchemaField("units_expired_fefo", "INT64"),
                bigquery.SchemaField("units_expired_fifo", "INT64"),
                bigquery.SchemaField("waste_avoided_by_fefo_units", "INT64"),
                bigquery.SchemaField("waste_avoided_share", "FLOAT64"),
            ],
            write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
        ),
    ).result()
    print(f"  impact_metrics written: {fifo_expired - expired:,} units of "
          "waste avoided by FEFO")


IMPACT_PARTS = f"{PROJECT}.{DATASET}.impact_metrics_parts"


def _merge_impact(client, frame, state, unmet, expired, fifo_expired):
    """Fold an added state into the network impact figures, idempotently.

    `impact_metrics` is one row for the whole network. Before Uttar Pradesh
    it described the original run only, so the rupee waste figure applied the
    original waste-avoided share to six states' expiries and divided by 200
    centres. Now each part is kept in `impact_metrics_parts` (the original run
    under `__original__`, each added state under its name), a rerun replaces
    its own part, and `impact_metrics` is rebuilt as the sum.
    """
    dispensed = int(frame.loc[frame["event_type"] == "dispensed",
                              "quantity"].sum())
    client.query(f"""
        CREATE TABLE IF NOT EXISTS `{IMPACT_PARTS}` (
          part STRING, as_of_date DATE, units_dispensed INT64,
          units_unmet INT64, units_expired_fefo INT64, units_expired_fifo INT64)
    """).result()
    has_original = next(iter(client.query(
        f"SELECT COUNT(*) AS n FROM `{IMPACT_PARTS}` "
        f"WHERE part = '__original__'").result())).n
    if not has_original:
        client.query(f"""
            INSERT INTO `{IMPACT_PARTS}`
            SELECT '__original__', as_of_date, units_dispensed, units_unmet,
                   units_expired_fefo, units_expired_fifo
            FROM {IMPACT_METRICS}
        """.replace("{IMPACT_METRICS}", f"`{IMPACT_METRICS}`")).result()
    cfg = bigquery.QueryJobConfig(query_parameters=[
        bigquery.ScalarQueryParameter("part", "STRING", state),
        bigquery.ScalarQueryParameter("d", "INT64", dispensed),
        bigquery.ScalarQueryParameter("u", "INT64", int(unmet)),
        bigquery.ScalarQueryParameter("e", "INT64", int(expired)),
        bigquery.ScalarQueryParameter("f", "INT64", int(fifo_expired)),
        bigquery.ScalarQueryParameter("asof", "DATE", END_DATE),
    ])
    client.query(f"DELETE FROM `{IMPACT_PARTS}` WHERE part = @part",
                 job_config=cfg).result()
    client.query(f"INSERT INTO `{IMPACT_PARTS}` VALUES "
                 f"(@part, @asof, @d, @u, @e, @f)", job_config=cfg).result()
    client.query(f"""
        CREATE OR REPLACE TABLE `{IMPACT_METRICS}` AS
        SELECT MAX(as_of_date) AS as_of_date,
               SUM(units_dispensed) AS units_dispensed,
               SUM(units_unmet) AS units_unmet,
               ROUND(SAFE_DIVIDE(SUM(units_unmet),
                     SUM(units_dispensed) + SUM(units_unmet)), 4) AS unmet_share,
               SUM(units_expired_fefo) AS units_expired_fefo,
               SUM(units_expired_fifo) AS units_expired_fifo,
               SUM(units_expired_fifo) - SUM(units_expired_fefo)
                 AS waste_avoided_by_fefo_units,
               ROUND(SAFE_DIVIDE(SUM(units_expired_fifo) - SUM(units_expired_fefo),
                     SUM(units_expired_fifo)), 4) AS waste_avoided_share
        FROM `{IMPACT_PARTS}`
    """).result()
    row = next(iter(client.query(f"SELECT * FROM `{IMPACT_METRICS}`").result()))
    print(f"  impact_metrics now covers every part: "
          f"{row.waste_avoided_by_fefo_units:,} units avoided "
          f"({row.waste_avoided_share:.1%})")


def _pick_scenarios(facilities: pd.DataFrame):
    """Choose facilities to push into deficit, each with a same-district donor.

    Pairing inside a district guarantees the donor is close enough to be a
    legitimate transfer candidate, so the demo always has a recommendation.
    """
    ordered = facilities.sort_values("facility_id").reset_index(drop=True)
    deficit, surplus = [], []
    for _, grp in ordered.groupby(["state", "district"]):
        if len(grp) >= 2 and len(deficit) < 3:
            deficit.append(grp.iloc[0]["facility_id"])
            surplus.append(grp.iloc[1]["facility_id"])
    return deficit, surplus


def _run_ledger(demand, mode, reliability=1.0, rng=None, shelf_lives=None,
                policy="fefo"):
    """Walk one facility-item ledger through a year, batch by batch.

    Returns `(dispensed, receipts, expiries, unmet)`:

    * `dispensed` — units actually handed over: demand capped by what is on the
      shelf **and still in date**.
    * `receipts` — `(day_index, quantity, shelf_life_days)` per indent.
    * `expiries` — `(day_index, quantity)` write-offs when a batch reaches its
      expiry date with units left. This is real waste.
    * `unmet` — demand that could not be served.

    `policy` selects the issuing rule:

    * `fefo` — first-expiry-first-out, what the product recommends.
    * `fifo` — first-in-first-out, what a facility does when it takes whatever
      is at the front of the shelf. Used only to measure the counterfactual:
      the difference in write-offs between the two is the waste FEFO avoids.

    Expired units are written off rather than dispensed. An earlier version had
    no expiry step at all, so short-dated stock was quietly handed to patients
    after its expiry date, which made waste invisible entirely.
    """
    days = len(demand)
    dispensed = np.zeros(days, dtype=np.int64)
    receipts = []
    expiries = []
    cycle_starts = list(range(0, days, INDENT_CYCLE_DAYS))
    total_cycles = len(cycle_starts)
    unmet = 0

    # Open batches as [expiry_day_index, remaining_units], sorted by expiry.
    batches = []
    stock = 0

    for n, start_day in enumerate(cycle_starts):
        end_day = min(start_day + INDENT_CYCLE_DAYS, days)
        window = demand[start_day:end_day]
        if window.size == 0:
            continue

        if n == 0:
            rate = float(window.mean())
        else:
            previous = dispensed[max(0, start_day - INDENT_CYCLE_DAYS):start_day]
            rate = float(previous.mean()) if previous.size else float(window.mean())

        ordered = max(0.0, rate * TARGET_COVER_DAYS - stock)

        fill_rate = reliability
        if rng is not None:
            fill_rate = float(np.clip(
                rng.normal(reliability, FILL_NOISE_SD), 0.15, 1.6))
        if n >= total_cycles - SCENARIO_CYCLES:
            if mode == "deficit":
                fill_rate = DEFICIT_FILL_RATE
            elif mode == "surplus":
                fill_rate = SURPLUS_FILL_RATE

        quantity = int(round(ordered * fill_rate))
        if quantity > 0:
            life = int(shelf_lives[n]) if shelf_lives is not None else 540
            receipts.append((start_day, quantity, life))
            batches.append([start_day + life, quantity, start_day])
            if policy == "fefo":
                batches.sort(key=lambda b: b[0])   # soonest expiry first
            else:
                batches.sort(key=lambda b: b[2])   # oldest receipt first
            stock += quantity

        for offset in range(end_day - start_day):
            day = start_day + offset

            for batch in batches:
                if batch[0] <= day and batch[1] > 0:
                    expiries.append((day, batch[1]))
                    stock -= batch[1]
                    batch[1] = 0

            need = int(window[offset])
            if need <= 0:
                continue

            served = 0
            for batch in batches:
                if batch[1] <= 0 or batch[0] <= day:
                    continue
                take = min(batch[1], need - served)
                batch[1] -= take
                served += take
                if served >= need:
                    break
            dispensed[day] = served
            stock -= served
            unmet += need - served

        batches = [b for b in batches if b[1] > 0]

    return dispensed, receipts, expiries, unmet


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
    parser.add_argument("--add-state",
                        help="generate only this state's forecast facilities "
                             "and append them, leaving the rest untouched")
    args = parser.parse_args()
    try:
        generate(dry_run=args.dry_run, add_state=args.add_state)
    except Exception as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        raise
