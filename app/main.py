"""DaySupply — deployment skeleton (Block 1)."""

import os

from fastapi import FastAPI, UploadFile, Form
from fastapi.staticfiles import StaticFiles

from app.capture import handle_capture
from app.forecast import get_forecast_daily_demand
from app.redistribute import get_recommendations
from app.patterns import get_local_patterns, ingest_peer_pattern, PatternNode

app = FastAPI(title="DaySupply", version="0.1.0")


@app.get("/healthz")
async def healthz():
    """Liveness probe for Cloud Run."""
    return {"status": "ok"}



@app.post("/api/v1/voice-note")
async def post_voice_note(
    file: UploadFile,
    facility_id: str = Form(...)
):
    """Processes a voice note using Gemini and stores structured data."""
    audio_bytes = await file.read()
    content_type = file.content_type or "audio/mp3"
    results = handle_capture(audio_bytes, facility_id, content_type)
    return results

@app.get("/api/v1/review-queue")
async def get_review_queue():
    """Returns items that need manual review."""
    from google.cloud import firestore
    try:
        db = firestore.Client(project=os.getenv("GOOGLE_CLOUD_PROJECT", "daysupply"))
        docs = db.collection("review_queue").where("status", "==", "pending").stream()
        return {"items": [doc.to_dict() for doc in docs]}
    except Exception as e:
        return {"error": str(e), "items": []}

@app.get("/api/v1/forecast/{facility_id}/{item_id}")
async def get_forecast(facility_id: str, item_id: str):
    """Returns the forecasted daily demand for a facility and item."""
    daily_demand = get_forecast_daily_demand(facility_id, item_id)
    return {
        "facility_id": facility_id,
        "item_id": item_id,
        "forecast_daily_demand": daily_demand
    }

@app.get("/api/v1/alerts")
async def get_alerts():
    """Returns active stock-out warnings from Firestore."""
    from google.cloud import firestore
    try:
        db = firestore.Client(project=os.getenv("GOOGLE_CLOUD_PROJECT", "daysupply"))
        docs = db.collection("alerts").where("status", "==", "active").stream()
        return {"alerts": [doc.to_dict() for doc in docs]}
    except Exception as e:
        return {"error": str(e), "alerts": []}

@app.get("/api/v1/recommendations")
async def fetch_recommendations(threshold_days: int = 14, transfer_max_km: float = 50.0):
    from google.cloud import firestore
    try:
        db = firestore.Client(project=os.getenv("GOOGLE_CLOUD_PROJECT", "daysupply"))
        
        # 1. Fetch inventory data
        inventory_docs = db.collection("inventory_snapshot").stream()
        inventory_data = [doc.to_dict() for doc in inventory_docs]
        
        # 2. Fetch facilities metadata
        facilities_docs = db.collection("facilities").stream()
        facilities_metadata = {
            doc.id: {"lat": doc.get("lat"), "lon": doc.get("lon"), "name": doc.get("name")}
            for doc in facilities_docs
        }
        
        recs = get_recommendations(inventory_data, facilities_metadata, threshold_days, transfer_max_km)
        return {"recommendations": recs}
    except Exception as e:
        return {"error": str(e), "recommendations": []}

@app.post("/api/v1/recommendations/{rec_id}/approve")
async def approve_recommendation(rec_id: str):
    """Approves a transfer and triggers stock updates."""
    from google.cloud import firestore
    try:
        db = firestore.Client(project=os.getenv("GOOGLE_CLOUD_PROJECT", "daysupply"))
        # Hackathon: In a real app, this would deduct from donor and add to receiver in Firestore transaction
        return {"status": "approved", "recommendation_id": rec_id}
    except Exception as e:
        return {"error": str(e)}

@app.get("/api/v1/patterns")
async def fetch_patterns():
    """Export local seasonal coefficients."""
    return {"patterns": get_local_patterns()}

@app.post("/api/v1/patterns")
async def post_patterns(pattern: PatternNode):
    """Ingest peer coefficients as a prior."""
    return ingest_peer_pattern(pattern)

app.mount("/", StaticFiles(directory="web", html=True), name="web")
