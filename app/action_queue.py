"""The action queue, triaged by what can actually be done about each shortage.

## Why this replaces a list of everything

The page used to open with "Everything that is failing" — all 597 shortages —
above a queue of 527 transfers awaiting approval. **525 of those 597 rows
already appeared in the queue below with an Approve button on them**, so the
first list was 88% a restatement of the second, which is exactly why it read as
a log with nothing to do.

What that duplication hid was the 72 shortages with **no transfer available at
all** — nothing within reach to move — and inside those, the ones where an
order placed today would not arrive before the shelf is empty.

## Three states, and every shortage is in exactly one

    597 shortages
    ├─ 525  a transfer is waiting          -> approve it
    └─  72  nothing nearby to move
       ├─ 33  an order arrives in time     -> procure, with a deadline
       └─ 39  an order does NOT arrive     -> escalate; nothing routine works
              (5 of them life-saving)

The third group is the point. **Sonawade is at zero Albendazole with a 13-day
delivery time**: there is nothing to move and nothing to order that arrives
soon enough, so it needs a decision no dashboard can make on its own. Thirty-
nine of those existed the whole time, in row three hundred of a list nobody
could act on.

The split is mutually exclusive and exhaustive by construction, and a test
asserts the three counts sum to the total — because the failure mode here is a
shortage falling through the gap between two panels and being seen by nobody.

## What "in time" means

`days_of_cover < lead_time_days` — the stock runs out before a delivery could
physically arrive. Lead time is derived from real road distance to the district
headquarters, with a documented days-per-km conversion; the distance is real
and the conversion is a stated proxy.
"""

from __future__ import annotations

import os

from google.cloud import bigquery

from app.bq import run_query

PROJECT = os.getenv("GCP_PROJECT", "daysupply")
DATASET = os.getenv("BQ_DATASET", "daysupply")
D = f"{PROJECT}.{DATASET}"


def _where(state: str, district: str, phc: str) -> str:
    parts = ["needs_reorder"]
    if state:
        parts.append("state = @state")
    if district:
        parts.append("district = @district")
    if phc:
        parts.append("facility_id = @phc")
    return " AND ".join(parts)


def triage(state: str = "", district: str = "", phc: str = "") -> dict:
    """Split every shortage by what can be done about it."""
    params = []
    if state:
        params.append(bigquery.ScalarQueryParameter("state", "STRING", state))
    if district:
        params.append(
            bigquery.ScalarQueryParameter("district", "STRING", district))
    if phc:
        params.append(bigquery.ScalarQueryParameter("phc", "STRING", phc))

    rows = run_query(f"""
    WITH short AS (
      SELECT facility_id, facility_name, state, district,
             item_id, item_name, unit, ven_class,
             on_hand, reorder_point, days_of_cover, lead_time_days,
             lead_time_is_estimated, distance_to_hq_km, status,
             GREATEST(CAST(ROUND(reorder_point - on_hand) AS INT64), 0) AS shortfall
      FROM `{D}.reorder_status`
      WHERE {_where(state, district, phc)}
    ),
    -- A shortage counts as covered if any transfer already proposes to fill
    -- it. `recommendations` is keyed by the RECEIVING facility and the item it
    -- asked for, which is the same pair a shortage is keyed by.
    covered AS (
      SELECT DISTINCT to_facility_id AS facility_id,
             requested_item_id AS item_id
      FROM `{D}.recommendations`
    )
    SELECT
      s.facility_id, s.facility_name, s.state, s.district,
      s.item_id, s.item_name, s.unit, s.ven_class,
      s.on_hand, s.reorder_point, s.shortfall, s.days_of_cover,
      s.lead_time_days, s.lead_time_is_estimated, s.distance_to_hq_km, s.status,
      c.facility_id IS NOT NULL AS has_transfer,
      -- Unknown cover is not treated as "too late": an unmeasured line is
      -- unmeasured, and calling it an emergency would put a guess at the top
      -- of the page that most needs to be trusted.
      (c.facility_id IS NULL
       AND s.days_of_cover IS NOT NULL
       AND s.days_of_cover < s.lead_time_days) AS too_late_to_order
    FROM short s
    LEFT JOIN covered c
      ON c.facility_id = s.facility_id AND c.item_id = s.item_id
    ORDER BY s.days_of_cover, s.ven_class
    """, params, cache_key=f"triage:{state}:{district}:{phc}", ttl=300)

    all_rows = [dict(r) for r in rows]
    transfer = [r for r in all_rows if r["has_transfer"]]
    escalate = [r for r in all_rows if r["too_late_to_order"]]
    order = [r for r in all_rows
             if not r["has_transfer"] and not r["too_late_to_order"]]

    return {
        "escalate": escalate,
        "order": order,
        "transfer": transfer,
        "all_shortages": all_rows,
        "summary": _summary(all_rows, escalate, order, transfer),
    }


def _summary(all_rows: list, escalate: list, order: list,
             transfer: list) -> dict:
    vital = sum(1 for r in escalate if r["ven_class"] == "Vital")
    out_now = sum(1 for r in escalate if (r["on_hand"] or 0) <= 0)
    worst = escalate[0] if escalate else None

    return {
        "total": len(all_rows),
        "transfer": len(transfer),
        "order": len(order),
        "escalate": len(escalate),
        "escalate_vital": vital,
        "escalate_out_now": out_now,
        "headline": (
            f"{len(all_rows):,} shortages: {len(transfer):,} can be fixed by "
            f"moving stock, {len(order):,} need an order, and "
            f"{len(escalate):,} cannot be fixed by either."),
        "escalate_note": (
            f"Nothing within reach to move, and an order would arrive after "
            f"the shelf is empty. {vital:,} "
            f"{'is' if vital == 1 else 'are'} life-saving; "
            f"{out_now:,} {'is' if out_now == 1 else 'are'} already at zero."
            if escalate else
            "Every shortage here can be fixed by moving stock or by ordering "
            "in time."),
        "worst": (
            f"{worst['facility_name']} has {worst['days_of_cover']:g} days of "
            f"{worst['item_name']} left and delivery takes "
            f"{worst['lead_time_days']:g}."
            if worst else ""),
    }
