"""
Demo data for hackathon presentation.
Provides realistic sample data so every screen looks populated.
Supports cascading filters: State → District → PHC.
"""

import hashlib
import math
import random
import uuid
from datetime import datetime, timedelta

# ── Hierarchical geography: State → District → PHC ──────────────────
STATE_HIERARCHY = {
    "Telangana": {
        "Ranga Reddy": ["PHC Shadnagar", "PHC Shamshabad", "PHC Chevella"],
        "Mahbubnagar": ["PHC Jadcherla", "PHC Kalwakurthy", "PHC Makthal"],
        "Warangal": ["PHC Hanamkonda", "PHC Jangaon"],
    },
    "Maharashtra": {
        "Pune": ["PHC Baramati", "PHC Junnar", "PHC Bhor"],
        "Nagpur": ["PHC Kamptee", "PHC Hingna", "PHC Ramtek"],
        "Nashik": ["PHC Sinnar", "PHC Igatpuri"],
    },
    "Rajasthan": {
        "Jaipur": ["PHC Amber", "PHC Sanganer", "PHC Chaksu"],
        "Jodhpur": ["PHC Osian", "PHC Bilara"],
        "Udaipur": ["PHC Salumber", "PHC Gogunda"],
    },
    "Delhi": {
        "North Delhi": ["PHC Narela", "PHC Alipur", "PHC Bawana"],
        "South Delhi": ["PHC Mehrauli", "PHC Saket"],
        "East Delhi": ["PHC Shahdara", "PHC Vivek Vihar"],
    },
    "Assam": {
        "Kamrup": ["PHC Mirza", "PHC Sonapur", "PHC Boko"],
        "Nagaon": ["PHC Raha", "PHC Dhing"],
        "Dibrugarh": ["PHC Naharkatia", "PHC Lahowal"],
    },
}

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


def get_hierarchy():
    """Returns full State -> District -> PHC hierarchy for the frontend."""
    return STATE_HIERARCHY


def get_demo_stats(state: str = "Telangana", district: str = "", phc: str = ""):
    seed = _seed_from(state, district, phc)
    base_facilities = 200 if not district else (50 if not phc else 1)
    base_captures = 47 if not district else (18 if not phc else 6)
    base_alerts = 12 if not district else (5 if not phc else 2)
    base_transfers = 5 if not district else (2 if not phc else 1)
    return {
        "facilities": base_facilities + (seed % 30),
        "captures_today": base_captures + (seed % 15),
        "stockout_alerts": base_alerts + (seed % 8),
        "pending_transfers": base_transfers + (seed % 4),
        "items_tracked": 15,
        "last_sync": datetime.utcnow().isoformat() + "Z",
        "delta_facilities": round(((seed % 7) - 3) * 0.5, 1),
        "delta_captures": round(((seed % 13) - 5) * 1.2, 1),
        "delta_alerts": round(((seed % 9) - 4) * -1.5, 1),
        "delta_transfers": round(((seed % 5) - 2) * 2.0, 1),
    }


def _get_phcs_for_filter(state, district, phc):
    """Get the list of PHC names based on active filters."""
    hierarchy = STATE_HIERARCHY.get(state, {})
    if phc:
        return [phc]
    if district:
        return hierarchy.get(district, ["PHC Default"])
    all_phcs = []
    for d_phcs in hierarchy.values():
        all_phcs.extend(d_phcs)
    return all_phcs


def get_demo_review_queue(state: str = "Telangana", district: str = "", phc: str = ""):
    phcs = _get_phcs_for_filter(state, district, phc)
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
            "facility_id": f"IN-10{1000+i}",
            "facility_name": fac,
            "raw_transcript": transcript,
            "item_id": item_id, "item_name": item_name,
            "quantity": qty, "unit": unit, "event_type": etype,
            "confidence": conf,
            "created_at": (datetime.utcnow() - timedelta(minutes=12 * (i + 1))).isoformat() + "Z",
        })
    return items


def get_demo_recommendations(state: str = "Telangana", district: str = "", phc: str = ""):
    phcs = _get_phcs_for_filter(state, district, phc)
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
            "from_facility_id": f"IN-10{2000+i}", "from_facility_name": from_phc,
            "to_facility_id": f"IN-10{3000+i}", "to_facility_name": to_phc,
            "quantity": qty, "unit": unit, "distance_km": dist,
            "donor_cover_before": db, "donor_post_cover": da,
            "receiver_cover_before": rb, "receiver_post_cover": ra,
            "urgency": urgency,
        })
    return recs


def get_demo_alerts(state: str = "Telangana", district: str = "", phc: str = ""):
    phcs = _get_phcs_for_filter(state, district, phc)
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
            "facility_id": f"IN-10{4000+i}", "facility_name": fac,
            "item_id": iid, "item_name": iname,
            "days_of_cover": days, "status": "active", "severity": sev,
        })
    return alerts


def get_demo_forecast_chart(days: int = 7, state: str = "Telangana", district: str = "", phc: str = ""):
    seed = _seed_from(state, district, phc)
    random.seed(seed)
    today = datetime.now()
    labels, historical, forecast = [], [], []
    base_demand = 50 + (seed % 30)

    for i in range(30, 0, -1):
        d = today - timedelta(days=i)
        labels.append(d.strftime("%b %d"))
        val = base_demand + 20 * math.sin(i * 0.5)
        historical.append(round(val + random.uniform(-10, 10)))
        forecast.append(None)

    current_val = round(base_demand + random.uniform(-10, 10))
    labels.append("Today")
    historical.append(current_val)
    forecast.append(current_val)

    for i in range(1, days + 1):
        d = today + timedelta(days=i)
        labels.append(d.strftime("%b %d"))
        historical.append(None)
        trend = base_demand + 20 * math.sin(-i * 0.5) + (i * 0.5)
        forecast.append(round(trend + random.uniform(-5, 5)))

    random.seed()
    scope = phc if phc else (district if district else f"{state} State")
    return {
        "item_name": "Paracetamol 500mg", "facility_name": scope,
        "labels": labels, "historical": historical, "forecast": forecast,
    }


def get_demo_expiry_chart(state: str = "Telangana", district: str = "", phc: str = ""):
    """Returns medicine expiry data for the horizontal bar chart."""
    seed = _seed_from(state, district, phc)
    random.seed(seed)
    medicines = ["Paracetamol", "Amoxicillin", "Chloroquine", "ORS", "Iron Tab", "Metronidazole"]
    expired = [random.randint(50, 300) for _ in medicines]
    expiring_30d = [random.randint(100, 500) for _ in medicines]
    safe = [random.randint(500, 2000) for _ in medicines]
    random.seed()
    return {"labels": medicines, "expired": expired, "expiring_30d": expiring_30d, "safe": safe}
