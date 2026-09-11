"""Generate bed occupancy and personnel attendance into `resource_events`.

Both ride the medicine pipeline rather than forming a second product: same
table, same partitioning, same `(facility_id, item_id)` grain, same disclosure
discipline. Only `resource_type` differs.

**Beds — capacity real, occupancy generated.**
Capacity is the IPHS 2022 norm applied to real facilities (see
`set_bed_capacity.py`) and is not generated at all. Occupancy is generated, and
it is anchored the same way medicine demand is: the district's real HMIS
`Inpatient admissions - total` volume, divided by the real number of PHCs and
scaled by the same `PHC_SHARE` assumption, converted to beds occupied by an
average length of stay. It is then capped at capacity — a PHC with six beds
cannot have seven occupied, and demand above capacity becomes *turned away*,
which is the signal a referral needs.

Urban PHCs hold day-care beds under the norm and are not expected to provide
in-patient care, so they are given day-time occupancy only and never counted as
overnight beds.

**Personnel — establishment and vacancy real, attendance generated.**
Sanctioned posts and the vacancy rate come from Rural Health Statistics 2017
(see `build_facility_staffing.py`). A vacant post cannot be attended, so
attendance is bounded by posts actually filled. Day-to-day presence is then
generated: a fixed-seed per-facility attendance propensity, lower on Sundays,
with occasional multi-day absences for leave and training.

**These two are not forecast by ARIMA, deliberately.** Adding 200 bed series
and 1,000 personnel series would take the trained model from 2,794 to roughly
3,994 of the 5,000-series ceiling, for two quantities that are bounded small
integers — a PHC has six beds and about one doctor. A time-series model adds
nothing over an occupancy rate and an attendance rate, and it would spend most
of the remaining ceiling. Medicines keep ARIMA; beds and personnel use
rule-based statistics.
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
DEMAND_REF = f"`{PROJECT}.{DATASET}.demand_reference`"
FACILITY_STAFFING = f"`{PROJECT}.{DATASET}.facility_staffing`"
RESOURCE_EVENTS = f"{PROJECT}.{DATASET}.resource_events"

SEED = 20260831
DAYS = 365
END_DATE = date(2026, 8, 29)

MONTH_NAMES = ["January", "February", "March", "April", "May", "June", "July",
               "August", "September", "October", "November", "December"]
COVID_MONTH = "March"
CLEAN_BASELINE_MONTHS = MONTH_NAMES[3:12]

BED_DRIVER = "Inpatient admissions - total"

# Average length of stay at a PHC, in days. PHC admissions are short —
# observation, stabilisation, uncomplicated delivery — before discharge or
# referral upward.
AVERAGE_LENGTH_OF_STAY = 1.8

# Urban PHCs run day-care beds only, so a bed turns over within the day and
# is never occupied overnight.
DAY_CARE_TURNOVER = 3.0

# Attendance. Monday..Sunday.
ATTENDANCE_DOW = np.array([0.97, 0.97, 0.96, 0.96, 0.95, 0.90, 0.55])
# Per-facility baseline propensity, before the day-of-week effect.
ATTENDANCE_BASE = (0.82, 0.98)
# Occasional multi-day absence: leave, training, deputation.
ABSENCE_SPELL_CHANCE = 0.004
ABSENCE_SPELL_DAYS = (3, 12)

SCHEMA = [
    bigquery.SchemaField("event_id", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("resource_type", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("facility_id", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("item_id", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("event_type", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("quantity", "INT64", mode="REQUIRED"),
    bigquery.SchemaField("event_ts", "TIMESTAMP", mode="REQUIRED"),
    bigquery.SchemaField("source", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("confidence", "FLOAT64"),
    bigquery.SchemaField("raw_transcript", "STRING"),
    bigquery.SchemaField("expiry_date", "DATE"),
    bigquery.SchemaField("resource_subtype", "STRING"),
    bigquery.SchemaField("capacity", "FLOAT64"),
]

# Personnel attendance is no longer generated. It was a fixed-seed propensity,
# lower on Sundays, and every figure built on it was removed from the product
# on 2026-09-11 (CLAIMS §8a) — no public facility-level attendance data exists
# in India to replace it with. Left on, a rerun would also crash: the 2021-22
# establishment has one "Health assistant" cadre, which has no entry below.
# The personnel rows already in `resource_events` are orphaned history that
# nothing reads; a rerun with this off removes them.
GENERATE_PERSONNEL = False

CADRE_ITEM_IDS = {
    "Doctor (allopathic)": "STAFF-DOCTOR",
    "Nursing staff": "STAFF-NURSE",
    "Pharmacist": "STAFF-PHARMACIST",
    "Health assistant (male)": "STAFF-HA-MALE",
    "Health assistant (female)": "STAFF-HA-FEMALE",
}


def fetch(client: bigquery.Client):
    facilities = client.query(f"""
        SELECT facility_id, admin_l1 AS state, admin_l2 AS district,
               UPPER(TRIM(admin_l2)) AS district_key,
               bed_capacity, beds_are_day_care
        FROM {FACILITIES}
        WHERE is_forecast_facility
        ORDER BY facility_id
    """).to_dataframe()

    phc_counts = client.query(f"""
        SELECT admin_l1 AS state, UPPER(TRIM(admin_l2)) AS district_key,
               COUNT(*) AS phcs
        FROM {FACILITIES}
        WHERE country_code = 'IN' AND facility_type = 'phc'
        GROUP BY state, district_key
    """).to_dataframe()

    hmis = client.query(f"""
        WITH baseline AS (
          SELECT admin_l1 AS state, district_key, AVG(value) AS baseline
          FROM {DEMAND_REF}
          WHERE indicator = @driver AND month IN UNNEST(@clean_months)
          GROUP BY state, district_key
        )
        SELECT d.admin_l1 AS state, d.district_key, d.month, d.value, b.baseline
        FROM {DEMAND_REF} d
        JOIN baseline b
          ON b.state = d.admin_l1 AND b.district_key = d.district_key
        WHERE d.indicator = @driver
    """, job_config=bigquery.QueryJobConfig(query_parameters=[
        bigquery.ScalarQueryParameter("driver", "STRING", BED_DRIVER),
        bigquery.ArrayQueryParameter("clean_months", "STRING",
                                     CLEAN_BASELINE_MONTHS),
    ])).to_dataframe()

    staffing = client.query(f"""
        SELECT facility_id, cadre, sanctioned_posts, expected_in_position
        FROM {FACILITY_STAFFING}
        ORDER BY facility_id, cadre
    """).to_dataframe()

    return facilities, phc_counts, hmis, staffing


def build_seasonality(hmis: pd.DataFrame) -> dict:
    table: dict[tuple[str, str], np.ndarray] = {}
    for (state, district), grp in hmis.groupby(["state", "district_key"]):
        baseline = grp["baseline"].iloc[0]
        multipliers = np.ones(12)
        if baseline and baseline > 0:
            by_month = dict(zip(grp["month"], grp["value"]))
            for idx, month in enumerate(MONTH_NAMES):
                if month == COVID_MONTH:
                    continue
                value = by_month.get(month)
                if value is not None and not pd.isna(value):
                    multipliers[idx] = value / baseline
        table[(state, district)] = np.clip(multipliers, 0.25, 4.0)
    return table


def build_scale(hmis: pd.DataFrame, phc_counts: pd.DataFrame) -> dict:
    phcs = {(r.state, r.district_key): r.phcs for r in phc_counts.itertuples()}
    scale: dict[tuple[str, str], float] = {}
    for (state, district), grp in hmis.groupby(["state", "district_key"]):
        baseline = grp["baseline"].iloc[0]
        count = phcs.get((state, district), 0)
        if baseline and count:
            scale[(state, district)] = float(baseline) / count
    return scale


def generate(dry_run: bool = False) -> None:
    client = bigquery.Client(project=PROJECT, location=LOCATION)

    print("Fetching real inputs ...")
    facilities, phc_counts, hmis, staffing = fetch(client)
    print(f"  facilities:   {len(facilities)}")
    print(f"  staffing rows:{len(staffing)}")
    print(f"  HMIS rows:    {len(hmis)}")

    seasonality = build_seasonality(hmis)
    scale = build_scale(hmis, phc_counts)
    share = phc_share(BED_DRIVER)

    rng = np.random.default_rng(SEED)
    dates = pd.date_range(end=END_DATE, periods=DAYS, freq="D")
    month_index = dates.month.values - 1
    dow_index = dates.dayofweek.values
    days_in_month = dates.days_in_month.values

    by_facility = {
        fid: grp for fid, grp in staffing.groupby("facility_id")
    }

    chunks: list[pd.DataFrame] = []
    turned_away_total = 0
    bed_days = 0
    occupied_days = 0

    for idx, facility in facilities.reset_index(drop=True).iterrows():
        fid = facility["facility_id"]
        key = (facility["state"], facility["district_key"])
        capacity = 0 if pd.isna(facility["bed_capacity"]) else int(
            facility["bed_capacity"])
        day_care = bool(facility["beds_are_day_care"]) if not pd.isna(
            facility["beds_are_day_care"]) else False

        # ---- Beds ---------------------------------------------------------
        monthly_admissions = scale.get(key)
        season = seasonality.get(key)
        if monthly_admissions and season is not None and capacity > 0:
            daily_admissions = (
                monthly_admissions * share * season[month_index] / days_in_month
            )
            turnover = DAY_CARE_TURNOVER if day_care else AVERAGE_LENGTH_OF_STAY
            # Beds needed = admissions per day x length of stay (or / turnover
            # for day-care, where one bed serves several patients a day).
            if day_care:
                demand = daily_admissions / turnover
            else:
                demand = daily_admissions * turnover
            drawn = rng.poisson(np.clip(demand, 0, None))
            occupied = np.minimum(drawn, capacity)
            turned_away = drawn - occupied

            turned_away_total += int(turned_away.sum())
            bed_days += capacity * DAYS
            occupied_days += int(occupied.sum())

            chunks.append(pd.DataFrame({
                "event_id": [f"seed-bed-{fid}-{d:%Y%m%d}" for d in dates],
                "resource_type": "bed",
                "facility_id": fid,
                "item_id": "BED-DAYCARE" if day_care else "BED-INPATIENT",
                "event_type": "occupancy",
                "quantity": occupied.astype("int64"),
                "event_ts": dates,
                "source": "seed",
                "confidence": 1.0,
                "raw_transcript": None,
                "expiry_date": pd.NaT,
                "resource_subtype": "day_care" if day_care else "inpatient",
                "capacity": float(capacity),
            }))

            if turned_away.any():
                keep = turned_away > 0
                chunks.append(pd.DataFrame({
                    "event_id": [f"seed-bedref-{fid}-{d:%Y%m%d}"
                                 for d in dates[keep]],
                    "resource_type": "bed",
                    "facility_id": fid,
                    "item_id": "BED-DAYCARE" if day_care else "BED-INPATIENT",
                    "event_type": "turned_away",
                    "quantity": turned_away[keep].astype("int64"),
                    "event_ts": dates[keep],
                    "source": "seed",
                    "confidence": 1.0,
                    "raw_transcript": None,
                    "expiry_date": pd.NaT,
                    "resource_subtype": "referral_needed",
                    "capacity": float(capacity),
                }))

        # ---- Personnel ----------------------------------------------------
        posts = by_facility.get(fid) if GENERATE_PERSONNEL else None
        if posts is None:
            continue
        base = rng.uniform(*ATTENDANCE_BASE)
        for post in posts.itertuples():
            # Nullable integer columns come back as pd.NA, which is not
            # falsy — coerce explicitly rather than relying on `or`.
            filled = 0 if pd.isna(post.expected_in_position) else int(
                post.expected_in_position)
            sanctioned = 0 if pd.isna(post.sanctioned_posts) else int(
                post.sanctioned_posts)
            if sanctioned <= 0:
                continue
            if filled <= 0:
                # Every post vacant: the facility reports zero attendance,
                # which is a real and important state, not missing data.
                present = np.zeros(DAYS, dtype=np.int64)
            else:
                rate = np.clip(base * ATTENDANCE_DOW[dow_index], 0, 1)
                # Multi-day absences: leave, training, deputation.
                spells = rng.random(DAYS) < ABSENCE_SPELL_CHANCE
                for start in np.flatnonzero(spells):
                    length = rng.integers(*ABSENCE_SPELL_DAYS)
                    rate[start:start + length] *= 0.15
                present = rng.binomial(filled, rate).astype("int64")

            chunks.append(pd.DataFrame({
                "event_id": [
                    f"seed-att-{fid}-{CADRE_ITEM_IDS[post.cadre]}-{d:%Y%m%d}"
                    for d in dates
                ],
                "resource_type": "personnel",
                "facility_id": fid,
                "item_id": CADRE_ITEM_IDS[post.cadre],
                "event_type": "attendance",
                "quantity": present,
                "event_ts": dates,
                "source": "seed",
                "confidence": 1.0,
                "raw_transcript": None,
                "expiry_date": pd.NaT,
                "resource_subtype": post.cadre,
                "capacity": float(sanctioned),
            }))

        if (idx + 1) % 50 == 0:
            print(f"  {idx + 1}/{len(facilities)} facilities")

    frame = pd.concat(chunks, ignore_index=True)
    frame["event_ts"] = pd.to_datetime(frame["event_ts"], utc=True)
    frame["expiry_date"] = pd.to_datetime(
        frame["expiry_date"], errors="coerce").dt.date

    beds = frame[frame["resource_type"] == "bed"]
    staff = frame[frame["resource_type"] == "personnel"]
    print(f"\nBuilt {len(frame):,} rows")
    print(f"  bed events:       {len(beds):,}")
    print(f"  personnel events: {len(staff):,}")
    if bed_days:
        print(f"  mean bed occupancy: {occupied_days / bed_days:.0%}")
    print(f"  patients turned away for want of a bed: "
          f"{turned_away_total:,} (referral signal)")
    attendance = staff[staff["capacity"] > 0]
    if len(attendance):
        print(f"  mean attendance vs sanctioned posts: "
              f"{attendance['quantity'].sum() / attendance['capacity'].sum():.0%}")

    if dry_run:
        print("\n[DRY RUN] Nothing written.")
        print(frame.head(4).to_string())
        return

    print(f"\nAppending to {RESOURCE_EVENTS} "
          "(medicine rows untouched) ...")
    before = next(iter(client.query(f"""
        SELECT COUNTIF(resource_type = 'medicine') AS medicine,
               COUNT(*) AS total
        FROM `{RESOURCE_EVENTS}`
    """).result()))

    client.query(
        f"DELETE FROM `{RESOURCE_EVENTS}` "
        "WHERE resource_type IN ('bed', 'personnel')"
    ).result()

    client.load_table_from_dataframe(
        frame, RESOURCE_EVENTS,
        job_config=bigquery.LoadJobConfig(
            schema=SCHEMA,
            write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
        ),
    ).result()

    after = next(iter(client.query(f"""
        SELECT COUNTIF(resource_type = 'medicine')  AS medicine,
               COUNTIF(resource_type = 'bed')       AS bed,
               COUNTIF(resource_type = 'personnel') AS personnel,
               COUNT(*) AS total
        FROM `{RESOURCE_EVENTS}`
    """).result()))
    print(f"  medicine:  {after.medicine:,} (was {before.medicine:,})")
    print(f"  bed:       {after.bed:,}")
    print(f"  personnel: {after.personnel:,}")
    print(f"  total:     {after.total:,}")

    if after.medicine != before.medicine:
        raise SystemExit(
            "Medicine row count changed. The medicine path must not move.")
    print("\nOK — medicine path untouched.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    try:
        generate(dry_run=args.dry_run)
    except Exception as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        raise
