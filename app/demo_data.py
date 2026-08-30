"""
The last generated figures in the product, and the only ones.

Stock-out alerts, transfer recommendations, days of cover, reorder points,
waste avoided and reporting consistency are all real — computed in BigQuery
from the ledger and the trained model. See `app/supply.py`.

What remains here:

* `captures_today` — how many voice notes were recorded today. There is no
  source for this until capture is running in production against real users.
  The API marks it `captures_today_is_generated: true`.
* `get_demo_review_queue` — three worked examples of low-confidence extractions
  so the review-queue screen is demonstrable before a live Gemini call.
  Real extractions land in Firestore and take precedence over these.

`get_demo_alerts` and `get_demo_recommendations` were deleted in Block C. If
BigQuery is unreachable those endpoints now report the failure rather than
inventing a stock-out.
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


def get_demo_stats(state: str = "Telangana", district: str = "", phc: str = ""):
    seed = _seed_from(state, district, phc)
    base_captures = 47 if not district else (18 if not phc else 6)
    base_alerts = 12 if not district else (5 if not phc else 2)
    base_transfers = 5 if not district else (2 if not phc else 1)
    return {
        "captures_today": base_captures + (seed % 15),
        "last_sync": datetime.utcnow().isoformat() + "Z",
    }


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
