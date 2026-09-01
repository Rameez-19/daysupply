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

Three ways in, **one pipeline**. The modes differ only in how the text is
obtained; everything after that is the same code path, in `app/capture_pipeline.py`:

```
extract  →  match against all 385 NLEM medicines  →  confidence gate  →  write
            (two-stage, thresholds 85 / 90)          (below 0.6)         or review
```

| Rank | Mode | When it wins | Needs | Extraction confidence |
|---|---|---|---|---|
| 1 | **Barcode** | Most accurate — the code names the product, there is no speech to mis-hear | Labelled stock, working camera | 1.0 |
| 2 | **Voice** | **Works when nothing else does.** No labels, no keyboard, no connectivity | 30 seconds, any language | Per item, from the model |
| 3 | **Chat** | When audio is impractical — shared room, night shift, noisy clinic | A keyboard | Per item, from the model |

The hierarchy is only meaningful because a worse input mode yields a
*lower-confidence record*, not a differently-shaped one. Below 0.6 confidence,
or where the spoken name does not resolve to a medicine, the record goes to the
review queue instead of the ledger — including an unrecognised barcode. A wrong
`item_id` is the worst output this system can produce, so the bias is always
toward asking a human.

**Matching is two-stage**, because real speech comes in two shapes. A clean
name is compared whole (`token_sort_ratio`, threshold 85). A name buried in a
phrase — *"paracetamol ke do sau tablet"*, *"sugar ki goli metformin"* — is
caught by containment (`token_set_ratio`, threshold 90). Across a corpus of
unrelated clinic speech (*"haan ji boliye"*, *"doctor sahab nahi aaye"*,
*"wo neeli wali dawai"*) the best score is 60, so the gap is wide.

Verify the modes agree: `GET /api/v1/capture-modes`.

## What is real

This matters more than any feature list, and the full accounting is in
[`Data/README.md`](Data/README.md).

| | |
|---|---|
| **200,438 facilities** | Every health facility in India, from the government directory. 37 states, 668 districts. Not a sample |
| **HMIS 2019-20 seasonality** | Real monthly morbidity from MoHFW, driving demand shape |
| **385 medicines** | The complete National List of Essential Medicines 2022 |
| **A trained ARIMA_PLUS model** | 2,794 series, trained in BigQuery ML on the project's own history |
| **Supply-chain logic** | Lead-time reorder points, VEN ranking, FEFO, ATC substitution, reporting consistency — all computed |
| **Generated** | Daily dispensing, receipt and expiry events for 200 PHCs — anchored to the real HMIS series above, and labelled as generated everywhere it appears |

HMIS is loaded for **five states — 137 districts, 34,524 rows across 21 demand
drivers** — and 6,989 of
the 7,092 demo PHCs (98.5%) join to it. Forecasting is active where sufficient
signal exists: every essential medicine is tracked, 39 are forecast, across 200
PHCs spanning 5 states and 116 districts.

`captures_today` counts real capture events and is **legitimately zero** until
someone captures something. It is not a placeholder number.

## Integration posture

Every state already runs DVDMS or e-Aushadhi, under HMIS and ABDM. StockPulse
is a **capture and intelligence layer above those systems, not a replacement**
— see [`docs/architecture.png`](docs/architecture.png). What those systems lack
is data from the last mile, because the person who should enter it is running a
clinic alone.

`GET /api/v1/export/stock-events` emits events in a documented interchange
format (`stockpulse.stock-events.v1`) keyed on the NHM directory's own facility
identifiers, so a state system can match them against its existing facility
master without knowing anything about StockPulse.

## Cross-district pattern exchange

Districts publish a **12-element monthly multiplier per ATC class** and nothing
else — no facility rows, no patient records, no stock levels. A district with
three months of history borrows the network's pooled seasonal vector as a prior.

The improvement is measured, not asserted. Districts with full history are
truncated to three months and the rest predicted four ways
(`GET /api/v1/exchange/evaluation`):

| Arm | Weighted MAPE |
|---|---|
| flat — own three months, no seasonality | 19.4% |
| nearest demographic match, different state | 71.2% — **51.8pt worse** |
| nearest demographic match, same state | 16.4% — 3.0pt better |
| **pooled — mean vector across all districts** | **14.4% — 5.0pt better** |

**Cross-state demographic matching loses catastrophically** — 71.2% against a
19.4% flat baseline, nearly four times the error of doing nothing. Seasonality
here is climate-driven and population density does not predict climate: Assam
and Rajasthan can be demographically near-identical and have opposite malaria
seasons. A single donor also carries all of its own reporting noise.

**Restricting the match to the same state fixes most of it** (16.4%, a modest
3.0pt better than flat), which is the confirmation rather than the refutation:
what a same-state donor shares with the receiver is climate, not demography.

**Pooling beats both** at 14.4%, because averaging across every district cancels
individual reporting noise while keeping the shared seasonal shape. Pooling is
what ships. The losing arms are kept because a claim is only worth what it beats.

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
python -m ingestion.parse_hmis             # HMIS, 5 states
python -m ingestion.build_items            # full NLEM 2022 catalogue
python -m ingestion.set_forecast_facilities
python -m ingestion.set_lead_times         # distance to district HQ
python -m ingestion.generate_usage         # stock_events + expiry
python -m ingestion.build_current_stock    # batch-level stock, FEFO
python -m ingestion.train_forecast         # ARIMA_PLUS
python -m ingestion.build_supply_plan      # reorder points, transfers
python -m ingestion.build_facility_metrics # reporting consistency
python -m ingestion.build_pattern_exchange # cross-district vectors

# Serve
uvicorn app.main:app --reload
```

Environment: `GEMINI_API_KEY`, `GCP_PROJECT`. See `.env.example`.

> **`GEMINI_API_KEY` must be set on the Cloud Run service.** It is not, at the
> time of writing, so voice and chat capture return a 403 from the Generative
> Language API in production while working locally. Barcode capture is
> unaffected — it needs no model. Set it with:
> ```
> gcloud run services update daysupply --region asia-south1 >   --set-env-vars GEMINI_API_KEY=...
> ```

**Health check:** `/api/v1/healthz`. Google's frontend intercepts the bare
`/healthz` path in production, so probe the versioned one.

## Known data-quality exclusions

Loading all 200,438 facilities rather than a convenient subset surfaces real
defects in the source. They are excluded from specific calculations and
**never corrected** — inferring that a Mizoram row reading `92.41, 23.25` was
meant to be `23.25, 92.41` is a guess. `GET /api/v1/data-quality`.

| Defect | Rows | Excluded from |
|---|---|---|
| Coordinates missing | 80 | Distance and transfer matching |
| Latitude outside ±90 | 224 | Distance and transfer matching |
| Longitude outside ±180 | 248 | Distance and transfer matching |
| Inside the globe but outside India (some transposed) | 287 | Distance and transfer matching |
| Over 200 km from own district HQ (95th pct is 97 km) | 4 | Lead time marked `estimated` |
| Population not published (Delhi CHC average is `NA`) | 73 | Demand scaling |
| No ATC code assignable with confidence | 121 | Therapeutic substitution |

Every facility remains loaded and searchable. **633** are excluded from
distance maths, one of them a demo facility.

## Cost discipline

- Never `SELECT *` on `facilities` — enforced in `app/bq.py`, not by convention
- Every query is dry-run first and refused above 10 GB
- `stock_events` is partitioned by `DATE(event_ts)` and clustered by
  `facility_id`
- Cloud Run runs at `--min-instances 0`
