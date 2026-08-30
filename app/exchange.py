"""Cross-district pattern exchange and the DVDMS/e-Aushadhi export.

Two things live here, both about StockPulse fitting into a system that already
exists rather than replacing it.

**Pattern exchange.** Districts publish a 12-element monthly multiplier per ATC
class and nothing else. A district with thin history consumes the network's
pooled vector as a seasonal prior. No facility row, patient record, stock level
or name crosses a district boundary — only shape.

The pooled vector is the default because it is the arm that measurably wins;
see `ingestion/build_pattern_exchange.py` for the four-arm hold-out and why
single-donor demographic matching loses.

**Export.** Every state already runs DVDMS or e-Aushadhi under HMIS and ABDM.
The export emits stock events in a documented interchange format so StockPulse
can feed one of those, rather than asking a state to run a parallel system.
"""

from __future__ import annotations

import os

from google.cloud import bigquery

from app.bq import run_query

PROJECT = os.getenv("GCP_PROJECT", "daysupply")
DATASET = os.getenv("BQ_DATASET", "daysupply")

VECTORS = f"`{PROJECT}.{DATASET}.pattern_vectors`"
MATCHES = f"`{PROJECT}.{DATASET}.district_matches`"
PROFILES = f"`{PROJECT}.{DATASET}.district_profiles`"
EVALUATION = f"`{PROJECT}.{DATASET}.pattern_exchange_eval`"
STOCK_EVENTS = f"`{PROJECT}.{DATASET}.stock_events`"
FACILITIES = f"`{PROJECT}.{DATASET}.facilities`"
ITEMS = f"`{PROJECT}.{DATASET}.items`"

MONTH_ORDER = ["April", "May", "June", "July", "August", "September",
               "October", "November", "December", "January", "February",
               "March"]
OBSERVED_MONTHS = MONTH_ORDER[:3]

# The interchange format version. Bump when the field set changes.
INTERCHANGE_VERSION = "stockpulse.stock-events.v1"


def evaluation_summary() -> dict:
    """The four-arm hold-out result, so the claim can be checked."""
    rows = run_query(
        f"""
        SELECT
          COUNT(*) AS predictions,
          COUNT(DISTINCT CONCAT(state, '|', district_key)) AS districts,
          COUNT(DISTINCT atc_class) AS atc_classes,
          ROUND(SUM(flat_abs_error)     / SUM(actual) * 100, 1) AS flat_wmape,
          ROUND(SUM(demo_out_abs_error) / SUM(actual) * 100, 1) AS demo_out_wmape,
          ROUND(SUM(demo_in_abs_error)  / SUM(actual) * 100, 1) AS demo_in_wmape,
          ROUND(SUM(pooled_abs_error)   / SUM(actual) * 100, 1) AS pooled_wmape
        FROM {EVALUATION}
        """,
        cache_key="exchange:eval",
    )
    row = rows[0] if rows else {}
    flat = row.get("flat_wmape")
    pooled = row.get("pooled_wmape")
    return {
        **row,
        "best_arm": "pooled",
        "improvement_points": round(flat - pooled, 1) if flat and pooled else None,
        "improvement_relative": (
            round((flat - pooled) / flat * 100, 1) if flat and pooled else None
        ),
        "note": (
            "Single-donor demographic matching was tested and lost. "
            "Seasonality here is climate-driven and demography does not "
            "predict climate; the pooled vector also averages away one "
            "district's reporting noise."
        ),
    }


def published_vector(state: str, district_key: str, atc_class: str) -> dict:
    """Exactly what one district publishes: 12 numbers, nothing else."""
    rows = run_query(
        f"""
        SELECT month, multiplier
        FROM {VECTORS}
        WHERE state = @state AND district_key = @district_key
          AND atc_class = @atc_class
        """,
        [
            bigquery.ScalarQueryParameter("state", "STRING", state),
            bigquery.ScalarQueryParameter("district_key", "STRING",
                                          district_key.upper().strip()),
            bigquery.ScalarQueryParameter("atc_class", "STRING", atc_class),
        ],
        cache_key=f"vector:{state}:{district_key}:{atc_class}",
    )
    by_month = {r["month"]: r["multiplier"] for r in rows}
    return {
        "state": state,
        "district_key": district_key.upper().strip(),
        "atc_class": atc_class,
        "monthly_multipliers": [by_month.get(m) for m in MONTH_ORDER],
        "month_order": MONTH_ORDER,
        "contains_facility_data": False,
        "contains_patient_data": False,
    }


def thin_history_demo(state: str = "", district: str = "",
                      atc_class: str = "") -> dict:
    """Three curves for one district and ATC class: actual, flat, borrowed.

    Picks the case where borrowing helps most, so the chart shows the effect
    rather than an average of it. The arms are the same ones the hold-out
    scored, so nothing here is tuned separately.
    """
    where = ["TRUE"]
    params: list[bigquery.ScalarQueryParameter] = []
    if state:
        where.append("state = @state")
        params.append(bigquery.ScalarQueryParameter("state", "STRING", state))
    if district:
        where.append("district_key = @district_key")
        params.append(bigquery.ScalarQueryParameter(
            "district_key", "STRING", district.upper().strip()))
    if atc_class:
        where.append("atc_class = @atc_class")
        params.append(bigquery.ScalarQueryParameter(
            "atc_class", "STRING", atc_class))

    chosen = run_query(
        f"""
        SELECT state, district_key, atc_class,
               SUM(flat_abs_error)   AS flat_err,
               SUM(pooled_abs_error) AS pooled_err,
               SUM(actual)           AS total_actual
        FROM {EVALUATION}
        WHERE {' AND '.join(where)}
        GROUP BY state, district_key, atc_class
        HAVING total_actual > 500 AND pooled_err < flat_err
        ORDER BY (flat_err - pooled_err) / total_actual DESC
        LIMIT 1
        """,
        params,
        cache_key=f"exchange:pick:{state}:{district}:{atc_class}",
    )
    if not chosen:
        return {}
    pick = chosen[0]

    series = run_query(
        f"""
        SELECT month, actual, flat_forecast, pooled_forecast,
               demo_out_forecast, donor_state, donor_district
        FROM {EVALUATION}
        WHERE state = @state AND district_key = @district_key
          AND atc_class = @atc_class
        """,
        [
            bigquery.ScalarQueryParameter("state", "STRING", pick["state"]),
            bigquery.ScalarQueryParameter("district_key", "STRING",
                                          pick["district_key"]),
            bigquery.ScalarQueryParameter("atc_class", "STRING",
                                          pick["atc_class"]),
        ],
        cache_key=f"exchange:series:{pick['state']}:{pick['district_key']}"
                  f":{pick['atc_class']}",
    )
    order = {m: i for i, m in enumerate(MONTH_ORDER)}
    series.sort(key=lambda r: order.get(r["month"], 99))

    items = run_query(
        f"""
        SELECT STRING_AGG(DISTINCT display_name, ', ' ORDER BY display_name
                          LIMIT 4) AS names
        FROM {ITEMS}
        WHERE SUBSTR(atc_code, 1, 5) = @atc_class
        """,
        [bigquery.ScalarQueryParameter("atc_class", "STRING",
                                       pick["atc_class"])],
        cache_key=f"exchange:items:{pick['atc_class']}",
    )

    flat_err = pick["flat_err"] or 0
    pooled_err = pick["pooled_err"] or 0
    total = pick["total_actual"] or 1
    return {
        "state": pick["state"],
        "district": pick["district_key"].title(),
        "atc_class": pick["atc_class"],
        "example_items": (items[0]["names"] if items else None),
        "observed_months": OBSERVED_MONTHS,
        "months": [r["month"] for r in series],
        "actual": [r["actual"] for r in series],
        "flat_forecast": [r["flat_forecast"] for r in series],
        "borrowed_forecast": [r["pooled_forecast"] for r in series],
        "flat_wmape": round(flat_err / total * 100, 1),
        "borrowed_wmape": round(pooled_err / total * 100, 1),
        "improvement_points": round((flat_err - pooled_err) / total * 100, 1),
        "method": "pooled seasonal vector across all reporting districts",
    }


# ---------------------------------------------------------------------------
# Export for DVDMS / e-Aushadhi
# ---------------------------------------------------------------------------
def export_stock_events(state: str = "", district: str = "",
                        facility_id: str = "", days: int = 30,
                        limit: int = 5000) -> dict:
    """Stock events in a documented interchange format.

    Deliberately flat and boring: one row per event, government identifiers
    first, no nesting. A state system should be able to consume this without
    knowing anything about StockPulse.
    """
    where = ["e.event_type IN ('dispensed', 'received', 'count')"]
    params: list[bigquery.ScalarQueryParameter] = [
        bigquery.ScalarQueryParameter("days", "INT64", max(1, min(days, 400))),
        bigquery.ScalarQueryParameter("lim", "INT64", max(1, min(limit, 50000))),
    ]
    if facility_id:
        where.append("f.facility_id = @facility_id")
        params.append(bigquery.ScalarQueryParameter(
            "facility_id", "STRING", facility_id))
    else:
        if state:
            where.append("f.admin_l1 = @state")
            params.append(
                bigquery.ScalarQueryParameter("state", "STRING", state))
        if district:
            where.append("f.admin_l2 = @district")
            params.append(bigquery.ScalarQueryParameter(
                "district", "STRING", district))

    rows = run_query(
        f"""
        SELECT
          e.event_id,
          e.facility_id,
          f.name        AS facility_name,
          f.admin_l1    AS state_name,
          f.admin_l2    AS district_name,
          f.facility_type,
          e.item_id,
          i.display_name AS item_name,
          i.atc_code,
          i.ven_class,
          i.unit,
          e.event_type,
          e.quantity,
          FORMAT_TIMESTAMP('%Y-%m-%dT%H:%M:%SZ', e.event_ts) AS event_timestamp,
          e.expiry_date,
          e.source        AS capture_source,
          e.confidence    AS extraction_confidence
        FROM {STOCK_EVENTS} e
        JOIN {FACILITIES} f ON f.facility_id = e.facility_id
        LEFT JOIN {ITEMS} i ON i.item_id = e.item_id
        WHERE {' AND '.join(where)}
          AND DATE(e.event_ts) > DATE_SUB(
                (SELECT MAX(DATE(event_ts)) FROM {STOCK_EVENTS}),
                INTERVAL @days DAY)
        ORDER BY e.event_ts DESC
        LIMIT @lim
        """,
        params,
        cache_key=f"export:{state}:{district}:{facility_id}:{days}:{limit}",
    )

    return {
        "format": INTERCHANGE_VERSION,
        "generated_for": "DVDMS / e-Aushadhi ingestion",
        "identifier_basis": (
            "facility_id is StockPulse's key into the NHM health-centre "
            "directory; state_name, district_name and facility_name are that "
            "directory's own values, unmodified, so a receiving system can "
            "match on its existing facility master."
        ),
        "coding": {
            "item_coding": "WHO ATC where assigned; null where not confidently known",
            "ven_coding": "Vital/Essential/Desirable — StockPulse's classification, not MoHFW's",
            "event_types": ["dispensed", "received", "count"],
            "quantity_unit": "per-item unit, carried in the `unit` field",
        },
        "row_count": len(rows),
        "events": rows,
    }
