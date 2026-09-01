"""Surge signals, and scenario mode.

Two different things live here and the difference matters.

**Detected surges** are read from `surge_signals` and `surge_supply_impact`,
built by the ingestion modules from real HMIS months. Nothing is computed at
request time; the dashboard reads an answer.

**Scenario mode** is the opposite. The user picks a district, an ATC class and a
multiplier, and the answer is computed live against the current stock positions
and the same reorder-point formula the steady-state plan uses. It is not a
lookup into precomputed 2x/3x/5x rows and it is not an animation — an arbitrary
multiplier produces an arbitrary answer, because the arithmetic actually runs.
The three preset multipliers in `network_absorption` exist for the district
overview; scenario mode does not read them.

Guard rails: every scenario query is scoped to one district and one ATC class,
which is at most a few dozen rows of `reorder_status`, and goes through
`app.bq.run_query` like everything else.
"""

from __future__ import annotations

import os

from google.cloud import bigquery

from app.bq import run_query

PROJECT = os.getenv("GCP_PROJECT", "daysupply")
DATASET = os.getenv("BQ_DATASET", "daysupply")

SURGE_SIGNALS = f"`{PROJECT}.{DATASET}.surge_signals`"
SURGE_SUPPLY = f"`{PROJECT}.{DATASET}.surge_supply_impact`"
SURGE_RECOMMENDATIONS = f"`{PROJECT}.{DATASET}.surge_recommendations`"
NETWORK_ABSORPTION = f"`{PROJECT}.{DATASET}.network_absorption`"
REORDER_STATUS = f"`{PROJECT}.{DATASET}.reorder_status`"
FACILITIES = f"`{PROJECT}.{DATASET}.facilities`"
POPULATION_REACH = f"`{PROJECT}.{DATASET}.population_reach`"

SERVICE_LEVEL_Z = float(os.getenv("SERVICE_LEVEL_Z", "1.65"))
SURGE_SIGMA_EXPONENT = float(os.getenv("SURGE_SIGMA_EXPONENT", "1.0"))
SURGE_TRANSFER_MAX_KM = float(os.getenv("SURGE_TRANSFER_MAX_KM", "300"))

# A scenario multiplier outside this range is not a supply question.
MIN_MULTIPLIER = 1.0
MAX_MULTIPLIER = 20.0


class ScenarioError(ValueError):
    """The caller asked for something the model cannot answer."""


def get_surge_signals(state: str = "", district: str = "",
                      atc_class: str = "", month: str = "",
                      limit: int = 50) -> list[dict]:
    """Detected surges, largest first.

    Every threshold that the row was tested against is returned alongside it,
    so the UI can show why a near miss did not fire.
    """
    where = ["is_surge"]
    params: list[bigquery.ScalarQueryParameter] = []
    for column, value, name in (("state", state, "state"),
                                ("atc_class", atc_class, "atc_class"),
                                ("month", month, "month")):
        if value:
            where.append(f"{column} = @{name}")
            params.append(bigquery.ScalarQueryParameter(name, "STRING", value))
    if district:
        where.append("district_key = UPPER(@district)")
        params.append(
            bigquery.ScalarQueryParameter("district", "STRING", district))
    params.append(bigquery.ScalarQueryParameter("limit", "INT64", limit))

    return run_query(f"""
        SELECT state, district_key, atc_class, month,
               observed, expected, baseline, pooled_multiplier,
               surge_multiplier, z_modified, z_classical, mad,
               threshold_z, threshold_ratio, threshold_absolute,
               passes_statistic, passes_ratio, passes_magnitude
        FROM {SURGE_SIGNALS}
        WHERE {' AND '.join(where)}
        ORDER BY surge_multiplier DESC, z_modified DESC
        LIMIT @limit
    """, params)


def get_surge_impact(state: str = "", district: str = "",
                     atc_class: str = "", limit: int = 100) -> list[dict]:
    """Facilities whose supply answer a detected surge changes.

    Ordered so the facilities that cannot be resupplied in time come first —
    those are the ones where the recommendation is not "order more".
    """
    where = ["TRUE"]
    params: list[bigquery.ScalarQueryParameter] = []
    for column, value, name in (("state", state, "state"),
                                ("district", district, "district"),
                                ("atc_class", atc_class, "atc_class")):
        if value:
            where.append(f"{column} = @{name}")
            params.append(bigquery.ScalarQueryParameter(name, "STRING", value))
    params.append(bigquery.ScalarQueryParameter("limit", "INT64", limit))

    return run_query(f"""
        SELECT facility_id, facility_name, state, district,
               item_id, item_name, unit, ven_class, atc_class,
               surge_month, surge_multiplier, z_modified,
               driver_observed, driver_expected,
               lead_time_days, lead_time_is_estimated,
               on_hand,
               avg_daily_demand, reorder_point, days_of_cover,
               status_baseline,
               avg_daily_demand_surge, reorder_point_surge,
               days_of_cover_surge, days_to_stockout,
               needs_reorder, needs_reorder_surge, newly_at_risk,
               lead_time_decisive, surge_action, shortfall_units
        FROM {SURGE_SUPPLY}
        WHERE {' AND '.join(where)}
        ORDER BY lead_time_decisive DESC, newly_at_risk DESC,
                 days_to_stockout ASC
        LIMIT @limit
    """, params)


def current_surge_month() -> str:
    """The calendar month the live stock position sits in.

    `surge_recommendations` holds a row for every detected surge month, and
    those months are **alternative episodes, not a plan**. A donor's spare
    stock is one current position: it can be promised within a month, but
    summing across months would promise the same units twelve times. So every
    read of that table is scoped to a single month, and this is the default —
    the month the stock is actually in.
    """
    rows = run_query(f"""
        SELECT FORMAT_DATE('%B', MAX(as_of_date)) AS month
        FROM `{PROJECT}.{DATASET}.current_stock`
    """)
    return rows[0]["month"] if rows else ""


def get_surge_transfers(state: str = "", district: str = "",
                        month: str = "", limit: int = 100) -> list[dict]:
    """Transfers recommended under detected surge conditions, for one month.

    Scoped to a single surge month by construction — see
    `current_surge_month()` for why mixing months would over-promise donors.
    """
    month = month or current_surge_month()
    where = ["surge_month = @month"]
    params: list[bigquery.ScalarQueryParameter] = [
        bigquery.ScalarQueryParameter("month", "STRING", month)]
    if state:
        where.append("to_state = @state")
        params.append(bigquery.ScalarQueryParameter("state", "STRING", state))
    if district:
        where.append("to_district = @district")
        params.append(
            bigquery.ScalarQueryParameter("district", "STRING", district))
    params.append(bigquery.ScalarQueryParameter("limit", "INT64", limit))

    return run_query(f"""
        SELECT recommendation_id, to_facility_id, to_facility_name,
               to_state, to_district, from_facility_id, from_facility_name,
               requested_item_name, supplied_item_name, is_substitution,
               ven_class, unit, atc_class, surge_month, surge_multiplier,
               lead_time_decisive, surge_action, claim_rank,
               requested_quantity, quantity, donor_partially_exhausted,
               distance_km, receiver_lead_time,
               receiver_cover_before, receiver_cover_after,
               donor_cover_before, donor_cover_after, transfer_max_km
        FROM {SURGE_RECOMMENDATIONS}
        WHERE {' AND '.join(where)}
        ORDER BY lead_time_decisive DESC, claim_rank, distance_km
        LIMIT @limit
    """, params)


def get_absorption(state: str = "", district: str = "",
                   atc_class: str = "", limit: int = 200) -> list[dict]:
    """Can a district's own stock absorb a spike before resupply can land."""
    where = ["TRUE"]
    params: list[bigquery.ScalarQueryParameter] = []
    for column, value, name in (("state", state, "state"),
                                ("district", district, "district"),
                                ("atc_class", atc_class, "atc_class")):
        if value:
            where.append(f"{column} = @{name}")
            params.append(bigquery.ScalarQueryParameter(name, "STRING", value))
    params.append(bigquery.ScalarQueryParameter("limit", "INT64", limit))

    return run_query(f"""
        SELECT state, district, atc_class, ven_class, facilities, stock_rows,
               district_on_hand, district_daily_demand,
               slowest_lead_time, fastest_lead_time,
               multiplier, absorption_days, absorbs, units_short,
               max_multiplier_absorbed
        FROM {NETWORK_ABSORPTION}
        WHERE {' AND '.join(where)}
        ORDER BY district, atc_class, multiplier
        LIMIT @limit
    """, params)


def get_scenario_options() -> dict:
    """District and ATC-class combinations scenario mode can actually run.

    Only combinations with real stock positions are offered, so the UI cannot
    ask a question the data cannot answer.
    """
    rows = run_query(f"""
        SELECT state, district, atc_class,
               ANY_VALUE(ven_class)        AS ven_class,
               COUNT(DISTINCT facility_id) AS facilities,
               COUNT(DISTINCT item_name)   AS items,
               STRING_AGG(DISTINCT item_name ORDER BY item_name LIMIT 4)
                                           AS example_items,
               SUM(on_hand)                AS on_hand,
               MAX(lead_time_days)         AS slowest_lead_time
        FROM {REORDER_STATUS}
        WHERE atc_class IS NOT NULL AND avg_daily_demand > 0
        GROUP BY state, district, atc_class
        HAVING facilities >= 2
        ORDER BY state, district, atc_class
    """)
    return {
        "multipliers": [1.5, 2.0, 3.0, 5.0],
        "min_multiplier": MIN_MULTIPLIER,
        "max_multiplier": MAX_MULTIPLIER,
        "combinations": rows,
    }


def run_scenario(district: str, atc_class: str,
                 multiplier: float) -> dict:
    """Compute, live, what a spike of `multiplier` does to one district.

    Not a lookup. The reorder point, the day each facility runs out, whether an
    indent can arrive before it does, which transfers would be recommended and
    whether the district holds are all evaluated against current stock at the
    multiplier asked for.
    """
    if not district or not atc_class:
        raise ScenarioError("district and atc_class are both required")
    try:
        multiplier = float(multiplier)
    except (TypeError, ValueError):
        raise ScenarioError("multiplier must be a number") from None
    if not MIN_MULTIPLIER <= multiplier <= MAX_MULTIPLIER:
        raise ScenarioError(
            f"multiplier must be between {MIN_MULTIPLIER:g} and "
            f"{MAX_MULTIPLIER:g}; {multiplier:g} is outside what the model "
            "can say anything useful about")

    params = [
        bigquery.ScalarQueryParameter("district", "STRING", district),
        bigquery.ScalarQueryParameter("atc_class", "STRING", atc_class),
        bigquery.ScalarQueryParameter("m", "FLOAT64", multiplier),
    ]

    # The same formula as build_supply_plan.py and build_surge_supply.py, run
    # at request time against whatever multiplier was asked for.
    facilities = run_query(f"""
        WITH scoped AS (
          SELECT *,
                 avg_daily_demand * @m AS mu_surge,
                 IFNULL(demand_std_dev, 0)
                   * POW(@m, {SURGE_SIGMA_EXPONENT}) AS sigma_surge
          FROM {REORDER_STATUS}
          WHERE district = @district AND atc_class = @atc_class
            AND avg_daily_demand > 0
        )
        SELECT
          facility_id, facility_name, state, district,
          item_id, item_name, unit, ven_class,
          lead_time_days, lead_time_is_estimated,
          on_hand, avg_daily_demand, reorder_point, days_of_cover,
          needs_reorder, status AS status_baseline,
          ROUND(mu_surge, 2) AS avg_daily_demand_surge,
          ROUND(mu_surge * lead_time_days
                + {SERVICE_LEVEL_Z} * sigma_surge * SQRT(lead_time_days), 1)
                             AS reorder_point_surge,
          ROUND(SAFE_DIVIDE(on_hand, mu_surge), 1) AS days_to_stockout,
          (SAFE_DIVIDE(on_hand, mu_surge) < lead_time_days)
                             AS lead_time_decisive,
          (on_hand < mu_surge * lead_time_days
           + {SERVICE_LEVEL_Z} * sigma_surge * SQRT(lead_time_days))
                             AS needs_reorder_surge,
          GREATEST(ROUND(mu_surge * lead_time_days
                   + {SERVICE_LEVEL_Z} * sigma_surge * SQRT(lead_time_days)
                   - on_hand, 0), 0) AS shortfall_units,
          CASE
            WHEN SAFE_DIVIDE(on_hand, mu_surge) < lead_time_days
              THEN 'transfer_only'
            WHEN on_hand < mu_surge * lead_time_days
                 + {SERVICE_LEVEL_Z} * sigma_surge * SQRT(lead_time_days)
              THEN 'reorder_now'
            ELSE 'holds'
          END                AS surge_action
        FROM scoped
        ORDER BY days_to_stockout ASC, facility_name
    """, params)

    if not facilities:
        raise ScenarioError(
            f"no stock positions for {atc_class} in {district}; scenario mode "
            "only runs where there is real stock to run it against")

    # Transfers, computed at this multiplier. A donor must still be able to
    # cover itself at the same multiplier — a spike hits the whole district.
    transfers = run_query(f"""
        WITH scoped AS (
          -- Columns projected explicitly. The guard rails bar a star-select
          -- in any query touching the facility master, and rightly so --
          -- including, as it turns out, one written inside a comment.
          SELECT
            r.facility_id, r.facility_name, r.item_id, r.item_name,
            r.unit, r.ven_class, r.on_hand, r.avg_daily_demand,
            r.lead_time_days,
            f.latitude, f.longitude,
            r.avg_daily_demand * @m AS mu_surge,
            r.avg_daily_demand * @m * r.lead_time_days
              + {SERVICE_LEVEL_Z} * IFNULL(r.demand_std_dev, 0)
                * POW(@m, {SURGE_SIGMA_EXPONENT})
                * SQRT(r.lead_time_days) AS rp_surge
          FROM {REORDER_STATUS} r
          JOIN {FACILITIES} f ON f.facility_id = r.facility_id
          WHERE r.district = @district AND r.atc_class = @atc_class
            AND r.avg_daily_demand > 0 AND f.has_valid_coords
        ),
        -- Also projected explicitly. The guard rail is a whole-query text
        -- check, and it is worth more as a strict rule than a convenience.
        need AS (
          SELECT facility_id, facility_name, item_id, item_name, unit,
                 ven_class, on_hand, avg_daily_demand, lead_time_days,
                 latitude, longitude, mu_surge, rp_surge
          FROM scoped WHERE on_hand < rp_surge
        ),
        spare AS (
          SELECT facility_id, facility_name, item_id, item_name,
                 on_hand, avg_daily_demand, latitude, longitude,
                 on_hand - rp_surge AS spare_units
          FROM scoped WHERE on_hand > rp_surge
        )
        SELECT
          n.facility_id     AS to_facility_id,
          n.facility_name   AS to_facility_name,
          n.item_name       AS requested_item_name,
          n.ven_class, n.unit,
          n.lead_time_days  AS receiver_lead_time,
          (SAFE_DIVIDE(n.on_hand, n.mu_surge) < n.lead_time_days)
                            AS lead_time_decisive,
          s.facility_id     AS from_facility_id,
          s.facility_name   AS from_facility_name,
          s.item_name       AS supplied_item_name,
          (s.item_id != n.item_id) AS is_substitution,
          CAST(LEAST(n.rp_surge * 1.5 - n.on_hand, s.spare_units)
               AS INT64)    AS quantity,
          ROUND(ST_DISTANCE(ST_GEOGPOINT(n.longitude, n.latitude),
                            ST_GEOGPOINT(s.longitude, s.latitude)) / 1000.0, 1)
                            AS distance_km,
          ROUND(SAFE_DIVIDE(n.on_hand, n.mu_surge), 1) AS days_to_stockout
        FROM need n
        JOIN spare s ON s.facility_id != n.facility_id
        WHERE ST_DISTANCE(ST_GEOGPOINT(n.longitude, n.latitude),
                          ST_GEOGPOINT(s.longitude, s.latitude)) / 1000.0
              <= {SURGE_TRANSFER_MAX_KM}
        QUALIFY ROW_NUMBER() OVER (
          PARTITION BY n.facility_id, n.item_id
          ORDER BY (s.item_id != n.item_id), distance_km) = 1
        ORDER BY lead_time_decisive DESC, days_to_stockout
    """, params)
    transfers = [t for t in transfers if (t.get("quantity") or 0) >= 1]

    district_on_hand = sum(f["on_hand"] or 0 for f in facilities)
    district_daily = sum(f["avg_daily_demand"] or 0 for f in facilities)
    slowest = max((f["lead_time_days"] or 0) for f in facilities)
    surge_daily = district_daily * multiplier
    # Rounded first, then compared. The UI shows "3.4 days against an 8-day
    # lead time"; the verdict has to follow from the figure the reader sees,
    # not from a hidden extra decimal.
    absorption_days = (round(district_on_hand / surge_daily, 1)
                       if surge_daily else None)
    holds = bool(absorption_days is not None and absorption_days >= slowest)

    failing = [f for f in facilities if f["surge_action"] != "holds"]
    transfer_only = [f for f in facilities if f["lead_time_decisive"]]
    first_out = min((f["days_to_stockout"] for f in facilities
                     if f["days_to_stockout"] is not None), default=None)

    # How large a spike this district could take before it stops absorbing.
    # Below 1.0 the district cannot cover its *normal* demand across its own
    # lead time — which is a finding about the network, not a model defect,
    # and has to be labelled as one wherever it surfaces.
    max_absorbed = (round(district_on_hand / (district_daily * slowest), 2)
                    if district_daily and slowest else None)
    structurally_thin = bool(max_absorbed is not None and max_absorbed < 1.0)

    if holds:
        verdict = (
            f"The district holds. Pooled stock covers {absorption_days:.1f} "
            f"days at {multiplier:g}x, against a slowest lead time of "
            f"{slowest} days, so resupply can land before the district runs "
            "dry.")
    elif transfers:
        verdict = (
            f"The district does not hold on its own. Pooled stock covers "
            f"{absorption_days:.1f} days at {multiplier:g}x against a "
            f"{slowest}-day slowest lead time, leaving a gap. "
            f"{len(transfers)} transfer(s) close part of it; the rest needs "
            "resupply from outside the district.")
    else:
        verdict = (
            f"The district does not hold and cannot fix it internally. "
            f"Pooled stock covers {absorption_days:.1f} days at "
            f"{multiplier:g}x against a {slowest}-day slowest lead time, and "
            "no facility has spare stock to donate. This needs stock from "
            "outside the district.")

    if structurally_thin:
        verdict += (
            f" Note that this district absorbs at most {max_absorbed:g}x — "
            "below 1.0, meaning its pooled stock does not cover even its "
            "normal demand across its own lead time. That is a finding about "
            "how thinly this district is stocked, not a consequence of the "
            "scenario: it is true before any surge.")

    return {
        "district": district,
        "atc_class": atc_class,
        "multiplier": multiplier,
        "computed_live": True,
        "max_multiplier_absorbed": max_absorbed,
        "structurally_thin": structurally_thin,
        "structurally_thin_note": (
            "The district's pooled stock does not cover its normal demand "
            "across its own lead time, before any surge is applied. This is a "
            "measured property of the stock position, not a model artefact."
        ) if structurally_thin else None,
        "method": (
            "reorder_point = demand x multiplier x lead_time + "
            f"{SERVICE_LEVEL_Z} x sigma x multiplier^{SURGE_SIGMA_EXPONENT:g} "
            "x sqrt(lead_time) — the same formula as the steady-state plan, "
            "evaluated against current stock at the multiplier you chose"),
        "facility_count": len(facilities),
        "facilities_failing": len(failing),
        "facilities_transfer_only": len(transfer_only),
        "first_stockout_days": first_out,
        "district_on_hand": district_on_hand,
        "district_daily_demand": round(district_daily, 2),
        "district_daily_demand_surge": round(surge_daily, 2),
        "slowest_lead_time": slowest,
        "absorption_days": absorption_days or 0,
        "district_holds": holds,
        # Same rule as network_absorption: a district that absorbs the spike
        # is not short, and must never be reported as both.
        "units_short": 0 if holds else max(
            int(round(surge_daily * slowest - district_on_hand)), 0),
        "verdict": verdict,
        "facilities": facilities,
        "transfers": transfers,
    }


def get_population_reach() -> dict:
    """Reach, counted once. See ingestion/build_population_reach.py."""
    rows = run_query(f"""
        SELECT tier, description, phcs, states, districts, population,
               mean_catchment, pct_of_census_2011_rural,
               census_2011_rural_india
        FROM {POPULATION_REACH} ORDER BY tier_order
    """)
    return {
        "tiers": rows,
        "counted": (
            "Rural PHC catchments only. Sub-centre, PHC and CHC catchments "
            "cover the same people, so counting every facility type would "
            "count most of rural India three times."),
        "assumed": (
            "That each PHC serves its state's average rural catchment. No "
            "per-facility catchment is published anywhere in India, so a "
            "state x facility-type average is the finest granularity that "
            "exists."),
        "excluded": (
            "Urban PHCs contribute zero — the Rural Health Statistics figure "
            "is a rural average and applying it to urban PHCs would be a "
            "category error."),
        "direction_of_error": (
            "The population base is Census 2011. India's rural population has "
            "grown since, so these figures understate current reach."),
    }
