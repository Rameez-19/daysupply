"""
Demo data for hackathon presentation.
Provides realistic sample data so every screen looks populated.
"""

import random
import uuid
from datetime import datetime, timedelta

DEMO_FACILITIES = [
    {"id": "IN-101234", "name": "PHC Shadnagar", "district": "Ranga Reddy", "lat": 17.0712, "lon": 78.1448},
    {"id": "IN-101891", "name": "PHC Jadcherla", "district": "Mahbubnagar", "lat": 16.7667, "lon": 78.1333},
    {"id": "IN-102455", "name": "PHC Kalwakurthy", "district": "Mahbubnagar", "lat": 16.6667, "lon": 78.5000},
    {"id": "IN-103012", "name": "PHC Makthal", "district": "Mahbubnagar", "lat": 16.5167, "lon": 77.5833},
    {"id": "IN-103678", "name": "PHC Shamshabad", "district": "Ranga Reddy", "lat": 17.2833, "lon": 78.3667},
    {"id": "IN-104201", "name": "PHC Tandur", "district": "Ranga Reddy", "lat": 17.2500, "lon": 77.5833},
    {"id": "IN-104890", "name": "PHC Chevella", "district": "Ranga Reddy", "lat": 17.3167, "lon": 78.1500},
    {"id": "IN-105543", "name": "PHC Wanaparthy", "district": "Mahbubnagar", "lat": 16.3636, "lon": 78.0650},
]

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

def get_demo_stats():
    return {
        "facilities": 200,
        "captures_today": 47,
        "stockout_alerts": 12,
        "pending_transfers": 5,
        "items_tracked": 15,
        "last_sync": datetime.utcnow().isoformat() + "Z",
    }

def get_demo_review_queue():
    items = [
        {
            "event_id": "evt-" + uuid.uuid4().hex[:8],
            "facility_id": "IN-101234",
            "facility_name": "PHC Shadnagar",
            "raw_transcript": "Paracetamol ke do sau tablet aaye hain aur ORS ke pachaas packet bhi",
            "item_id": "PARA-500",
            "item_name": "Paracetamol 500mg",
            "quantity": 200,
            "unit": "tablets",
            "event_type": "received",
            "confidence": 0.52,
            "created_at": (datetime.utcnow() - timedelta(minutes=12)).isoformat() + "Z",
        },
        {
            "event_id": "evt-" + uuid.uuid4().hex[:8],
            "facility_id": "IN-102455",
            "facility_name": "PHC Kalwakurthy",
            "raw_transcript": "Amoxicillin teen sau capsule dispense kiye hain is mahine",
            "item_id": "AMOX-250",
            "item_name": "Amoxicillin 250mg",
            "quantity": 300,
            "unit": "capsules",
            "event_type": "dispensed",
            "confidence": 0.41,
            "created_at": (datetime.utcnow() - timedelta(minutes=45)).isoformat() + "Z",
        },
        {
            "event_id": "evt-" + uuid.uuid4().hex[:8],
            "facility_id": "IN-103678",
            "facility_name": "PHC Shamshabad",
            "raw_transcript": "Iron folic acid ki ginti... lagbhag ek sau tablet bachi hain",
            "item_id": "IRON-TAB",
            "item_name": "Iron + Folic Acid",
            "quantity": 100,
            "unit": "tablets",
            "event_type": "stock_count",
            "confidence": 0.38,
            "created_at": (datetime.utcnow() - timedelta(hours=2)).isoformat() + "Z",
        },
    ]
    return items

def get_demo_recommendations():
    return [
        {
            "recommendation_id": "rec-" + uuid.uuid4().hex[:8],
            "item_id": "PARA-500",
            "item_name": "Paracetamol 500mg",
            "from_facility_id": "IN-101234",
            "from_facility_name": "PHC Shadnagar",
            "to_facility_id": "IN-102455",
            "to_facility_name": "PHC Kalwakurthy",
            "quantity": 500,
            "unit": "tablets",
            "distance_km": 38.2,
            "donor_cover_before": 52,
            "donor_post_cover": 28,
            "receiver_cover_before": 3,
            "receiver_post_cover": 18,
            "urgency": "high",
        },
        {
            "recommendation_id": "rec-" + uuid.uuid4().hex[:8],
            "item_id": "ORS-PKT",
            "item_name": "ORS Sachets",
            "from_facility_id": "IN-103678",
            "from_facility_name": "PHC Shamshabad",
            "to_facility_id": "IN-103012",
            "to_facility_name": "PHC Makthal",
            "quantity": 200,
            "unit": "sachets",
            "distance_km": 22.7,
            "donor_cover_before": 45,
            "donor_post_cover": 25,
            "receiver_cover_before": 5,
            "receiver_post_cover": 19,
            "urgency": "high",
        },
        {
            "recommendation_id": "rec-" + uuid.uuid4().hex[:8],
            "item_id": "CHLOR-Q",
            "item_name": "Chloroquine 250mg",
            "from_facility_id": "IN-104201",
            "from_facility_name": "PHC Tandur",
            "to_facility_id": "IN-104890",
            "to_facility_name": "PHC Chevella",
            "quantity": 150,
            "unit": "tablets",
            "distance_km": 47.1,
            "donor_cover_before": 38,
            "donor_post_cover": 22,
            "receiver_cover_before": 2,
            "receiver_post_cover": 14,
            "urgency": "critical",
        },
        {
            "recommendation_id": "rec-" + uuid.uuid4().hex[:8],
            "item_id": "IRON-TAB",
            "item_name": "Iron + Folic Acid",
            "from_facility_id": "IN-101891",
            "from_facility_name": "PHC Jadcherla",
            "to_facility_id": "IN-105543",
            "to_facility_name": "PHC Wanaparthy",
            "quantity": 300,
            "unit": "tablets",
            "distance_km": 31.5,
            "donor_cover_before": 60,
            "donor_post_cover": 35,
            "receiver_cover_before": 4,
            "receiver_post_cover": 16,
            "urgency": "medium",
        },
    ]

def get_demo_alerts():
    return [
        {"facility_id": "IN-102455", "facility_name": "PHC Kalwakurthy", "item_id": "PARA-500", "item_name": "Paracetamol 500mg", "days_of_cover": 3, "status": "active", "severity": "critical"},
        {"facility_id": "IN-103012", "facility_name": "PHC Makthal",     "item_id": "ORS-PKT",  "item_name": "ORS Sachets",        "days_of_cover": 5, "status": "active", "severity": "high"},
        {"facility_id": "IN-104890", "facility_name": "PHC Chevella",    "item_id": "CHLOR-Q",  "item_name": "Chloroquine 250mg",  "days_of_cover": 2, "status": "active", "severity": "critical"},
        {"facility_id": "IN-105543", "facility_name": "PHC Wanaparthy",  "item_id": "IRON-TAB", "item_name": "Iron + Folic Acid",  "days_of_cover": 4, "status": "active", "severity": "high"},
    ]

def get_demo_forecast_chart(days: int = 7):
    import math
    import random
    from datetime import datetime, timedelta
    
    today = datetime.now()
    labels = []
    historical = []
    forecast = []
    
    # 30 days of historical data for smoothing
    for i in range(30, 0, -1):
        d = today - timedelta(days=i)
        labels.append(d.strftime("%b %d"))
        base_val = 50 + 20 * math.sin(i * 0.5)
        historical.append(round(base_val + random.uniform(-10, 10)))
        forecast.append(None)
        
    current_val = round(50 + random.uniform(-10, 10))
    labels.append("Today")
    historical.append(current_val)
    forecast.append(current_val)
    
    for i in range(1, days + 1):
        d = today + timedelta(days=i)
        labels.append(d.strftime("%b %d"))
        historical.append(None)
        trend = 50 + 20 * math.sin(-i * 0.5) + (i * 0.5)
        forecast.append(round(trend + random.uniform(-5, 5)))
        
    return {
        "item_name": "Paracetamol 500mg",
        "facility_name": "PHC District Aggregate",
        "labels": labels,
        "historical": historical,
        "forecast": forecast
    }
