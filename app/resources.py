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
          COUNT(DISTINCT CONCAT(state, '|', cadre)) AS roles,
          SUM(sanctioned_posts)                   AS sanctioned_posts,
          ROUND(100 * SAFE_DIVIDE(
                  SUM(vacancy_rate * sanctioned_posts),
                  SUM(IF(vacancy_rate IS NULL, 0, sanctioned_posts))),
                1)                                AS vacancy_pct,
          COUNTIF(vacancy_rate IS NULL)           AS no_rhs_figure,
          SUM(nurses_short_of_bed_norm)           AS nurses_short_of_bed_norm,
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
               ROUND(100 * SAFE_DIVIDE(
                       SUM(vacancy_rate * sanctioned_posts),
                       SUM(IF(vacancy_rate IS NULL, 0, sanctioned_posts))),
                     1)                             AS vacancy_pct
        FROM {STAFF_STATUS}
        WHERE {where}
        GROUP BY cadre, item_id
        ORDER BY vacancy_pct DESC
        """,
        params,
        cache_key=f"staff:cadre:{state}:{district}:{facility_id}",
    )
    return {
        **(overall[0] if overall else {}),
        "by_cadre": by_cadre,
        "basis": (
            "Sanctioned posts and vacancy rates are real, from Rural Health "
            "Statistics 2017 — and they exist only at state-and-cadre grain: "
            "`vacancy_rate` takes 23 distinct values across all 928 rows, so "
            "it does not vary by district or facility. Rates are weighted by "
            "sanctioned posts. Day-to-day presence was generated by a "
            "fixed-seed propensity and has been removed from this response "
            "rather than served as though it were measured."
        ),
    }


def staff_facilities(state: str = "", district: str = "",
                     facility_id: str = "", limit: int = 50) -> list[dict]:
    where, params = _scope(state, district, facility_id)
    params.append(bigquery.ScalarQueryParameter("lim", "INT64", limit))
    return run_query(
        f"""
        SELECT facility_id, facility_name, state, district, cadre, item_id,
               sanctioned_posts, vacancy_rate, nurses_short_of_bed_norm,
               bed_capacity, nurses_required
        FROM {STAFF_STATUS}
        WHERE {where}
        ORDER BY vacancy_rate DESC, facility_name
        LIMIT @lim
        """,
        params,
        cache_key=f"staff:list:{state}:{district}:{facility_id}:{limit}",
    )


def staff_reallocation(state: str = "", district: str = "",
                       facility_id: str = "", limit: int = 50) -> dict:
    """Why staff cannot be reallocated here — which is the real answer.

    This used to return proposed moves from `staff_reallocation`, a table built
    by comparing `to_present` against `from_present`. Both come from the
    fixed-seed random attendance propensity in
    `ingestion/generate_bed_personnel.py`, so every move it proposed was two
    random numbers being differenced, and the `status` values that selected
    donors and recipients (`unstaffed`, `adequate`) are thresholds on the same
    generated column.

    The moves are gone. The explanation stays, because it was always the
    stronger half and it rests entirely on real data: `sanctioned_posts` is the
    IPHS establishment, and four of the five cadres are sanctioned **one post
    per PHC** — three of the five, not the four an earlier docstring claimed.
    A single-post cadre has nobody to send. That is a recruitment
    finding, not a logistics one, and it is the honest answer to "can we move
    staff to cover this?" — no, and here is why.
    """
    scope_where, scope_params = _scope(state, district, facility_id)
    diag = run_query(
        f"""
        -- A cadre can only donate if some centre is sanctioned MORE than one
        -- post for it, so the test is MAX(sanctioned_posts) per cadre. Two
        -- earlier attempts got this wrong: counting cadres with *any*
        -- single-post centre returned 5 of 5 (nursing has single-post centres
        -- too), and doing it with a window function counted rows rather than
        -- cadres, which reported "564 of the 5 cadres" and listed the donor
        -- cadre once per row.
        WITH per_cadre AS (
          SELECT cadre,
                 MAX(sanctioned_posts) AS max_posts,
                 SUM(sanctioned_posts) AS cadre_posts
          FROM {STAFF_STATUS}
          WHERE {scope_where}
          GROUP BY cadre
        ),
        scope AS (
          SELECT COUNT(DISTINCT CONCAT(state, '|', cadre)) AS roles,
                 COUNT(DISTINCT district) AS districts
          FROM {STAFF_STATUS}
          WHERE {scope_where}
        )
        SELECT
          (SELECT roles FROM scope)                        AS roles,
          (SELECT districts FROM scope)                    AS districts,
          COUNT(*)                                         AS cadres,
          SUM(cadre_posts)                                 AS posts,
          COUNTIF(max_posts <= 1)                          AS single_post_cadres,
          SUM(IF(max_posts <= 1, cadre_posts, 0))          AS posts_in_single_post_cadres,
          STRING_AGG(IF(max_posts > 1, cadre, NULL), ', '
                     ORDER BY cadre)                       AS donor_cadres
        FROM per_cadre
        """,
        scope_params,
        cache_key=f"staff:alloc-diag2:{state}:{district}:{facility_id}",
    )
    row = dict(diag[0]) if diag else {}
    single = row.get("single_post_cadres") or 0
    cadres = row.get("cadres") or 0
    return {
        "reallocations": [],
        "constraint": {
            "cadres": cadres,
            "single_post_cadres": single,
            "sanctioned_posts": row.get("posts"),
            "posts_in_single_post_cadres": row.get("posts_in_single_post_cadres"),
            "donor_cadres": row.get("donor_cadres"),
            "districts": row.get("districts"),
            "why": (
                f"{single} of the {cadres} cadres here are sanctioned at most "
                "one post at every health centre, so no centre can lend one "
                "without leaving itself empty. Those vacancies need "
                "recruitment, not reallocation."
                + ((f" Only {row.get('donor_cadres')} "
                    + ("carry" if "," in (row.get("donor_cadres") or "")
                       else "carries")
                    + " more than one post anywhere, and the centres holding "
                      f"them are spread across {row.get('districts') or 0} "
                      "districts — far beyond any sensible staff transfer.")
                   if row.get("donor_cadres") else
                   " No cadre in scope has a spare post anywhere.")
            ),
            "basis": (
                "Sanctioned strength is the IPHS establishment and is real. "
                "Proposed moves were removed: they were differences between "
                "two generated attendance figures."
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
