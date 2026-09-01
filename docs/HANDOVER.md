# StockPulse — Project Handover

> Supersedes the agent-written handover. Now at `docs/HANDOVER.md`.
> Read alongside `docs/MASTER_PROMPT.md` (governing spec) and
> `BUILD_PROMPT_BLOCKS_A-E.md` (the work queue).
>
> **Naming:** the project was renamed mid-build. **StockPulse** is current.
> "DaySupply" survives in the repo name and the Cloud Run URL. See §9.

---

## 1. Read this first — what is real and what is not

This section matters more than anything else in this document. The product looks
substantially more complete than it is, and anyone continuing without knowing the
difference will overclaim in the submission.

> **Revised 30 August 2026, after Block A.** The previous version of this
> section was wrong on a central point — it said there was no BigQuery in the
> stack and that the facilities had never been loaded. Both claims were false
> when written. Corrected below.

| Component | Status | Notes |
|---|---|---|
| Gemini voice extraction | **REAL** | Live Gemini API calls, audio → structured JSON |
| Offline queue + sync | **REAL** | Service Worker + IndexedDB, genuinely works offline |
| PWA / dashboard UI | **REAL** | Vanilla JS, Chart.js, deployed and functional |
| Barcode scanning | **REAL** | `html5-qrcode` |
| Review queue | **REAL** | Confidence-threshold routing implemented |
| Cloud Run deployment | **REAL** | Live, containerised, `asia-south1` |
| Haversine distance maths | **REAL** | Correct calculation |
| **Facility data** | **REAL** | All 200,438 facilities in BigQuery; dashboard queries them directly |
| **Facility counts / geography** | **REAL** | 37 states, 668 districts, from `daysupply.facilities` |
| **HMIS seasonality reference** | **REAL** | `demand_reference`, 4,092 rows — **Telangana only** |
| **Item catalogue** | **PARTIAL** | 15 items loaded; full NLEM 2022 catalogue is Block B |
| **Demand forecast** | **REAL** | BigQuery ML ARIMA_PLUS, 2,794 series, served via `ML.FORECAST` |
| **Stock-out alerts** | **REAL** | Lead-time reorder points, VEN-weighted. `get_demo_alerts` deleted |
| **Transfer recommendations** | **REAL** | FEFO batch selection, ATC substitution. `get_demo_recommendations` deleted |
| **Reporting consistency** | **REAL** | Measured from `count` events in the ledger |
| **Waste avoided** | **REAL** | 94,542 units, measured against a FIFO replay |
| **Lead times** | **REAL DISTANCE, ASSUMED CONVERSION** | Distance to district HQ is real; days-per-km is a documented proxy |
| **VEN classification** | **DERIVED** | Ours, not MoHFW's — NLEM does not publish VEN |
| **Daily stock events** | **GENERATED** | Anchored to real HMIS demand; see `Data/README.md` §9 |
| **`captures_today`** | **GENERATED** | The only fabricated figure left, flagged in the API response |

### What was actually wrong with the previous version

The `daysupply` dataset existed in `asia-south1` the whole time, with three
populated tables: `facilities`, `items` (15 rows) and `demand_reference`
(4,092 rows). India's 200,438 facilities **had** been loaded. So had Brazil's
50,697 — the table held **251,135 rows**, because `ingestion/load_india.py` used
`WRITE_APPEND` with no preceding delete, and had been run more than once.

The real gap was never ingestion. It was that **nothing in the application
queried any of it** — `app/demo_data.py` held a hardcoded five-state hierarchy
and the dashboard read from that. Block A closed the wiring gap, not a data gap.

Two smaller corrections:

- The facility master has **80 rows with unusable coordinates**, not 15. They
  are loaded regardless and excluded from distance maths.
- The venv was missing `google-generativeai`, `google-cloud-firestore` and
  `thefuzz`, so **the app could not start locally at all**. `requirements.txt`
  was correct; only the environment was stale. Reinstall with
  `.venv/Scripts/python -m pip install -r requirements.txt`.

### Current state after Block A

`daysupply.facilities` holds 200,438 Indian rows (37 states, 668 district names,
701 state×district pairs) plus 50,697 Brazilian rows retained but never queried —
every application query filters `country_code = 'IN'`. `is_demo_facility` is
TRUE for **7,092** rows: PHCs in Telangana, Maharashtra, Rajasthan, Delhi, Assam.
`daysupply.geo_summary` is a ~738-row derived table backing the dropdowns.

**Still true:** there is no trained model. Until Block B lands, "AI forecasting"
must not appear in the deck, the video or the README.

---

## 2. What the product is

**StockPulse** — a voice-first medicine stock reporting and redistribution system
for Primary Health Centres in India.

**The problem.** Public health systems know what they hold in aggregate and
almost nothing about where it is right now. A district warehouse can hold six
months of a drug while a PHC 40 km away turns patients away. Evidence: overall
essential-medicine availability measured at 45.2% in Punjab and 51.1% in Haryana;
41.3% in Delhi; one survey found 13% of PHCs had no essential medicines and
insufficient stock in 75% of those surveyed.

**The root cause is capture, not analytics.** The person expected to record stock
is a pharmacist or ANM running a clinic alone, often without connectivity, for
whom data entry is unpaid overtime. Entries are late, batched at month-end, or
fabricated. Every dashboard above them inherits that.

**The thesis.** Existing systems start at the dashboard and hope data arrives.
StockPulse starts at the person holding the register and works upward.

**Design precedent.** Tamil Nadu's TNMSC — India's best-functioning public health
supply chain — succeeded partly on a "passbook" system, explicitly modelled on
banking, because it borrowed a mental model people already had. The voice
interface is the same move applied to the last mile.

---

## 3. Hackathon context

**Build with AI: Code for Communities, 2nd Edition** (hack2skill + Google Cloud).
Track 3: **Smart Health & Supply Chain Resilience**.

- **Submission closes 30 September 2026** (extended from 24 August; confirmed by
  email from the Google DevRel program manager). Personal target: **20 September**.
- Solo entry. Registered.

**⚠️ Scope changed mid-build:** the BRICS/global framing was removed. The event is
now India-only. The criterion **"Cross-Border Applicability" no longer exists** —
it is now **"Depth & Reach Across India"** at the same ~20% weight.

Consequences:
- Do not build a Brazil config. Brazilian data stays unused on disk.
- Federated exchange becomes **cross-district within India**.
- Remove "Global South" and similar phrasing from all copy.

**Judging weights:** Technical Execution 25%, Deployability & Scalability 20%,
Depth & Reach Across India ~20%, Problem–Solution Fit 20%, Impact 10%,
Presentation 5%.

**Submission package:** source code (GitHub, private with access granted), demo
video 3–5 min, pitch deck 10–12 slides, 2–3 line description, live deployed link.

**Known competitor in the same cohort:** "Sanjeevani Grid" — same core idea
(ASHA worker voice → Gemini extraction → transfer recommendation), India-only,
and its own description says its forecasting is *simulated via Vertex AI*. Our
differentiation must therefore be: real national-scale government data, a really
trained model, offline-first capture, and consultant-grade supply chain logic.

---

## 4. Architecture

```
Health worker (PWA, offline-first)
   │  voice note | barcode scan | chat text
   ▼
Cloud Run — FastAPI (asia-south1)
   ├─► Gemini API           audio/text → structured JSON       [REAL]
   ├─► BigQuery facilities  200,438 rows, all geography        [REAL]
   ├─► BigQuery geo_summary ~738-row dropdown cache            [REAL]
   ├─► BigQuery items       item catalogue                     [15 rows; full NLEM is Block B]
   ├─► BigQuery demand_ref  HMIS 2019-20 seasonality           [REAL, Telangana only]
   ├─► app/demo_data.py     operational counters only          [TO BE REPLACED, Block B]
   └─► BigQuery ML          ARIMA_PLUS                         [NOT BUILT — Block B]
   ▼
Dashboard — Chart.js, cascading state/district/PHC filters
```

**Target architecture after Block B:** the same, with `app/demo_data.py` removed
and BigQuery as the single source of truth for stock events, forecasts and
recommendations as well as facilities.

### Stack

| Layer | Technology |
|---|---|
| Frontend | Vanilla HTML5/CSS3/JS, PWA (`sw.js` + IndexedDB), Chart.js, `html5-qrcode` |
| Backend | Python, FastAPI, containerised |
| AI | Google Gemini (extraction). BigQuery ML ARIMA_PLUS **planned, not built** |
| Hosting | Google Cloud Run, region `asia-south1` |

**Deliberately not used:** Vertex AI AutoML (credit-hungry, no gain over
ARIMA_PLUS here), Dialogflow (Gemini does it in one call), separate
Speech-to-Text + Translation chain (three failure points instead of one).

---

## 5. Repo structure

```
daysupply/
├── app/
│   ├── main.py          FastAPI, all /api/v1/... endpoints
│   ├── capture.py       Gemini audio → structured JSON
│   ├── demo_data.py     ⚠️ seeded generator — TO BE REPLACED by BigQuery
│   └── ...
├── web/
│   ├── index.html       SPA: dashboard, filters, charts
│   ├── app.js           views, Chart.js, MediaRecorder, IndexedDB queue
│   ├── styles.css       "Deep Blue" NHM-style design system
│   └── sw.js            Service Worker, offline cache
├── ingestion/           load_facilities.py, build_geo_summary.py, parse_nlem.py, ...
├── config/              country abstraction (India only in use)
├── docs/
│   ├── MASTER_PROMPT.md governing spec
│   ├── HANDOVER.md      this file
│   ├── PROGRESS.md      one line per session
│   ├── pitch_deck.md    ⚠️ currently OUTSIDE the repo — move it in
│   └── video_script.md  ⚠️ currently OUTSIDE the repo — move it in
├── Data/                raw files gitignored; Data/README.md IS tracked — see §6
├── Dockerfile
└── .gitignore
```

`ingestion/` is named that way deliberately: Windows treats `Data/` and `data/`
as the same folder, so raw data and ingestion code cannot share a name.

---

## 6. Data inventory

Raw files under `Data/` are **gitignored**. `Data/README.md` is tracked and records provenance. `cnes_estabelecimentos.csv`
alone is 229 MB and GitHub rejects files over 100 MB.

### India — `Data/India/` (all currently unused by the application)

| File | Contents | Gotchas |
|---|---|---|
| `geocode_health_centre.csv` | **200,438 facilities**, 37 states, 668 districts. 29,733 PHCs, 5,389 CHCs, 163,131 sub-centres | Only 15 rows lack coordinates. Columns: State Name, District Name, Subdistrict Name, Facility Type, Facility Name, Latitude, Longitude, ActiveFlag_C, Location Type, Type Of Facility |
| `<State>.xls` × 36 + `All_India.xls` | HMIS 2019-20 monthly data, ~120 MB each | **NOT Excel.** SAS-generated HTML with `.xls` extension, `latin-1`. Parse with `pandas.read_html` / BeautifulSoup. Districts × data items × 12 months, split Public/Private and Urban/Rural |
| `rural-population-centre_2017.csv` | Population covered per centre | **State-level, not facility-level.** Applied as a state x facility-type average — see `Data/README.md` §2 |
| `pharmacists-PHCS-CHCS_2017.xls` | Pharmacist counts and vacancies | Deck evidence only |
| `facilities-PHCS_2017.xls` | PHC infrastructure/functioning | Deck evidence only |
| `nlem2022.pdf` / `nlem2022.xlsx` | National List of Essential Medicines 2022 | Use the **.xlsx**. 30 sheets, a PDF table extraction — see `ingestion/parse_nlem.py` for its many conversion artefacts |

**Usable HMIS indicators:** `Outpatient - Diabetes`, `- Hypertension`,
`- Epilepsy`, `- Mental illness`, `- Dental`, `- Ophthalmic Related`,
`- Acute Heart Diseases`, `- Stroke (Paralysis)`; Malaria microscopy and RDT
positives by species; Childhood Diseases; Inpatient counts.

These map to drug categories — hypertension outpatients drive antihypertensive
demand, malaria positives drive antimalarial demand. **This is the real
seasonality signal.**

> **Read §16 of `Data/README.md` before trusting any driver.** The first
> implementation selected indicators by matching words in the HMIS label, and
> that was wrong in three places. The malaria driver summed *blood smears
> examined* with *cases confirmed*, making it 99.8% testing effort; "Childhood
> Diseases" averaged fourteen unrelated conditions; "Inpatient counts" added
> deaths to admissions. Drivers are now selected by **item code** in
> `ingestion/hmis_drivers.py`, each with its clinical rationale.
>
> Three items previously recorded as having no available driver — paracetamol,
> ibuprofen and IFA — turned out to have exact indicators in the same file that
> had simply never been parsed. The full file carries 368 data items, not 11.

⚠️ 2019-20 = April 2019 to March 2020. Feb–Mar 2020 is COVID-affected. Use
April–December or smooth explicitly.

### Brazil — `Data/Brazil/` (**no longer in scope**, retain on disk)

CNES establishments (632,726 rows, semicolon-delimited, `latin-1`), CNES
coordinates, IBGE municipality population 1970–2022, RENAME 2022. Keep for one
scalability slide; do not build against it.

### Sources

- India facilities: Kaggle — All India Health Centres Directory
- India primary health care data: Kaggle — India Primary Health Care Data
- HMIS: `hmis.mohfw.gov.in` → Standard Reports → C2 → All States and Districts
  Across Months → 2019-20
- NLEM 2022: MoHFW
- Brazil: CNES via `dadosabertos.saude.gov.br`; population via Kaggle; RENAME
  2022 via `gov.br/saude` publications

---

## 7. Environment and deployment

| Item | Value |
|---|---|
| GCP project | `daysupply` |
| Region | `asia-south1` (Mumbai) |
| Live URL | `https://daysupply-898541549182.asia-south1.run.app/` |
| Billing | Free trial, ₹28,694 credit, expires 21 Nov 2026, plus $30 Developer Program credits |
| APIs enabled | Cloud Run, BigQuery, Firestore, Generative Language (Gemini), Maps JavaScript |

**Environment variables** (`.env`, gitignored; `.env.example` in repo):
- `GEMINI_API_KEY`
- `GCP_PROJECT`

**Deploy:**
```
gcloud run deploy daysupply --source . --region asia-south1 \
  --min-instances 0 --allow-unauthenticated
```

**Health check — read this before wiring any monitor.**

`/healthz` **does not work in production.** Google's frontend intercepts that
exact path and returns a Google-branded 404 without the request ever reaching
the container. The giveaway is that the 404 response carries no
`server: Google Frontend` header, while real responses do — and `/healthz2`,
`/healthz/` and `/health` all pass through normally.

| Path | Local | Cloud Run |
|---|---|---|
| `/healthz` | works | **intercepted, 404** |
| `/api/v1/healthz` | works | **works — use this** |

Both are served by the same handler in `app/main.py`. Probe
`/api/v1/healthz` in production and in any uptime check.

**Run locally:**
```
uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload
```
Hard-refresh (`Ctrl+Shift+R`) when testing frontend changes — the Service Worker
caches aggressively.

**Cost rules:** never `SELECT *` on the facility table; flag before any query
scanning >10 GB or training >5,000 series; keep `--min-instances 0`.

---

## 8. Work queue

Full detail in `BUILD_PROMPT_BLOCKS_A-E.md`. Summary:

- **Block A — real data.** Load all 200,438 facilities into BigQuery, populate
  `population_served`, rewire dashboard filters and counts to query BigQuery,
  delete `app/demo_data.py`. Assert row counts and fail loudly. *Serves "Depth &
  Reach Across India" (~20%).*
- **Block B — real forecasting.** Generate `stock_events` for demo facilities
  only (partitioned by date, clustered by facility), train a real ARIMA_PLUS
  model, serve via `ML.FORECAST`, purge the word "simulated". *Serves Technical
  Execution (25%).*
- **Block C — supply-chain logic.** Lead-time-aware reorder points
  (`avg_daily_demand × lead_time + safety_stock`), VEN classification weighting
  alerts, FEFO in redistribution, therapeutic substitution via ATC codes,
  reporting-consistency score per facility.
- **Block D — positioning.** Cross-district pattern exchange; an export endpoint
  and architecture diagram showing StockPulse as a capture/intelligence layer
  **above** existing DVDMS/e-Aushadhi systems rather than a replacement.

**If time runs short, protect in this order:** deployed URL, voice capture, a
specific transfer recommendation, review queue. Then real BigQuery data, then
real ARIMA_PLUS, then lead-time-aware thresholds. Everything else is optional.

---

## 9. Open issues

1. **Naming inconsistency.** UI says StockPulse; repo, GCP project and URL say
   daysupply. Either redeploy under a `stockpulse` service name or add a line to
   the README explaining the rename. A judge will notice the mismatch.
2. **Expiry tracker has no data source.** Either drop it or implement FEFO
   (Block C) so it becomes part of the logic rather than decoration.
3. **Scope items not in the original spec** — barcode scanning, expiry tracking,
   five-state filter — were added during the UI sprint. Barcode is justified
   (degradation hierarchy: barcode → voice → chat). Expiry needs Block C to earn
   its place.
4. **Deck and video script live outside the repo.** Move to `docs/`.
5. **"India and the Global South"** copy predates the scope change. Remove.
6. **Lead-time data does not exist publicly.** Block C derives it from distance
   to district HQ. This is a proxy and must be labelled as an assumption in
   `Data/README.md`, never presented as measured.
7. ~~`Data/README.md` does not exist yet.~~ **Done.** It records provenance and
   every real-vs-generated decision, and is now tracked in git.

8. **50,697 Brazilian facility rows are still in `facilities`.** They predate
   the India-only scope change and survived the loader rewrite, because
   `load_facilities.py` deletes and re-appends only `country_code = 'IN'` — by
   design, so a re-run cannot touch anything else. They are **inert**: every
   application query filters on `country_code`, `is_forecast_facility` or
   `facility_type`, and none of them counts rows unfiltered, so no figure
   anywhere is inflated by them. But `SELECT COUNT(*) FROM facilities` returns
   251,135 rather than 200,438, which is a question waiting to be asked in a
   demo. **Decision needed:** delete them (one statement,
   `DELETE FROM facilities WHERE country_code = 'BR'`, and `load_brazil.py`
   stays in the repo as the proof the country abstraction is real), or keep
   them and say plainly that the schema is multi-country while the scope is
   India-only. Not deleted unilaterally — it is data removal and it is the
   owner's call.

