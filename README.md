# StockPulse 📦🎙️

> **Voice-first medicine stock reporting and redistribution for India's primary
> health centres.**

Built for **Build with AI: Code for Communities, 2nd Edition** — Track 3, Smart
Health & Supply Chain Resilience.

> **Naming:** the project was renamed mid-build. **StockPulse** is current;
> `daysupply` survives in the repository name, the GCP project and the Cloud Run
> URL.

## The problem

Public health systems know what they hold in aggregate and almost nothing about
where it is right now. A district warehouse can hold six months of a drug while
a PHC 40 km away turns patients away. Essential-medicine availability has been
measured at 45.2% in Punjab, 51.1% in Haryana and 41.3% in Delhi.

The root cause is **capture, not analytics**. The person expected to record
stock is a pharmacist or ANM running a clinic alone, often without
connectivity, for whom data entry is unpaid overtime. Entries are late, batched
at month-end, or fabricated — and every dashboard above them inherits that.

Existing systems start at the dashboard and hope data arrives. StockPulse starts
at the person holding the register and works upward.

## Capture degrades gracefully

Three modes, one extraction and validation pipeline, in order of accuracy:

| Mode | When it wins | Needs |
|---|---|---|
| **Barcode** | Labelled stock, good light | Camera, printed barcode |
| **Voice** | Anything else — the hero path | 30 seconds, any language |
| **Chat** | Noisy room, shared clinic, night shift | A keyboard |

All three produce the same structured record, run through the same confidence
threshold, and land in the same review queue below 0.6 confidence.

## What is real

This matters more than any feature list, and the full accounting is in
[`Data/README.md`](Data/README.md).

| | |
|---|---|
| **200,438 facilities** | Every health facility in India, from the government directory. 37 states, 668 districts. Not a sample |
| **HMIS 2019-20 seasonality** | Real monthly morbidity from MoHFW, driving demand shape |
| **385 medicines** | The complete National List of Essential Medicines 2022 |
| **A trained ARIMA_PLUS model** | 3,725 series, trained in BigQuery ML on the project's own history |
| **Generated** | Daily dispensing and receipt events for 200 PHCs — anchored to the real HMIS series above, and labelled as generated everywhere it appears |

Forecasting is active where sufficient signal exists. Every essential medicine
is tracked; 39 are forecast, across 200 PHCs in Telangana, which is where real
HMIS demand data has been loaded.

## Architecture

```
Health worker (PWA, offline-first)
   │  voice note | barcode scan | chat text
   ▼
Cloud Run — FastAPI (asia-south1)
   ├─► Gemini API        audio/text → structured JSON
   ├─► BigQuery          facilities, items, demand_reference, stock_events
   └─► BigQuery ML       ARIMA_PLUS demand forecast
   ▼
Dashboard — Chart.js, cascading state/district/PHC filters
```

- **Frontend**: Vanilla JS PWA — Service Worker, IndexedDB offline queue,
  MediaRecorder, `html5-qrcode`
- **Backend**: FastAPI, containerised on Google Cloud Run, `asia-south1`
- **AI**: Gemini multimodal audio for extraction; BigQuery ML `ARIMA_PLUS` for
  forecasting

## Setup

```bash
pip install -r requirements.txt

# Ingestion — in order
python -m ingestion.load_facilities        # 200,438 facilities
python -m ingestion.build_geo_summary      # dropdown cache
python -m ingestion.build_items            # full NLEM 2022 catalogue
python -m ingestion.set_forecast_facilities
python -m ingestion.generate_usage         # stock_events
python -m ingestion.train_forecast         # ARIMA_PLUS

# Serve
uvicorn app.main:app --reload
```

Environment: `GEMINI_API_KEY`, `GCP_PROJECT`. See `.env.example`.

**Health check:** `/api/v1/healthz`. Google's frontend intercepts the bare
`/healthz` path in production, so probe the versioned one.

## Cost discipline

- Never `SELECT *` on `facilities` — enforced in `app/bq.py`, not by convention
- Every query is dry-run first and refused above 10 GB
- `stock_events` is partitioned by `DATE(event_ts)` and clustered by
  `facility_id`
- Cloud Run runs at `--min-instances 0`
