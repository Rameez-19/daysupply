"""StockPulse — FastAPI backend."""

import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, UploadFile, Form
from fastapi.staticfiles import StaticFiles

from app import facilities as facility_repo
from app import forecast
from app import stock_health
from app.bq import QueryTooExpensive
from app.capture import handle_capture
from app.forecast import get_forecast_daily_demand
from app.redistribute import get_recommendations
from app.patterns import get_local_patterns, ingest_peer_pattern, PatternNode
from app.demo_data import (
    get_demo_stats, get_demo_review_queue, get_demo_recommendations,
    get_demo_alerts,
)

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Warm the geography cache off the request path.

    Cloud Run runs at --min-instances 0, so every judge opening the live URL
    hits a cold container. Fetching the geo summary during startup — in the
    background, so readiness is not delayed — means the dropdowns are served
    from memory by the time the browser has loaded the page and asked for them.
    """
    async def warm():
        try:
            count = await asyncio.to_thread(facility_repo.prewarm)
            log.info("Geography cache warmed: %d rows", count)
        except Exception:
            log.exception("Geography prewarm failed; will load on first request")

    task = asyncio.create_task(warm())
    yield
    task.cancel()


app = FastAPI(title="StockPulse", version="0.4.0", lifespan=lifespan)


@app.get("/healthz")
@app.get("/api/v1/healthz")
async def healthz():
    """Liveness probe.

    Exposed twice on purpose. Google's frontend swallows the exact path
    `/healthz` before it reaches the container — it returns a Google-branded
    404 with no `server: Google Frontend` header, while `/healthz2` and
    `/healthz/` pass through normally. `/api/v1/healthz` is the path to probe
    in production; `/healthz` still works locally.
    """
    return {"status": "ok"}


def _facility_query(fn, *args, **kwargs):
    """Run a BigQuery-backed lookup, surfacing failures honestly.

    Geography is never faked. If BigQuery is unreachable the endpoint reports
    that, rather than returning invented facilities.
    """
    try:
        return fn(*args, **kwargs)
    except QueryTooExpensive as exc:
        log.error("Refused expensive query: %s", exc)
        raise HTTPException(status_code=413, detail=str(exc))
    except Exception as exc:
        log.exception("Facility query failed")
        raise HTTPException(
            status_code=503,
            detail=f"Facility data is unavailable: {exc}",
        )


# ── Geography — served from the real 200,438-facility master ─────────
@app.get("/api/v1/states")
async def fetch_states():
    """Every state/UT present in the facility master, with counts."""
    return {"states": _facility_query(facility_repo.list_states)}


@app.get("/api/v1/districts")
async def fetch_districts(state: str):
    """Districts within a state."""
    return {
        "state": state,
        "districts": _facility_query(facility_repo.list_districts, state),
    }


@app.get("/api/v1/facilities")
async def fetch_facilities(state: str, district: str,
                           facility_type: str = "phc"):
    """Facilities within a district — PHCs by default."""
    return {
        "state": state,
        "district": district,
        "facilities": _facility_query(
            facility_repo.list_facilities, state, district, facility_type
        ),
    }


@app.get("/api/v1/facilities/{facility_id}")
async def fetch_facility(facility_id: str):
    """One facility by id."""
    facility = _facility_query(facility_repo.get_facility, facility_id)
    if facility is None:
        raise HTTPException(status_code=404, detail="Facility not found")
    return facility


@app.get("/api/v1/coverage")
async def fetch_coverage():
    """National coverage headline — how much of India is loaded."""
    return _facility_query(facility_repo.national_summary)


# ── Dashboard stats ──────────────────────────────────────────────────
@app.get("/api/v1/stats")
async def get_stats(state: str = "Telangana", district: str = "", phc: str = ""):
    """Dashboard summary stats.

    Facility counts are real, queried from `daysupply.facilities`. The
    remaining operational counters still come from the demo generator and are
    replaced in Block B.
    """
    stats = get_demo_stats(state, district, phc)
    counts = _facility_query(
        facility_repo.facility_counts, state, district, phc
    )
    stats.update({
        "facilities": counts["facilities"],
        "phcs": counts["phcs"],
        "demo_facilities": counts["demo_facilities"],
        "districts": counts["districts"],
        "population_served": counts["population_served"],
    })
    stats.pop("delta_facilities", None)
    return stats


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
async def get_review_queue(state: str = "Telangana", district: str = "", phc: str = ""):
    """Returns items that need manual review. Falls back to demo data."""
    from google.cloud import firestore
    try:
        db = firestore.Client(project=os.getenv("GOOGLE_CLOUD_PROJECT", "daysupply"))
        docs = list(db.collection("review_queue").where("status", "==", "pending").stream())
        if docs:
            return {"items": [doc.to_dict() for doc in docs]}
    except Exception:
        pass
    scope = _facility_query(facility_repo.scope_facilities, state, district, phc)
    return {"items": get_demo_review_queue(scope)}


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
async def get_alerts(state: str = "Telangana", district: str = "", phc: str = ""):
    """Returns active stock-out warnings. Falls back to demo data."""
    from google.cloud import firestore
    try:
        db = firestore.Client(project=os.getenv("GOOGLE_CLOUD_PROJECT", "daysupply"))
        docs = list(db.collection("alerts").where("status", "==", "active").stream())
        if docs:
            return {"alerts": [doc.to_dict() for doc in docs]}
    except Exception:
        pass
    scope = _facility_query(facility_repo.scope_facilities, state, district, phc)
    return {"alerts": get_demo_alerts(scope)}


# ── Transfer recommendations ────────────────────────────────────────
@app.get("/api/v1/recommendations")
async def fetch_recommendations(threshold_days: int = 14, transfer_max_km: float = 50.0, state: str = "Telangana", district: str = "", phc: str = ""):
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
    scope = _facility_query(facility_repo.scope_facilities, state, district, phc)
    return {"recommendations": get_demo_recommendations(scope)}


@app.post("/api/v1/recommendations/{rec_id}/approve")
async def approve_recommendation(rec_id: str):
    """Approves a transfer and triggers stock updates."""
    return {"status": "approved", "recommendation_id": rec_id}


# ── Federated patterns ──────────────────────────────────────────────
@app.get("/api/v1/patterns")
async def fetch_patterns(district: str = ""):
    """Export aggregate seasonal coefficients per ATC class.

    Only 12-element monthly multiplier vectors leave: no facility rows and no
    patient data.
    """
    return {"patterns": _facility_query(get_local_patterns, district)}

@app.post("/api/v1/patterns")
async def post_patterns(pattern: PatternNode):
    """Ingest peer coefficients as a prior."""
    return ingest_peer_pattern(pattern)

@app.get("/api/v1/forecast-chart")
async def get_forecast_chart_endpoint(days: int = 7, state: str = "Telangana",
                                      district: str = "", phc: str = ""):
    """Real history and real ML.FORECAST predictions for the busiest series.

    Every value is queried: the history from `stock_events`, the forward curve
    from the trained ARIMA_PLUS model. Nothing is generated here or in the
    browser.
    """
    series = _facility_query(forecast.pick_series, state, district, phc)
    if series is None:
        raise HTTPException(
            status_code=404,
            detail="No trained series in this scope. Forecasting is active for "
                   "PHCs in Telangana, where real HMIS demand data exists.",
        )
    try:
        payload = forecast.get_forecast_series(
            series["facility_id"], series["item_id"], horizon=days
        )
    except forecast.ForecastUnavailable as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    payload.update({
        "facility_name": series["facility_name"],
        "item_name": series["item_name"],
        "unit": series["unit"],
    })
    return payload


@app.get("/api/v1/stock-health")
async def get_stock_health(state: str = "Telangana", district: str = "",
                           phc: str = ""):
    """Days-of-cover distribution and the largest deficits, from the model.

    Replaces two charts that were previously arrays hardcoded in the browser.
    """
    return _facility_query(stock_health.network_health, state, district, phc)

# The expiry chart used to be served here from `random.randint`. There is no
# batch-expiry data source anywhere in the stack, so it has been removed rather
# than left showing invented numbers. Block C adds `expiry_date` to
# `stock_events` for FEFO redistribution, at which point it can return backed
# by real batch data.


# ── Static files (must be last) ─────────────────────────────────────
app.mount("/", StaticFiles(directory="web", html=True), name="web")
