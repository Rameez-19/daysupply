"""
Operational demo data for the hackathon presentation.

Geography is NOT defined here. Every state, district and facility comes from
`daysupply.facilities` — the real 200,438-row national facility master — and is
passed in by the caller. This module only fills in the operational counters
(captures, alerts, transfers, expiry) that have no data source yet; those are
replaced by real BigQuery-backed figures in Block B.
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
        "stockout_alerts": base_alerts + (seed % 8),
        "pending_transfers": base_transfers + (seed % 4),
        "items_tracked": 15,
        "last_sync": datetime.utcnow().isoformat() + "Z",
        "delta_captures": round(((seed % 13) - 5) * 1.2, 1),
        "delta_alerts": round(((seed % 9) - 4) * -1.5, 1),
        "delta_transfers": round(((seed % 5) - 2) * 2.0, 1),
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


def get_demo_recommendations(scope: list[dict]):
    phcs = _names(scope)
    transfers = [
        ("PARA-500", "Paracetamol 500mg", 500, "tablets", 38.2, 52, 28, 3, 18, "high"),
        ("ORS-PKT", "ORS Sachets", 200, "sachets", 22.7, 45, 25, 5, 19, "high"),
        ("CHLOR-Q", "Chloroquine 250mg", 150, "tablets", 47.1, 38, 22, 2, 14, "critical"),
        ("IRON-TAB", "Iron + Folic Acid", 300, "tablets", 31.5, 60, 35, 4, 16, "medium"),
    ]
    recs = []
    for i, (iid, iname, qty, unit, dist, db, da, rb, ra, urgency) in enumerate(transfers):
        from_phc = phcs[i % len(phcs)]
        to_phc = phcs[(i + 1) % len(phcs)]
        recs.append({
            "recommendation_id": "rec-" + uuid.uuid4().hex[:8],
            "item_id": iid, "item_name": iname,
            "from_facility_id": from_phc["facility_id"],
            "from_facility_name": from_phc["name"],
            "to_facility_id": to_phc["facility_id"],
            "to_facility_name": to_phc["name"],
            "quantity": qty, "unit": unit, "distance_km": dist,
            "donor_cover_before": db, "donor_post_cover": da,
            "receiver_cover_before": rb, "receiver_post_cover": ra,
            "urgency": urgency,
        })
    return recs


def get_demo_alerts(scope: list[dict]):
    phcs = _names(scope)
    alert_items = [
        ("PARA-500", "Paracetamol 500mg", 3, "critical"),
        ("ORS-PKT", "ORS Sachets", 5, "high"),
        ("CHLOR-Q", "Chloroquine 250mg", 2, "critical"),
        ("IRON-TAB", "Iron + Folic Acid", 4, "high"),
    ]
    alerts = []
    for i, (iid, iname, days, sev) in enumerate(alert_items):
        fac = phcs[i % len(phcs)]
        alerts.append({
            "facility_id": fac["facility_id"], "facility_name": fac["name"],
            "item_id": iid, "item_name": iname,
            "days_of_cover": days, "status": "active", "severity": sev,
        })
    return alerts


# The forecast chart and the expiry chart used to be generated here — a sine
# wave and random.randint respectively. Both are gone. The forecast is served
# from the trained ARIMA_PLUS model in app/forecast.py; expiry returns in
# Block C backed by real batch data.
