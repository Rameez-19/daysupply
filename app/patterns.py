"""Aggregate seasonal pattern exchange.

A district with thin history borrows the seasonal shape of demand from a
district that has years of it, matched on ATC class. Only a 12-element monthly
multiplier vector per ATC class ever moves — no facility rows, no patient data,
no raw records.

The vectors are computed from the real HMIS 2019-20 series in
`demand_reference`. Each item names an HMIS indicator as its `demand_driver`,
and items are grouped by the first four characters of their ATC code, which is
the WHO therapeutic subgroup — P01B is antimalarials, C09A is ACE inhibitors.

March is excluded from the baseline for the same reason as everywhere else in
this codebase: HMIS 2019-20 ends in March 2020, the month India locked down,
and that month's fall is service disruption rather than seasonality.
"""

from __future__ import annotations

import os
from typing import List

from fastapi import HTTPException
from google.cloud import bigquery
from pydantic import BaseModel

from app.bq import run_query

PROJECT = os.getenv("GCP_PROJECT", os.getenv("GOOGLE_CLOUD_PROJECT", "daysupply"))
DATASET = os.getenv("BQ_DATASET", "daysupply")

DEMAND_REF = f"`{PROJECT}.{DATASET}.demand_reference`"
ITEMS = f"`{PROJECT}.{DATASET}.items`"

MONTH_ORDER = ["January", "February", "March", "April", "May", "June", "July",
               "August", "September", "October", "November", "December"]
BASELINE_MONTHS = MONTH_ORDER[3:12]  # April - December
COVID_MONTH = "March"


class PatternNode(BaseModel):
    country_code: str
    atc_code: str
    monthly_coefficients: List[float]  # 12 elements, index 0 = January
    source_district: str | None = None
    based_on_indicator: str | None = None


def get_local_patterns(district: str = "") -> List[PatternNode]:
    """Real monthly seasonal multipliers per ATC class, from HMIS data."""
    params = []
    where = ""
    if district:
        where = "AND UPPER(TRIM(d.admin_l2)) = UPPER(TRIM(@district))"
        params.append(
            bigquery.ScalarQueryParameter("district", "STRING", district))

    rows = run_query(
        f"""
        WITH item_drivers AS (
          SELECT DISTINCT SUBSTR(atc_code, 1, 4) AS atc_class, demand_driver
          FROM {ITEMS}
          WHERE atc_code IS NOT NULL AND demand_driver IS NOT NULL
        ),
        monthly AS (
          SELECT
            i.atc_class,
            i.demand_driver,
            d.month,
            SUM(d.value) AS value
          FROM {DEMAND_REF} d
          JOIN item_drivers i ON i.demand_driver = d.indicator
          WHERE TRUE {where}
          GROUP BY i.atc_class, i.demand_driver, d.month
        ),
        baseline AS (
          SELECT atc_class, AVG(value) AS baseline
          FROM monthly
          WHERE month IN UNNEST(@baseline_months)
          GROUP BY atc_class
        )
        SELECT
          m.atc_class,
          ANY_VALUE(m.demand_driver) AS demand_driver,
          ARRAY_AGG(
            STRUCT(m.month AS month,
                   SAFE_DIVIDE(m.value, b.baseline) AS multiplier)
          ) AS points
        FROM monthly m
        JOIN baseline b USING (atc_class)
        WHERE b.baseline > 0
        GROUP BY m.atc_class
        ORDER BY m.atc_class
        """,
        params + [bigquery.ArrayQueryParameter(
            "baseline_months", "STRING", BASELINE_MONTHS)],
        cache_key=f"patterns:{district}",
    )

    patterns: List[PatternNode] = []
    for row in rows:
        by_month = {p["month"]: p["multiplier"] for p in row["points"]}
        coefficients = []
        for month in MONTH_ORDER:
            # March is a lockdown artefact; hold it at the baseline.
            value = 1.0 if month == COVID_MONTH else by_month.get(month)
            coefficients.append(round(float(value if value else 1.0), 3))
        patterns.append(PatternNode(
            country_code="IN",
            atc_code=row["atc_class"],
            monthly_coefficients=coefficients,
            source_district=district or "Telangana (all districts)",
            based_on_indicator=row["demand_driver"],
        ))
    return patterns


def ingest_peer_pattern(pattern: PatternNode):
    """Store a peer district's vector as a prior for thin-history forecasting."""
    from google.cloud import firestore
    if len(pattern.monthly_coefficients) != 12:
        raise HTTPException(
            status_code=422,
            detail="monthly_coefficients must have exactly 12 elements",
        )
    try:
        db = firestore.Client(project=PROJECT)
        doc = db.collection("pattern_vectors").document(
            f"{pattern.country_code}_{pattern.atc_code}")
        doc.set({
            "country_code": pattern.country_code,
            "atc_code": pattern.atc_code,
            "monthly_coefficients": pattern.monthly_coefficients,
            "source_district": pattern.source_district,
            "based_on_indicator": pattern.based_on_indicator,
            "ingested_at": firestore.SERVER_TIMESTAMP,
        })
        return {
            "status": "success",
            "message": f"Ingested {pattern.atc_code} from "
                       f"{pattern.source_district or pattern.country_code}",
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
