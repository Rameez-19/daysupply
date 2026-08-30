"""
Worked examples for the review-queue screen. Nothing else.

Every figure in the product is now computed: alerts, transfers, days of cover,
reorder points, waste avoided, reporting consistency and capture counts. See
`app/supply.py` and `app/quality.py`.

What remains is three example low-confidence extractions, so the review-queue
screen is demonstrable before a live Gemini call has produced any. Real
extractions land in Firestore and take precedence over these — they are only
returned when the queue is genuinely empty.

Deleted from this module as their real implementations landed:
`get_demo_alerts` and `get_demo_recommendations` (Block C, replaced by the
redistribution engine), `get_demo_forecast_chart` and `get_demo_expiry_chart`
(Block B), `get_demo_stats` (Block D — `captures_today` is now counted from
the ledger), and `STATE_HIERARCHY` (Block A).
"""

import hashlib
import math
import random
import uuid
from datetime import datetime, timedelta

DEMO_ITEMS = [
    {"id": "PARA-500", "name": "Paracetamol 500mg",  "unit": "tablets"},
    {"id": "AMOX-250", "name": "Amoxicillin 250mg",  "unit": "capsules"},
    {"id": "ORS-PKT",  "name": "ORS Sachets",         "unit": "sachets"},
    {"id": "IRON-TAB", "name": "Iron + Folic Acid",   "unit": "tablets"},
    {"id": "CHLOR-Q",  "name": "Chloroquine 250mg",   "unit": "tablets"},
    {"id": "METRO-400","name": "Metronidazole 400mg", "unit": "tablets"},
    {"id": "COTRI-DS", "name": "Cotrimoxazole DS",    "unit": "tablets"},
    {"id": "DICLOF-50","name": "Diclofenac 50mg",     "unit": "tablets"},
]


def _seed_from(state: str, district: str = "", phc: str = "") -> int:
    """Deterministic seed from filter combination for consistent demo data."""
    key = f"{state}:{district}:{phc}"
    return int(hashlib.md5(key.encode()).hexdigest(), 16) % 1000


def _names(scope: list[dict]) -> list[dict]:
    """Normalise the caller's facility scope to id/name pairs."""
    if not scope:
        return [{"facility_id": "IN-unknown", "name": "No facility selected"}]
    return [
        {
            "facility_id": f.get("facility_id", "IN-unknown"),
            "name": f.get("name") or "Unnamed facility",
        }
        for f in scope
    ]


def get_demo_review_queue(scope: list[dict]):
    phcs = _names(scope)
    items = []
    transcripts = [
        ("PARA-500", "Paracetamol 500mg", "Paracetamol ke do sau tablet aaye hain", 200, "tablets", "received", 0.52),
        ("AMOX-250", "Amoxicillin 250mg", "Amoxicillin teen sau capsule dispense kiye", 300, "capsules", "dispensed", 0.41),
        ("IRON-TAB", "Iron + Folic Acid", "Iron folic acid ki ginti lagbhag ek sau", 100, "tablets", "stock_count", 0.38),
    ]
    for i, (item_id, item_name, transcript, qty, unit, etype, conf) in enumerate(transcripts):
        fac = phcs[i % len(phcs)]
        items.append({
            "event_id": "evt-" + uuid.uuid4().hex[:8],
            "facility_id": fac["facility_id"],
            "facility_name": fac["name"],
            "raw_transcript": transcript,
            "item_id": item_id, "item_name": item_name,
            "quantity": qty, "unit": unit, "event_type": etype,
            "confidence": conf,
            "created_at": (datetime.utcnow() - timedelta(minutes=12 * (i + 1))).isoformat() + "Z",
        })
    return items


# The forecast chart and the expiry chart used to be generated here — a sine
# wave and random.randint respectively. Both are gone. The forecast is served
# from the trained ARIMA_PLUS model in app/forecast.py; expiry returns in
# Block C backed by real batch data.
