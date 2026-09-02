"""Executing a transfer — the difference between "computed" and "automated".

The redistribution engine says what should move. Until this existed, that was
all it did: `POST /api/v1/recommendations/{id}/approve` returned
`{"status": "approved"}`, wrote nothing, and its docstring claimed it
"triggers stock updates". The UI faded the card and called no endpoint at all.
That was the last simulated surface in the product, and it sat directly under
the clause a reviewer is most likely to click.

## The lifecycle

    recommended -> approved -> dispatched -> received

**Dispatch and receipt are separate on purpose.** Stock on a vehicle belongs to
neither facility. Writing both movements at once would mean a transfer that
never arrives silently credits the recipient — which is precisely the failure a
supply chain most needs to see. Between the two states the units have left the
donor and not yet arrived, and the ledger says so.

Each step writes a real event into `resource_events`:

* **dispatch** — a `dispatched` event at the donor. `build_current_stock.py`
  nets it out of on-hand, so the donor's position falls immediately.
* **receipt** — a `received` event at the recipient, which becomes a new FEFO
  batch and raises their on-hand.

## No retraction, by design

Per HANDOVER §9e, streaming-insert rows resist DML for up to ~90 minutes, so a
retract button would appear to work and silently not. A transfer that should
not have happened is corrected with a compensating movement, never by deleting
the record. Nothing here offers to undo anything.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone

from google.cloud import bigquery

from app.bq import run_query, invalidate_stock_reads

PROJECT = os.getenv("GCP_PROJECT", "daysupply")
DATASET = os.getenv("BQ_DATASET", "daysupply")
LOCATION = os.getenv("BQ_LOCATION", "asia-south1")

RECOMMENDATIONS = f"`{PROJECT}.{DATASET}.recommendations`"
FULFILMENT = f"`{PROJECT}.{DATASET}.transfer_fulfilment`"
FULFILMENT_ID = f"{PROJECT}.{DATASET}.transfer_fulfilment"
RESOURCE_EVENTS_ID = f"{PROJECT}.{DATASET}.resource_events"

LIFECYCLE = ("recommended", "approved", "dispatched", "received")
# What each state may become. A transfer only moves forward.
NEXT_STATE = {
    "recommended": "approved",
    "approved": "dispatched",
    "dispatched": "received",
    "received": None,
}


class TransferError(ValueError):
    """The caller asked for a state change the lifecycle does not allow."""


def _client() -> bigquery.Client:
    return bigquery.Client(project=PROJECT, location=LOCATION)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_state(recommendation_id: str) -> dict | None:
    """Current fulfilment state, or None if the transfer has never been acted on."""
    rows = run_query(f"""
        SELECT recommendation_id, fulfilment_status, from_facility_id,
               to_facility_id, item_id, quantity,
               approved_at, dispatched_at, received_at,
               dispatch_event_id, receipt_event_id
        FROM {FULFILMENT}
        WHERE recommendation_id = @rid
        ORDER BY updated_at DESC LIMIT 1
    """, [bigquery.ScalarQueryParameter("rid", "STRING", recommendation_id)])
    return rows[0] if rows else None


def _recommendation(recommendation_id: str) -> dict | None:
    rows = run_query(f"""
        SELECT recommendation_id, from_facility_id, from_facility_name,
               to_facility_id, to_facility_name, supplied_item_id,
               requested_item_name, quantity, unit, ven_class, distance_km
        FROM {RECOMMENDATIONS}
        WHERE recommendation_id = @rid
    """, [bigquery.ScalarQueryParameter("rid", "STRING", recommendation_id)])
    return rows[0] if rows else None


def _write_events(client: bigquery.Client, rows: list[dict]) -> str | None:
    errors = client.insert_rows_json(RESOURCE_EVENTS_ID, rows)
    return f"BigQuery rejected the movement: {errors[:2]}" if errors else None


def _ledger_event(facility_id: str, item_id: str, event_type: str,
                  quantity: int, note: str) -> dict:
    return {
        "event_id": str(uuid.uuid4()),
        "resource_type": "medicine",
        "facility_id": facility_id,
        "item_id": item_id,
        "event_type": event_type,
        "quantity": int(quantity),
        "event_ts": _now(),
        "source": "transfer",
        "confidence": 1.0,
        "raw_transcript": note,
        "expiry_date": None,
        "resource_subtype": None,
        "capacity": None,
    }


def _save_state(client: bigquery.Client, state: dict) -> str | None:
    errors = client.insert_rows_json(FULFILMENT_ID, [state])
    return f"could not record fulfilment state: {errors[:2]}" if errors else None


def advance(recommendation_id: str, to_status: str) -> dict:
    """Move a transfer one step along the lifecycle, writing real movements.

    Refuses to skip a step or go backwards: a transfer cannot be received
    before it was dispatched, and dispatching twice would take the stock off
    the donor twice.
    """
    if to_status not in LIFECYCLE:
        raise TransferError(
            f"{to_status!r} is not a transfer state; expected one of "
            f"{', '.join(LIFECYCLE)}")

    rec = _recommendation(recommendation_id)
    if rec is None:
        raise TransferError(
            f"no recommendation {recommendation_id}. Note that the plan is "
            "rebuilt periodically and recommendation ids are regenerated with "
            "it, so an id from an older plan will not resolve.")

    current = get_state(recommendation_id)
    current_status = current["fulfilment_status"] if current else "recommended"
    if current_status == to_status:
        raise TransferError(f"this transfer is already {to_status}")
    if NEXT_STATE.get(current_status) != to_status:
        raise TransferError(
            f"cannot go from {current_status} to {to_status}; the next step is "
            f"{NEXT_STATE.get(current_status) or 'nothing — it is complete'}")

    client = _client()
    quantity = int(rec["quantity"])
    state = {
        "recommendation_id": recommendation_id,
        "fulfilment_status": to_status,
        "from_facility_id": rec["from_facility_id"],
        "to_facility_id": rec["to_facility_id"],
        "item_id": rec["supplied_item_id"],
        "quantity": quantity,
        "approved_at": (current or {}).get("approved_at"),
        "dispatched_at": (current or {}).get("dispatched_at"),
        "received_at": (current or {}).get("received_at"),
        "dispatch_event_id": (current or {}).get("dispatch_event_id"),
        "receipt_event_id": (current or {}).get("receipt_event_id"),
        "updated_at": _now(),
    }

    movement = None
    if to_status == "approved":
        # A decision, not a movement. Stock has not left anywhere yet.
        state["approved_at"] = _now()

    elif to_status == "dispatched":
        event = _ledger_event(
            rec["from_facility_id"], rec["supplied_item_id"], "dispatched",
            quantity,
            f"transfer {recommendation_id[:8]} dispatched to "
            f"{rec['to_facility_name']}")
        error = _write_events(client, [event])
        if error:
            raise TransferError(error)
        state["dispatched_at"] = _now()
        state["dispatch_event_id"] = event["event_id"]
        movement = {"facility": rec["from_facility_name"],
                    "direction": "out", "quantity": quantity}

    elif to_status == "received":
        event = _ledger_event(
            rec["to_facility_id"], rec["supplied_item_id"], "received",
            quantity,
            f"transfer {recommendation_id[:8]} received from "
            f"{rec['from_facility_name']}")
        error = _write_events(client, [event])
        if error:
            raise TransferError(error)
        state["received_at"] = _now()
        state["receipt_event_id"] = event["event_id"]
        movement = {"facility": rec["to_facility_name"],
                    "direction": "in", "quantity": quantity}

    save_error = _save_state(client, state)
    if save_error:
        raise TransferError(save_error)

    # On-hand has changed, so every cached answer that depends on it is stale.
    invalidate_stock_reads()

    return {
        "recommendation_id": recommendation_id,
        "from_status": current_status,
        "fulfilment_status": to_status,
        "next_action": NEXT_STATE[to_status],
        "item": rec["requested_item_name"],
        "quantity": quantity,
        "unit": rec["unit"],
        "from_facility": rec["from_facility_name"],
        "to_facility": rec["to_facility_name"],
        "distance_km": rec["distance_km"],
        "stock_moved": movement,
        "note": (
            "Approved. No stock has moved yet — dispatch records that it left "
            "the donor." if to_status == "approved" else
            "Dispatched. The units are out of the donor's on-hand and in "
            "transit; they belong to neither facility until receipt."
            if to_status == "dispatched" else
            "Received. The units are now on the recipient's shelf and count "
            "towards their days of cover."),
    }


def pending(state: str = "", limit: int = 50) -> list[dict]:
    """Transfers that have been acted on, most recent first."""
    where = ["TRUE"]
    params: list[bigquery.ScalarQueryParameter] = []
    if state:
        where.append("fulfilment_status = @state")
        params.append(bigquery.ScalarQueryParameter("state", "STRING", state))
    params.append(bigquery.ScalarQueryParameter("limit", "INT64", limit))
    return run_query(f"""
        SELECT recommendation_id, fulfilment_status, from_facility_id,
               to_facility_id, item_id, quantity,
               approved_at, dispatched_at, received_at
        FROM {FULFILMENT}
        WHERE {' AND '.join(where)}
        QUALIFY ROW_NUMBER() OVER (
          PARTITION BY recommendation_id ORDER BY updated_at DESC) = 1
        ORDER BY updated_at DESC
        LIMIT @limit
    """, params)
