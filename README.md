# StockPulse 📦🎙️

> **Voice-first medicine stock reporting and redistribution for India's primary
> health centres.**

Built for **Build with AI: Code for Communities, 2nd Edition**.

| | |
|---|---|
| **Theme** | **Resilience** — Track 3, Smart Health & Supply Chain Resilience |
| **Live app** | https://daysupply-898541549182.asia-south1.run.app |
| **Google AI** | Gemini Flash on Vertex AI (reads voice, text and register photos; drafts escalation notes) · BigQuery ML ARIMA_PLUS (demand forecasting) · Cloud Text-to-Speech (read-back in five Indian languages) |
| **Google Cloud** | Cloud Run · BigQuery · BigQuery GIS · Firestore (Firebase) |
| **Architecture** | [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) |
| **Data sources** | [`docs/DATA_SOURCES.md`](docs/DATA_SOURCES.md): every dataset, its publisher, and how much is loaded |
| **Prompts** | [`prompts/`](prompts/) — every Gemini instruction and the model chain, as files |
| **Running it** | [Running StockPulse](#running-stockpulse) below |

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

Six ways in, **one pipeline**. The modes differ only in how the rows are
obtained; everything after that is the same code path, in `app/capture_pipeline.py`:

```
extract  →  match against all 385 NLEM medicines  →  read back  →  confidence gate  →  write
            (two-stage, thresholds 85 / 90)         (worker says yes)  (below 0.6)      or review
```

The Report page is built for the person holding the phone at the end of a
shift, not for an analyst: it reads in English, Hindi, Marathi, Telugu or Bengali from one picker, the
default mode needs no typing beyond a number, and **nothing is written until
the worker has heard it read back and said yes** (the offline queue is the one
exception, because nobody is holding the phone when it syncs).

| Rank | Mode | When it wins | Needs | Extraction confidence |
|---|---|---|---|---|
| 0 | **Tap** | The default. What happened → which medicine (39 tiles, Devanagari names where the catalogue has them) → how many, on a keypad | A thumb | 1.0 — nothing to extract |
| 1 | **Barcode** | Most accurate — the code names the product, there is no speech to mis-hear | Labelled stock, working camera | 1.0 |
| 2 | **Voice** | **Works when nothing else does.** No labels, no keyboard, no connectivity | 30 seconds, any language | Per item, from the model |
| 3 | **Chat** | When audio is impractical — shared room, night shift, noisy clinic | A keyboard | Per item, from the model |
| 4 | **Photo** | A whole page of the stock register in one shot, read by Gemini. **Preview only** — every row is shown for the worker to check; a photo can never write unconfirmed | A camera and the register | Per row, from the model |
| 5 | **SMS** | No data connection at all. `POST /api/v1/sms-note` is what a gateway would call; the reply is one plain line per record. **No gateway is connected in this deployment** | Any phone, plus a gateway | Per item, from the model |

The same page takes **staff on duty today** and **beds in use right now**,
as personnel and bed `count` events through the same pipeline. Those are the
only attendance and occupancy counts the system holds as fact: what centres
report. Today's staff and bed views count the centres that reported in the
last 24 hours.

**Gemini also writes, where writing is the work.** Each shortage nothing
routine will fix carries a *Draft note* button: an escalation note for the
district officer, drafted from the row's own figures and then checked against
them. A draft that mentions a number the data does not contain comes back
flagged, with the numbers listed, never silently.

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
| **A trained ARIMA_PLUS model** | 3,818 series, trained in BigQuery ML on the project's own history |
| **Supply-chain logic** | Lead-time reorder points, VEN ranking, FEFO, ATC substitution, reporting consistency — all computed |
| **Generated** | Daily dispensing, receipt and expiry events for 275 PHCs — anchored to the real HMIS series above, and labelled as generated everywhere it appears |

HMIS is loaded for **six states — 212 districts, 53,424 rows across 21 demand
drivers** — and 6,989 of
the 7,092 demo PHCs (98.5%) join to it. Forecasting is active where sufficient
signal exists: every essential medicine is tracked, 39 are forecast, across 275
PHCs spanning 6 states and 191 districts. Uttar Pradesh was added on
2026-09-23 with [`docs/ONBOARD_A_STATE.md`](docs/ONBOARD_A_STATE.md).

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
| flat — own three months, no seasonality | 21.1% |
| nearest demographic match, different state | 46.5% — **25.4pt worse** |
| nearest demographic match, same state | 18.6% — 2.5pt better |
| **pooled — mean vector across all districts** | **15.6% — 5.5pt better** |

**Cross-state demographic matching loses badly** — 46.5% against a 21.1%
flat baseline, more than twice the error of doing nothing. (Across the
original five states it was 71.2% against 19.4%; see `docs/CLAIMS.md` §0.) Seasonality
here is climate-driven and population density does not predict climate: Assam
and Rajasthan can be demographically near-identical and have opposite malaria
seasons. A single donor also carries all of its own reporting noise.

**Restricting the match to the same state fixes most of it** (18.6%, a modest
2.5pt better than flat), which is the confirmation rather than the refutation:
what a same-state donor shares with the receiver is climate, not demography.

**Pooling beats both** at 15.6%, because averaging across every district cancels
individual reporting noise while keeping the shared seasonal shape. Pooling is
what ships. The losing arms are kept because a claim is only worth what it beats.

## Architecture

One FastAPI service on **Cloud Run** serves the web app and its API. It calls
**Gemini on Vertex AI** to read reports and draft notes, keeps the ledger and
the forecasting model in **BigQuery**, speaks read-backs with **Cloud
Text-to-Speech**, and holds reports awaiting review in **Firestore**. The full
diagram and the path of one report are in
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

![StockPulse architecture: every tool and technology, and the path one report takes](docs/architecture-google-cloud.png)

```
Health worker's phone (PWA, offline queue)      Officer's browser
        │ tap · speak · photo · scan · type              │
        ▼                                                ▼
Cloud Run — FastAPI, asia-south1 ─────────────────────────────────────────
   ├─► Vertex AI Gemini   3.8 → 3.7 → 3.6 → 3.5 → 2.5 Flash (prompts/models.json)
   ├─► Cloud Text-to-Speech   read-back in en · hi · mr · te · bn
   ├─► BigQuery              ledger, facility register, HMIS demand, views
   │     └─► BigQuery ML     ARIMA_PLUS, 3,818 demand series
   └─► Firestore (Firebase) review queue, capture audit trail
```

## Running StockPulse

### Prerequisites

- Python 3.11+, and the Google Cloud CLI signed in:
  `gcloud auth application-default login`
- A Google Cloud project with billing and these APIs enabled: Vertex AI,
  BigQuery, Cloud Text-to-Speech, Firestore, Cloud Run.

### Run it locally

```bash
pip install -r requirements.txt
cp .env.example .env          # set GCP_PROJECT
uvicorn app.main:app --reload --port 8080
# open http://localhost:8080
```

Gemini is reached through Vertex AI with your own Google Cloud credentials; no
API key is needed.

### Load the data (first time only, in order)

```bash
python -m ingestion.load_facilities        # 200,438 facilities
python -m ingestion.build_geo_summary      # dropdown cache
python -m ingestion.parse_hmis             # HMIS demand; add states with --state
python -m ingestion.build_items            # full NLEM 2022 catalogue
python -m ingestion.set_forecast_facilities
python -m ingestion.set_lead_times         # distance to district HQ
python -m ingestion.generate_usage         # daily stock ledger + expiry
python -m ingestion.train_forecast         # BigQuery ML ARIMA_PLUS
python -m ingestion.build_supply_plan      # reorder points, transfers
python -m ingestion.build_facility_metrics # reporting consistency
python -m ingestion.build_pattern_exchange # cross-district seasonal shape
```

Adding a state is a runbook of its own: [`docs/ONBOARD_A_STATE.md`](docs/ONBOARD_A_STATE.md).

### Deploy to Cloud Run

```bash
gcloud run deploy daysupply --source . --region asia-south1 \
  --min-instances 1 --allow-unauthenticated
```

The service runs as its Cloud Run service account, which needs the Vertex AI
User, BigQuery User and Cloud Datastore User roles.

### Check it

```bash
pytest                                  # unit and data tests
python -m scripts.smoke_test            # every endpoint the web app calls, on the live service
python -m scripts.eval_prompts          # the extraction prompt against 20 edge cases
```

### Configuration

| Variable | Default | Purpose |
|---|---|---|
| `GCP_PROJECT` | `daysupply` | Google Cloud project |
| `GEMINI_MODEL` / `GEMINI_FALLBACK_MODELS` | from `prompts/models.json` | Override the model chain (`model@location`) |
| `GEMINI_TIMEOUT_MS` | `25000` | Per-call limit before moving to the next model |
| `GEMINI_BACKEND` | `vertex` | `apikey` uses `GEMINI_API_KEY` with AI Studio instead, for local experiments |

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
