"""Facility queries against BigQuery — the real 200,438-row facility master.

This module is the only source of geography in the application. There are no
hardcoded state, district or facility lists anywhere: the dropdowns list what is
actually in `daysupply.facilities`, which is every health facility in India.

All queries project explicit columns (never `SELECT *`) and every reference
query is cached, because the facility master changes only when it is reloaded.
"""

from __future__ import annotations

from google.cloud import bigquery

from app.bq import FACILITIES, GEO_SUMMARY, run_query

COUNTRY = "IN"

# Facility types that can be selected as a reporting unit in the dashboard.
# PHCs are the unit the product is built around.
PHC_TYPE = "phc"

# District spellings that differ between government sources. Both are real and
# both stay in the data: HMIS says "Ahmadnagar", the facility directory says
# "Ahmednagar", and rewriting either to fit a join is how undetectable errors
# get introduced. This map is presentation only — it changes what a dropdown
# shows, never what is stored or joined on.
DISTRICT_DISPLAY_NAMES = {
    ("Maharashtra", "AHMADNAGAR"): "Ahmednagar",
}


def display_district(state: str, district: str) -> str:
    """The spelling to show a user. The stored value is untouched."""
    return DISTRICT_DISPLAY_NAMES.get(
        (state, (district or "").upper().strip()), district)


FACILITY_TYPE_LABELS = {
    "sub_cen": "Sub-Centre",
    "phc": "Primary Health Centre",
    "chc": "Community Health Centre",
    "dis_h": "District Hospital",
    "s_t_h": "State Hospital",
}


def _geo_rows() -> list[dict]:
    """The whole geo summary — ~740 rows, fetched once and held in process.

    One small query serves every state and district dropdown for the life of
    the container, so a visitor never waits on a BigQuery round trip for
    geography after the first.
    """
    return run_query(
        f"""
        SELECT level, state, district, facility_count, phc_count,
               district_count, demo_count, population_served
        FROM {GEO_SUMMARY}
        ORDER BY state, district
        """,
        cache_key="geo_summary",
    )


def prewarm() -> int:
    """Populate the geography cache. Called at startup, off the request path."""
    return len(_geo_rows())


def list_states() -> list[dict]:
    """Every state/UT present in the facility master, with facility counts."""
    return [
        {
            "state": row["state"],
            "facility_count": row["facility_count"],
            "phc_count": row["phc_count"],
            "district_count": row["district_count"],
        }
        for row in _geo_rows()
        if row["level"] == "state"
    ]


def list_districts(state: str) -> list[dict]:
    """Districts within a state, with facility counts."""
    if not state:
        return []
    return [
        {
            "district": row["district"],
            "display_name": display_district(state, row["district"]),
            "facility_count": row["facility_count"],
            "phc_count": row["phc_count"],
        }
        for row in _geo_rows()
        if row["level"] == "district" and row["state"] == state
    ]


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


def _totals(rows: list[dict]) -> dict:
    return {
        "facilities": sum(r["facility_count"] for r in rows),
        "phcs": sum(r["phc_count"] for r in rows),
        "demo_facilities": sum(r["demo_count"] for r in rows),
        "population_served": sum(r["population_served"] or 0 for r in rows),
    }


def facility_counts(state: str = "", district: str = "",
                    facility_id: str = "") -> dict:
    """Facility counts for the current filter scope.

    Served from the geo summary, so changing the state filter does not cost a
    BigQuery round trip. Narrowing to a single facility returns that facility.
    """
    if facility_id:
        facility = get_facility(facility_id)
        if facility is None:
            return {"facilities": 0, "phcs": 0, "demo_facilities": 0,
                    "states": 0, "districts": 0, "population_served": 0}
        is_phc = facility.get("facility_type") == PHC_TYPE
        return {
            "facilities": 1,
            "phcs": 1 if is_phc else 0,
            "demo_facilities": 1 if facility.get("is_demo_facility") else 0,
            "states": 1,
            "districts": 1,
            "population_served": int(facility.get("population_served") or 0),
        }

    rows = _geo_rows()
    if district:
        scope = [r for r in rows if r["level"] == "district"
                 and r["state"] == state and r["district"] == district]
        districts = len(scope)
    elif state:
        scope = [r for r in rows if r["level"] == "state" and r["state"] == state]
        districts = sum(r["district_count"] for r in scope)
    else:
        scope = [r for r in rows if r["level"] == "state"]
        districts = sum(r["district_count"] for r in scope)

    return {
        **_totals(scope),
        "states": len({r["state"] for r in scope}),
        "districts": districts,
    }


def national_summary() -> dict:
    """Headline national coverage figures — every facility in the country."""
    states = [r for r in _geo_rows() if r["level"] == "state"]
    districts = [r for r in _geo_rows() if r["level"] == "district"]
    totals = _totals(states)
    # Two different counts, and only one of them answers "how many districts".
    #
    #   701 — state x district pairs. This is the district count.
    #   668 — distinct district *names*. Lower, because names such as
    #         Aurangabad and Bilaspur recur across states, so counting names
    #         alone merges 33 genuinely different districts into one another.
    #
    # `districts` is the pair count, because that is the honest answer to the
    # question the dashboard is asking. The name count is returned alongside it
    # so the difference is visible rather than hidden, and so nothing downstream
    # has to guess which one it is looking at. See docs/CLAIMS.md section 1.
    return {
        "facilities": totals["facilities"],
        "states": len(states),
        "districts": len(districts),
        "district_names": len({r["district"] for r in districts}),
        "district_count_basis": (
            "state x district pairs; 33 district names recur across states, "
            "so counting distinct names alone undercounts by 33"),
        "demo_facilities": totals["demo_facilities"],
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
