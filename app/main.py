"""StockPulse — FastAPI backend."""

import asyncio
import logging
import os
from datetime import datetime, timezone
from contextlib import asynccontextmanager

from dotenv import load_dotenv

from fastapi import FastAPI, HTTPException, UploadFile, Form
from fastapi.staticfiles import StaticFiles

# ---------------------------------------------------------------------------
# Load .env BEFORE importing anything from app.*
# ---------------------------------------------------------------------------
# This call's position is load-bearing, not stylistic. Modules under app/ read
# their configuration at *import* time — `PROJECT = os.getenv("GCP_PROJECT")`
# and friends run when the module is first imported, not when a function is
# called. Moving this below the `from app import ...` block would leave those
# constants already bound to their defaults, and the .env file would silently
# do nothing.
#
# `python-dotenv` was in requirements.txt and `.env.example` existed, but
# nothing ever called this, so a .env file was read by nobody. Fixed here.
#
# On Cloud Run there is no .env file and none is needed: env vars are injected
# into the container directly. load_dotenv() finds no file, changes nothing,
# and returns False. It never overrides a variable that is already set.
load_dotenv()

from app import facilities as facility_repo  # noqa: E402
from app import forecast
from app import stock_health
from app import supply
from app import exchange
from app import items
from app import quality
from app import resources
from app import surge
from app import transfers
from app.bq import QueryTooExpensive
from app import capture_pipeline
from app.capture import handle_capture, handle_chat
from app.forecast import get_forecast_daily_demand
from app.patterns import get_local_patterns, ingest_peer_pattern, PatternNode
from app.demo_data import get_demo_review_queue

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
async def get_stats(state: str = "Telangana", district: str = "",
                    phc: str = ""):
    """Dashboard summary.

    Every figure is now real. Facility counts come from the facility master,
    alerts and transfers from the supply engine, and `captures_today` is
    counted from capture-sourced events in the ledger — legitimately zero
    until someone captures something.
    """
    counts = _facility_query(
        facility_repo.facility_counts, state, district, phc)
    engine = _facility_query(supply.get_summary, state, district, phc)
    captures = _facility_query(quality.captures_today)

    return {
        **engine,
        "facilities": counts["facilities"],
        "phcs": counts["phcs"],
        "demo_facilities": counts["demo_facilities"],
        "districts": counts["districts"],
        "population_served": counts["population_served"],
        "stockout_alerts": engine["open_alerts"],
        "captures_today": captures["captures_today"],
        "captures_last_7_days": captures["captures_last_7_days"],
        "captures_all_time": captures["captures_all_time"],
        "captures_by_mode": captures["by_mode"],
        "captures_today_is_generated": False,
        # Two different waste figures exist and they are not interchangeable.
        # `waste_avoided_units` here is the sum over *pending transfers* of
        # stock the donor could not have used before it expired — legitimately
        # 0, because FEFO at each facility has already consumed everything
        # short-dated. The headline 26,612 at /api/v1/impact is a different
        # quantity: the whole year's ledger replayed under FIFO and differenced
        # against FEFO. Naming the distinction here so the two cannot be read
        # as contradicting each other. See docs/CLAIMS.md section 7.
        "waste_avoided_basis": (
            "pending transfers only; for the year-long FEFO-vs-FIFO "
            "counterfactual see /api/v1/impact"),
        "scope": {
            "state": state or "(all)",
            "district": district or "(all)",
            "facility": phc or "(all)",
            "note": ("counts are scoped to the filter above; state defaults to "
                     "Telangana, so an unfiltered call is not a national total"),
        },
        "last_sync": datetime.now(timezone.utc).isoformat(),
    }


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


@app.post("/api/v1/chat-note")
async def post_chat_note(message: str = Form(...),
                         facility_id: str = Form(...)):
    """Chat capture — for a shared room, a night shift, a noisy clinic.

    Same extraction prompt, same catalogue matcher, same confidence gate and
    same review queue as voice. Only the input differs.
    """
    return handle_chat(message, facility_id)


@app.post("/api/v1/barcode-scan")
async def post_barcode_scan(code: str = Form(...),
                            facility_id: str = Form(...),
                            quantity: int = Form(None),
                            event_type: str = Form("received"),
                            unit: str = Form("unknown")):
    """Barcode capture — the most accurate mode when stock is labelled.

    The scanned code is resolved against the catalogue by the same matcher at
    the same threshold. An unrecognised code goes to the review queue rather
    than being written as an invented item.
    """
    return capture_pipeline.handle_barcode(
        code, facility_id, quantity, event_type, unit)


@app.get("/api/v1/capture-modes")
async def capture_modes():
    """The degradation hierarchy, and the pipeline all three share."""
    return {
        "shared_pipeline": [
            "extract (Gemini for voice and chat; the code itself for barcode)",
            f"match against all {len(_facility_query(items.catalog))} NLEM "
            f"medicines at threshold {items.MATCH_THRESHOLD}",
            f"gate on confidence < {capture_pipeline.CONFIDENCE_THRESHOLD}",
            "route to the ledger or the review queue",
        ],
        "modes": [
            {
                "mode": "barcode",
                "rank": 1,
                "accuracy": "highest",
                "requires": "labelled stock and a working camera",
                "extraction_confidence": capture_pipeline.BARCODE_CONFIDENCE,
                "why": "the code identifies the product outright, so there is "
                       "no speech to mis-hear",
            },
            {
                "mode": "voice",
                "rank": 2,
                "accuracy": "high",
                "requires": "30 seconds and any language",
                "extraction_confidence": "returned by the model per item",
                "why": "works when nothing else does — no labels, no keyboard, "
                       "no connectivity",
            },
            {
                "mode": "chat",
                "rank": 3,
                "accuracy": "high, but slower to enter",
                "requires": "a keyboard",
                "extraction_confidence": "returned by the model per item",
                "why": "when audio is impractical: a shared room, a night "
                       "shift, a noisy clinic",
            },
        ],
    }


# ── Review queue ─────────────────────────────────────────────────────
@app.get("/api/v1/review-queue")
async def get_review_queue(state: str = "Telangana", district: str = "",
                           phc: str = ""):
    """Low-confidence extractions awaiting a human decision.

    Real extractions live in Firestore and always take precedence. When the
    queue is genuinely empty, three worked examples are returned so the screen
    is demonstrable — and they are **labelled as examples in the payload**,
    because an unlabelled example is indistinguishable from a real pending
    review and that is exactly the kind of thing this project does not do.
    """
    from google.cloud import firestore
    try:
        db = firestore.Client(
            project=os.getenv("GOOGLE_CLOUD_PROJECT", "daysupply"))
        docs = list(db.collection("review_queue")
                    .where("status", "==", "pending").stream())
        if docs:
            return {
                "items": [doc.to_dict() for doc in docs],
                "is_example_data": False,
                "basis": "Real low-confidence extractions from Firestore.",
            }
    except Exception:
        pass
    scope = _facility_query(facility_repo.scope_facilities, state, district, phc)
    return {
        "items": [{**item, "is_example": True}
                  for item in get_demo_review_queue(scope)],
        "is_example_data": True,
        "basis": (
            "No real extraction is pending, so three worked examples are shown "
            "to demonstrate the confidence gate. They are illustrative, not "
            "captured. Real extractions replace them as soon as any exist."),
    }


# ── Forecasting ──────────────────────────────────────────────────────
@app.post("/api/v1/review-queue/{event_id}/approve")
async def approve_review_item(event_id: str, quantity: int | None = None):
    """Promote a reviewed extraction into the ledger.

    The other half of the confidence gate. A high-confidence extraction goes
    straight to `resource_events`; one the model was unsure about waits here
    until a human says yes, and then lands in the same table with the same
    columns, so nothing downstream can tell them apart or needs to.

    `quantity` supplies the number the speaker never gave — "aadha dabba",
    "kuch strips". Approval is refused without one, because a stock event with
    no quantity records no stock movement while still counting as a capture.
    """
    result = capture_pipeline.approve_review_item(event_id, quantity)
    if not result.get("approved"):
        raise HTTPException(status_code=400, detail=result)
    return result


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
async def get_alerts(state: str = "", district: str = "", phc: str = "",
                     limit: int = 50):
    """Open stock-out alerts from the reorder engine, VEN-ranked.

    A vital medicine outranks a desirable one at the same days of cover. Every
    figure is computed: on-hand from the ledger, demand from the trained model,
    the reorder point from the facility's own lead time.
    """
    return {
        "alerts": _facility_query(
            supply.get_alerts, state, district, phc, limit),
    }


# ── Transfer recommendations ────────────────────────────────────────
@app.get("/api/v1/recommendations")
async def fetch_recommendations(state: str = "", district: str = "",
                                phc: str = "", limit: int = 50):
    """Transfer recommendations from the redistribution engine.

    Each row names a donor, a receiver, the FEFO batch being moved and its
    expiry, and post-transfer cover for both sides. Substitutions are flagged
    with both the requested and the supplied item.
    """
    return {
        "recommendations": _facility_query(
            supply.get_recommendations, state, district, phc, limit),
    }


# ── Surge and emergency early warning ───────────────────────────────
@app.get("/api/v1/surge/signals")
async def fetch_surge_signals(state: str = "", district: str = "",
                              atc_class: str = "", month: str = "",
                              limit: int = 50):
    """District-months whose demand departed from the pooled seasonal pattern.

    The statistic is the Iglewicz-Hoaglin modified z-score, not a plain
    standardised residual: with twelve monthly observations the classical z is
    bounded at 3.175 and saturates, so it cannot rank outbreaks. Every
    threshold the row was tested against is returned with it.
    """
    return {
        "signals": surge.get_surge_signals(
            state, district, atc_class, month, limit),
    }


@app.get("/api/v1/surge/impact")
async def fetch_surge_impact(state: str = "", district: str = "",
                             atc_class: str = "", limit: int = 100):
    """What a detected surge does to each facility's supply answer.

    `lead_time_decisive` is the row that matters: the facility runs out before
    an indent can physically arrive, so ordering cannot be the answer and only
    a lateral transfer reaches it in time.
    """
    return {
        "impact": surge.get_surge_impact(state, district, atc_class, limit),
    }


@app.get("/api/v1/surge/transfers")
async def fetch_surge_transfers(state: str = "", district: str = "",
                                month: str = "", limit: int = 100):
    """Transfers recommended under surge — Vital first, wider radius.

    Scoped to one surge month, defaulting to the month the live stock sits in.
    The months are alternative episodes, not a combined plan: a donor's spare
    stock is one position, so mixing months would promise the same units twice.
    """
    resolved = month or surge.current_surge_month()
    return {
        "surge_month": resolved,
        "transfers": surge.get_surge_transfers(state, district, resolved,
                                               limit),
    }


@app.get("/api/v1/surge/absorption")
async def fetch_absorption(state: str = "", district: str = "",
                           atc_class: str = "", limit: int = 200):
    """Whether a district's own stock can carry it until resupply lands."""
    return {
        "absorption": surge.get_absorption(state, district, atc_class, limit),
    }


@app.get("/api/v1/surge/scenario/options")
async def fetch_scenario_options():
    """District and ATC-class combinations that have real stock to model."""
    return surge.get_scenario_options()


@app.get("/api/v1/surge/scenario")
async def fetch_scenario(district: str, atc_class: str,
                         multiplier: float = 3.0):
    """Run a spike of any size against current stock, computed live.

    Not a lookup into precomputed rows: the reorder point, the day each
    facility runs out, the transfers and the district verdict are all evaluated
    at the multiplier asked for.
    """
    try:
        return surge.run_scenario(district, atc_class, multiplier)
    except surge.ScenarioError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/v1/reach")
async def fetch_reach():
    """Population reached, counted once, with what is assumed stated."""
    return surge.get_population_reach()


@app.get("/api/v1/substitutes")
async def fetch_substitutes(state: str = "", district: str = "",
                            phc: str = "", limit: int = 50):
    """ATC-equivalent items a facility already holds for something it lacks.

    When the list is empty the reason is returned with it. Substitution is
    working and finding nothing, because only one ATC level-4 class in the
    forecast set contains two forecast items — an empty list with no
    explanation would read as a broken feature instead of a real limit.
    """
    rows = _facility_query(
        supply.get_substitutes, state, district, phc, limit)
    payload = {"substitutes": rows}
    if not rows:
        payload["constraint"] = supply.substitution_constraint()
    return payload


@app.get("/api/v1/reporting")
async def fetch_reporting(state: str = "", district: str = "",
                          phc: str = "", limit: int = 200):
    """Reporting consistency per facility over the last 90 days."""
    return _facility_query(supply.get_reporting, state, district, phc, limit)


@app.get("/api/v1/exchange/evaluation")
async def fetch_exchange_evaluation():
    """The four-arm hold-out behind the pattern-exchange claim."""
    return _facility_query(exchange.evaluation_summary)


@app.get("/api/v1/exchange/demo")
async def fetch_exchange_demo(state: str = "", district: str = "",
                              atc_class: str = ""):
    """Actual, flat and borrowed curves for one thin-history district."""
    result = _facility_query(exchange.thin_history_demo, state, district,
                             atc_class)
    if not result:
        raise HTTPException(
            status_code=404,
            detail="No district in this scope where borrowing helps.")
    return result


@app.get("/api/v1/exchange/vector")
async def fetch_published_vector(state: str, district_key: str,
                                 atc_class: str):
    """Exactly what one district publishes: 12 multipliers, nothing else."""
    return _facility_query(exchange.published_vector, state, district_key,
                           atc_class)


@app.get("/api/v1/export/stock-events")
async def export_stock_events(state: str = "", district: str = "",
                              phc: str = "", days: int = 30,
                              limit: int = 5000):
    """Stock events for ingestion by DVDMS / e-Aushadhi.

    StockPulse is a capture and intelligence layer above the systems a state
    already runs, not a replacement for them. This is how the data gets back.
    """
    return _facility_query(exchange.export_stock_events, state, district, phc,
                           days, limit)


@app.get("/api/v1/resources/coverage")
async def fetch_resource_coverage():
    """What the platform tracks per resource type."""
    return _facility_query(resources.coverage)


@app.get("/api/v1/beds")
async def fetch_beds(state: str = "", district: str = "", phc: str = "",
                     limit: int = 50):
    """Bed capacity, occupancy and pressure.

    Capacity is the IPHS 2022 norm applied to real facilities; occupancy is
    generated from real HMIS admission volumes.
    """
    return {
        "summary": _facility_query(resources.bed_summary, state, district, phc),
        "facilities": _facility_query(
            resources.bed_facilities, state, district, phc, limit),
    }


@app.get("/api/v1/beds/referrals")
async def fetch_bed_referrals(state: str = "", district: str = "",
                              phc: str = "", limit: int = 50):
    """Where to send a patient when a facility has no bed.

    Beds cannot be transferred, so bed pressure produces a referral route
    rather than a movement.
    """
    return {
        "referrals": _facility_query(
            resources.bed_referrals, state, district, phc, limit),
    }


@app.get("/api/v1/personnel")
async def fetch_personnel(state: str = "", district: str = "", phc: str = "",
                          limit: int = 50):
    """Staffing establishment, vacancy and attendance."""
    return {
        "summary": _facility_query(
            resources.staff_summary, state, district, phc),
        "facilities": _facility_query(
            resources.staff_facilities, state, district, phc, limit),
    }


@app.get("/api/v1/personnel/reallocation")
async def fetch_staff_reallocation(state: str = "", district: str = "",
                                   phc: str = "", limit: int = 50):
    """Proposed staff moves, with an explanation when none are possible."""
    return _facility_query(
        resources.staff_reallocation, state, district, phc, limit)


@app.get("/api/v1/data-quality")
async def fetch_data_quality():
    """Defects found in the source data, and what each one is excluded from.

    Surfaced rather than hidden: a figure that silently ignores 633 facilities
    is worse than one that says so.
    """
    return _facility_query(quality.data_quality)


@app.get("/api/v1/captures")
async def fetch_captures():
    """Real capture counts by mode. Zero until someone captures something."""
    return _facility_query(quality.captures_today)


@app.get("/api/v1/impact")
async def fetch_impact():
    """Network impact metrics, including waste avoided by FEFO."""
    return _facility_query(supply.get_impact)


@app.get("/api/v1/lead-time-contrast")
async def fetch_lead_time_contrast(state: str = "", district: str = ""):
    """Two PHCs, same medicine, different distance to their warehouse."""
    return _facility_query(supply.lead_time_contrast, state, district)


@app.post("/api/v1/recommendations/{rec_id}/approve")
async def approve_recommendation(rec_id: str):
    """Approve a transfer. A decision, not yet a movement.

    Until 2026-09-02 this returned `{"status": "approved"}` and wrote nothing,
    while claiming to trigger stock updates. It now records a real approval and
    the transfer becomes dispatchable.
    """
    try:
        return transfers.advance(rec_id, "approved")
    except transfers.TransferError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/v1/recommendations/{rec_id}/dispatch")
async def dispatch_recommendation(rec_id: str):
    """Record that the stock left the donor.

    Writes a `dispatched` ledger event, so the donor's on-hand falls
    immediately. The units are now in transit and belong to neither facility.
    """
    try:
        return transfers.advance(rec_id, "dispatched")
    except transfers.TransferError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/v1/recommendations/{rec_id}/receive")
async def receive_recommendation(rec_id: str):
    """Record arrival at the recipient.

    Writes a `received` ledger event, which becomes a new FEFO batch and raises
    the recipient's on-hand and days of cover.
    """
    try:
        return transfers.advance(rec_id, "received")
    except transfers.TransferError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/v1/transfers/fulfilment")
async def transfer_fulfilment(state: str = "", limit: int = 50):
    """Transfers that have been acted on, and where each one has got to."""
    return {
        "lifecycle": list(transfers.LIFECYCLE),
        "transfers": transfers.pending(state, limit),
    }


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
