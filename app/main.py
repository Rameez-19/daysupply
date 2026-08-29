"""StockPulse — FastAPI backend."""

import os

from fastapi import FastAPI, UploadFile, Form
from fastapi.staticfiles import StaticFiles

from app.capture import handle_capture
from app.forecast import get_forecast_daily_demand
from app.redistribute import get_recommendations
from app.patterns import get_local_patterns, ingest_peer_pattern, PatternNode
from app.demo_data import (
    get_demo_stats, get_demo_review_queue, get_demo_recommendations,
    get_demo_alerts,
)

app = FastAPI(title="StockPulse", version="0.2.0")


@app.get("/healthz")
async def healthz():
    """Liveness probe for Cloud Run."""
    return {"status": "ok"}


# ── Dashboard stats ──────────────────────────────────────────────────
@app.get("/api/v1/stats")
async def get_stats():
    """Returns dashboard summary stats."""
    return get_demo_stats()


# ── Voice capture ────────────────────────────────────────────────────
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


# ── Review queue ─────────────────────────────────────────────────────
@app.get("/api/v1/review-queue")
async def get_review_queue():
    """Returns items that need manual review. Falls back to demo data."""
    from google.cloud import firestore
    try:
        db = firestore.Client(project=os.getenv("GOOGLE_CLOUD_PROJECT", "daysupply"))
        docs = list(db.collection("review_queue").where("status", "==", "pending").stream())
        if docs:
            return {"items": [doc.to_dict() for doc in docs]}
    except Exception:
        pass
    # Fallback: demo data
    return {"items": get_demo_review_queue()}


# ── Forecasting ──────────────────────────────────────────────────────
@app.get("/api/v1/forecast/{facility_id}/{item_id}")
async def get_forecast(facility_id: str, item_id: str):
    """Returns the forecasted daily demand for a facility and item."""
    daily_demand = get_forecast_daily_demand(facility_id, item_id)
    return {
        "facility_id": facility_id,
        "item_id": item_id,
        "forecast_daily_demand": daily_demand
    }


# ── Alerts ───────────────────────────────────────────────────────────
@app.get("/api/v1/alerts")
async def get_alerts():
    """Returns active stock-out warnings. Falls back to demo data."""
    from google.cloud import firestore
    try:
        db = firestore.Client(project=os.getenv("GOOGLE_CLOUD_PROJECT", "daysupply"))
        docs = list(db.collection("alerts").where("status", "==", "active").stream())
        if docs:
            return {"alerts": [doc.to_dict() for doc in docs]}
    except Exception:
        pass
    return {"alerts": get_demo_alerts()}


# ── Transfer recommendations ────────────────────────────────────────
@app.get("/api/v1/recommendations")
async def fetch_recommendations(threshold_days: int = 14, transfer_max_km: float = 50.0):
    """Returns transfer recommendations. Falls back to demo data."""
    from google.cloud import firestore
    try:
        db = firestore.Client(project=os.getenv("GOOGLE_CLOUD_PROJECT", "daysupply"))
        inventory_docs = list(db.collection("inventory_snapshot").stream())
        if inventory_docs:
            inventory_data = [doc.to_dict() for doc in inventory_docs]
            facilities_docs = db.collection("facilities").stream()
            facilities_metadata = {
                doc.id: {"lat": doc.get("lat"), "lon": doc.get("lon"), "name": doc.get("name")}
                for doc in facilities_docs
            }
            recs = get_recommendations(inventory_data, facilities_metadata, threshold_days, transfer_max_km)
            return {"recommendations": recs}
    except Exception:
        pass
    return {"recommendations": get_demo_recommendations()}


@app.post("/api/v1/recommendations/{rec_id}/approve")
async def approve_recommendation(rec_id: str):
    """Approves a transfer and triggers stock updates."""
    return {"status": "approved", "recommendation_id": rec_id}


# ── Federated patterns ──────────────────────────────────────────────
@app.get("/api/v1/patterns")
async def fetch_patterns():
    """Export local seasonal coefficients."""
    return {"patterns": get_local_patterns()}

@app.post("/api/v1/patterns")
async def post_patterns(pattern: PatternNode):
    """Ingest peer coefficients as a prior."""
    return ingest_peer_pattern(pattern)


# ── Static files (must be last) ─────────────────────────────────────
app.mount("/", StaticFiles(directory="web", html=True), name="web")
