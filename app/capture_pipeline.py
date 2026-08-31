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
