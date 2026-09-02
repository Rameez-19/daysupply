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

# A scanned barcode identifies the product outright.
BARCODE_CONFIDENCE = 1.0

SOURCES = ("barcode", "voice", "chat")

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
        except (TypeError, ValueError) as exc:
            result["errors"].append({"data": raw, "error": str(exc)})
            continue

        # Server-side matching, always. The model is never asked for an
        # item_id — a hallucinated drug code is the worst failure available.
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
        }

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
        from app.bq import invalidate

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

        # The dashboard caches capture counts for 60 seconds. Without dropping
        # that entry the counter would not move for up to a minute after a
        # capture, which looks exactly like the bug this replaced.
        invalidate("quality:captures")
        return len(records), None
    except Exception as exc:
        log.warning("Could not write capture to the ledger: %s", exc)
        return 0, str(exc)


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


def approve_review_item(event_id: str) -> dict:
    """A human approved a low-confidence extraction: write it to the ledger.

    This is the other half of the gate. Approval is what promotes a record the
    model was unsure about into the same ledger a confident one goes to
    directly — same table, same columns, same `source`, so nothing downstream
    can tell them apart or needs to.
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

    written, error = write_to_ledger([record])
    if error:
        return {"approved": False, "reason": error, "event_id": event_id}

    doc_ref.set({**record, "status": "approved",
                 "approved_at": datetime.now(timezone.utc).isoformat()})
    return {"approved": True, "event_id": event_id,
            "written_to_ledger": written, "item_id": record.get("item_id"),
            "quantity": record.get("quantity")}


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
    return persist(route(
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
    ))
