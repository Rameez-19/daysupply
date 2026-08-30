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
          raw_transcript: str | None = None) -> dict:
    """Match, gate on confidence, and split into events and review items.

    This is the single path. `handle_capture` (voice), `handle_chat` and
    `handle_barcode` all end here, so a record's shape never depends on how it
    was captured — only its confidence does.
    """
    if source not in SOURCES:
        raise ValueError(f"Unknown capture source: {source}")

    now = datetime.now(timezone.utc).isoformat()
    result: dict = {"events": [], "review_queue": [], "errors": [],
                    "source": source}

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
        item_id = item_catalog.match(local_name)

        record = {
            "event_id": str(uuid.uuid4()),
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
            record["review_reason"] = (
                f"'{local_name}' did not match any medicine in the National "
                "List at the matching threshold")
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


def persist(result: dict) -> dict:
    """Write events and review items to Firestore.

    Firestore being unavailable must not lose the extraction, so the result is
    returned either way with a flag saying whether it was stored.
    """
    try:
        from google.cloud import firestore
        db = firestore.Client(
            project=os.getenv("GCP_PROJECT",
                              os.getenv("GOOGLE_CLOUD_PROJECT", "daysupply")))
        for event in result["events"]:
            db.collection("pending_events").document(
                event["event_id"]).set(event)
        for review in result["review_queue"]:
            db.collection("review_queue").document(
                review["event_id"]).set({**review, "status": "pending"})
        result["persisted"] = True
    except Exception as exc:
        log.warning("Could not persist capture: %s", exc)
        result["persisted"] = False
        result["persist_error"] = str(exc)
    return result


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
