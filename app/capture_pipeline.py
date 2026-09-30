"""One extraction and validation pipeline, three ways in.

Barcode, voice and chat differ only in how the text is obtained. Everything
after that — item matching against the full NLEM catalogue at threshold 85, the
0.6 confidence gate, the review queue, the write — is the same code path for
all three. That is the point: the degradation hierarchy only works if a worse
input mode produces a *lower-confidence record*, not a differently-shaped one.

    barcode   most accurate. Needs labelled stock and a working camera.
              The code identifies the item outright, so extraction confidence
              is 1.0 and only the quantity is spoken or typed.
    voice     works when nothing else does. One 30-second note, any language,
              offline-capable. Gemini returns items and quantities with its own
              confidence.
    chat      when audio is impractical — a shared room, a night shift, a
              noisy clinic. Same extraction prompt, text instead of audio.

Anything below `CONFIDENCE_THRESHOLD`, or whose spoken name does not resolve to
an item, goes to the review queue instead of the ledger. A wrong item_id is the
worst output this system can produce, so the bias is always toward asking a
human.

**Three resource types, still one pipeline.** "twelve beds occupied, three free"
and "two ANMs present today" are extractions like any other: same confidence
gate, same review queue, same record shape. They differ only in what the spoken
name resolves against — a medicine resolves against the NLEM catalogue, a bed or
a cadre against a small fixed vocabulary. Routing is by `resource_type`, and
`medicine` remains the default so nothing already written changes.
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime, timezone

from app import items as item_catalog

log = logging.getLogger(__name__)

# Below this, an extraction is reviewed rather than trusted.
CONFIDENCE_THRESHOLD = 0.6

# Every stock movement this system will record. Anything else goes to review
# rather than to the ledger — see the check in `route()` for why an unvalidated
# event type is a silent way to lose stock.
#
# `lost` is one of the three core LMIS data items (stock on hand, consumption,
# **losses and adjustments**) and was absent until now. A supply chain that
# cannot see breakage, spoilage and theft cannot explain its own shortfalls —
# it just shows stock that should be there and is not.
EVENT_TYPES = frozenset({
    "received", "dispensed", "count", "lost", "dispatched", "expired",
})

# Reasons a health worker actually gives. `unknown` is deliberately a first-
# class member: "it's gone and I don't know why" is a real and common answer,
# and forcing it into a category the speaker never gave would be inventing
# data. Anything unrecognised is kept verbatim rather than discarded, so the
# taxonomy can be widened later from what people really said.
LOSS_REASONS = frozenset({
    "damaged", "broken", "expired", "spilled", "stolen", "unknown",
})


def normalise_loss_reason(event_type: str, reason) -> str | None:
    """Keep a loss reason only where it means something.

    A reason on a receipt is noise, so it is dropped. A reason we do not
    recognise is kept as the speaker gave it, lowercased — the categories here
    are a starting point, not a closed vocabulary, and throwing away an
    unfamiliar word would destroy the evidence for widening them.
    """
    if event_type != "lost":
        return None
    text = str(reason or "").strip().lower()
    return text or "unknown"

# A scanned barcode identifies the product outright.
BARCODE_CONFIDENCE = 1.0

# `tap`: a medicine tile was pressed and a number typed. `photo`: a page of
# the stock register photographed and read by Gemini, then confirmed by the
# worker before anything is written. `sms`: plain text arriving from a
# gateway, for a phone with no data connection. Every one of them ends in
# `route()`; the source only says how the record came in.
SOURCES = ("barcode", "voice", "chat", "tap", "photo", "sms")

# A record the worker has read back and confirmed, or entered by tapping a
# named tile, has no extraction left to doubt. Like a barcode, it carries full
# confidence; unlike a barcode it can still lack a quantity, and then it is
# reviewed exactly as a spoken record would be.
CONFIRMED_CONFIDENCE = 1.0

RESOURCE_TYPES = ("medicine", "bed", "personnel")

# Beds and staff cadres are a closed vocabulary, unlike the 385-medicine
# catalogue, so they are matched against these directly. Keys are what a health
# worker actually says.
BED_VOCABULARY = {
    "bed": "BED-INPATIENT",
    "beds": "BED-INPATIENT",
    "inpatient bed": "BED-INPATIENT",
    "bistar": "BED-INPATIENT",
    "palang": "BED-INPATIENT",
    "day care bed": "BED-DAYCARE",
    "daycare bed": "BED-DAYCARE",
}

PERSONNEL_VOCABULARY = {
    "doctor": "STAFF-DOCTOR",
    "medical officer": "STAFF-DOCTOR",
    "mo": "STAFF-DOCTOR",
    "daktar": "STAFF-DOCTOR",
    "nurse": "STAFF-NURSE",
    "staff nurse": "STAFF-NURSE",
    "anm": "STAFF-NURSE",
    "gnm": "STAFF-NURSE",
    "nars": "STAFF-NURSE",
    "pharmacist": "STAFF-PHARMACIST",
    "compounder": "STAFF-PHARMACIST",
    "dawa wala": "STAFF-PHARMACIST",
    "health assistant male": "STAFF-HA-MALE",
    "male health assistant": "STAFF-HA-MALE",
    "mpw": "STAFF-HA-MALE",
    "health assistant female": "STAFF-HA-FEMALE",
    "female health assistant": "STAFF-HA-FEMALE",
    "lhv": "STAFF-HA-FEMALE",
}


def match_resource(local_name: str, resource_type: str) -> str | None:
    """Resolve a spoken name to a resource id for its type.

    Medicines go to the full NLEM catalogue matcher; beds and staff cadres go
    to their closed vocabulary. Both return None rather than guessing, and both
    feed the same review queue.
    """
    if resource_type == "medicine":
        return item_catalog.match(local_name)

    vocabulary = (BED_VOCABULARY if resource_type == "bed"
                  else PERSONNEL_VOCABULARY)
    spoken = " ".join((local_name or "").lower().split())
    if not spoken:
        return None
    if spoken in vocabulary:
        return vocabulary[spoken]
    # A phrase like "two nurses present" contains the term; take the longest
    # vocabulary entry it contains so "health assistant female" beats "female".
    hits = [term for term in vocabulary if term in spoken]
    if hits:
        return vocabulary[max(hits, key=len)]
    return None


class ExtractionError(RuntimeError):
    """The model returned something that could not be read as extractions."""


def parse_model_json(raw: str) -> list[dict]:
    """Read the model's reply, tolerating the fences it sometimes adds."""
    text = (raw or "").strip()
    if text.startswith("```"):
        text = text.strip("`").lstrip("json").strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ExtractionError(f"Model did not return JSON: {exc}") from exc
    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list):
        raise ExtractionError("Model returned neither an object nor an array")
    return data


def route(extractions: list[dict], facility_id: str, source: str,
          raw_transcript: str | None = None,
          resource_type: str = "medicine") -> dict:
    """Match, gate on confidence, and split into events and review items.

    This is the single path. `handle_capture` (voice), `handle_chat` and
    `handle_barcode` all end here, so a record's shape never depends on how it
    was captured — only its confidence does.
    """
    if source not in SOURCES:
        raise ValueError(f"Unknown capture source: {source}")
    if resource_type not in RESOURCE_TYPES:
        raise ValueError(f"Unknown resource type: {resource_type}")

    now = datetime.now(timezone.utc).isoformat()
    result: dict = {"events": [], "review_queue": [], "errors": [],
                    "source": source, "resource_type": resource_type}

    for raw in extractions:
        try:
            local_name = str(raw.get("local_name") or "").strip()
            confidence = float(raw.get("confidence", 0.0))
            quantity = raw.get("quantity")
            event_type = str(raw.get("event_type") or "count")
            unit = str(raw.get("unit") or "unknown")
            loss_reason = raw.get("loss_reason")
        except (TypeError, ValueError) as exc:
            result["errors"].append({"data": raw, "error": str(exc)})
            continue

        # Server-side matching, always. The model is never asked for an
        # item_id — a hallucinated drug code is the worst failure available.
        # A client MAY name one (a tapped tile, a confirmed preview row), and
        # then it is verified against the catalogue rather than trusted: an id
        # that is not in the catalogue falls back to matching the name.
        given = str(raw.get("item_id") or "").strip()
        if given and resource_type == "medicine" and item_catalog.known(given):
            item_id = given
        else:
            item_id = match_resource(local_name, resource_type)

        record = {
            "event_id": str(uuid.uuid4()),
            "resource_type": resource_type,
            "facility_id": facility_id,
            "local_name": local_name,
            "item_id": item_id,
            "event_type": event_type,
            "quantity": quantity,
            "unit": unit,
            "confidence": round(confidence, 3),
            "source": source,
            "event_ts": now,
            "raw_transcript": raw_transcript,
            # A loss reason rides in `resource_subtype` rather than a new
            # column: it is exactly what that field is for, and the schema
            # already carries it through to the ledger.
            "resource_subtype": normalise_loss_reason(event_type, loss_reason),
        }

        # The event type was previously passed through unchecked, straight from
        # the model into the ledger. A single hallucinated word — "issued",
        # "consumed" — would have written an event type that the balance
        # arithmetic nets neither in nor out, so the stock would quietly stop
        # adding up and nothing would say why.
        if event_type not in EVENT_TYPES:
            record["review_reason"] = (
                f"'{event_type}' is not a stock movement this system records "
                f"({', '.join(sorted(EVENT_TYPES))})")
            result["review_queue"].append(record)
            continue

        if item_id is None:
            what = {
                "medicine": "any medicine in the National List at the "
                            "matching threshold",
                "bed": "a known bed type",
                "personnel": "a known staff cadre",
            }[resource_type]
            record["review_reason"] = f"'{local_name}' did not match {what}"
            result["review_queue"].append(record)
        elif confidence < CONFIDENCE_THRESHOLD:
            record["review_reason"] = (
                f"extraction confidence {confidence:.2f} is below "
                f"{CONFIDENCE_THRESHOLD}")
            result["review_queue"].append(record)
        elif quantity is None:
            record["review_reason"] = "no quantity was stated"
            result["review_queue"].append(record)
        else:
            result["events"].append(record)

    return result


def describe(result: dict) -> dict:
    """Add the catalogue's display name to every record, for a screen or a
    read-back. Purely additive: the ledger projection ignores it."""
    for record in result.get("events", []) + result.get("review_queue", []):
        if record.get("resource_type", "medicine") == "medicine" and record.get("item_id"):
            record["item_name"] = item_catalog.display_name(record["item_id"])
    return result


def preview(extractions: list[dict], facility_id: str, source: str,
            raw_transcript: str | None = None,
            resource_type: str = "medicine") -> dict:
    """Route without persisting: what WOULD be written, for a read-back.

    A health worker hears "Paracetamol, 200 tablets, received" and says yes or
    no before a row exists anywhere. Nothing here touches the ledger or the
    review queue; `confirm()` does, once they have answered.
    """
    result = describe(route(extractions, facility_id, source,
                            raw_transcript=raw_transcript,
                            resource_type=resource_type))
    result["preview"] = True
    result["persisted"] = False
    return result


def confirm(rows: list[dict], facility_id: str, source: str,
            raw_transcript: str | None = None,
            resource_type: str = "medicine") -> dict:
    """Write rows a human has confirmed, through the one pipeline.

    Confidence is set to `CONFIRMED_CONFIDENCE` because the doubt the gate
    exists for — did the model hear the right drug? — has been answered by
    the person who said it. The other reasons for review still apply: an item
    that resolves to nothing, an event type the ledger does not record, a
    missing quantity. A confirmed row cannot skip those, and must not.
    """
    if source not in SOURCES:
        raise ValueError(f"Unknown capture source: {source}")
    prepared = []
    for row in rows or []:
        prepared.append({
            "item_id": row.get("item_id"),
            "local_name": row.get("local_name") or row.get("item_name") or "",
            "event_type": row.get("event_type") or "count",
            "quantity": row.get("quantity"),
            "unit": row.get("unit") or "unknown",
            "loss_reason": row.get("loss_reason"),
            "confidence": CONFIRMED_CONFIDENCE,
        })
    result = persist(route(prepared, facility_id, source,
                           raw_transcript=raw_transcript,
                           resource_type=resource_type))
    result["confirmed_by"] = "health worker"
    return describe(result)


# Columns of `resource_events`. Records carry more than this — `local_name`,
# `unit`, `review_reason` — which are useful for review and meaningless to the
# ledger, so the row is projected rather than dumped.
LEDGER_COLUMNS = (
    "event_id", "resource_type", "facility_id", "item_id", "event_type",
    "quantity", "event_ts", "source", "confidence", "raw_transcript",
    "expiry_date", "resource_subtype", "capacity",
)


def _ledger_row(record: dict) -> dict:
    """Project a capture record onto the ledger schema."""
    return {c: record.get(c) for c in LEDGER_COLUMNS}


def write_to_ledger(records: list[dict]) -> tuple[int, str | None]:
    """Insert capture records straight into `resource_events`.

    Returns (rows_written, error). Streaming inserts are used rather than a
    load job because the point of this path is immediacy: a health worker who
    has just spoken into the app must see the counter move, and a load job
    takes too long to be believable in a demo, let alone in a clinic.

    Rows land in the streaming buffer and are queryable by standard SQL within
    seconds. They are *not* immediately visible to some DML, which does not
    matter here — nothing updates these rows in place.
    """
    if not records:
        return 0, None
    try:
        from google.cloud import bigquery
        from app.bq import invalidate_stock_reads

        project = os.getenv("GCP_PROJECT", "daysupply")
        dataset = os.getenv("BQ_DATASET", "daysupply")
        client = bigquery.Client(project=project,
                                 location=os.getenv("BQ_LOCATION",
                                                    "asia-south1"))
        table = f"{project}.{dataset}.resource_events"
        errors = client.insert_rows_json(
            table, [_ledger_row(r) for r in records])
        if errors:
            return 0, f"BigQuery rejected {len(errors)} row(s): {errors[:2]}"

        # Every cached answer that depends on the stock position is now stale:
        # the capture counter, alerts, recommendations, stock health, impact.
        # Without this the view returns the new position while the API keeps
        # serving the old one — observed for real, with `reorder_status`
        # reporting on_hand 1000 and status ok while `/api/v1/alerts` still
        # called the facility stocked out.
        invalidate_stock_reads()
        return len(records), None
    except Exception as exc:
        log.warning("Could not write capture to the ledger: %s", exc)
        return 0, str(exc)


# Movements that take stock off the shelf. Mirrors
# ingestion.build_current_stock.CONSUMING_EVENT_TYPES, which is what the batch
# view subtracts.
CONSUMING = ("dispensed", "expired", "dispatched", "lost")


def recorded_balance(pairs: list[tuple[str, str]]) -> dict[tuple[str, str], int]:
    """Received minus consumed, per (facility, medicine), from the ledger."""
    if not pairs:
        return {}
    from google.cloud import bigquery
    from app.bq import run_query
    keys = sorted({f"{f}|{i}" for f, i in pairs})
    rows = run_query(f"""
        SELECT facility_id, item_id,
               SUM(IF(event_type = 'received', quantity, 0))
                 - SUM(IF(event_type IN UNNEST(@consuming), quantity, 0)) AS balance
        FROM `{os.getenv("GCP_PROJECT", "daysupply")}.{os.getenv("BQ_DATASET", "daysupply")}.resource_events`
        WHERE resource_type = 'medicine'
          AND CONCAT(facility_id, '|', item_id) IN UNNEST(@keys)
        GROUP BY facility_id, item_id
    """, [bigquery.ArrayQueryParameter("keys", "STRING", keys),
          bigquery.ArrayQueryParameter("consuming", "STRING", list(CONSUMING))])
    return {(r["facility_id"], r["item_id"]): int(r["balance"] or 0) for r in rows}


def hold_overdraws(result: dict, balance_fn=None) -> dict:
    """Hold any report that takes off the shelf more than the ledger holds.

    Found in the first week of real phone captures: "Salbutamol ke pachas
    tablet khatam ho gaye" at a centre with no Salbutamol on record wrote a
    dispensing of 50 against a balance of 0. The ledger went negative, which
    no shelf can be, and batch stock stopped reconciling with it. A report
    like that usually means a receipt was never recorded, and deciding which
    is exactly what the pharmacist's review is for. Receipts in the same
    report are counted first, in order.

    If the balance cannot be read, nothing is held: a lookup failure must not
    lose a report.
    """
    events = result.get("events", [])
    wanted = [(e["facility_id"], e["item_id"]) for e in events
              if e.get("resource_type", "medicine") == "medicine"
              and e.get("event_type") in CONSUMING and e.get("item_id")
              and e.get("quantity") is not None]
    if not wanted:
        return result
    try:
        running = dict((balance_fn or recorded_balance)(wanted))
    except Exception as exc:  # never block a capture on a read
        log.warning("Could not read balances for the overdraw check: %s", exc)
        return result
    keep = []
    for e in events:
        key = (e.get("facility_id"), e.get("item_id"))
        qty = e.get("quantity")
        if e.get("resource_type", "medicine") != "medicine" or qty is None or not e.get("item_id"):
            keep.append(e)
            continue
        have = running.get(key, 0)
        if e.get("event_type") == "received":
            running[key] = have + int(qty)
        elif e.get("event_type") in CONSUMING:
            if int(qty) > have:
                e["review_reason"] = (f"{qty} {e.get('unit') or ''} {e['event_type']} is "
                                      f"more than the {max(have, 0)} on record").replace("  ", " ")
                result.setdefault("review_queue", []).append(e)
                continue
            running[key] = have - int(qty)
        keep.append(e)
    result["events"] = keep
    return result


def persist(result: dict) -> dict:
    """Store a capture, synchronously, above the confidence gate.

    **Nothing above the gate waits.** A high-confidence extraction is written
    straight into `resource_events`, so it counts towards `captures_today` and
    reaches the supply chain immediately. That is the whole product thesis —
    capture flowing upward — and until this existed the loop was open: an
    extraction could be perfectly correct and the dashboard would never move.

    Below the gate the record goes to the Firestore review queue and reaches
    the ledger only when a human approves it, via `approve_review_item()`.
    A machine that is unsure does not get to write to the ledger unreviewed.

    Firestore is also written for high-confidence events, as an audit trail of
    what was captured and what the model said. Neither store failing may lose
    the extraction, so the result comes back either way with flags saying what
    was stored where.
    """
    hold_overdraws(result)
    events = result.get("events", [])
    reviews = result.get("review_queue", [])

    written, ledger_error = write_to_ledger(events)
    result["written_to_ledger"] = written
    if ledger_error:
        result["ledger_error"] = ledger_error

    try:
        from google.cloud import firestore
        db = firestore.Client(
            project=os.getenv("GCP_PROJECT",
                              os.getenv("GOOGLE_CLOUD_PROJECT", "daysupply")))
        for event in events:
            db.collection("pending_events").document(
                event["event_id"]).set({**event, "status": "in_ledger"})
        for review in reviews:
            db.collection("review_queue").document(
                review["event_id"]).set({**review, "status": "pending"})
        result["persisted"] = True
    except Exception as exc:
        log.warning("Could not persist capture: %s", exc)
        result["persisted"] = False
        result["persist_error"] = str(exc)
    return result


def approve_review_item(event_id: str, quantity: int | None = None) -> dict:
    """A human approved a low-confidence extraction: write it to the ledger.

    This is the other half of the gate. Approval promotes a record the model
    was unsure about into the same ledger a confident one goes to directly —
    same table, same columns, same `source`, so nothing downstream can tell
    them apart or needs to.

    **Approval must produce a usable row, and two things can stop it.**

    *No matched item.* Nothing to write; the item has to be chosen first.

    *No quantity.* The commonest reason a record lands here at all is that the
    speaker never gave a usable number — "aadha dabba", "kuch strips". A stock
    event with a NULL quantity records no stock movement, so it is worse than
    useless: it inflates the capture count while telling the supply chain
    nothing. Approving one is therefore refused unless the reviewer supplies
    the number, which is precisely the fact a human is here to add.

    An earlier version of this function did not check, and wrote exactly such
    a row into `resource_events` during live testing.
    """
    from google.cloud import firestore
    db = firestore.Client(
        project=os.getenv("GCP_PROJECT",
                          os.getenv("GOOGLE_CLOUD_PROJECT", "daysupply")))
    doc_ref = db.collection("review_queue").document(event_id)
    snapshot = doc_ref.get()
    if not snapshot.exists:
        return {"approved": False, "reason": f"no review item {event_id}"}

    record = snapshot.to_dict()
    if record.get("status") == "approved":
        return {"approved": False, "reason": "already approved",
                "event_id": event_id}
    if not record.get("item_id"):
        return {"approved": False,
                "reason": ("this item was never matched to the catalogue, so "
                           "there is nothing to write to the ledger; it needs "
                           "an item chosen first"),
                "event_id": event_id}

    resolved_quantity = quantity if quantity is not None \
        else record.get("quantity")
    if resolved_quantity is None:
        return {"approved": False,
                "reason": ("no quantity was captured, so approving this would "
                           "write a row that records no stock movement. "
                           "Supply a quantity with the approval."),
                "event_id": event_id,
                "needs_quantity": True,
                "item_id": record.get("item_id"),
                "raw_transcript": record.get("raw_transcript")}
    try:
        resolved_quantity = int(resolved_quantity)
    except (TypeError, ValueError):
        return {"approved": False,
                "reason": f"quantity {resolved_quantity!r} is not a number",
                "event_id": event_id}
    if resolved_quantity < 0:
        return {"approved": False,
                "reason": "quantity cannot be negative", "event_id": event_id}

    record = {**record, "quantity": resolved_quantity}
    written, error = write_to_ledger([record])
    if error:
        return {"approved": False, "reason": error, "event_id": event_id}

    doc_ref.set({**record, "status": "approved",
                 "approved_quantity_source": (
                     "reviewer" if quantity is not None else "extraction"),
                 "approved_at": datetime.now(timezone.utc).isoformat()})
    return {"approved": True, "event_id": event_id,
            "written_to_ledger": written, "item_id": record.get("item_id"),
            "quantity": resolved_quantity}


def handle_barcode(code: str, facility_id: str, quantity: int | None = None,
                   event_type: str = "received",
                   unit: str = "unknown") -> dict:
    """Barcode: the most accurate mode, because the code names the product.

    The scanned code is resolved against the catalogue exactly like a spoken
    name — the same matcher, the same threshold, the same review queue. What
    differs is only that extraction confidence is 1.0: there is no speech to
    mis-hear. If the code does not resolve to a known medicine it is reviewed,
    never guessed at.
    """
    return describe(persist(route(
        [{
            "local_name": code,
            "event_type": event_type,
            "quantity": quantity,
            "unit": unit,
            "confidence": BARCODE_CONFIDENCE,
        }],
        facility_id,
        source="barcode",
        raw_transcript=f"barcode:{code}",
    )))
