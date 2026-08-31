"""Bed and personnel views, served from the precomputed status tables.

Medicines keep their own module (`app/supply.py`) because they carry the deep
logic — reorder points, FEFO, substitution. Beds and personnel are thinner by
design: capacity, occupancy, attendance, and what each shortage implies.
"""

from __future__ import annotations

import os

from google.cloud import bigquery

from app.bq import run_query

PROJECT = os.getenv("GCP_PROJECT", "daysupply")
DATASET = os.getenv("BQ_DATASET", "daysupply")

BED_STATUS = f"`{PROJECT}.{DATASET}.bed_status`"
BED_REFERRALS = f"`{PROJECT}.{DATASET}.bed_referrals`"
STAFF_STATUS = f"`{PROJECT}.{DATASET}.staff_status`"
STAFF_REALLOCATION = f"`{PROJECT}.{DATASET}.staff_reallocation`"
FACILITIES = f"`{PROJECT}.{DATASET}.facilities`"

RESOURCE_TYPES = ("medicine", "bed", "personnel")


def _scope(state: str, district: str, facility_id: str,
           facility_column: str = "facility_id"):
    where: list[str] = []
    params: list[bigquery.ScalarQueryParameter] = []
    if facility_id:
        where.append(f"{facility_column} = @facility_id")
        params.append(bigquery.ScalarQueryParameter(
            "facility_id", "STRING", facility_id))
    else:
        if state:
            where.append("state = @state")
            params.append(
                bigquery.ScalarQueryParameter("state", "STRING", state))
        if district:
            where.append("district = @district")
            params.append(bigquery.ScalarQueryParameter(
                "district", "STRING", district))
    return (" AND ".join(where) or "TRUE"), params


def bed_summary(state: str = "", district: str = "",
                facility_id: str = "") -> dict:
    """Occupancy, capacity and pressure across the scope."""
    where, params = _scope(state, district, facility_id)
    rows = run_query(
        f"""
        SELECT
          COUNT(*)                                AS facilities,
          SUM(bed_capacity)                       AS total_beds,
          SUM(IF(NOT beds_are_day_care, bed_capacity, 0)) AS overnight_beds,
          ROUND(SUM(mean_occupied), 1)            AS beds_occupied,
          ROUND(AVG(occupancy_rate) * 100, 1)     AS mean_occupancy_pct,
          SUM(free_beds)                          AS free_beds,
          SUM(turned_away)                        AS turned_away_30d,
          COUNTIF(status = 'has_capacity')        AS has_capacity,
          COUNTIF(status = 'under_pressure')      AS under_pressure,
          COUNTIF(status = 'over_capacity')       AS over_capacity,
          MAX(as_of_date)                         AS as_of
        FROM {BED_STATUS}
        WHERE {where}
        """,
        params,
        cache_key=f"beds:sum:{state}:{district}:{facility_id}",
    )
    summary = rows[0] if rows else {}
    return {
        **summary,
        "capacity_basis": (
            "IPHS 2022 norm applied to real facilities: 2 essential + 4 "
            "desirable beds per PHC, day-care in urban PHCs. Capacity is real; "
            "occupancy is generated from real HMIS admission volumes."
        ),
    }


def bed_facilities(state: str = "", district: str = "", facility_id: str = "",
                   limit: int = 50) -> list[dict]:
    where, params = _scope(state, district, facility_id)
    params.append(bigquery.ScalarQueryParameter("lim", "INT64", limit))
    return run_query(
        f"""
        SELECT facility_id, facility_name, state, district, bed_type,
               beds_are_day_care, bed_capacity, mean_occupied, peak_occupied,
               occupancy_rate, free_beds, turned_away, status
        FROM {BED_STATUS}
        WHERE {where}
        ORDER BY turned_away DESC, occupancy_rate DESC
        LIMIT @lim
        """,
        params,
        cache_key=f"beds:list:{state}:{district}:{facility_id}:{limit}",
    )


def bed_referrals(state: str = "", district: str = "", facility_id: str = "",
                  limit: int = 50) -> list[dict]:
    """Where to send a patient when a facility has no bed.

    Beds cannot be transferred, so the output is a route, not a movement.
    """
    where, params = _scope(state, district, facility_id, "from_facility_id")
    params.append(bigquery.ScalarQueryParameter("lim", "INT64", limit))
    return run_query(
        f"""
        SELECT from_facility_id, from_facility_name, state, district,
               from_capacity, from_occupancy_rate, from_turned_away,
               from_status, to_facility_id, to_facility_name, to_free_beds,
               to_occupancy_rate, distance_km, referral_rank
        FROM {BED_REFERRALS}
        WHERE {where}
        ORDER BY from_turned_away DESC, referral_rank, distance_km
        LIMIT @lim
        """,
        params,
        cache_key=f"beds:ref:{state}:{district}:{facility_id}:{limit}",
    )


def staff_summary(state: str = "", district: str = "",
                  facility_id: str = "") -> dict:
    where, params = _scope(state, district, facility_id)
    overall = run_query(
        f"""
        SELECT
          COUNT(DISTINCT facility_id)             AS facilities,
          SUM(sanctioned_posts)                   AS sanctioned_posts,
          ROUND(SUM(mean_present), 1)             AS staff_present,
          ROUND(SAFE_DIVIDE(SUM(mean_present),
                            NULLIF(SUM(sanctioned_posts), 0)) * 100, 1)
                                                  AS attendance_pct,
          COUNTIF(status = 'unstaffed')           AS unstaffed,
          COUNTIF(status = 'critically_short')    AS critically_short,
          COUNTIF(status = 'short')               AS short,
          COUNTIF(status = 'adequate')            AS adequate,
          MAX(as_of_date)                         AS as_of
        FROM {STAFF_STATUS}
        WHERE {where}
        """,
        params,
        cache_key=f"staff:sum:{state}:{district}:{facility_id}",
    )
    by_cadre = run_query(
        f"""
        SELECT cadre, item_id,
               COUNT(*)                             AS facilities,
               SUM(sanctioned_posts)                AS sanctioned_posts,
               ROUND(SUM(mean_present), 1)          AS present,
               ROUND(AVG(attendance_vs_sanctioned) * 100, 1) AS attendance_pct,
               ROUND(AVG(vacancy_rate) * 100, 1)    AS vacancy_pct,
               COUNTIF(status = 'unstaffed')        AS unstaffed
        FROM {STAFF_STATUS}
        WHERE {where}
        GROUP BY cadre, item_id
        ORDER BY attendance_pct
        """,
        params,
        cache_key=f"staff:cadre:{state}:{district}:{facility_id}",
    )
    return {
        **(overall[0] if overall else {}),
        "by_cadre": by_cadre,
        "basis": (
            "Sanctioned posts and vacancy rates are real, from Rural Health "
            "Statistics 2017. A vacant post cannot be attended, so vacancy "
            "sets the ceiling. Daily attendance is generated."
        ),
    }


def staff_facilities(state: str = "", district: str = "",
                     facility_id: str = "", limit: int = 50) -> list[dict]:
    where, params = _scope(state, district, facility_id)
    params.append(bigquery.ScalarQueryParameter("lim", "INT64", limit))
    return run_query(
        f"""
        SELECT facility_id, facility_name, state, district, cadre, item_id,
               sanctioned_posts, mean_present, attendance_vs_sanctioned,
               vacancy_rate, days_none_present, nurses_short_of_bed_norm,
               bed_capacity, nurses_required, status
        FROM {STAFF_STATUS}
        WHERE {where}
        ORDER BY attendance_vs_sanctioned, facility_name
        LIMIT @lim
        """,
        params,
        cache_key=f"staff:list:{state}:{district}:{facility_id}:{limit}",
    )


def staff_reallocation(state: str = "", district: str = "",
                       facility_id: str = "", limit: int = 50) -> dict:
    """Proposed staff moves, and an explanation when there are none.

    Empty is a legitimate answer: four of the five cadres have an
    establishment of one post, so no facility can donate, and the forecast set
    spans 116 districts so nothing is within travelling distance.
    """
    where, params = _scope(state, district, facility_id, "to_facility_id")
    params.append(bigquery.ScalarQueryParameter("lim", "INT64", limit))
    moves = run_query(
        f"""
        SELECT to_facility_id, to_facility_name, state, district, cadre,
               to_sanctioned, to_present, to_status,
               from_facility_id, from_facility_name, from_present,
               from_present_after, to_present_after, staff_to_move, distance_km
        FROM {STAFF_REALLOCATION}
        WHERE {where}
        ORDER BY distance_km
        LIMIT @lim
        """,
        params,
        cache_key=f"staff:alloc:{state}:{district}:{facility_id}:{limit}",
    )
    if moves:
        return {"reallocations": moves, "constraint": None}

    scope_where, scope_params = _scope(state, district, facility_id)
    diag = run_query(
        f"""
        SELECT
          COUNTIF(status IN ('unstaffed', 'critically_short')) AS short,
          COUNTIF(status = 'adequate' AND mean_present >= 2)   AS can_donate,
          COUNT(DISTINCT IF(sanctioned_posts <= 1, cadre, NULL))
            AS single_post_cadres
        FROM {STAFF_STATUS}
        WHERE {scope_where}
        """,
        scope_params,
        cache_key=f"staff:alloc-diag:{state}:{district}:{facility_id}",
    )
    row = diag[0] if diag else {}
    return {
        "reallocations": [],
        "constraint": {
            "facilities_short": row.get("short"),
            "facilities_able_to_donate": row.get("can_donate"),
            "single_post_cadres": row.get("single_post_cadres"),
            "why": (
                "Four of the five cadres are sanctioned one post per PHC, so "
                "no facility can donate a doctor, pharmacist or health "
                "assistant without leaving itself empty — those vacancies need "
                "recruitment, not reallocation. Only nursing has spare "
                "capacity anywhere, and the facilities holding it are over "
                "1,200 km from those that need it, because the forecast set "
                "was chosen to span 116 districts."
            ),
        },
    }


def coverage() -> dict:
    """What the platform tracks per resource type, for the selector."""
    rows = run_query(
        f"""
        SELECT resource_type,
               COUNT(*) AS events,
               COUNT(DISTINCT facility_id) AS facilities,
               COUNT(DISTINCT item_id) AS distinct_resources
        FROM `{PROJECT}.{DATASET}.resource_events`
        GROUP BY resource_type ORDER BY resource_type
        """,
        cache_key="resources:coverage",
    )
    return {
        "resource_types": rows,
        "notes": {
            "medicine": "Deep vertical: ARIMA_PLUS forecasting, lead-time "
                        "reorder points, FEFO, ATC substitution, transfers.",
            "bed": "Capacity from the IPHS 2022 norm. Not transferable — "
                   "pressure produces referral routes.",
            "personnel": "Establishment and vacancy from Rural Health "
                         "Statistics 2017. Reallocation where possible.",
        },
    }
