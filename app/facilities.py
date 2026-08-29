"""Facility queries against BigQuery — the real 200,438-row facility master.

This module is the only source of geography in the application. There are no
hardcoded state, district or facility lists anywhere: the dropdowns list what is
actually in `daysupply.facilities`, which is every health facility in India.

All queries project explicit columns (never `SELECT *`) and every reference
query is cached, because the facility master changes only when it is reloaded.
"""

from __future__ import annotations

from google.cloud import bigquery

from app.bq import FACILITIES, run_query

COUNTRY = "IN"

# Facility types that can be selected as a reporting unit in the dashboard.
# PHCs are the unit the product is built around.
PHC_TYPE = "phc"

FACILITY_TYPE_LABELS = {
    "sub_cen": "Sub-Centre",
    "phc": "Primary Health Centre",
    "chc": "Community Health Centre",
    "dis_h": "District Hospital",
    "s_t_h": "State Hospital",
}


def list_states() -> list[dict]:
    """Every state/UT present in the facility master, with facility counts."""
    return run_query(
        f"""
        SELECT
          admin_l1                  AS state,
          COUNT(*)                  AS facility_count,
          COUNTIF(facility_type = @phc) AS phc_count,
          COUNT(DISTINCT admin_l2)  AS district_count
        FROM {FACILITIES}
        WHERE country_code = @cc AND admin_l1 != ''
        GROUP BY state
        ORDER BY state
        """,
        [
            bigquery.ScalarQueryParameter("cc", "STRING", COUNTRY),
            bigquery.ScalarQueryParameter("phc", "STRING", PHC_TYPE),
        ],
        cache_key="states",
    )


def list_districts(state: str) -> list[dict]:
    """Districts within a state, with facility counts."""
    if not state:
        return []
    return run_query(
        f"""
        SELECT
          admin_l2                      AS district,
          COUNT(*)                      AS facility_count,
          COUNTIF(facility_type = @phc) AS phc_count
        FROM {FACILITIES}
        WHERE country_code = @cc AND admin_l1 = @state AND admin_l2 != ''
        GROUP BY district
        ORDER BY district
        """,
        [
            bigquery.ScalarQueryParameter("cc", "STRING", COUNTRY),
            bigquery.ScalarQueryParameter("state", "STRING", state),
            bigquery.ScalarQueryParameter("phc", "STRING", PHC_TYPE),
        ],
        cache_key=f"districts:{state}",
    )


def list_facilities(state: str, district: str,
                    facility_type: str = PHC_TYPE,
                    limit: int = 500) -> list[dict]:
    """Facilities within a district. Defaults to PHCs, the reporting unit."""
    if not state or not district:
        return []
    return run_query(
        f"""
        SELECT
          facility_id,
          name,
          facility_type,
          latitude,
          longitude,
          population_served
        FROM {FACILITIES}
        WHERE country_code = @cc
          AND admin_l1 = @state
          AND admin_l2 = @district
          AND facility_type = @ftype
        ORDER BY name
        LIMIT @lim
        """,
        [
            bigquery.ScalarQueryParameter("cc", "STRING", COUNTRY),
            bigquery.ScalarQueryParameter("state", "STRING", state),
            bigquery.ScalarQueryParameter("district", "STRING", district),
            bigquery.ScalarQueryParameter("ftype", "STRING", facility_type),
            bigquery.ScalarQueryParameter("lim", "INT64", limit),
        ],
        cache_key=f"facilities:{state}:{district}:{facility_type}:{limit}",
    )


def facility_counts(state: str = "", district: str = "",
                    facility_id: str = "") -> dict:
    """Facility counts for the current filter scope.

    Narrowing to a single facility returns 1 — the count is always the real
    number of facilities the dashboard is currently looking at.
    """
    where = ["country_code = @cc"]
    params = [bigquery.ScalarQueryParameter("cc", "STRING", COUNTRY)]

    if facility_id:
        where.append("facility_id = @fid")
        params.append(
            bigquery.ScalarQueryParameter("fid", "STRING", facility_id)
        )
    else:
        if state:
            where.append("admin_l1 = @state")
            params.append(
                bigquery.ScalarQueryParameter("state", "STRING", state)
            )
        if district:
            where.append("admin_l2 = @district")
            params.append(
                bigquery.ScalarQueryParameter("district", "STRING", district)
            )
    params.append(bigquery.ScalarQueryParameter("phc", "STRING", PHC_TYPE))

    rows = run_query(
        f"""
        SELECT
          COUNT(*)                      AS facilities,
          COUNTIF(facility_type = @phc) AS phcs,
          COUNTIF(is_demo_facility)     AS demo_facilities,
          COUNT(DISTINCT admin_l1)      AS states,
          COUNT(DISTINCT admin_l2)      AS districts,
          SUM(population_served)        AS population_served
        FROM {FACILITIES}
        WHERE {' AND '.join(where)}
        """,
        params,
        cache_key=f"counts:{state}:{district}:{facility_id}",
    )
    row = rows[0] if rows else {}
    return {
        "facilities": int(row.get("facilities") or 0),
        "phcs": int(row.get("phcs") or 0),
        "demo_facilities": int(row.get("demo_facilities") or 0),
        "states": int(row.get("states") or 0),
        "districts": int(row.get("districts") or 0),
        "population_served": int(row.get("population_served") or 0),
    }


def national_summary() -> dict:
    """Headline national coverage figures — every facility in the country."""
    rows = run_query(
        f"""
        SELECT
          COUNT(*)                  AS facilities,
          COUNT(DISTINCT admin_l1)  AS states,
          COUNT(DISTINCT admin_l2)  AS districts,
          COUNTIF(is_demo_facility) AS demo_facilities
        FROM {FACILITIES}
        WHERE country_code = @cc
        """,
        [bigquery.ScalarQueryParameter("cc", "STRING", COUNTRY)],
        cache_key="national_summary",
    )
    row = rows[0] if rows else {}
    return {
        "facilities": int(row.get("facilities") or 0),
        "states": int(row.get("states") or 0),
        "districts": int(row.get("districts") or 0),
        "demo_facilities": int(row.get("demo_facilities") or 0),
    }


def scope_facilities(state: str = "", district: str = "",
                     facility_id: str = "", limit: int = 12) -> list[dict]:
    """Real facilities representing the dashboard's current filter scope.

    Screens that show per-facility rows use this so they name facilities that
    actually exist in the district being viewed, rather than invented ones.
    """
    where = ["country_code = @cc", "facility_type = @phc"]
    params = [
        bigquery.ScalarQueryParameter("cc", "STRING", COUNTRY),
        bigquery.ScalarQueryParameter("phc", "STRING", PHC_TYPE),
    ]
    if facility_id:
        where = ["country_code = @cc", "facility_id = @fid"]
        params = [
            bigquery.ScalarQueryParameter("cc", "STRING", COUNTRY),
            bigquery.ScalarQueryParameter("fid", "STRING", facility_id),
        ]
    else:
        if state:
            where.append("admin_l1 = @state")
            params.append(
                bigquery.ScalarQueryParameter("state", "STRING", state)
            )
        if district:
            where.append("admin_l2 = @district")
            params.append(
                bigquery.ScalarQueryParameter("district", "STRING", district)
            )
    params.append(bigquery.ScalarQueryParameter("lim", "INT64", limit))

    return run_query(
        f"""
        SELECT
          facility_id, name, admin_l1, admin_l2,
          latitude, longitude, population_served
        FROM {FACILITIES}
        WHERE {' AND '.join(where)}
        ORDER BY name
        LIMIT @lim
        """,
        params,
        cache_key=f"scope:{state}:{district}:{facility_id}:{limit}",
    )


def get_facility(facility_id: str) -> dict | None:
    """One facility by id."""
    rows = run_query(
        f"""
        SELECT
          facility_id, name, admin_l1, admin_l2, admin_l3,
          facility_type, latitude, longitude,
          population_served, is_demo_facility
        FROM {FACILITIES}
        WHERE country_code = @cc AND facility_id = @fid
        LIMIT 1
        """,
        [
            bigquery.ScalarQueryParameter("cc", "STRING", COUNTRY),
            bigquery.ScalarQueryParameter("fid", "STRING", facility_id),
        ],
        cache_key=f"facility:{facility_id}",
    )
    return rows[0] if rows else None
